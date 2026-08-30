"""
Kelly criterion applied to Shannon's coin-flip game.

A two-outcome bet is repeated for many periods with a fixed fraction of wealth staked and the
weights restored every period. This module traces the resulting growth rate as a function of that
fraction, locates the optimum in closed form and numerically, and checks both against a Monte Carlo
simulation of the same game.

Changelog:
- 0.0.0 Initial release.
- 0.1.0 Simulate the game here instead of importing it, so the module stands on its own.
- 0.2.0 Add the bet-size zone chart and the formula card used by section 4 of the document.
"""

__author__ = 'yRocket'
__version__ = "0.2.1.2026.8.30"

import argparse
import enum
import pathlib
import sys
from dataclasses import dataclass

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TABLEAU_COLORS
from scipy.optimize import minimize_scalar
from tqdm import tqdm

matplotlib.use('Agg')  # headless rendering; batch runs have no display server

__all__ = [
    'Column',
    'BetSpec',
    'KellyAnalyzer',
    'simulate_terminal_wealth',
    'build_curve_frame',
    'build_simulation_frame',
    'plot_growth_zones',
    'plot_formula_card',
    'plot_growth_curve',
    'plot_growth_violin',
]

FIGSIZE: tuple = (9.0, 6.0)
REFERENCE_WIDTH: float = 9.0        # the width BASE_FONT_SIZE was chosen for
BASE_FONT_SIZE: float = 9.0
FIGURE_DPI: int = 300
PALETTE: list = list(TABLEAU_COLORS.values())

DEFAULT_UP_FACTOR: float = 2.0
DEFAULT_DOWN_FACTOR: float = 0.5
DEFAULT_CASH_FACTOR: float = 1.0
DEFAULT_UP_PROB: float = 0.5
DEFAULT_GRID_POINTS: int = 401
DEFAULT_MAX_FRACTION: float = 1.0
DEFAULT_SIM_FRACTIONS: tuple = (0.10, 0.25, 0.50, 0.75, 1.00)
DEFAULT_N_PERIODS: int = 100
DEFAULT_N_PATHS: int = 20000
DEFAULT_CHUNK_SIZE: int = 4000
DEFAULT_SEED: int = 20260829
OPTIMUM_AGREEMENT_TOLERANCE: float = 1e-6
ZONE_FIGSIZE: tuple = (9.0, 6.0)        # 3:2, rendered at 600 x 400
CARD_FIGSIZE: tuple = (9.0, 9.0)        # 1:1, rendered at 600 x 600
ZONE_EDGES: tuple = (0.0, 0.5, 1.0, 2.0)   # in multiples of the optimum
ZONE_LABELS: tuple = ('Conservative', 'Aggressive', 'Over-aggressive', 'Insane')
ZONE_COLOURS: tuple = ('tab:olive', 'tab:orange', 'tab:red', 'dimgrey')
ZONE_TAIL: float = 2.4                  # right edge of the plot, in multiples of the optimum
ZONE_FLOOR: float = -1.4                # bottom of the y axis, in multiples of the peak growth
OUTPUT_STEM: str = 'kelly'


class Column(enum.StrEnum):
    """Column names of every frame this module writes."""

    FRACTION = enum.auto()
    LOG_GROWTH = enum.auto()
    RETURN_PER_PERIOD = enum.auto()
    PATH = enum.auto()
    LOG_GROWTH_PER_PERIOD = enum.auto()


@dataclass(frozen=True)
class BetSpec:
    """The two-outcome bet whose optimal sizing is being solved."""

    up_factor: float = DEFAULT_UP_FACTOR
    down_factor: float = DEFAULT_DOWN_FACTOR
    cash_factor: float = DEFAULT_CASH_FACTOR
    up_prob: float = DEFAULT_UP_PROB

    def __post_init__(self) -> None:
        if not 0.0 < self.up_prob < 1.0:
            raise ValueError(f"up_prob must lie strictly inside (0, 1); got {self.up_prob!r}.")
        if not self.down_factor < self.cash_factor < self.up_factor:
            raise ValueError(
                f"the bet needs an up side and a down side around cash; got down={self.down_factor!r}, "
                f"cash={self.cash_factor!r}, up={self.up_factor!r}."
            )

    @property
    def ruin_fraction(self) -> float:
        """Smallest fraction at which a down move wipes the portfolio out."""
        return float(self.cash_factor / (self.cash_factor - self.down_factor))


