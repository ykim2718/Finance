"""
Rebalancing backtest on real price history.

The simulations in this folder answer what rebalancing is worth under assumed return processes.
This module asks the same questions of an actual price series read from disk, so the modelled
numbers can be checked against what a portfolio would really have earned.

Four questions are answered, each with its own output:
- Rebalanced versus buy-and-hold over the whole sample.
- Net advantage across rebalancing intervals and transaction cost levels.
- Band rebalancing, which trades only when a weight drifts past a threshold, against the calendar.
- Rolling windows, showing how much the advantage depends on when the holding period starts.

Input files are read, never fetched. The provenance of the price data is recorded verbatim from
the CLI into `data_provenance.json` beside the results, so a result can never be separated from
the source it came from.

Changelog:
- 0.0.0 Initial release.
"""

__author__ = 'yRocket'
__version__ = "0.0.0.2026.8.29"

import argparse
import enum
import json
import pathlib
import sys
from dataclasses import dataclass, field

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TABLEAU_COLORS
from tqdm import tqdm

matplotlib.use('Agg')  # headless rendering; batch runs have no display server

__all__ = [
    'Column',
    'RebalanceRule',
    'RebalancePolicy',
    'PriceLoader',
    'Backtester',
    'plot_wealth_curves',
    'plot_cost_sweep',
    'plot_band_comparison',
    'plot_rolling_windows',
]

FIGSIZE: tuple = (9.0, 6.0)
REFERENCE_WIDTH: float = 9.0        # the width BASE_FONT_SIZE was chosen for
BASE_FONT_SIZE: float = 9.0
FIGURE_DPI: int = 300
PALETTE: list = list(TABLEAU_COLORS.values())

TRADING_DAYS_PER_YEAR: int = 252
DEFAULT_DATE_COLUMN: str = 'Date'
DEFAULT_PRICE_COLUMN: str = 'Close'
DEFAULT_REBALANCE_INTERVALS: tuple = (1, 5, 21, 63, 126, 252)
DEFAULT_COST_BPS: tuple = (0.0, 5.0, 10.0, 25.0, 50.0)
DEFAULT_BAND_WIDTHS: tuple = (0.01, 0.02, 0.05, 0.10, 0.20)
DEFAULT_ROLLING_YEARS: int = 10
DEFAULT_ROLLING_STRIDE_DAYS: int = 21
DEFAULT_BAND_CHECK_INTERVAL: int = 1
BASIS_POINT: float = 1e-4
MIN_OVERLAP_DAYS: int = 2
INTERVAL_LABELS: dict = {1: 'daily', 5: 'weekly', 21: 'monthly', 63: 'quarterly',
                         126: 'semiannual', 252: 'annual'}
OUTPUT_STEM: str = 'backtest'
PROVENANCE_FILENAME: str = 'data_provenance.json'


class Column(enum.StrEnum):
    """Column names of every frame this module writes."""

    DATE = enum.auto()
    STRATEGY = enum.auto()
    WEALTH = enum.auto()
    POLICY = enum.auto()
    REBALANCE_INTERVAL = enum.auto()
    BAND_WIDTH = enum.auto()
    COST_BPS = enum.auto()
    CAGR = enum.auto()
    BUY_HOLD_CAGR = enum.auto()
    ADVANTAGE = enum.auto()
    ANNUAL_TURNOVER = enum.auto()
    MAX_DRAWDOWN = enum.auto()
    ANNUAL_VOLATILITY = enum.auto()
    WINDOW_START = enum.auto()
    WINDOW_END = enum.auto()


class RebalanceRule(enum.StrEnum):
    """The three ways a portfolio can be managed here."""

    BUY_AND_HOLD = enum.auto()
    CALENDAR = enum.auto()
    BAND = enum.auto()


