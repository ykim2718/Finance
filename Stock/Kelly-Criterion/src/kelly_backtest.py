"""
Kelly criterion tested against a real price history.

The closed-form optimum is derived from a bet whose odds are known exactly. Real prices give
neither the odds nor a second chance, so this module asks two questions of an actual series.

- Does the realised growth curve peak where the estimated Kelly fraction says it should?
- Does an estimate made from past data still work when applied forward?

The second question is the one that matters. A fraction that is optimal in hindsight is not a
strategy; a fraction estimated from data available at the time is.

Changelog:
- 0.0.0 Initial release.
- 0.1.0 Record a wipeout as an outcome instead of raising. A fraction that ruins the portfolio
        is the answer to the question being asked, not a bad argument.
"""

__author__ = 'yRocket'
__version__ = "0.1.0.2026.8.30"

import argparse
import enum
import json
import pathlib
import sys
from dataclasses import dataclass

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TABLEAU_COLORS
from tqdm import tqdm

matplotlib.use('Agg')  # headless rendering; batch runs have no display server

__all__ = [
    'Column',
    'MarketEstimate',
    'KellyBacktester',
    'build_growth_curve',
    'build_walk_forward',
    'plot_growth_curve',
    'plot_walk_forward',
]

FIGSIZE: tuple = (9.0, 6.0)
REFERENCE_WIDTH: float = 9.0        # the width BASE_FONT_SIZE was chosen for
BASE_FONT_SIZE: float = 9.0
FIGURE_DPI: int = 300
PALETTE: list = list(TABLEAU_COLORS.values())

TRADING_DAYS_PER_YEAR: int = 252
DEFAULT_DATE_COLUMN: str = 'Date'
DEFAULT_PRICE_COLUMN: str = 'Adj Close'
DEFAULT_MAX_FRACTION: float = 2.0
DEFAULT_GRID_POINTS: int = 201
DEFAULT_REBALANCE_INTERVAL: int = 21
DEFAULT_ANNUAL_RISK_FREE: float = 0.0
DEFAULT_ESTIMATE_YEARS: int = 5
DEFAULT_APPLY_YEARS: int = 1
HALF: float = 0.5
OUTPUT_STEM: str = 'kelly_backtest'
PROVENANCE_FILENAME: str = 'data_provenance.json'


class Column(enum.StrEnum):
    """Column names of every frame this module writes."""

    FRACTION = enum.auto()
    REALISED_LOG_GROWTH = enum.auto()
    PREDICTED_LOG_GROWTH = enum.auto()
    ANNUAL_RETURN = enum.auto()
    MAX_DRAWDOWN = enum.auto()
    RUINED = enum.auto()
    POLICY = enum.auto()
    WINDOW_START = enum.auto()
    WINDOW_END = enum.auto()
    ESTIMATED_KELLY = enum.auto()
    APPLIED_FRACTION = enum.auto()


@dataclass(frozen=True)
class MarketEstimate:
    """Drift, volatility and the Kelly fraction implied by one stretch of returns."""

    annual_drift: float
    annual_volatility: float
    annual_risk_free: float

    def __post_init__(self) -> None:
        if self.annual_volatility <= 0.0:
            raise ValueError(f"annual_volatility must be positive; got {self.annual_volatility!r}.")

    @property
    def kelly_fraction(self) -> float:
        """
        Return the growth-optimal fraction under the lognormal approximation.

        With a risk-free rate r, drift mu and volatility sigma, the growth rate of a portfolio
        holding fraction f is r + f (mu - r) - f^2 sigma^2 / 2, which is maximised at
        (mu - r) / sigma^2.
        """
        return float((self.annual_drift - self.annual_risk_free) / self.annual_volatility ** 2)

    def predicted_log_growth(self, fraction) -> np.ndarray:
        """Return the growth rate the estimate predicts for the given fraction."""
        fraction = np.asarray(fraction, dtype=float)
        excess = self.annual_drift - self.annual_risk_free
        return (self.annual_risk_free + fraction * excess
                - 0.5 * fraction ** 2 * self.annual_volatility ** 2)


