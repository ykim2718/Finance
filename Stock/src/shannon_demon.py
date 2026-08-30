"""
Monte Carlo of Shannon's Demon: a rebalanced two-asset portfolio versus buy-and-hold.

The game follows Claude Shannon's 1966 lecture example. One asset is a coin-flip stock that is
multiplied by `up_factor` or by `down_factor` every period. The other asset is cash. Holding the
stock alone has a geometric mean of one, yet rebalancing the pair to a fixed weight every period
turns two flat assets into a growing portfolio.

Changelog:
- 0.0.0 Initial release.
"""

__author__ = 'yRocket'
__version__ = "0.0.0.2026.8.29"

import argparse
import enum
import pathlib
import sys
from dataclasses import dataclass
from typing import Union

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TABLEAU_COLORS
from tqdm import tqdm

matplotlib.use('Agg')  # headless rendering; batch runs have no display server

__all__ = [
    'Strategy',
    'Column',
    'GameSpec',
    'ShannonDemonSimulator',
    'build_terminal_frame',
    'build_path_frame',
    'plot_wealth_paths',
    'plot_growth_distribution',
]

FIGSIZE: tuple = (9.0, 6.0)
REFERENCE_WIDTH: float = 9.0        # the width BASE_FONT_SIZE was chosen for
BASE_FONT_SIZE: float = 9.0
FIGURE_DPI: int = 300
PALETTE: list = list(TABLEAU_COLORS.values())
HIST_BINS: int = 70

DEFAULT_UP_FACTOR: float = 2.0
DEFAULT_DOWN_FACTOR: float = 0.5
DEFAULT_CASH_FACTOR: float = 1.0
DEFAULT_UP_PROB: float = 0.5
DEFAULT_STOCK_WEIGHT: float = 0.5
DEFAULT_N_PERIODS: int = 100
DEFAULT_N_PATHS: int = 20000
DEFAULT_CHUNK_SIZE: int = 4000
DEFAULT_N_SAMPLE_PATHS: int = 40
DEFAULT_SEED: int = 20260829
OUTPUT_STEM: str = 'shannon_demon'


class Strategy(enum.StrEnum):
    """Portfolio management rules compared by this module."""

    REBALANCED = enum.auto()
    BUY_AND_HOLD = enum.auto()


class Column(enum.StrEnum):
    """Column names of every frame this module writes."""

    PATH = enum.auto()
    PERIOD = enum.auto()
    STRATEGY = enum.auto()
    WEALTH = enum.auto()
    TERMINAL_WEALTH = enum.auto()
    LOG_GROWTH_PER_PERIOD = enum.auto()


@dataclass(frozen=True)
class GameSpec:
    """One parameterisation of the coin-flip game."""

    up_factor: float = DEFAULT_UP_FACTOR
    down_factor: float = DEFAULT_DOWN_FACTOR
    cash_factor: float = DEFAULT_CASH_FACTOR
    up_prob: float = DEFAULT_UP_PROB
    stock_weight: float = DEFAULT_STOCK_WEIGHT
    n_periods: int = DEFAULT_N_PERIODS
    n_paths: int = DEFAULT_N_PATHS
    seed: int = DEFAULT_SEED

    def __post_init__(self) -> None:
        if not 0.0 < self.up_prob < 1.0:
            raise ValueError(f"up_prob must lie strictly inside (0, 1); got {self.up_prob!r}.")
        if self.up_factor <= 0.0 or self.down_factor <= 0.0 or self.cash_factor <= 0.0:
            raise ValueError(
                f"growth factors must be positive; got up={self.up_factor!r}, "
                f"down={self.down_factor!r}, cash={self.cash_factor!r}."
            )
        if self.up_factor <= self.down_factor:
            raise ValueError(
                f"up_factor must exceed down_factor; got {self.up_factor!r} <= {self.down_factor!r}."
            )
        if self.n_periods < 1 or self.n_paths < 1:
            raise ValueError(f"n_periods and n_paths must be >= 1; got {self.n_periods!r}, {self.n_paths!r}.")
        rebalanced_floor = self.stock_weight * self.down_factor + (1.0 - self.stock_weight) * self.cash_factor
        if rebalanced_floor <= 0.0:
            raise ValueError(
                f"stock_weight={self.stock_weight!r} wipes the rebalanced portfolio out on a down move; "
                "choose a weight that keeps the one-period factor positive."
            )

    @property
    def stock_log_growth(self) -> float:
        """Expected log growth per period of the stock held alone."""
        return float(self.up_prob * np.log(self.up_factor) + (1.0 - self.up_prob) * np.log(self.down_factor))