class KellyAnalyzer:
    """Growth rate of the bet as a function of the fraction staked."""

    def __init__(self, spec: BetSpec) -> None:
        self.spec = spec

    def log_growth(self, fraction) -> np.ndarray:
        """Expected log growth per period at the given fraction; NaN where the portfolio can be wiped out."""
        spec = self.spec
        fraction = np.asarray(fraction, dtype=float)
        up_wealth = fraction * spec.up_factor + (1.0 - fraction) * spec.cash_factor
        down_wealth = fraction * spec.down_factor + (1.0 - fraction) * spec.cash_factor
        feasible = (up_wealth > 0.0) & (down_wealth > 0.0)
        # Guard the logarithms with a dummy 1.0 on the infeasible side, then mask those entries out.
        safe_growth = (spec.up_prob * np.log(np.where(feasible, up_wealth, 1.0))
                       + (1.0 - spec.up_prob) * np.log(np.where(feasible, down_wealth, 1.0)))
        return np.where(feasible, safe_growth, np.nan)

    def closed_form_optimum(self) -> float:
        """Return the fraction maximising expected log growth, solved analytically."""
        spec = self.spec
        up_edge = spec.up_factor - spec.cash_factor
        down_edge = spec.down_factor - spec.cash_factor
        weighted_edge = spec.up_prob * up_edge + (1.0 - spec.up_prob) * down_edge
        return float(-spec.cash_factor * weighted_edge / (up_edge * down_edge))

    def numeric_optimum(self, max_fraction: float) -> float:
        """Return the fraction maximising expected log growth, solved numerically on (0, max_fraction]."""
        if max_fraction <= 0.0:
            raise ValueError(f"max_fraction must be positive; got {max_fraction!r}.")
        upper = min(max_fraction, self.spec.ruin_fraction * (1.0 - OPTIMUM_AGREEMENT_TOLERANCE))
        result = minimize_scalar(lambda f: -float(self.log_growth(f)), bounds=(0.0, upper), method='bounded')
        if not result.success:
            raise RuntimeError(f"numeric optimisation failed on (0, {upper}]: {result.message}")
        return float(result.x)


def build_curve_frame(analyzer: KellyAnalyzer, max_fraction: float, grid_points: int) -> pd.DataFrame:
    """
    Return the analytic growth curve, one row per fraction on the grid.

    Index: RangeIndex.
    Columns: `fraction`, `log_growth`, `return_per_period`.
    """
    if grid_points < 2:
        raise ValueError(f"grid_points must be >= 2; got {grid_points!r}.")
    if max_fraction >= analyzer.spec.ruin_fraction:
        raise ValueError(
            f"max_fraction {max_fraction!r} reaches the ruin fraction "
            f"{analyzer.spec.ruin_fraction!r}; a down move would wipe the portfolio out."
        )
    fractions = np.linspace(0.0, max_fraction, grid_points)
    growth = analyzer.log_growth(fractions)
    return pd.DataFrame({
        str(Column.FRACTION): fractions,
        str(Column.LOG_GROWTH): growth,
        str(Column.RETURN_PER_PERIOD): np.expm1(growth),
    })