class KellyBacktester:
    """Hold a fixed fraction of a real price series and measure what actually happened."""

    def __init__(self, prices: pd.Series, annual_risk_free: float = DEFAULT_ANNUAL_RISK_FREE,
                 trading_days_per_year: int = TRADING_DAYS_PER_YEAR) -> None:
        if prices.size < 2:
            raise ValueError(f"need at least 2 prices to form a return; got {prices.size}.")
        if (prices <= 0.0).any():
            raise ValueError("prices contain non-positive values, which cannot be turned into returns.")
        if trading_days_per_year < 1:
            raise ValueError(f"trading_days_per_year must be >= 1; got {trading_days_per_year!r}.")
        self.prices = prices
        self.annual_risk_free = annual_risk_free
        self.trading_days_per_year = trading_days_per_year
        self.simple_returns = (prices / prices.shift(1)).iloc[1:].to_numpy() - 1.0
        self.dates = prices.index[1:]
        self.daily_risk_free = annual_risk_free / trading_days_per_year

    def _slice(self, start: int, end: int) -> np.ndarray:
        """Return the simple returns of the half-open step range `[start, end)`."""
        if not 0 <= start < end <= self.simple_returns.size:
            raise ValueError(f"invalid step range [{start}, {end}) for {self.simple_returns.size} steps.")
        return self.simple_returns[start:end]

    def estimate(self, start: int = 0, end: int = None) -> MarketEstimate:
        """
        Return the drift and volatility implied by the returns in the range.

        Volatility comes from the log returns and the drift is the arithmetic one the Kelly
        formula expects, recovered as the log mean plus half the variance.
        """
        end = self.simple_returns.size if end is None else end
        returns = self._slice(start=start, end=end)
        log_returns = np.log1p(returns)
        daily_variance = float(np.var(log_returns, ddof=1))
        daily_drift = float(np.mean(log_returns)) + 0.5 * daily_variance
        return MarketEstimate(
            annual_drift=daily_drift * self.trading_days_per_year,
            annual_volatility=float(np.sqrt(daily_variance * self.trading_days_per_year)),
            annual_risk_free=self.annual_risk_free,
        )

    def run(self, fraction: float, rebalance_interval: int, start: int = 0, end: int = None) -> dict:
        """
        Return `{'log_growth': ..., 'annual_return': ..., 'max_drawdown': ...}` for a fixed fraction.

        The weights are restored every `rebalance_interval` steps, so within one interval the two
        sleeves compound on their own and the interval multiplier is a blend of the two.
        """
        if rebalance_interval < 1:
            raise ValueError(f"rebalance_interval must be >= 1; got {rebalance_interval!r}.")
        end = self.simple_returns.size if end is None else end
        returns = self._slice(start=start, end=end)
        n_blocks = int(np.ceil(returns.size / rebalance_interval))
        multipliers = np.empty(n_blocks)
        for block in range(n_blocks):
            chunk = returns[block * rebalance_interval:(block + 1) * rebalance_interval]
            stock_growth = float(np.prod(1.0 + chunk))
            cash_growth = float((1.0 + self.daily_risk_free) ** chunk.size)
            multipliers[block] = fraction * stock_growth + (1.0 - fraction) * cash_growth
        # A wipeout is a fact about this fraction on this history, so it is reported rather than
        # raised. Growth is undefined once wealth reaches zero, hence the NaN.
        if np.any(multipliers <= 0.0):
            return {'ruined': True, 'log_growth': np.nan, 'annual_return': np.nan,
                    'max_drawdown': -1.0}
        wealth = np.cumprod(multipliers)
        years = returns.size / self.trading_days_per_year
        running_max = np.maximum.accumulate(wealth)
        return {
            'ruined': False,
            'log_growth': float(np.log(wealth[-1]) / years),
            'annual_return': float(wealth[-1] ** (1.0 / years) - 1.0),
            'max_drawdown': float((wealth / running_max - 1.0).min()),
        }