@dataclass(frozen=True)
class RebalancePolicy:
    """
    One rebalancing rule.

    The constructor is not called directly. Each rule needs a different parameter, and a plain
    dataclass taking both would let a caller pass an interval to a band policy and never learn that
    it was ignored. The three factories below make that state unrepresentable.
    """

    rule: RebalanceRule
    interval: int = 0
    band_width: float = 0.0

    def __post_init__(self) -> None:
        if self.rule == RebalanceRule.BUY_AND_HOLD and (self.interval != 0 or self.band_width != 0.0):
            raise ValueError("buy-and-hold takes neither an interval nor a band.")
        if self.rule == RebalanceRule.CALENDAR and (self.interval < 1 or self.band_width != 0.0):
            raise ValueError(f"a calendar policy needs interval >= 1 and no band; got {self!r}.")
        if self.rule == RebalanceRule.BAND and (self.band_width <= 0.0 or self.interval < 1):
            raise ValueError(f"a band policy needs band > 0 and a check interval >= 1; got {self!r}.")

    @classmethod
    def buy_and_hold(cls) -> 'RebalancePolicy':
        """Never trade after the first purchase."""
        return cls(rule=RebalanceRule.BUY_AND_HOLD)

    @classmethod
    def calendar(cls, interval: int) -> 'RebalancePolicy':
        """Restore the target weights every `interval` trading days."""
        return cls(rule=RebalanceRule.CALENDAR, interval=interval)

    @classmethod
    def band(cls, width: float, check_interval: int = DEFAULT_BAND_CHECK_INTERVAL) -> 'RebalancePolicy':
        """Restore the target weights whenever a weight has drifted more than `width` away."""
        return cls(rule=RebalanceRule.BAND, band_width=width, interval=check_interval)

    @property
    def label(self) -> str:
        """Short human-readable name used in frames and figures."""
        if self.rule == RebalanceRule.BUY_AND_HOLD:
            return 'buy and hold'
        if self.rule == RebalanceRule.CALENDAR:
            return INTERVAL_LABELS.get(self.interval, f"every {self.interval} days")
        return f"band {self.band_width:.0%}"


@dataclass
class PriceLoader:
    """Read one csv per asset from a folder and align them on their common dates."""

    folder: pathlib.Path
    tickers: tuple
    date_column: str = DEFAULT_DATE_COLUMN
    price_column: str = DEFAULT_PRICE_COLUMN
    date_format: str = None
    file_suffix: str = '.csv'
    loaded_files: dict = field(default_factory=dict)

    def _read_one(self, ticker: str) -> pd.Series:
        """Return the price series of one ticker, indexed by date and sorted."""
        path = self.folder / f"{ticker}{self.file_suffix}"
        if not path.is_file():
            raise FileNotFoundError(
                f"no price file for ticker {ticker!r} at {path}. Expected one csv per ticker named "
                f"<ticker>{self.file_suffix}."
            )
        frame = pd.read_csv(path)
        missing = [name for name in (self.date_column, self.price_column) if name not in frame.columns]
        if missing:
            raise ValueError(
                f"{path} is missing column(s) {missing}. Found {list(frame.columns)}. Set "
                "--date-column and --price-column to the names this file actually uses."
            )
        series = pd.Series(
            pd.to_numeric(frame[self.price_column], errors='coerce').to_numpy(),
            index=pd.to_datetime(frame[self.date_column], format=self.date_format, errors='coerce'),
            name=ticker,
        )
        bad_dates = int(series.index.isna().sum())
        bad_prices = int(series.isna().sum())
        if bad_dates or bad_prices:
            # Report rather than drop silently: a parse failure is a fact about the input file.
            print(f"WARNING: {path.name} has {bad_dates} unparsable dates and {bad_prices} "
                  f"unparsable prices out of {len(series)} rows; those rows are dropped.")
        series = series[series.index.notna()].dropna()
        if (series <= 0.0).any():
            raise ValueError(f"{path} contains non-positive prices, which cannot be turned into returns.")
        series = series.sort_index()
        duplicates = int(series.index.duplicated().sum())
        if duplicates:
            raise ValueError(
                f"{path} has {duplicates} duplicated dates. Deduplicate the file rather than letting "
                "the backtest pick one row arbitrarily."
            )
        self.loaded_files[ticker] = {'path': str(path), 'rows_used': int(series.size),
                                     'first_date': str(series.index[0].date()),
                                     'last_date': str(series.index[-1].date())}
        return series

    def load(self) -> pd.DataFrame:
        """
        Return the aligned price panel.

        Index: DatetimeIndex named `date`, the dates present in every ticker.
        Columns: one per ticker, in the order given.
        """
        if len(self.tickers) < 2:
            raise ValueError(f"a rebalancing backtest needs at least 2 tickers; got {self.tickers!r}.")
        if len(set(self.tickers)) != len(self.tickers):
            raise ValueError(f"tickers must be distinct; got {self.tickers!r}.")
        pbar = tqdm(self.tickers, ncols=100, unit='ticker')
        series = []
        for ticker in pbar:
            pbar.set_description(f"Reading {ticker}")
            series.append(self._read_one(ticker=ticker))
        panel = pd.concat(series, axis=1, join='inner').sort_index()
        panel.index.name = str(Column.DATE)
        if panel.shape[0] < MIN_OVERLAP_DAYS:
            raise ValueError(
                f"the tickers overlap on only {panel.shape[0]} dates. Check that the files cover a "
                "common period and use the same date format."
            )
        return panel


