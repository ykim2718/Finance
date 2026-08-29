"""
How much of Shannon's Demon survives realistic parameters.

The coin-flip game of `shannon_demon.py` is deliberately extreme. This module measures the same
effect on lognormal assets at plausible volatilities, charges transaction cost for every rebalance,
and lets the returns carry autocorrelation so the trending case can be told apart from the
mean-reverting one.

Three questions are answered, each with its own output:
- Gross rebalancing bonus as a function of volatility and correlation, in closed form.
- Net bonus after transaction cost, as a function of how often the portfolio is rebalanced.
- Sign of the bonus when log returns follow an AR(1) process instead of being independent.

Changelog:
- 0.0.0 Initial release.
- 0.1.0 Add the weighted-average-asset benchmark, so the closed-form bonus can be validated
        against the simulation and told apart from the advantage over buy-and-hold.
"""

__author__ = 'yRocket'
__version__ = "0.1.0.2026.8.29"

import argparse
import enum
import pathlib
import sys
from dataclasses import dataclass
from typing import Literal

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TABLEAU_COLORS
from tqdm import tqdm

matplotlib.use('Agg')  # headless rendering; batch runs have no display server

__all__ = [
    'Column',
    'MarketSpec',
    'RebalanceBonusAnalyzer',
    'gross_rebalancing_bonus',
    'build_bonus_grid',
    'plot_bonus_heatmap',
    'plot_frequency_net_bonus',
    'plot_autocorrelation_effect',
]

FIGSIZE: tuple = (9.0, 6.0)
HEATMAP_FIGSIZE: tuple = (9.0, 5.4)
REFERENCE_WIDTH: float = 9.0        # the width BASE_FONT_SIZE was chosen for
BASE_FONT_SIZE: float = 9.0
FIGURE_DPI: int = 300
PALETTE: list = list(TABLEAU_COLORS.values())

DEFAULT_STEPS_PER_YEAR: int = 252
DEFAULT_N_YEARS: int = 20
DEFAULT_N_PATHS: int = 1000
DEFAULT_ANNUAL_DRIFT: float = 0.05
DEFAULT_ANNUAL_VOLATILITY: float = 0.20
DEFAULT_CORRELATION: float = 0.20
DEFAULT_STOCK_WEIGHT: float = 0.50
DEFAULT_SEED: int = 20260829

DEFAULT_REBALANCE_INTERVALS: tuple = (1, 5, 21, 63, 126, 252)
DEFAULT_COST_BPS: tuple = (0.0, 5.0, 10.0, 25.0, 50.0)
DEFAULT_PHI_GRID: tuple = (-0.30, -0.20, -0.10, -0.05, 0.0, 0.05, 0.10, 0.20, 0.30)
DEFAULT_SIGMA_GRID: tuple = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60)
DEFAULT_RHO_GRID: tuple = (-0.90, -0.60, -0.30, 0.0, 0.30, 0.60, 0.90)
BASIS_POINT: float = 1e-4
QUARTILE_LOW: float = 0.25
QUARTILE_HIGH: float = 0.75
NORMALIZATIONS: tuple = ('step', 'horizon')
DEFAULT_NORMALIZATION: str = 'horizon'
CLOSED_FORM_TOLERANCE: float = 5e-4   # 0.05 %p; the gap a finite rebalancing interval still leaves
OUTPUT_STEM: str = 'rebalance_bonus'

INTERVAL_LABELS: dict = {1: 'daily', 5: 'weekly', 21: 'monthly', 63: 'quarterly',
                         126: 'semiannual', 252: 'annual'}


class Column(enum.StrEnum):
    """Column names of every frame this module writes."""

    SIGMA = enum.auto()
    RHO = enum.auto()
    GROSS_BONUS = enum.auto()
    PATH = enum.auto()
    REBALANCE_INTERVAL = enum.auto()
    COST_BPS = enum.auto()
    PHI = enum.auto()
    REBALANCED_CAGR = enum.auto()
    BUY_HOLD_CAGR = enum.auto()
    ADVANTAGE = enum.auto()
    WEIGHTED_ASSET_CAGR = enum.auto()
    BONUS_VS_WEIGHTED_ASSET = enum.auto()
    ANNUAL_TURNOVER = enum.auto()