def build_growth_curve(backtester: KellyBacktester, max_fraction: float, grid_points: int,
                       rebalance_interval: int) -> pd.DataFrame:
    """
    Return the realised and predicted growth at each fraction on the grid, one row per fraction.

    Index: RangeIndex.
    Columns: `fraction`, `realised_log_growth`, `predicted_log_growth`, `annual_return`,
             `max_drawdown`, `ruined`.
    """
    if grid_points < 2:
        raise ValueError(f"grid_points must be >= 2; got {grid_points!r}.")
    if max_fraction <= 0.0:
        raise ValueError(f"max_fraction must be positive; got {max_fraction!r}.")
    estimate = backtester.estimate()
    fractions = np.linspace(0.0, max_fraction, grid_points)
    rows = []
    pbar = tqdm(fractions, ncols=100, unit='fraction')
    for fraction in pbar:
        pbar.set_description(f"Holding {fraction:.2f}")
        outcome = backtester.run(fraction=float(fraction), rebalance_interval=rebalance_interval)
        rows.append({
            str(Column.FRACTION): float(fraction),
            str(Column.REALISED_LOG_GROWTH): outcome['log_growth'],
            str(Column.PREDICTED_LOG_GROWTH): float(estimate.predicted_log_growth(fraction)),
            str(Column.ANNUAL_RETURN): outcome['annual_return'],
            str(Column.MAX_DRAWDOWN): outcome['max_drawdown'],
            str(Column.RUINED): outcome['ruined'],
        })
    return pd.DataFrame(rows)


def build_walk_forward(backtester: KellyBacktester, estimate_years: int, apply_years: int,
                       rebalance_interval: int, fixed_fractions: tuple) -> pd.DataFrame:
    """
    Return the out-of-sample outcome of each policy, one row per (window, policy).

    Every window estimates from the preceding `estimate_years` and holds the resulting fraction for
    `apply_years`. The estimate never sees the window it is applied to.

    Index: RangeIndex.
    Columns: `window_start`, `window_end`, `policy`, `estimated_kelly`, `applied_fraction`,
             `realised_log_growth`, `annual_return`, `max_drawdown`, `ruined`.
    """
    if estimate_years < 1 or apply_years < 1:
        raise ValueError(f"estimate_years and apply_years must be >= 1; got {estimate_years!r}, {apply_years!r}.")
    estimate_steps = estimate_years * backtester.trading_days_per_year
    apply_steps = apply_years * backtester.trading_days_per_year
    total = backtester.simple_returns.size
    if estimate_steps + apply_steps > total:
        raise ValueError(
            f"a {estimate_years}-year estimate plus a {apply_years}-year application needs "
            f"{estimate_steps + apply_steps} steps but the sample has {total}."
        )
    starts = list(range(estimate_steps, total - apply_steps + 1, apply_steps))
    rows = []
    pbar = tqdm(starts, ncols=100, unit='window')
    for start in pbar:
        pbar.set_description(f"Window from {backtester.dates[start].date()}")
        estimate = backtester.estimate(start=start - estimate_steps, end=start)
        kelly = estimate.kelly_fraction
        policies = {'full Kelly': kelly, 'half Kelly': HALF * kelly}
        policies.update({f"fixed {value:.2f}": value for value in fixed_fractions})
        for policy, fraction in policies.items():
            outcome = backtester.run(fraction=float(fraction), rebalance_interval=rebalance_interval,
                                     start=start, end=start + apply_steps)
            rows.append({
                str(Column.WINDOW_START): backtester.dates[start].date(),
                str(Column.WINDOW_END): backtester.dates[start + apply_steps - 1].date(),
                str(Column.POLICY): policy,
                str(Column.ESTIMATED_KELLY): kelly,
                str(Column.APPLIED_FRACTION): float(fraction),
                str(Column.REALISED_LOG_GROWTH): outcome['log_growth'],
                str(Column.ANNUAL_RETURN): outcome['annual_return'],
                str(Column.MAX_DRAWDOWN): outcome['max_drawdown'],
                str(Column.RUINED): outcome['ruined'],
            })
    return pd.DataFrame(rows)