class Backtester:
    """Run rebalancing policies over an aligned price panel."""

    def __init__(self, prices: pd.DataFrame, weights: np.ndarray,
                 trading_days_per_year: int = TRADING_DAYS_PER_YEAR) -> None:
        if prices.shape[1] != weights.size:
            raise ValueError(
                f"got {prices.shape[1]} price columns but {weights.size} weights; they must match."
            )
        if not np.isclose(weights.sum(), 1.0):
            raise ValueError(f"weights must sum to 1; got {weights} summing to {weights.sum()!r}.")
        if np.any(weights <= 0.0):
            raise ValueError(f"every weight must be positive; got {weights}. A zero weight leaves "
                             "nothing to rebalance in that sleeve.")
        if trading_days_per_year < 1:
            raise ValueError(f"trading_days_per_year must be >= 1; got {trading_days_per_year!r}.")
        self.prices = prices
        self.weights = weights
        self.trading_days_per_year = trading_days_per_year
        self.gross = (prices / prices.shift(1)).iloc[1:].to_numpy()
        self.dates = prices.index[1:]

    def _slice(self, start: int, end: int) -> tuple:
        """Return the growth factors and dates of the half-open step range `[start, end)`."""
        if not 0 <= start < end <= self.gross.shape[0]:
            raise ValueError(
                f"invalid step range [{start}, {end}) for {self.gross.shape[0]} steps."
            )
        return self.gross[start:end, :], self.dates[start:end]

    def run(self, policy: RebalancePolicy, cost_rate: float = 0.0,
            start: int = 0, end: int = None) -> dict:
        """
        Run one policy and return its outcome.

        Returns `{'wealth': pd.Series, 'cagr': float, 'annual_turnover': float,
        'max_drawdown': float, 'annual_volatility': float}`. `wealth` starts at 1 on the first
        step of the range. `cost_rate` is charged on every unit of notional traded, on both sides.
        """
        if cost_rate < 0.0:
            raise ValueError(f"cost_rate must be >= 0; got {cost_rate!r}.")
        if policy.rule == RebalanceRule.BUY_AND_HOLD and cost_rate > 0.0:
            raise ValueError(
                "buy-and-hold trades nothing, so a non-zero cost_rate is contradictory; pass "
                "cost_rate=0 or a rebalancing policy."
            )
        end = self.gross.shape[0] if end is None else end
        gross, dates = self._slice(start=start, end=end)

        holdings = self.weights.copy()
        traded_notional = 0.0
        wealth = np.empty(gross.shape[0])
        for step in range(gross.shape[0]):
            holdings = holdings * gross[step, :]
            total = holdings.sum()
            if total <= 0.0:
                raise RuntimeError(f"portfolio reached non-positive value at {dates[step]}.")
            if self._should_rebalance(policy=policy, step=step, holdings=holdings, total=total):
                target = total * self.weights
                volume = float(np.abs(target - holdings).sum())
                traded_notional += volume / total
                total_after = total - cost_rate * volume
                if total_after <= 0.0:
                    raise RuntimeError(
                        f"transaction cost wiped the portfolio out at {dates[step]}; cost_rate="
                        f"{cost_rate!r} is too large for this policy."
                    )
                holdings = total_after * self.weights
                total = total_after
            wealth[step] = total

        years = gross.shape[0] / self.trading_days_per_year
        series = pd.Series(wealth, index=dates, name=policy.label)
        running_max = np.maximum.accumulate(wealth)
        step_returns = np.diff(np.concatenate([[1.0], wealth])) / np.concatenate([[1.0], wealth[:-1]])
        return {
            'wealth': series,
            'cagr': float(wealth[-1] ** (1.0 / years) - 1.0),
            'annual_turnover': float(traded_notional / years),
            'max_drawdown': float((wealth / running_max - 1.0).min()),
            'annual_volatility': float(step_returns.std(ddof=1) * np.sqrt(self.trading_days_per_year)),
        }

    def _should_rebalance(self, policy: RebalancePolicy, step: int, holdings: np.ndarray,
                          total: float) -> bool:
        """Decide whether the policy trades at this step."""
        if policy.rule == RebalanceRule.BUY_AND_HOLD:
            return False
        if (step + 1) % policy.interval != 0:
            return False
        if policy.rule == RebalanceRule.CALENDAR:
            return True
        return bool(np.abs(holdings / total - self.weights).max() > policy.band_width)