@dataclass(frozen=True)
class MarketSpec:
    """Two lognormal assets with equal parameters, held at a fixed target weight."""

    annual_drift: float = DEFAULT_ANNUAL_DRIFT
    annual_volatility: float = DEFAULT_ANNUAL_VOLATILITY
    correlation: float = DEFAULT_CORRELATION
    stock_weight: float = DEFAULT_STOCK_WEIGHT
    steps_per_year: int = DEFAULT_STEPS_PER_YEAR
    n_years: int = DEFAULT_N_YEARS
    n_paths: int = DEFAULT_N_PATHS
    seed: int = DEFAULT_SEED

    def __post_init__(self) -> None:
        if self.annual_volatility <= 0.0:
            raise ValueError(f"annual_volatility must be positive; got {self.annual_volatility!r}.")
        if not -1.0 < self.correlation < 1.0:
            raise ValueError(f"correlation must lie strictly inside (-1, 1); got {self.correlation!r}.")
        if not 0.0 < self.stock_weight < 1.0:
            raise ValueError(
                f"stock_weight must lie strictly inside (0, 1); got {self.stock_weight!r}. "
                "A degenerate weight leaves nothing to rebalance."
            )
        if self.steps_per_year < 1 or self.n_years < 1 or self.n_paths < 1:
            raise ValueError(
                f"steps_per_year, n_years and n_paths must be >= 1; got {self.steps_per_year!r}, "
                f"{self.n_years!r}, {self.n_paths!r}."
            )

    @property
    def n_steps(self) -> int:
        """Total number of simulated steps per path."""
        return self.steps_per_year * self.n_years

    @property
    def weights(self) -> np.ndarray:
        """Target weights of the two assets."""
        return np.array([self.stock_weight, 1.0 - self.stock_weight])


def gross_rebalancing_bonus(sigma: np.ndarray, rho: np.ndarray, weight: float) -> np.ndarray:
    """
    Return the closed-form rebalancing bonus of two equal-volatility assets, in log growth per year.

    The bonus is half the gap between the weighted average of the asset variances and the portfolio
    variance, which is the only term by which continuously rebalanced growth beats the weighted
    average of the individual growth rates.
    """
    if not 0.0 <= weight <= 1.0:
        raise ValueError(f"weight must lie in [0, 1]; got {weight!r}.")
    sigma = np.asarray(sigma, dtype=float)
    rho = np.asarray(rho, dtype=float)
    if np.any(sigma < 0.0):
        raise ValueError("sigma must be non-negative.")
    if np.any(np.abs(rho) > 1.0):
        raise ValueError("rho must lie in [-1, 1].")
    other = 1.0 - weight
    weighted_variance = (weight + other) * sigma ** 2
    portfolio_variance = (weight ** 2 + other ** 2 + 2.0 * weight * other * rho) * sigma ** 2
    return 0.5 * (weighted_variance - portfolio_variance)


def build_bonus_grid(sigma_grid: tuple, rho_grid: tuple, weight: float) -> pd.DataFrame:
    """
    Return the closed-form bonus over the volatility by correlation grid, one row per cell.

    Index: RangeIndex.
    Columns: `sigma`, `rho`, `gross_bonus`.
    """
    if len(sigma_grid) == 0 or len(rho_grid) == 0:
        raise ValueError("sigma_grid and rho_grid must both be non-empty.")
    sigma_mesh, rho_mesh = np.meshgrid(np.asarray(sigma_grid, dtype=float),
                                       np.asarray(rho_grid, dtype=float), indexing='ij')
    bonus = gross_rebalancing_bonus(sigma=sigma_mesh, rho=rho_mesh, weight=weight)
    return pd.DataFrame({
        str(Column.SIGMA): sigma_mesh.reshape(-1),
        str(Column.RHO): rho_mesh.reshape(-1),
        str(Column.GROSS_BONUS): bonus.reshape(-1),
    })