def plot_growth_curve(curve_frame: pd.DataFrame, kelly_fraction: float,
                      output_path: pathlib.Path) -> None:
    """Draw the realised growth curve against the one the full-sample estimate predicts."""
    font_size = BASE_FONT_SIZE * FIGSIZE[0] / REFERENCE_WIDTH
    fractions = curve_frame[str(Column.FRACTION)]
    fig, axis = plt.subplots(figsize=FIGSIZE)
    axis.plot(fractions, curve_frame[str(Column.REALISED_LOG_GROWTH)] * 100.0,
              color=PALETTE[0], linewidth=1.8, label='realised')
    axis.plot(fractions, curve_frame[str(Column.PREDICTED_LOG_GROWTH)] * 100.0,
              color=PALETTE[1], linewidth=1.4, linestyle='--', label='predicted by the estimate')
    realised_best = curve_frame.loc[curve_frame[str(Column.REALISED_LOG_GROWTH)].idxmax(),
                                    str(Column.FRACTION)]
    axis.axvline(kelly_fraction, color=PALETTE[3], linestyle='--', linewidth=1.2,
                 label=f"estimated Kelly {kelly_fraction:.3f}")
    axis.axvline(realised_best, color=PALETTE[2], linestyle=':', linewidth=1.2,
                 label=f"realised optimum {realised_best:.3f}")
    axis.axhline(0.0, color='black', linewidth=0.8)
    axis.set_xlabel('Fraction held in the stock', fontsize=font_size)
    axis.set_ylabel('Annual log growth (%)', fontsize=font_size)
    axis.set_title('Realised growth against bet size on the full sample', fontsize=font_size + 2)
    axis.tick_params(labelsize=font_size - 1)
    axis.legend(fontsize=font_size)
    axis.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI)
    plt.close(fig)


def plot_walk_forward(walk_frame: pd.DataFrame, output_path: pathlib.Path) -> None:
    """Draw the estimated Kelly fraction over time and the distribution of out-of-sample growth."""
    font_size = BASE_FONT_SIZE * FIGSIZE[0] / REFERENCE_WIDTH
    policies = list(dict.fromkeys(walk_frame[str(Column.POLICY)]))
    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE, gridspec_kw={'width_ratios': [2.0, 1.0]})

    full = walk_frame[walk_frame[str(Column.POLICY)] == 'full Kelly']
    axes[0].plot(pd.to_datetime(full[str(Column.WINDOW_START)]),
                 full[str(Column.ESTIMATED_KELLY)], marker='o', color=PALETTE[0])
    axes[0].axhline(1.0, color='grey', linewidth=0.9, linestyle=':')
    axes[0].set_title('(a) Kelly fraction estimated from the prior window', fontsize=font_size + 1)
    axes[0].set_xlabel('Window start date', fontsize=font_size)
    axes[0].set_ylabel('Estimated Kelly fraction', fontsize=font_size)
    axes[0].tick_params(labelsize=font_size - 1)
    axes[0].grid(True, alpha=0.25)

    samples = [walk_frame.loc[walk_frame[str(Column.POLICY)] == policy,
                              str(Column.REALISED_LOG_GROWTH)].to_numpy() * 100.0
               for policy in policies]
    parts = axes[1].violinplot(samples, positions=np.arange(len(policies)), showmedians=True)
    for index, body in enumerate(parts['bodies']):
        body.set_facecolor(PALETTE[index % len(PALETTE)])
        body.set_alpha(0.55)
    axes[1].axhline(0.0, color='black', linewidth=0.9)
    axes[1].set_xticks(np.arange(len(policies)))
    axes[1].set_xticklabels(policies, rotation=45, ha='right')
    axes[1].set_ylabel('Out-of-sample annual log growth (%)', fontsize=font_size)
    axes[1].set_title('(b) out-of-sample growth', fontsize=font_size + 1)
    axes[1].tick_params(labelsize=font_size - 1)
    axes[1].grid(True, axis='y', alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI)
    plt.close(fig)