def build_wealth_frame(outcomes: dict) -> pd.DataFrame:
    """
    Return the wealth curves in long form, one row per (date, strategy).

    Index: RangeIndex.
    Columns: `date`, `strategy`, `wealth`.
    """
    if not outcomes:
        raise ValueError("outcomes is empty; nothing to write.")
    frames = []
    for label, outcome in outcomes.items():
        series = outcome['wealth']
        frames.append(pd.DataFrame({
            str(Column.DATE): series.index,
            str(Column.STRATEGY): label,
            str(Column.WEALTH): series.to_numpy(),
        }))
    return pd.concat(frames, ignore_index=True)


def run_cost_sweep(backtester: Backtester, policies: tuple, cost_bps_grid: tuple) -> pd.DataFrame:
    """
    Return every policy at every cost level, one row per pair.

    Index: RangeIndex.
    Columns: `policy`, `rebalance_interval`, `band_width`, `cost_bps`, `cagr`, `buy_hold_cagr`,
             `advantage`, `annual_turnover`, `max_drawdown`, `annual_volatility`.
    """
    if len(policies) == 0 or len(cost_bps_grid) == 0:
        raise ValueError("policies and cost_bps_grid must both be non-empty.")
    baseline = backtester.run(policy=RebalancePolicy.buy_and_hold(), cost_rate=0.0)
    rows = []
    pairs = [(policy, cost) for policy in policies for cost in cost_bps_grid]
    pbar = tqdm(pairs, ncols=100, unit='run')
    for policy, cost_bps in pbar:
        pbar.set_description(f"{policy.label} at {cost_bps:g} bps")
        outcome = backtester.run(policy=policy, cost_rate=cost_bps * BASIS_POINT)
        rows.append({
            str(Column.POLICY): policy.label,
            str(Column.REBALANCE_INTERVAL): policy.interval,
            str(Column.BAND_WIDTH): policy.band_width,
            str(Column.COST_BPS): float(cost_bps),
            str(Column.CAGR): outcome['cagr'],
            str(Column.BUY_HOLD_CAGR): baseline['cagr'],
            str(Column.ADVANTAGE): outcome['cagr'] - baseline['cagr'],
            str(Column.ANNUAL_TURNOVER): outcome['annual_turnover'],
            str(Column.MAX_DRAWDOWN): outcome['max_drawdown'],
            str(Column.ANNUAL_VOLATILITY): outcome['annual_volatility'],
        })
    return pd.DataFrame(rows)


def run_rolling_windows(backtester: Backtester, policies: tuple, window_years: int,
                        stride_days: int, cost_bps: float) -> pd.DataFrame:
    """
    Return the advantage of each policy over overlapping windows, one row per (window, policy).

    Index: RangeIndex.
    Columns: `window_start`, `window_end`, `policy`, `cost_bps`, `cagr`, `buy_hold_cagr`,
             `advantage`, `annual_turnover`.
    """
    if window_years < 1 or stride_days < 1:
        raise ValueError(f"window_years and stride_days must be >= 1; got {window_years!r}, {stride_days!r}.")
    window_steps = window_years * backtester.trading_days_per_year
    total_steps = backtester.gross.shape[0]
    if window_steps > total_steps:
        raise ValueError(
            f"a {window_years}-year window needs {window_steps} steps but the sample has "
            f"{total_steps}. Shorten --rolling-years or supply a longer history."
        )
    starts = list(range(0, total_steps - window_steps + 1, stride_days))
    rows = []
    pbar = tqdm(starts, ncols=100, unit='window')
    for start in pbar:
        end = start + window_steps
        pbar.set_description(f"Window from {backtester.dates[start].date()}")
        baseline = backtester.run(policy=RebalancePolicy.buy_and_hold(), cost_rate=0.0,
                                  start=start, end=end)
        for policy in policies:
            outcome = backtester.run(policy=policy, cost_rate=cost_bps * BASIS_POINT,
                                     start=start, end=end)
            rows.append({
                str(Column.WINDOW_START): backtester.dates[start].date(),
                str(Column.WINDOW_END): backtester.dates[end - 1].date(),
                str(Column.POLICY): policy.label,
                str(Column.COST_BPS): float(cost_bps),
                str(Column.CAGR): outcome['cagr'],
                str(Column.BUY_HOLD_CAGR): baseline['cagr'],
                str(Column.ADVANTAGE): outcome['cagr'] - baseline['cagr'],
                str(Column.ANNUAL_TURNOVER): outcome['annual_turnover'],
            })
    return pd.DataFrame(rows)