class RebalanceBonusAnalyzer:
    """Simulate two lognormal assets and measure what rebalancing is worth after cost."""

    def __init__(self, spec: MarketSpec) -> None:
        self.spec = spec
        self._rng = np.random.default_rng(spec.seed)

    def reset_rng(self) -> None:
        """Rewind the generator to the seed so a later sweep redraws the same shocks."""
        self._rng = np.random.default_rng(self.spec.seed)

    def simulate_log_returns(self, phi: float = 0.0,
                             normalization: Literal['step', 'horizon'] = DEFAULT_NORMALIZATION) -> np.ndarray:
        """
        Return a (n_paths x n_steps x 2) array of log returns whose moments match the spec.

        `phi` is the AR(1) coefficient of the log returns. A positive value makes the series trend,
        a negative value makes it revert.

        `normalization` fixes what `annual_volatility` refers to, and the two answers differ in sign,
        so the choice is never made silently:
        - 'step' holds the one-step volatility fixed. A trending series then accumulates more
          long-horizon risk, so raising `phi` raises the total volatility available to harvest.
        - 'horizon' holds the one-year volatility of the cumulative log return fixed. Raising `phi`
          then only redistributes the same risk from step to step, which is the comparison that
          isolates trend from mean reversion.
        """
        if not -1.0 < phi < 1.0:
            raise ValueError(f"phi must lie strictly inside (-1, 1) for a stationary series; got {phi!r}.")
        if normalization not in NORMALIZATIONS:
            raise ValueError(f"normalization must be one of {NORMALIZATIONS}; got {normalization!r}.")
        spec = self.spec
        dt = 1.0 / spec.steps_per_year
        # Variance of a sum of n AR(1) terms grows by (1 + phi) / (1 - phi) relative to independent draws.
        horizon_correction = np.sqrt((1.0 - phi) / (1.0 + phi)) if normalization == 'horizon' else 1.0
        step_sigma = spec.annual_volatility * np.sqrt(dt) * horizon_correction
        step_drift = spec.annual_drift * dt
        covariance = step_sigma ** 2 * np.array([[1.0, spec.correlation], [spec.correlation, 1.0]])
        innovation_scale = np.sqrt(1.0 - phi ** 2)

        shocks = self._rng.multivariate_normal(mean=np.zeros(2), cov=covariance,
                                               size=(spec.n_paths, spec.n_steps))
        deviations = np.empty_like(shocks)
        deviations[:, 0, :] = shocks[:, 0, :]                       # start from the stationary distribution
        for step in range(1, spec.n_steps):
            deviations[:, step, :] = phi * deviations[:, step - 1, :] + innovation_scale * shocks[:, step, :]
        return step_drift + deviations

    def weighted_asset_cagr(self, log_returns: np.ndarray) -> np.ndarray:
        """
        Return the weighted average of the two assets' own CAGRs, one entry per path.

        This is the benchmark the closed-form bonus is written against. It is not buy-and-hold:
        buy-and-hold lets the winner's weight drift up, so it earns part of the same gap on its own.
        """
        asset_log_growth = log_returns.sum(axis=1) / self.spec.n_years
        return np.expm1((asset_log_growth * self.spec.weights).sum(axis=1))

    def run_strategy(self, log_returns: np.ndarray, rebalance_interval: int,
                     cost_rate: float) -> dict:
        """
        Return `{'cagr': ..., 'annual_turnover': ...}`, each a 1-D array with one entry per path.

        `rebalance_interval` is the number of steps between rebalances; 0 means buy-and-hold.
        `cost_rate` is charged on every unit of notional traded, on both the buy and the sell side.
        """
        if rebalance_interval < 0:
            raise ValueError(f"rebalance_interval must be >= 0; got {rebalance_interval!r}.")
        if cost_rate < 0.0:
            raise ValueError(f"cost_rate must be >= 0; got {cost_rate!r}.")
        if rebalance_interval == 0 and cost_rate > 0.0:
            raise ValueError(
                "buy-and-hold (rebalance_interval=0) trades nothing, so a non-zero cost_rate is "
                "contradictory; pass cost_rate=0 or a positive interval."
            )
        spec = self.spec
        gross = np.exp(log_returns)
        holdings = np.tile(spec.weights, (log_returns.shape[0], 1))
        traded_notional = np.zeros(log_returns.shape[0])

        for step in range(log_returns.shape[1]):
            holdings = holdings * gross[:, step, :]
            if rebalance_interval == 0 or (step + 1) % rebalance_interval != 0:
                continue
            total = holdings.sum(axis=1)
            target = total[:, None] * spec.weights
            volume = np.abs(target - holdings).sum(axis=1)
            traded_notional += volume / total
            total_after = total - cost_rate * volume
            if np.any(total_after <= 0.0):
                raise RuntimeError(
                    f"transaction cost wiped a path out at step {step}; cost_rate={cost_rate!r} is "
                    "too large for this rebalancing interval."
                )
            holdings = total_after[:, None] * spec.weights

        terminal = holdings.sum(axis=1)
        if np.any(terminal <= 0.0):
            raise RuntimeError("a path reached non-positive terminal wealth; the simulation is invalid.")
        return {
            'cagr': np.expm1(np.log(terminal) / spec.n_years),
            'annual_turnover': traded_notional / spec.n_years,
        }

    def sweep_frequency_and_cost(self, intervals: tuple, cost_bps_grid: tuple) -> pd.DataFrame:
        """
        Return the paired comparison of rebalancing against buy-and-hold, one row per (interval, cost, path).

        All configurations share one set of return paths, so the difference between rows isolates the
        rebalancing rule rather than the draw.

        Index: RangeIndex.
        Columns: `rebalance_interval`, `cost_bps`, `path`, `rebalanced_cagr`, `buy_hold_cagr`,
                 `advantage`, `weighted_asset_cagr`, `bonus_vs_weighted_asset`, `annual_turnover`.
        """
        if len(intervals) == 0 or len(cost_bps_grid) == 0:
            raise ValueError("intervals and cost_bps_grid must both be non-empty.")
        if any(interval < 1 for interval in intervals):
            raise ValueError(f"every rebalance interval must be >= 1; got {intervals!r}.")
        log_returns = self.simulate_log_returns(phi=0.0)
        buy_hold = self.run_strategy(log_returns=log_returns, rebalance_interval=0, cost_rate=0.0)
        weighted_asset = self.weighted_asset_cagr(log_returns=log_returns)

        frames = []
        configurations = [(interval, cost) for interval in intervals for cost in cost_bps_grid]
        pbar = tqdm(configurations, ncols=100, unit='config')
        for interval, cost_bps in pbar:
            pbar.set_description(f"Rebalance every {interval:>3d} steps at {cost_bps:g} bps")
            rebalanced = self.run_strategy(log_returns=log_returns, rebalance_interval=interval,
                                           cost_rate=cost_bps * BASIS_POINT)
            frames.append(pd.DataFrame({
                str(Column.REBALANCE_INTERVAL): interval,
                str(Column.COST_BPS): float(cost_bps),
                str(Column.PATH): np.arange(rebalanced['cagr'].size),
                str(Column.REBALANCED_CAGR): rebalanced['cagr'],
                str(Column.BUY_HOLD_CAGR): buy_hold['cagr'],
                str(Column.ADVANTAGE): rebalanced['cagr'] - buy_hold['cagr'],
                str(Column.WEIGHTED_ASSET_CAGR): weighted_asset,
                str(Column.BONUS_VS_WEIGHTED_ASSET): rebalanced['cagr'] - weighted_asset,
                str(Column.ANNUAL_TURNOVER): rebalanced['annual_turnover'],
            }))
        return pd.concat(frames, ignore_index=True)

    def sweep_autocorrelation(self, phi_grid: tuple, rebalance_interval: int, cost_bps: float,
                              normalization: Literal['step', 'horizon']) -> pd.DataFrame:
        """
        Return the rebalancing advantage under AR(1) log returns, one row per (phi, path).

        `normalization` is passed straight to `simulate_log_returns`. The generator is rewound
        before every `phi`, so all of them filter the same shocks and the comparison across `phi`
        is paired rather than confounded by the draw.

        Index: RangeIndex.
        Columns: `phi`, `path`, `rebalanced_cagr`, `buy_hold_cagr`, `advantage`.
        """
        if len(phi_grid) == 0:
            raise ValueError("phi_grid must be non-empty.")
        if rebalance_interval < 1:
            raise ValueError(f"rebalance_interval must be >= 1 here; got {rebalance_interval!r}.")
        frames = []
        pbar = tqdm(phi_grid, ncols=100, unit='phi')
        for phi in pbar:
            pbar.set_description(f"AR(1) coefficient {phi:+.2f}")
            self.reset_rng()
            log_returns = self.simulate_log_returns(phi=float(phi), normalization=normalization)
            buy_hold = self.run_strategy(log_returns=log_returns, rebalance_interval=0, cost_rate=0.0)
            rebalanced = self.run_strategy(log_returns=log_returns, rebalance_interval=rebalance_interval,
                                           cost_rate=cost_bps * BASIS_POINT)
            frames.append(pd.DataFrame({
                str(Column.PHI): float(phi),
                str(Column.PATH): np.arange(rebalanced['cagr'].size),
                str(Column.REBALANCED_CAGR): rebalanced['cagr'],
                str(Column.BUY_HOLD_CAGR): buy_hold['cagr'],
                str(Column.ADVANTAGE): rebalanced['cagr'] - buy_hold['cagr'],
            }))
        return pd.concat(frames, ignore_index=True)