def simulate_terminal_wealth(spec: BetSpec, fraction: float, n_periods: int, n_paths: int,
                             chunk_size: int, seed: int) -> np.ndarray:
    """
    Return terminal wealth of the rebalanced portfolio, one entry per path, starting from 1.

    The weights are restored every period, so one period multiplies wealth by a fixed blend of the
    two outcomes rather than by the bet alone. Paths are drawn in chunks to bound peak memory.
    """
    if not 0.0 <= fraction <= 1.0:
        raise ValueError(f"fraction must lie in [0, 1]; got {fraction!r}.")
    floor = fraction * spec.down_factor + (1.0 - fraction) * spec.cash_factor
    if floor <= 0.0:
        raise ValueError(
            f"fraction {fraction!r} wipes the portfolio out on a down move; it reaches the ruin "
            f"fraction {spec.ruin_fraction!r}."
        )
    rng = np.random.default_rng(seed)
    chunks = []
    remaining = n_paths
    while remaining > 0:
        size = min(chunk_size, remaining)
        is_up = rng.random((size, n_periods)) < spec.up_prob
        bet = np.where(is_up, spec.up_factor, spec.down_factor)
        blended = fraction * bet + (1.0 - fraction) * spec.cash_factor
        chunks.append(np.prod(blended, axis=1))
        remaining -= size
    return np.concatenate(chunks)


def build_simulation_frame(spec: BetSpec, fractions: tuple, n_periods: int, n_paths: int,
                           chunk_size: int, seed: int) -> pd.DataFrame:
    """
    Return simulated per-period log growth, one row per (fraction, path).

    Index: RangeIndex.
    Columns: `fraction`, `path`, `log_growth_per_period`.
    """
    if len(fractions) == 0:
        raise ValueError("fractions is empty; nothing to simulate.")
    if n_periods < 1 or n_paths < 1 or chunk_size < 1:
        raise ValueError(
            f"n_periods, n_paths and chunk_size must be >= 1; got {n_periods!r}, {n_paths!r}, "
            f"{chunk_size!r}."
        )
    frames = []
    pbar = tqdm(fractions, ncols=100, unit='fraction')
    for offset, fraction in enumerate(pbar):
        pbar.set_description(f"Simulating fraction {fraction:.2f}")
        wealth = simulate_terminal_wealth(spec=spec, fraction=float(fraction), n_periods=n_periods,
                                          n_paths=n_paths, chunk_size=chunk_size, seed=seed + offset)
        frames.append(pd.DataFrame({
            str(Column.FRACTION): float(fraction),
            str(Column.PATH): np.arange(wealth.size),
            str(Column.LOG_GROWTH_PER_PERIOD): np.log(wealth) / n_periods,
        }))
    return pd.concat(frames, ignore_index=True)


def plot_growth_zones(analyzer: KellyAnalyzer, optimum: float, output_path: pathlib.Path) -> None:
    """
    Draw the growth curve split into bet-size zones at half, one and two times the optimum.

    The zones are cut at multiples of the optimum rather than at fixed fractions, so the picture
    holds for any bet the analyzer describes.
    """
    if optimum <= 0.0:
        raise ValueError(f"optimum must be positive to scale the zones; got {optimum!r}.")
    font_size = BASE_FONT_SIZE * ZONE_FIGSIZE[0] / REFERENCE_WIDTH
    limit = min(ZONE_TAIL * optimum, analyzer.spec.ruin_fraction * (1.0 - OPTIMUM_AGREEMENT_TOLERANCE))
    fractions = np.linspace(0.0, limit, 400)
    growth = analyzer.log_growth(fractions)

    fig, axis = plt.subplots(figsize=ZONE_FIGSIZE)
    edges = [edge * optimum for edge in ZONE_EDGES] + [limit]
    for index, (left, right) in enumerate(zip(edges[:-1], edges[1:])):
        inside = (fractions >= left) & (fractions <= right)
        axis.fill_between(fractions[inside], 0.0, growth[inside],
                          color=ZONE_COLOURS[index], alpha=0.55, linewidth=0.0)
        axis.text(0.5 * (left + right), 0.5 * np.nanmax(growth) * 0.42, ZONE_LABELS[index],
                  ha='center', va='center', fontsize=font_size, fontweight='bold')
    axis.plot(fractions, growth, color='black', linewidth=2.0)
    axis.axhline(0.0, color='black', linewidth=1.0)

    # Mark the three boundaries on the curve itself, so the reader can read a value off each.
    # The last mark sits on the zero line, so its label goes below to clear the zone labels.
    for multiple, label, above in ((0.5, 'half Kelly', True), (1.0, 'Kelly', True),
                                   (2.0, 'twice Kelly', False)):
        position = multiple * optimum
        if position > limit:
            continue
        height = float(analyzer.log_growth(position))
        axis.plot([position], [height], marker='o', markersize=7, color='black', zorder=3)
        axis.annotate(f"{label}\nf = {position:.3f}, g = {height:+.4f}",
                      xy=(position, height), xytext=(0.0, 16.0 if above else -18.0),
                      textcoords='offset points', ha='center',
                      va='bottom' if above else 'top', fontsize=font_size - 1)
    axis.set_xticks(edges[:-1])
    axis.set_xticklabels(['0', 'half Kelly', 'Kelly', 'twice Kelly'])
    axis.set_xlim(0.0, limit)
    peak = float(np.nanmax(growth))
    axis.set_ylim(ZONE_FLOOR * peak, 1.25 * peak)
    axis.set_xlabel('Fraction staked', fontsize=font_size + 1)
    axis.set_ylabel('Log growth per period', fontsize=font_size + 1)
    axis.tick_params(labelsize=font_size)
    for spine in ('top', 'right'):
        axis.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI, facecolor='white')
    plt.close(fig)