def plot_wealth_curves(wealth_frame: pd.DataFrame, output_path: pathlib.Path) -> None:
    """Draw the wealth curve of each strategy on a log scale."""
    font_size = BASE_FONT_SIZE * FIGSIZE[0] / REFERENCE_WIDTH
    fig, axis = plt.subplots(figsize=FIGSIZE)
    for index, label in enumerate(dict.fromkeys(wealth_frame[str(Column.STRATEGY)])):
        subset = wealth_frame[wealth_frame[str(Column.STRATEGY)] == label]
        axis.plot(pd.to_datetime(subset[str(Column.DATE)]), subset[str(Column.WEALTH)],
                  color=PALETTE[index % len(PALETTE)], linewidth=1.2, label=label)
    axis.set_yscale('log')
    axis.set_xlabel('Date', fontsize=font_size)
    axis.set_ylabel('Wealth (start = 1)', fontsize=font_size)
    axis.set_title('Portfolio wealth by rebalancing policy, no transaction cost',
                   fontsize=font_size + 2)
    axis.tick_params(labelsize=font_size - 1)
    axis.legend(fontsize=font_size)
    axis.grid(True, which='both', alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI)
    plt.close(fig)


def plot_cost_sweep(sweep_frame: pd.DataFrame, output_path: pathlib.Path) -> None:
    """Draw the net advantage of each calendar interval against transaction cost."""
    font_size = BASE_FONT_SIZE * FIGSIZE[0] / REFERENCE_WIDTH
    calendar = sweep_frame[sweep_frame[str(Column.BAND_WIDTH)] == 0.0]
    intervals = sorted(calendar[str(Column.REBALANCE_INTERVAL)].unique())
    positions = np.arange(len(intervals))
    fig, axis = plt.subplots(figsize=FIGSIZE)
    for index, cost_bps in enumerate(sorted(calendar[str(Column.COST_BPS)].unique())):
        subset = calendar[calendar[str(Column.COST_BPS)] == cost_bps]
        values = subset.set_index(str(Column.REBALANCE_INTERVAL))[str(Column.ADVANTAGE)]
        axis.plot(positions, values.reindex(intervals).to_numpy() * 100.0, marker='o',
                  color=PALETTE[index % len(PALETTE)], label=f"{cost_bps:g} bps per trade")
    axis.axhline(0.0, color='black', linewidth=0.9)
    axis.set_xticks(positions)
    axis.set_xticklabels([f"{INTERVAL_LABELS.get(value, str(value))}\n({value})" for value in intervals])
    axis.set_xlabel('Rebalancing interval (trading days)', fontsize=font_size)
    axis.set_ylabel('CAGR advantage over buy-and-hold (%p)', fontsize=font_size)
    axis.set_title('Net rebalancing advantage on the real sample', fontsize=font_size + 2)
    axis.tick_params(labelsize=font_size - 1)
    axis.legend(fontsize=font_size)
    axis.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI)
    plt.close(fig)


def plot_band_comparison(sweep_frame: pd.DataFrame, output_path: pathlib.Path) -> None:
    """Draw turnover against net advantage, so calendar and band policies can be compared directly."""
    font_size = BASE_FONT_SIZE * FIGSIZE[0] / REFERENCE_WIDTH
    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE)
    families = [('a', 'calendar', sweep_frame[str(Column.BAND_WIDTH)] == 0.0),
                ('b', 'band', sweep_frame[str(Column.BAND_WIDTH)] > 0.0)]
    for panel, (label, name, mask) in enumerate(families):
        axis = axes[panel]
        family = sweep_frame[mask]
        for index, cost_bps in enumerate(sorted(family[str(Column.COST_BPS)].unique())):
            subset = family[family[str(Column.COST_BPS)] == cost_bps].sort_values(str(Column.ANNUAL_TURNOVER))
            axis.plot(subset[str(Column.ANNUAL_TURNOVER)], subset[str(Column.ADVANTAGE)] * 100.0,
                      marker='o', color=PALETTE[index % len(PALETTE)], label=f"{cost_bps:g} bps")
        axis.axhline(0.0, color='black', linewidth=0.9)
        axis.set_title(f"({label}) {name}", fontsize=font_size + 1)
        axis.set_xlabel('Annual turnover', fontsize=font_size)
        axis.tick_params(labelsize=font_size - 1)
        axis.grid(True, alpha=0.25)
    axes[0].set_ylabel('CAGR advantage over buy-and-hold (%p)', fontsize=font_size)
    axes[1].legend(fontsize=font_size)
    fig.suptitle('Advantage against turnover: calendar versus band rebalancing', fontsize=font_size + 2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI)
    plt.close(fig)