def plot_bonus_heatmap(bonus_frame: pd.DataFrame, output_path: pathlib.Path) -> None:
    """Draw the closed-form bonus as a matrix chart over volatility and correlation."""
    font_size = BASE_FONT_SIZE * HEATMAP_FIGSIZE[0] / REFERENCE_WIDTH
    matrix = bonus_frame.pivot(index=str(Column.SIGMA), columns=str(Column.RHO),
                               values=str(Column.GROSS_BONUS))
    fig, axis = plt.subplots(figsize=HEATMAP_FIGSIZE)
    image = axis.imshow(matrix.to_numpy() * 100.0, origin='lower', aspect='auto', cmap='viridis')
    axis.set_xticks(np.arange(matrix.shape[1]))
    axis.set_xticklabels([f"{value:+.2f}" for value in matrix.columns])
    axis.set_yticks(np.arange(matrix.shape[0]))
    axis.set_yticklabels([f"{value:.0%}" for value in matrix.index])
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            axis.text(column, row, f"{matrix.to_numpy()[row, column] * 100.0:.2f}",
                      ha='center', va='center', color='white', fontsize=font_size - 2)
    axis.set_xlabel('Correlation between the two assets', fontsize=font_size)
    axis.set_ylabel('Annual volatility of each asset', fontsize=font_size)
    axis.set_title('Gross rebalancing bonus (%p of annual log growth)', fontsize=font_size + 2)
    axis.tick_params(labelsize=font_size - 1)
    fig.colorbar(image, ax=axis, label='%p per year')
    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI)
    plt.close(fig)