class ShannonDemonSimulator:
    """Simulate both strategies on a shared set of coin-flip draws."""

    def __init__(self, spec: GameSpec, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        if chunk_size < 1:
            raise ValueError(f"chunk_size must be >= 1; got {chunk_size!r}.")
        self.spec = spec
        self.chunk_size = chunk_size
        self._rng = np.random.default_rng(spec.seed)

    def _draw_stock_factors(self, n_paths: int) -> np.ndarray:
        """Return a (n_paths x n_periods) array of per-period stock growth factors."""
        is_up = self._rng.random((n_paths, self.spec.n_periods)) < self.spec.up_prob
        return np.where(is_up, self.spec.up_factor, self.spec.down_factor)

    def _wealth_from_factors(self, stock_factors: np.ndarray) -> dict:
        """Return wealth paths of both strategies, each shaped (n_paths x (n_periods + 1)), starting at 1."""
        spec = self.spec
        weight = spec.stock_weight
        n_paths = stock_factors.shape[0]
        ones = np.ones((n_paths, 1))

        # Rebalanced: the weights are restored every period, so the portfolio factor is a fixed blend.
        blended = weight * stock_factors + (1.0 - weight) * spec.cash_factor
        rebalanced = np.hstack([ones, np.cumprod(blended, axis=1)])

        # Buy-and-hold: each sleeve compounds on its own and the weights drift.
        stock_sleeve = weight * np.cumprod(stock_factors, axis=1)
        periods = np.arange(1, spec.n_periods + 1)
        cash_sleeve = (1.0 - weight) * np.power(spec.cash_factor, periods)[None, :]
        buy_and_hold = np.hstack([ones, stock_sleeve + cash_sleeve])

        return {Strategy.REBALANCED: rebalanced, Strategy.BUY_AND_HOLD: buy_and_hold}

    def run(self, n_sample_paths: int = DEFAULT_N_SAMPLE_PATHS) -> tuple:
        """
        Simulate every path and return `(terminal_wealth, sample_paths)`.

        `terminal_wealth` maps each Strategy to a 1-D array of terminal wealth, one entry per path.
        `sample_paths` maps each Strategy to a (n_sample_paths x (n_periods + 1)) array of full paths
        taken from the first chunk, for plotting.
        """
        if n_sample_paths < 1:
            raise ValueError(f"n_sample_paths must be >= 1; got {n_sample_paths!r}.")
        if n_sample_paths > self.spec.n_paths:
            raise ValueError(
                f"n_sample_paths={n_sample_paths!r} exceeds n_paths={self.spec.n_paths!r}."
            )

        terminal = {strategy: [] for strategy in Strategy}
        samples: dict = {}
        remaining = self.spec.n_paths
        chunk_sizes = []
        while remaining > 0:
            chunk_sizes.append(min(self.chunk_size, remaining))
            remaining -= chunk_sizes[-1]

        pbar = tqdm(chunk_sizes, ncols=100, unit='chunk')
        for index, size in enumerate(pbar):
            pbar.set_description(f"Simulating chunk {index + 1}/{len(chunk_sizes)}")
            wealth = self._wealth_from_factors(self._draw_stock_factors(n_paths=size))
            for strategy, paths in wealth.items():
                terminal[strategy].append(paths[:, -1])
                if index == 0:
                    samples[strategy] = paths[:min(n_sample_paths, size), :]

        return {strategy: np.concatenate(chunks) for strategy, chunks in terminal.items()}, samples


def build_terminal_frame(terminal_wealth: dict, n_periods: int) -> pd.DataFrame:
    """
    Return one row per (path, strategy) sample.

    Index: RangeIndex.
    Columns: `path`, `strategy`, `terminal_wealth`, `log_growth_per_period`.
    """
    if n_periods < 1:
        raise ValueError(f"n_periods must be >= 1; got {n_periods!r}.")
    frames = []
    for strategy, wealth in terminal_wealth.items():
        if wealth.size == 0:
            raise ValueError(f"strategy {strategy!s} produced no terminal wealth samples.")
        frames.append(pd.DataFrame({
            str(Column.PATH): np.arange(wealth.size),
            str(Column.STRATEGY): str(strategy),
            str(Column.TERMINAL_WEALTH): wealth,
            str(Column.LOG_GROWTH_PER_PERIOD): np.log(wealth) / n_periods,
        }))
    return pd.concat(frames, ignore_index=True)


def build_path_frame(sample_paths: dict) -> pd.DataFrame:
    """
    Return one row per (path, period, strategy) point of the plotted sample paths.

    Index: RangeIndex.
    Columns: `path`, `period`, `strategy`, `wealth`.
    """
    frames = []
    for strategy, paths in sample_paths.items():
        n_paths, n_points = paths.shape
        path_ids = np.repeat(np.arange(n_paths), n_points)
        periods = np.tile(np.arange(n_points), n_paths)
        frames.append(pd.DataFrame({
            str(Column.PATH): path_ids,
            str(Column.PERIOD): periods,
            str(Column.STRATEGY): str(strategy),
            str(Column.WEALTH): paths.reshape(-1),
        }))
    return pd.concat(frames, ignore_index=True)


def plot_wealth_paths(path_frame: pd.DataFrame, spec: GameSpec, output_path: pathlib.Path) -> None:
    """Draw one panel per strategy showing the sampled wealth paths on a log scale."""
    font_size = BASE_FONT_SIZE * FIGSIZE[0] / REFERENCE_WIDTH
    strategies = [Strategy.REBALANCED, Strategy.BUY_AND_HOLD]
    fig, axes = plt.subplots(1, len(strategies), figsize=FIGSIZE, sharey=True)
    for panel, (label, strategy) in enumerate(zip('ab', strategies)):
        axis = axes[panel]
        subset = path_frame[path_frame[str(Column.STRATEGY)] == str(strategy)]
        for path_id, group in subset.groupby(str(Column.PATH)):
            axis.plot(group[str(Column.PERIOD)], group[str(Column.WEALTH)],
                      color=PALETTE[panel % len(PALETTE)], alpha=0.35, linewidth=0.8)
        axis.set_yscale('log')
        axis.axhline(1.0, color='black', linewidth=0.8, linestyle='--')
        axis.set_title(f"({label}) {str(strategy).replace('_', ' ')}", fontsize=font_size + 1)
        axis.set_xlabel('Period', fontsize=font_size)
        axis.tick_params(labelsize=font_size - 1)
        axis.grid(True, which='both', alpha=0.25)
    axes[0].set_ylabel('Wealth (start = 1)', fontsize=font_size)
    fig.suptitle(
        f"Sampled wealth paths, stock weight {spec.stock_weight:.0%}, {spec.n_periods} periods",
        fontsize=font_size + 2,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI)
    plt.close(fig)


def plot_growth_distribution(terminal_frame: pd.DataFrame, spec: GameSpec,
                             output_path: pathlib.Path) -> None:
    """Draw the distribution of per-period log growth for both strategies."""
    font_size = BASE_FONT_SIZE * FIGSIZE[0] / REFERENCE_WIDTH
    fig, axis = plt.subplots(figsize=FIGSIZE)
    column = str(Column.LOG_GROWTH_PER_PERIOD)
    values = terminal_frame[column].to_numpy()
    bins = np.linspace(values.min(), values.max(), HIST_BINS)
    for index, strategy in enumerate(Strategy):
        subset = terminal_frame[terminal_frame[str(Column.STRATEGY)] == str(strategy)][column]
        axis.hist(subset, bins=bins, alpha=0.55, label=str(strategy).replace('_', ' '),
                  color=PALETTE[index % len(PALETTE)])
        axis.axvline(float(np.median(subset)), color=PALETTE[index % len(PALETTE)],
                     linestyle='--', linewidth=1.2)
    axis.axvline(spec.stock_log_growth, color='black', linestyle=':', linewidth=1.2,
                 label='stock held alone')
    axis.set_xlabel('Log growth per period', fontsize=font_size)
    axis.set_ylabel('Path count', fontsize=font_size)
    axis.set_title(
        f"Per-period log growth over {spec.n_paths:,} paths (dashed lines: medians)",
        fontsize=font_size + 2,
    )
    axis.tick_params(labelsize=font_size - 1)
    axis.legend(fontsize=font_size)
    axis.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI)
    plt.close(fig)