def plot_rolling_windows(rolling_frame: pd.DataFrame, window_years: int,
                         output_path: pathlib.Path) -> None:
    """Draw the advantage of each policy over rolling windows, as a time series and a distribution."""
    font_size = BASE_FONT_SIZE * FIGSIZE[0] / REFERENCE_WIDTH
    labels = list(dict.fromkeys(rolling_frame[str(Column.POLICY)]))
    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE,
                             gridspec_kw={'width_ratios': [2.0, 1.0]})
    for index, label in enumerate(labels):
        subset = rolling_frame[rolling_frame[str(Column.POLICY)] == label]
        axes[0].plot(pd.to_datetime(subset[str(Column.WINDOW_START)]),
                     subset[str(Column.ADVANTAGE)] * 100.0,
                     color=PALETTE[index % len(PALETTE)], linewidth=1.2, label=label)
    axes[0].axhline(0.0, color='black', linewidth=0.9)
    axes[0].set_title("(a) advantage by window start", fontsize=font_size + 1)
    axes[0].set_xlabel('Window start date', fontsize=font_size)
    axes[0].set_ylabel(f"{window_years}-year CAGR advantage (%p)", fontsize=font_size)
    axes[0].tick_params(labelsize=font_size - 1)
    axes[0].legend(fontsize=font_size)
    axes[0].grid(True, alpha=0.25)

    samples = [rolling_frame.loc[rolling_frame[str(Column.POLICY)] == label,
                                 str(Column.ADVANTAGE)].to_numpy() * 100.0 for label in labels]
    parts = axes[1].violinplot(samples, positions=np.arange(len(labels)), showmedians=True)
    for index, body in enumerate(parts['bodies']):
        body.set_facecolor(PALETTE[index % len(PALETTE)])
        body.set_alpha(0.55)
    axes[1].axhline(0.0, color='black', linewidth=0.9)
    axes[1].set_xticks(np.arange(len(labels)))
    axes[1].set_xticklabels(labels, rotation=45, ha='right')
    axes[1].set_title('(b) distribution', fontsize=font_size + 1)
    axes[1].tick_params(labelsize=font_size - 1)
    axes[1].grid(True, axis='y', alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI)
    plt.close(fig)