def plot_frequency_net_bonus(sweep_frame: pd.DataFrame, output_path: pathlib.Path) -> None:
    """Draw the median net advantage of rebalancing against its interval, one line per cost level."""
    font_size = BASE_FONT_SIZE * FIGSIZE[0] / REFERENCE_WIDTH
    intervals = sorted(sweep_frame[str(Column.REBALANCE_INTERVAL)].unique())
    positions = np.arange(len(intervals))
    fig, axis = plt.subplots(figsize=FIGSIZE)
    for index, cost_bps in enumerate(sorted(sweep_frame[str(Column.COST_BPS)].unique())):
        subset = sweep_frame[sweep_frame[str(Column.COST_BPS)] == cost_bps]
        medians = subset.groupby(str(Column.REBALANCE_INTERVAL))[str(Column.ADVANTAGE)].median()
        axis.plot(positions, medians.reindex(intervals).to_numpy() * 100.0, marker='o',
                  color=PALETTE[index % len(PALETTE)], label=f"{cost_bps:g} bps per trade")
    axis.axhline(0.0, color='black', linewidth=0.9)
    axis.set_xticks(positions)
    axis.set_xticklabels([f"{INTERVAL_LABELS.get(interval, f'{interval} steps')}\n({interval})"
                          for interval in intervals])
    axis.set_xlabel('Rebalancing interval (trading days)', fontsize=font_size)
    axis.set_ylabel('Median CAGR advantage over buy-and-hold (%p)', fontsize=font_size)
    axis.set_title('Net rebalancing bonus after transaction cost', fontsize=font_size + 2)
    axis.tick_params(labelsize=font_size - 1)
    axis.legend(fontsize=font_size)
    axis.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI)
    plt.close(fig)