def report_summary(terminal_frame: pd.DataFrame, spec: GameSpec) -> pd.DataFrame:
    """
    Return the console summary computed from the saved samples.

    Index: RangeIndex.
    Columns: `strategy`, `median_terminal_wealth`, `mean_terminal_wealth`,
             `median_log_growth_per_period`, `median_return_per_period`, `loss_probability`.
    """
    rows = []
    for strategy in Strategy:
        subset = terminal_frame[terminal_frame[str(Column.STRATEGY)] == str(strategy)]
        wealth = subset[str(Column.TERMINAL_WEALTH)].to_numpy()
        growth = subset[str(Column.LOG_GROWTH_PER_PERIOD)].to_numpy()
        median_growth = float(np.median(growth))
        rows.append({
            'strategy': str(strategy),
            'median_terminal_wealth': float(np.median(wealth)),
            'mean_terminal_wealth': float(np.mean(wealth)),
            'median_log_growth_per_period': median_growth,
            'median_return_per_period': float(np.expm1(median_growth)),
            'loss_probability': float(np.mean(wealth < 1.0)),
        })
    summary = pd.DataFrame(rows)
    print(f"\nstock alone, expected log growth per period: {spec.stock_log_growth:+.6f}")
    print(summary.to_string(index=False))
    return summary


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
                    "Compare a periodically rebalanced portfolio with buy-and-hold on Shannon's "
                    "coin-flip game.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-v', '--version', action='version', version=f"{script_name} {__version__}")
    parser.add_argument('--output-folder', type=pathlib.Path, required=True,
                        help='root folder for every output; results land in <output-folder>/'
                             f'{OUTPUT_STEM}/')
    parser.add_argument('--up-factor', type=float, default=DEFAULT_UP_FACTOR,
                        help='stock growth factor on an up move')
    parser.add_argument('--down-factor', type=float, default=DEFAULT_DOWN_FACTOR,
                        help='stock growth factor on a down move')
    parser.add_argument('--cash-factor', type=float, default=DEFAULT_CASH_FACTOR,
                        help='growth factor of the cash sleeve per period')
    parser.add_argument('--up-prob', type=float, default=DEFAULT_UP_PROB,
                        help='probability of an up move')
    parser.add_argument('--stock-weight', type=float, default=DEFAULT_STOCK_WEIGHT,
                        help='portfolio weight held in the stock')
    parser.add_argument('--n-periods', type=int, default=DEFAULT_N_PERIODS,
                        help='number of periods per path')
    parser.add_argument('--n-paths', type=int, default=DEFAULT_N_PATHS,
                        help='number of Monte Carlo paths')
    parser.add_argument('--chunk-size', type=int, default=DEFAULT_CHUNK_SIZE,
                        help='paths simulated per chunk, bounding peak memory')
    parser.add_argument('--n-sample-paths', type=int, default=DEFAULT_N_SAMPLE_PATHS,
                        help='paths drawn for the wealth-path figure')
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED,
                        help='seed of the random generator')

    args = parser.parse_args()
    parent = args.output_folder.parent if args.output_folder.parent != pathlib.Path('') else pathlib.Path('.')
    if not parent.is_dir():
        parser.error(f"--output-folder {args.output_folder} cannot be created: {parent} is not a folder.")
    return args