def write_provenance(path: pathlib.Path, loader: PriceLoader, panel: pd.DataFrame,
                     source_name: str, source_url: str, source_origin: str) -> None:
    """Write the citation of the price data next to the results it produced."""
    payload = {
        'source_name': source_name,
        'source_url': source_url,
        'source_origin': source_origin,
        'date_column': loader.date_column,
        'date_format': loader.date_format,
        'price_column': loader.price_column,
        'tickers': list(loader.tickers),
        'files': loader.loaded_files,
        'aligned_rows': int(panel.shape[0]),
        'aligned_first_date': str(panel.index[0].date()),
        'aligned_last_date': str(panel.index[-1].date()),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')
    print(f"\ndata source: {source_name}")
    print(f"  url    : {source_url}")
    print(f"  origin : {source_origin}")
    print(f"  aligned: {payload['aligned_rows']:,} rows, "
          f"{payload['aligned_first_date']} to {payload['aligned_last_date']}")


def report_sweep(sweep_frame: pd.DataFrame, rolling_frame: pd.DataFrame, window_years: int) -> None:
    """Print the headline numbers, all computed from the saved frames."""
    print(f"\nbuy-and-hold CAGR: {sweep_frame[str(Column.BUY_HOLD_CAGR)].iloc[0] * 100.0:+.4f} %")
    print("\nCAGR advantage over buy-and-hold (%p):")
    table = sweep_frame.pivot_table(index=str(Column.POLICY), columns=str(Column.COST_BPS),
                                    values=str(Column.ADVANTAGE), aggfunc='first') * 100.0
    print(table.to_string(float_format=lambda value: f"{value:+.4f}"))
    print("\nannual turnover by policy:")
    turnover = sweep_frame[sweep_frame[str(Column.COST_BPS)] == sweep_frame[str(Column.COST_BPS)].min()]
    print(turnover.set_index(str(Column.POLICY))[str(Column.ANNUAL_TURNOVER)]
          .to_string(float_format=lambda value: f"{value:.4f}"))
    print(f"\n{window_years}-year rolling windows, advantage (%p):")
    summary = rolling_frame.groupby(str(Column.POLICY))[str(Column.ADVANTAGE)].agg(
        windows='size', median='median',
        q25=lambda values: values.quantile(0.25), q75=lambda values: values.quantile(0.75),
        win_rate=lambda values: (values > 0).mean())
    for column in ('median', 'q25', 'q75'):
        summary[column] = summary[column] * 100.0
    print(summary.to_string(float_format=lambda value: f"{value:+.4f}"))


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
                    "Backtest calendar and band rebalancing against buy-and-hold on price files "
                    "read from a folder, one csv per ticker.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-v', '--version', action='version', version=f"{script_name} {__version__}")
    parser.add_argument('--output-folder', type=pathlib.Path, required=True,
                        help=f'root folder for every output; results land in <output-folder>/{OUTPUT_STEM}/')
    parser.add_argument('--price-folder', type=pathlib.Path, required=True,
                        help='folder holding one csv per ticker, named <ticker>.csv')
    parser.add_argument('--tickers', nargs='+', required=True,
                        help='tickers to hold, in weight order; at least two')
    parser.add_argument('--weights', type=float, nargs='+', default=None,
                        help='target weights matching --tickers; defaults to equal weights')
    parser.add_argument('--date-column', default=DEFAULT_DATE_COLUMN,
                        help='name of the date column in the price files')
    parser.add_argument('--price-column', default=DEFAULT_PRICE_COLUMN,
                        help='name of the price column in the price files; use the split and dividend '
                             'adjusted column when the file has one')
    parser.add_argument('--date-format', default=None,
                        help='strptime format of the date column, for example %%d-%%m-%%Y. Give it whenever '
                             'the format is ambiguous, so day-first dates are not read as month-first')
    parser.add_argument('--source-name', required=True,
                        help='name of the dataset the price files came from')
    parser.add_argument('--source-url', required=True,
                        help='url of the dataset the price files came from')
    parser.add_argument('--source-origin', required=True,
                        help='where that dataset itself sourced the prices')
    parser.add_argument('--rebalance-intervals', type=int, nargs='+',
                        default=list(DEFAULT_REBALANCE_INTERVALS),
                        help='calendar rebalancing intervals in trading days')
    parser.add_argument('--band-widths', type=float, nargs='+', default=list(DEFAULT_BAND_WIDTHS),
                        help='band widths as absolute weight deviations, for example 0.05 for 5%%p')
    parser.add_argument('--cost-bps', type=float, nargs='+', default=list(DEFAULT_COST_BPS),
                        help='one-way transaction cost levels in basis points')
    parser.add_argument('--rolling-years', type=int, default=DEFAULT_ROLLING_YEARS,
                        help='length of each rolling window in years')
    parser.add_argument('--rolling-stride-days', type=int, default=DEFAULT_ROLLING_STRIDE_DAYS,
                        help='step between rolling window starts, in trading days')
    parser.add_argument('--rolling-cost-bps', type=float, default=DEFAULT_COST_BPS[1],
                        help='transaction cost used by the rolling-window analysis')
    parser.add_argument('--trading-days-per-year', type=int, default=TRADING_DAYS_PER_YEAR,
                        help='trading days assumed per year when annualising')

    args = parser.parse_args()
    if not args.price_folder.is_dir():
        parser.error(f"--price-folder {args.price_folder} is not a folder.")
    parent = args.output_folder.parent if args.output_folder.parent != pathlib.Path('') else pathlib.Path('.')
    if not parent.is_dir():
        parser.error(f"--output-folder {args.output_folder} cannot be created: {parent} is not a folder.")
    if len(args.tickers) < 2:
        parser.error(f"--tickers needs at least two entries; got {args.tickers}.")
    if args.weights is not None and len(args.weights) != len(args.tickers):
        parser.error(f"--weights has {len(args.weights)} entries but --tickers has {len(args.tickers)}.")
    if args.weights is not None and not np.isclose(sum(args.weights), 1.0):
        parser.error(f"--weights must sum to 1; got {args.weights} summing to {sum(args.weights)}.")
    if any(cost < 0.0 for cost in args.cost_bps) or args.rolling_cost_bps < 0.0:
        parser.error("transaction cost in basis points must be non-negative.")
    if any(width <= 0.0 or width >= 1.0 for width in args.band_widths):
        parser.error(f"--band-widths must lie strictly inside (0, 1); got {args.band_widths}.")
    if any(interval < 1 for interval in args.rebalance_intervals):
        parser.error(f"--rebalance-intervals must be >= 1; got {args.rebalance_intervals}.")
    return args


if __name__ == '__main__':
    cli_args = parse_args()
    result_folder = cli_args.output_folder / OUTPUT_STEM
    result_folder.mkdir(parents=True, exist_ok=True)

    price_loader = PriceLoader(
        folder=cli_args.price_folder,
        tickers=tuple(cli_args.tickers),
        date_column=cli_args.date_column,
        price_column=cli_args.price_column,
        date_format=cli_args.date_format,
    )
    price_panel = price_loader.load()
    target_weights = (np.full(len(cli_args.tickers), 1.0 / len(cli_args.tickers))
                      if cli_args.weights is None else np.asarray(cli_args.weights, dtype=float))

    write_provenance(path=result_folder / PROVENANCE_FILENAME, loader=price_loader,
                     panel=price_panel, source_name=cli_args.source_name,
                     source_url=cli_args.source_url, source_origin=cli_args.source_origin)
    price_panel.to_csv(result_folder / 'aligned_prices.csv', float_format='%.8g')

    engine = Backtester(prices=price_panel, weights=target_weights,
                        trading_days_per_year=cli_args.trading_days_per_year)
    calendar_policies = tuple(RebalancePolicy.calendar(interval=interval)
                              for interval in cli_args.rebalance_intervals)
    band_policies = tuple(RebalancePolicy.band(width=width) for width in cli_args.band_widths)
    all_policies = calendar_policies + band_policies

    curves = {RebalancePolicy.buy_and_hold().label:
              engine.run(policy=RebalancePolicy.buy_and_hold(), cost_rate=0.0)}
    for shown in (RebalancePolicy.calendar(interval=cli_args.rebalance_intervals[0]),
                  RebalancePolicy.calendar(interval=cli_args.rebalance_intervals[-1]),
                  RebalancePolicy.band(width=cli_args.band_widths[len(cli_args.band_widths) // 2])):
        curves[shown.label] = engine.run(policy=shown, cost_rate=0.0)
    wealth_df = build_wealth_frame(outcomes=curves)

    sweep_df = run_cost_sweep(backtester=engine, policies=all_policies,
                              cost_bps_grid=tuple(cli_args.cost_bps))
    rolling_df = run_rolling_windows(
        backtester=engine,
        policies=(RebalancePolicy.calendar(interval=cli_args.rebalance_intervals[len(
            cli_args.rebalance_intervals) // 2]),
            RebalancePolicy.band(width=cli_args.band_widths[len(cli_args.band_widths) // 2])),
        window_years=cli_args.rolling_years,
        stride_days=cli_args.rolling_stride_days,
        cost_bps=cli_args.rolling_cost_bps,
    )

    wealth_df.to_csv(result_folder / 'strategy_wealth.csv', index=False, float_format='%.8g')
    sweep_df.to_csv(result_folder / 'policy_cost_sweep.csv', index=False, float_format='%.8g')
    rolling_df.to_csv(result_folder / 'rolling_windows.csv', index=False, float_format='%.8g')

    plot_wealth_curves(wealth_frame=wealth_df, output_path=result_folder / 'wealth_curves.png')
    plot_cost_sweep(sweep_frame=sweep_df, output_path=result_folder / 'policy_cost_sweep.png')
    plot_band_comparison(sweep_frame=sweep_df, output_path=result_folder / 'band_comparison.png')
    plot_rolling_windows(rolling_frame=rolling_df, window_years=cli_args.rolling_years,
                         output_path=result_folder / 'rolling_windows.png')
    report_sweep(sweep_frame=sweep_df, rolling_frame=rolling_df, window_years=cli_args.rolling_years)
    print(f"\nwrote outputs to {result_folder}")