def plot_autocorrelation_effect(autocorr_frame: pd.DataFrame, output_path: pathlib.Path) -> None:
    """Draw the rebalancing advantage against the AR(1) coefficient, with the interquartile band."""
    font_size = BASE_FONT_SIZE * FIGSIZE[0] / REFERENCE_WIDTH
    grouped = autocorr_frame.groupby(str(Column.PHI))[str(Column.ADVANTAGE)]
    phi_values = np.array(sorted(autocorr_frame[str(Column.PHI)].unique()))
    medians = grouped.median().reindex(phi_values).to_numpy() * 100.0
    low = grouped.quantile(QUARTILE_LOW).reindex(phi_values).to_numpy() * 100.0
    high = grouped.quantile(QUARTILE_HIGH).reindex(phi_values).to_numpy() * 100.0

    fig, axis = plt.subplots(figsize=FIGSIZE)
    axis.fill_between(phi_values, low, high, color=PALETTE[0], alpha=0.25,
                      label='interquartile range')
    axis.plot(phi_values, medians, marker='o', color=PALETTE[0], label='median')
    axis.axhline(0.0, color='black', linewidth=0.9)
    axis.axvline(0.0, color='grey', linewidth=0.8, linestyle=':')
    axis.set_xlabel('AR(1) coefficient of log returns (negative: reverting, positive: trending)',
                    fontsize=font_size)
    axis.set_ylabel('CAGR advantage over buy-and-hold (%p)', fontsize=font_size)
    axis.set_title('Rebalancing advantage against return autocorrelation', fontsize=font_size + 2)
    axis.tick_params(labelsize=font_size - 1)
    axis.legend(fontsize=font_size)
    axis.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI)
    plt.close(fig)