def plot_formula_card(spec: BetSpec, optimum: float, output_path: pathlib.Path) -> None:
    """Draw the closed-form optimum and the meaning of each symbol on a plain white square."""
    font_size = BASE_FONT_SIZE * CARD_FIGSIZE[0] / REFERENCE_WIDTH
    fig, axis = plt.subplots(figsize=CARD_FIGSIZE)
    axis.set_axis_off()
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.0, 1.0)

    axis.text(0.5, 0.93, 'Kelly criterion', ha='center', va='center',
              fontsize=font_size + 8, fontweight='bold')
    axis.text(0.5, 0.76, r'$f^{*} = -\dfrac{c\,[\,p\,A + (1-p)\,B\,]}{A\,B}$',
              ha='center', va='center', fontsize=font_size + 12)
    axis.text(0.5, 0.62, r'$A = u - c, \qquad B = d - c$',
              ha='center', va='center', fontsize=font_size + 4)

    symbols = [
        (r'$f^{*}$', 'fraction of wealth to stake'),
        (r'$u$', 'multiplier when the bet wins'),
        (r'$d$', 'multiplier when the bet loses'),
        (r'$c$', 'multiplier of the cash held'),
        (r'$p$', 'probability that the bet wins'),
    ]
    for index, (symbol, meaning) in enumerate(symbols):
        height = 0.46 - index * 0.075
        axis.text(0.30, height, symbol, ha='right', va='center', fontsize=font_size + 4)
        axis.text(0.35, height, meaning, ha='left', va='center', fontsize=font_size + 2)

    axis.text(0.5, 0.05,
              f"this document: u={spec.up_factor:g}, d={spec.down_factor:g}, "
              f"c={spec.cash_factor:g}, p={spec.up_prob:g}  " + r'$\Rightarrow$' +
              f"  f* = {optimum:.3f}",
              ha='center', va='center', fontsize=font_size + 1)
    fig.savefig(output_path, dpi=FIGURE_DPI, facecolor='white')
    plt.close(fig)