def report(curve_frame: pd.DataFrame, walk_frame: pd.DataFrame, estimate: MarketEstimate) -> None:
    """Print the headline numbers, all computed from the saved frames."""
    print(f"\nfull-sample estimate: drift {estimate.annual_drift:+.4%}, "
          f"volatility {estimate.annual_volatility:.4%}, "
          f"risk-free {estimate.annual_risk_free:+.4%}")
    print(f"estimated Kelly fraction : {estimate.kelly_fraction:.4f}")
    best = curve_frame.loc[curve_frame[str(Column.REALISED_LOG_GROWTH)].idxmax()]
    print(f"realised optimum fraction: {best[str(Column.FRACTION)]:.4f} "
          f"( {best[str(Column.REALISED_LOG_GROWTH)] * 100.0:+.4f}% annual log growth )")

    ruined = curve_frame[curve_frame[str(Column.RUINED)]]
    if len(ruined):
        print(f"RUIN: {len(ruined)} of {len(curve_frame)} fractions on the grid wiped the portfolio "
              f"out; the lowest is {ruined[str(Column.FRACTION)].min():.4f}.")
    else:
        print("no fraction on the grid wiped the portfolio out.")

    ruined_walk = walk_frame[walk_frame[str(Column.RUINED)]]
    if len(ruined_walk):
        print(f"\nRUIN out of sample: {len(ruined_walk)} of {len(walk_frame)} "
              "(window, policy) pairs wiped the portfolio out.")
        print(ruined_walk[[str(Column.WINDOW_START), str(Column.POLICY),
                           str(Column.APPLIED_FRACTION)]].to_string(index=False))
    else:
        print("\nno (window, policy) pair wiped the portfolio out.")

    print("\nout-of-sample annual log growth by policy (%), ruined windows excluded:")
    summary = walk_frame.groupby(str(Column.POLICY))[str(Column.REALISED_LOG_GROWTH)].agg(
        windows='size', median='median',
        q25=lambda values: values.quantile(0.25), q75=lambda values: values.quantile(0.75),
        worst='min', best='max', win_rate=lambda values: (values > 0).mean())
    for column in ('median', 'q25', 'q75', 'worst', 'best'):
        summary[column] = summary[column] * 100.0
    print(summary.to_string(float_format=lambda value: f"{value:+.4f}"))

    print("\nmax drawdown by policy (median across windows):")
    drawdown = walk_frame.groupby(str(Column.POLICY))[str(Column.MAX_DRAWDOWN)].median() * 100.0
    print(drawdown.to_string(float_format=lambda value: f"{value:.4f}"))

    kelly = walk_frame[walk_frame[str(Column.POLICY)] == 'full Kelly'][str(Column.ESTIMATED_KELLY)]
    print(f"\nestimated Kelly fraction across windows: min {kelly.min():.4f}, "
          f"median {kelly.median():.4f}, max {kelly.max():.4f}")