def report_sweeps(spec: MarketSpec, sweep_frame: pd.DataFrame, autocorr_frame: pd.DataFrame) -> None:
    """Print the headline numbers, all computed from the saved sample frames."""
    closed_form = float(gross_rebalancing_bonus(sigma=spec.annual_volatility,
                                                rho=spec.correlation, weight=spec.stock_weight))
    print(f"\nclosed-form gross bonus at sigma={spec.annual_volatility:.0%}, "
          f"rho={spec.correlation:+.2f}: {closed_form * 100.0:.4f} %p per year")

    free = sweep_frame[sweep_frame[str(Column.COST_BPS)] == sweep_frame[str(Column.COST_BPS)].min()]

    # The closed form is the continuous-rebalancing bonus over the weighted average of the assets'
    # own growth, so that is the row it must be checked against, not the advantage over buy-and-hold.
    finest = free[free[str(Column.REBALANCE_INTERVAL)] == free[str(Column.REBALANCE_INTERVAL)].min()]
    simulated = float(np.median(np.log1p(finest[str(Column.REBALANCED_CAGR)])
                                - np.log1p(finest[str(Column.WEIGHTED_ASSET_CAGR)])))
    drift_gain = float(np.median(np.log1p(finest[str(Column.BUY_HOLD_CAGR)])
                                 - np.log1p(finest[str(Column.WEIGHTED_ASSET_CAGR)])))
    print(f"simulated bonus over the weighted-average asset:  {simulated * 100.0:.4f} %p per year")
    print(f"buy-and-hold gain from weight drift:              {drift_gain * 100.0:.4f} %p per year")
    if abs(simulated - closed_form) > CLOSED_FORM_TOLERANCE:
        print(f"WARNING: simulated bonus differs from the closed form by "
              f"{abs(simulated - closed_form) * 100.0:.4f} %p, above the "
              f"{CLOSED_FORM_TOLERANCE * 100.0:.4f} %p tolerance.")
    print("\nmedian CAGR advantage by rebalancing interval (%p):")
    table = sweep_frame.pivot_table(index=str(Column.REBALANCE_INTERVAL),
                                    columns=str(Column.COST_BPS),
                                    values=str(Column.ADVANTAGE), aggfunc='median') * 100.0
    print(table.to_string(float_format=lambda value: f"{value:+.4f}"))
    turnover = free.groupby(str(Column.REBALANCE_INTERVAL))[str(Column.ANNUAL_TURNOVER)].median()
    print("\nmedian annual turnover by rebalancing interval (fraction of portfolio traded):")
    print(turnover.to_string(float_format=lambda value: f"{value:.4f}"))

    print("\nmedian CAGR advantage by AR(1) coefficient (%p):")
    by_phi = autocorr_frame.groupby(str(Column.PHI))[str(Column.ADVANTAGE)].median() * 100.0
    print(by_phi.to_string(float_format=lambda value: f"{value:+.4f}"))


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
                    "Measure the rebalancing bonus on lognormal assets: gross by volatility and "
                    "correlation, net of transaction cost by rebalancing frequency, and by return "
                    "autocorrelation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-v', '--version', action='version', version=f"{script_name} {__version__}")
    parser.add_argument('--output-folder', type=pathlib.Path, required=True,
                        help=f'root folder for every output; results land in <output-folder>/{OUTPUT_STEM}/')
    parser.add_argument('--annual-drift', type=float, default=DEFAULT_ANNUAL_DRIFT,
                        help='annual log drift of each asset')
    parser.add_argument('--annual-volatility', type=float, default=DEFAULT_ANNUAL_VOLATILITY,
                        help='annual volatility of each asset')
    parser.add_argument('--correlation', type=float, default=DEFAULT_CORRELATION,
                        help='correlation between the two assets')
    parser.add_argument('--stock-weight', type=float, default=DEFAULT_STOCK_WEIGHT,
                        help='target weight of the first asset')
    parser.add_argument('--steps-per-year', type=int, default=DEFAULT_STEPS_PER_YEAR,
                        help='simulation steps per year')
    parser.add_argument('--n-years', type=int, default=DEFAULT_N_YEARS,
                        help='length of each path in years')
    parser.add_argument('--n-paths', type=int, default=DEFAULT_N_PATHS,
                        help='number of Monte Carlo paths')
    parser.add_argument('--rebalance-intervals', type=int, nargs='+',
                        default=list(DEFAULT_REBALANCE_INTERVALS),
                        help='rebalancing intervals in steps')
    parser.add_argument('--cost-bps', type=float, nargs='+', default=list(DEFAULT_COST_BPS),
                        help='one-way transaction cost levels in basis points')
    parser.add_argument('--phi-grid', type=float, nargs='+', default=list(DEFAULT_PHI_GRID),
                        help='AR(1) coefficients of the autocorrelation sweep')
    parser.add_argument('--autocorr-interval', type=int, default=DEFAULT_REBALANCE_INTERVALS[2],
                        help='rebalancing interval used by the autocorrelation sweep')
    parser.add_argument('--autocorr-cost-bps', type=float, default=DEFAULT_COST_BPS[0],
                        help='transaction cost used by the autocorrelation sweep')
    parser.add_argument('--autocorr-normalization', choices=list(NORMALIZATIONS),
                        default=DEFAULT_NORMALIZATION,
                        help='what --annual-volatility fixes in the autocorrelation sweep: the '
                             'one-step volatility or the one-year volatility of the cumulative return')
    parser.add_argument('--sigma-grid', type=float, nargs='+', default=list(DEFAULT_SIGMA_GRID),
                        help='annual volatilities of the closed-form bonus grid')
    parser.add_argument('--rho-grid', type=float, nargs='+', default=list(DEFAULT_RHO_GRID),
                        help='correlations of the closed-form bonus grid')
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED,
                        help='seed of the random generator')

    args = parser.parse_args()
    parent = args.output_folder.parent if args.output_folder.parent != pathlib.Path('') else pathlib.Path('.')
    if not parent.is_dir():
        parser.error(f"--output-folder {args.output_folder} cannot be created: {parent} is not a folder.")
    if any(cost < 0.0 for cost in args.cost_bps) or args.autocorr_cost_bps < 0.0:
        parser.error("transaction cost in basis points must be non-negative.")
    if any(abs(phi) >= 1.0 for phi in args.phi_grid):
        parser.error(f"--phi-grid values must lie strictly inside (-1, 1); got {args.phi_grid}.")
    return args