def plot_growth_curve(curve_frame: pd.DataFrame, simulation_frame: pd.DataFrame,
                      optimum: float, output_path: pathlib.Path) -> None:
    """Draw the analytic growth curve with the optimum marked and the simulated medians overlaid."""
    font_size = BASE_FONT_SIZE * FIGSIZE[0] / REFERENCE_WIDTH
    medians = simulation_frame.groupby(str(Column.FRACTION))[str(Column.LOG_GROWTH_PER_PERIOD)].median()
    fig, axis = plt.subplots(figsize=FIGSIZE)
    axis.plot(curve_frame[str(Column.FRACTION)], curve_frame[str(Column.LOG_GROWTH)],
              color=PALETTE[0], linewidth=1.8, label='analytic expected log growth')
    axis.plot(medians.index, medians.to_numpy(), linestyle='none', marker='o',
              color=PALETTE[1], label='simulated median')
    axis.axvline(optimum, color=PALETTE[3], linestyle='--', linewidth=1.2,
                 label=f"Kelly optimum f* = {optimum:.3f}")
    axis.axhline(0.0, color='black', linewidth=0.8)
    axis.set_xlabel('Fraction staked in the stock', fontsize=font_size)
    axis.set_ylabel('Log growth per period', fontsize=font_size)
    axis.set_title('Expected log growth against bet size', fontsize=font_size + 2)
    axis.tick_params(labelsize=font_size - 1)
    axis.legend(fontsize=font_size)
    axis.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI)
    plt.close(fig)


def plot_growth_violin(simulation_frame: pd.DataFrame, output_path: pathlib.Path) -> None:
    """Draw the simulated distribution of per-period log growth at each fraction."""
    font_size = BASE_FONT_SIZE * FIGSIZE[0] / REFERENCE_WIDTH
    fractions = sorted(simulation_frame[str(Column.FRACTION)].unique())
    samples = [simulation_frame.loc[simulation_frame[str(Column.FRACTION)] == fraction,
                                    str(Column.LOG_GROWTH_PER_PERIOD)].to_numpy()
               for fraction in fractions]
    fig, axis = plt.subplots(figsize=FIGSIZE)
    parts = axis.violinplot(samples, positions=np.arange(len(fractions)), showmedians=True)
    for index, body in enumerate(parts['bodies']):
        body.set_facecolor(PALETTE[index % len(PALETTE)])
        body.set_alpha(0.55)
    axis.axhline(0.0, color='black', linewidth=0.8)
    axis.set_xticks(np.arange(len(fractions)))
    axis.set_xticklabels([f"{fraction:.0%}" for fraction in fractions])
    axis.set_xlabel('Fraction staked in the stock', fontsize=font_size)
    axis.set_ylabel('Log growth per period', fontsize=font_size)
    axis.set_title('Simulated growth distribution by bet size', fontsize=font_size + 2)
    axis.tick_params(labelsize=font_size - 1)
    axis.grid(True, axis='y', alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI)
    plt.close(fig)