def parse_args() -> argparse.Namespace:
    """Parse and validate the command line options."""
    script_name = pathlib.Path(__file__).name
    if len(sys.argv) == 1:
        print(f"{script_name} {__version__}")
        print(f"\nRun `{script_name} --help` for the full option list.\n")
        sys.exit(0)

    parser = argparse.ArgumentParser(
        prog=script_name,
        description=f"{script_name} {__version__}\n\n"
                    "Test the Kelly criterion on a real price series: the realised growth curve "
                    "over the whole sample, and the out-of-sample result of estimating the "
                    "fraction from past data only.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-v', '--version', action='version', version=f"{script_name} {__version__}")
    parser.add_argument('--output-folder', type=pathlib.Path, required=True,
                        help=f'root folder for every output; results land in <output-folder>/{OUTPUT_STEM}/')
    parser.add_argument('--price-file', type=pathlib.Path, required=True,
                        help='csv holding the price series of one ticker')
    parser.add_argument('--ticker', required=True,
                        help='name of the ticker, used in labels and provenance')
    parser.add_argument('--date-column', default=DEFAULT_DATE_COLUMN,
                        help='name of the date column in the price file')
    parser.add_argument('--price-column', default=DEFAULT_PRICE_COLUMN,
                        help='name of the price column; use the split and dividend adjusted one')
    parser.add_argument('--date-format', default=None,
                        help='strptime format of the date column, given when the format is ambiguous')
    parser.add_argument('--source-name', required=True, help='name of the dataset the file came from')
    parser.add_argument('--source-url', required=True, help='url of the dataset the file came from')
    parser.add_argument('--source-origin', required=True, help='where that dataset sourced the prices')
    parser.add_argument('--annual-risk-free', type=float, default=DEFAULT_ANNUAL_RISK_FREE,
                        help='annual return of the cash sleeve')
    parser.add_argument('--max-fraction', type=float, default=DEFAULT_MAX_FRACTION,
                        help='largest fraction on the growth-curve grid')
    parser.add_argument('--grid-points', type=int, default=DEFAULT_GRID_POINTS,
                        help='number of points on the growth-curve grid')
    parser.add_argument('--rebalance-interval', type=int, default=DEFAULT_REBALANCE_INTERVAL,
                        help='trading days between weight restorations')
    parser.add_argument('--estimate-years', type=int, default=DEFAULT_ESTIMATE_YEARS,
                        help='length of the estimation window in years')
    parser.add_argument('--apply-years', type=int, default=DEFAULT_APPLY_YEARS,
                        help='length of the application window in years')
    parser.add_argument('--fixed-fractions', type=float, nargs='+', default=[0.5, 1.0],
                        help='fixed fractions compared against the estimated ones')
    parser.add_argument('--trading-days-per-year', type=int, default=TRADING_DAYS_PER_YEAR,
                        help='trading days assumed per year when annualising')

    args = parser.parse_args()
    if not args.price_file.is_file():
        parser.error(f"--price-file {args.price_file} is not a file.")
    parent = args.output_folder.parent if args.output_folder.parent != pathlib.Path('') else pathlib.Path('.')
    if not parent.is_dir():
        parser.error(f"--output-folder {args.output_folder} cannot be created: {parent} is not a folder.")
    if any(value < 0.0 for value in args.fixed_fractions):
        parser.error(f"--fixed-fractions must be non-negative; got {args.fixed_fractions}.")
    if any(value > args.max_fraction for value in args.fixed_fractions):
        parser.error(f"--fixed-fractions exceed --max-fraction={args.max_fraction}.")
    return args


if __name__ == '__main__':
    cli_args = parse_args()
    result_folder = cli_args.output_folder / OUTPUT_STEM
    result_folder.mkdir(parents=True, exist_ok=True)

    frame = pd.read_csv(cli_args.price_file)
    missing = [name for name in (cli_args.date_column, cli_args.price_column)
               if name not in frame.columns]
    if missing:
        raise ValueError(
            f"{cli_args.price_file} is missing column(s) {missing}. Found {list(frame.columns)}."
        )
    series = pd.Series(
        pd.to_numeric(frame[cli_args.price_column], errors='coerce').to_numpy(),
        index=pd.to_datetime(frame[cli_args.date_column], format=cli_args.date_format,
                             errors='coerce'),
        name=cli_args.ticker,
    )
    dropped = int(series.index.isna().sum() + series.isna().sum())
    if dropped:
        print(f"WARNING: dropped {dropped} of {series.size} rows that failed to parse.")
    series = series[series.index.notna()].dropna().sort_index()

    engine = KellyBacktester(prices=series, annual_risk_free=cli_args.annual_risk_free,
                             trading_days_per_year=cli_args.trading_days_per_year)
    full_estimate = engine.estimate()

    (result_folder / PROVENANCE_FILENAME).write_text(json.dumps({
        'source_name': cli_args.source_name,
        'source_url': cli_args.source_url,
        'source_origin': cli_args.source_origin,
        'price_file': str(cli_args.price_file),
        'ticker': cli_args.ticker,
        'price_column': cli_args.price_column,
        'rows_used': int(series.size),
        'first_date': str(series.index[0].date()),
        'last_date': str(series.index[-1].date()),
    }, indent=2, ensure_ascii=False) + '\n')

    curve_df = build_growth_curve(backtester=engine, max_fraction=cli_args.max_fraction,
                                  grid_points=cli_args.grid_points,
                                  rebalance_interval=cli_args.rebalance_interval)
    walk_df = build_walk_forward(backtester=engine, estimate_years=cli_args.estimate_years,
                                 apply_years=cli_args.apply_years,
                                 rebalance_interval=cli_args.rebalance_interval,
                                 fixed_fractions=tuple(cli_args.fixed_fractions))
    curve_df.to_csv(result_folder / 'growth_by_fraction.csv', index=False, float_format='%.8g')
    walk_df.to_csv(result_folder / 'walk_forward.csv', index=False, float_format='%.8g')

    plot_growth_curve(curve_frame=curve_df, kelly_fraction=full_estimate.kelly_fraction,
                      output_path=result_folder / 'growth_by_fraction.png')
    plot_walk_forward(walk_frame=walk_df, output_path=result_folder / 'walk_forward.png')
    report(curve_frame=curve_df, walk_frame=walk_df, estimate=full_estimate)
    print(f"\nticker {cli_args.ticker}, {series.size:,} rows, "
          f"{series.index[0].date()} to {series.index[-1].date()}")
    print(f"wrote outputs to {result_folder}")