if __name__ == '__main__':
    cli_args = parse_args()
    market_spec = MarketSpec(
        annual_drift=cli_args.annual_drift,
        annual_volatility=cli_args.annual_volatility,
        correlation=cli_args.correlation,
        stock_weight=cli_args.stock_weight,
        steps_per_year=cli_args.steps_per_year,
        n_years=cli_args.n_years,
        n_paths=cli_args.n_paths,
        seed=cli_args.seed,
    )
    result_folder = cli_args.output_folder / OUTPUT_STEM
    result_folder.mkdir(parents=True, exist_ok=True)

    bonus_df = build_bonus_grid(sigma_grid=tuple(cli_args.sigma_grid),
                                rho_grid=tuple(cli_args.rho_grid),
                                weight=market_spec.stock_weight)
    analyzer = RebalanceBonusAnalyzer(spec=market_spec)
    sweep_df = analyzer.sweep_frequency_and_cost(intervals=tuple(cli_args.rebalance_intervals),
                                                 cost_bps_grid=tuple(cli_args.cost_bps))
    autocorr_df = analyzer.sweep_autocorrelation(phi_grid=tuple(cli_args.phi_grid),
                                                 rebalance_interval=cli_args.autocorr_interval,
                                                 cost_bps=cli_args.autocorr_cost_bps,
                                                 normalization=cli_args.autocorr_normalization)

    bonus_df.to_csv(result_folder / 'bonus_grid.csv', index=False, float_format='%.8g')
    sweep_df.to_csv(result_folder / 'frequency_net_bonus.csv', index=False, float_format='%.8g')
    autocorr_df.to_csv(result_folder / 'autocorrelation_effect.csv', index=False, float_format='%.8g')

    plot_bonus_heatmap(bonus_frame=bonus_df, output_path=result_folder / 'bonus_heatmap.png')
    plot_frequency_net_bonus(sweep_frame=sweep_df,
                             output_path=result_folder / 'frequency_net_bonus.png')
    plot_autocorrelation_effect(autocorr_frame=autocorr_df,
                                output_path=result_folder / 'autocorrelation_effect.png')
    report_sweeps(spec=market_spec, sweep_frame=sweep_df, autocorr_frame=autocorr_df)
    print(f"\nwrote outputs to {result_folder}")