def report_optima(analyzer: KellyAnalyzer, max_fraction: float) -> float:
    """Print and cross-check the closed-form and numeric optima, returning the closed-form value."""
    closed_form = analyzer.closed_form_optimum()
    numeric = analyzer.numeric_optimum(max_fraction=max_fraction)
    gap = abs(closed_form - numeric)
    print(f"closed-form optimum f* = {closed_form:.6f}")
    print(f"numeric optimum    f* = {numeric:.6f}   (gap {gap:.2e})")
    if gap > 1e-4:
        raise RuntimeError(
            f"closed-form and numeric optima disagree by {gap:.2e}; the growth function or the "
            "solver bounds are wrong."
        )
    print(f"growth at f*          = {float(analyzer.log_growth(closed_form)):+.6f} log per period")
    return closed_form


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
                    "Locate the growth-optimal bet size of Shannon's coin-flip game and check it "
                    "against a Monte Carlo simulation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-v', '--version', action='version', version=f"{script_name} {__version__}")
    parser.add_argument('--output-folder', type=pathlib.Path, required=True,
                        help=f'root folder for every output; results land in <output-folder>/{OUTPUT_STEM}/')
    parser.add_argument('--up-factor', type=float, default=DEFAULT_UP_FACTOR,
                        help='stock growth factor on an up move')
    parser.add_argument('--down-factor', type=float, default=DEFAULT_DOWN_FACTOR,
                        help='stock growth factor on a down move')
    parser.add_argument('--cash-factor', type=float, default=DEFAULT_CASH_FACTOR,
                        help='growth factor of the cash sleeve per period')
    parser.add_argument('--up-prob', type=float, default=DEFAULT_UP_PROB,
                        help='probability of an up move')
    parser.add_argument('--max-fraction', type=float, default=DEFAULT_MAX_FRACTION,
                        help='largest fraction on the growth-curve grid')
    parser.add_argument('--grid-points', type=int, default=DEFAULT_GRID_POINTS,
                        help='number of points on the growth-curve grid')
    parser.add_argument('--sim-fractions', type=float, nargs='+', default=list(DEFAULT_SIM_FRACTIONS),
                        help='fractions simulated for the violin figure')
    parser.add_argument('--n-periods', type=int, default=DEFAULT_N_PERIODS,
                        help='number of periods per simulated path')
    parser.add_argument('--n-paths', type=int, default=DEFAULT_N_PATHS,
                        help='number of Monte Carlo paths per fraction')
    parser.add_argument('--chunk-size', type=int, default=DEFAULT_CHUNK_SIZE,
                        help='paths simulated per chunk, bounding peak memory')
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED,
                        help='seed of the random generator of the first fraction')

    args = parser.parse_args()
    parent = args.output_folder.parent if args.output_folder.parent != pathlib.Path('') else pathlib.Path('.')
    if not parent.is_dir():
        parser.error(f"--output-folder {args.output_folder} cannot be created: {parent} is not a folder.")
    out_of_range = [f for f in args.sim_fractions if f < 0.0 or f > args.max_fraction]
    if out_of_range:
        parser.error(f"--sim-fractions {out_of_range} fall outside [0, --max-fraction={args.max_fraction}].")
    return args


if __name__ == '__main__':
    cli_args = parse_args()
    bet_spec = BetSpec(
        up_factor=cli_args.up_factor,
        down_factor=cli_args.down_factor,
        cash_factor=cli_args.cash_factor,
        up_prob=cli_args.up_prob,
    )
    result_folder = cli_args.output_folder / OUTPUT_STEM
    result_folder.mkdir(parents=True, exist_ok=True)

    kelly_analyzer = KellyAnalyzer(spec=bet_spec)
    kelly_fraction = report_optima(analyzer=kelly_analyzer, max_fraction=cli_args.max_fraction)

    curve_df = build_curve_frame(analyzer=kelly_analyzer, max_fraction=cli_args.max_fraction,
                                 grid_points=cli_args.grid_points)
    simulation_df = build_simulation_frame(
        spec=bet_spec,
        fractions=tuple(cli_args.sim_fractions),
        n_periods=cli_args.n_periods,
        n_paths=cli_args.n_paths,
        chunk_size=cli_args.chunk_size,
        seed=cli_args.seed,
    )
    curve_df.to_csv(result_folder / 'growth_curve.csv', index=False, float_format='%.8g')
    simulation_df.to_csv(result_folder / 'simulated_log_growth.csv', index=False, float_format='%.8g')

    plot_growth_curve(curve_frame=curve_df, simulation_frame=simulation_df,
                      optimum=kelly_fraction, output_path=result_folder / 'growth_curve.png')
    plot_growth_violin(simulation_frame=simulation_df,
                       output_path=result_folder / 'growth_violin.png')
    plot_growth_zones(analyzer=kelly_analyzer, optimum=kelly_fraction,
                      output_path=result_folder / 'growth_zones.png')
    plot_formula_card(spec=bet_spec, optimum=kelly_fraction,
                      output_path=result_folder / 'formula_card.png')

    grid_best = curve_df.loc[curve_df[str(Column.LOG_GROWTH)].idxmax()]
    print(f"\nbest fraction on the grid: {grid_best[str(Column.FRACTION)]:.4f} "
          f"({grid_best[str(Column.RETURN_PER_PERIOD)]:+.4%} per period)")
    print(f"wrote outputs to {result_folder}")