if __name__ == '__main__':
    cli_args = parse_args()
    game_spec = GameSpec(
        up_factor=cli_args.up_factor,
        down_factor=cli_args.down_factor,
        cash_factor=cli_args.cash_factor,
        up_prob=cli_args.up_prob,
        stock_weight=cli_args.stock_weight,
        n_periods=cli_args.n_periods,
        n_paths=cli_args.n_paths,
        seed=cli_args.seed,
    )
    result_folder = cli_args.output_folder / OUTPUT_STEM
    result_folder.mkdir(parents=True, exist_ok=True)

    simulator = ShannonDemonSimulator(spec=game_spec, chunk_size=cli_args.chunk_size)
    terminal_wealth, sample_paths = simulator.run(n_sample_paths=cli_args.n_sample_paths)

    terminal_df = build_terminal_frame(terminal_wealth=terminal_wealth, n_periods=game_spec.n_periods)
    path_df = build_path_frame(sample_paths=sample_paths)
    terminal_df.to_csv(result_folder / 'terminal_wealth.csv', index=False, float_format='%.8g')
    path_df.to_csv(result_folder / 'wealth_paths.csv', index=False, float_format='%.8g')

    plot_wealth_paths(path_frame=path_df, spec=game_spec,
                      output_path=result_folder / 'wealth_paths.png')
    plot_growth_distribution(terminal_frame=terminal_df, spec=game_spec,
                             output_path=result_folder / 'growth_distribution.png')
    report_summary(terminal_frame=terminal_df, spec=game_spec)
    print(f"\nwrote outputs to {result_folder}")
