"""
Wealth under a deterministic alternating price path.

A price rises by a fixed rate on odd days and falls by the same rate on even days, so the two-day
cycle returns the price to a level below where it started. This module tracks what a fixed fraction
of wealth staked on that path is worth over time, for several fractions at once, and reports the
closed-form multiplier that explains the result.

Changelog:
- 0.0.0 Initial release.
- 0.1.0 Accept a zero fraction, so the all-cash baseline can be drawn alongside the staked paths.
"""

__author__ = 'yRocket'
__version__ = "0.1.0.2026.8.30"

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

matplotlib.use('Agg')  # headless rendering; batch runs have no display server

__all__ = [
    'Column',
    'PathSpec',
    'AlternatingPath',
    'build_wealth_frame',
    'plot_paths',
    'parse_args',
]

OUTPUT_STEM = 'alternating'
FIGSIZE = (11.0, 4.5)
DPI = 300
PALETTE = tuple(TABLEAU_COLORS.values())
PRICE_COLOUR = 'tab:blue'
DEFAULT_UP_RATE = 0.10
DEFAULT_DOWN_RATE = 0.10
DEFAULT_N_DAYS = 100
DEFAULT_INITIAL_PRICE = 1.0
DEFAULT_INITIAL_WEALTH = 100.0
DEFAULT_FRACTIONS = (0.00, 0.25, 0.50, 0.75, 1.00)


class Column(enum.StrEnum):
    """Column names shared by the emitted frames and CSV files."""

    DAY = 'day'
    PRICE = 'price'
    FRACTION = 'fraction'
    WEALTH = 'wealth'
    CYCLE_MULTIPLIER = 'cycle_multiplier'
    FINAL_WEALTH = 'final_wealth'
    TOTAL_RETURN_PCT = 'total_return_pct'


@dataclass(frozen=True)
class PathSpec:
    """A deterministic price path that alternates one up day with one down day."""

    up_rate: float
    down_rate: float
    n_days: int
    initial_price: float
    initial_wealth: float

    def __post_init__(self) -> None:
        if self.up_rate <= 0.0:
            raise ValueError(f"up_rate must be positive; got {self.up_rate}.")
        if not 0.0 < self.down_rate < 1.0:
            raise ValueError(f"down_rate must lie in (0, 1); got {self.down_rate}.")
        if self.n_days <= 0:
            raise ValueError(f"n_days must be positive; got {self.n_days}.")
        if self.initial_price <= 0.0:
            raise ValueError(f"initial_price must be positive; got {self.initial_price}.")
        if self.initial_wealth <= 0.0:
            raise ValueError(f"initial_wealth must be positive; got {self.initial_wealth}.")

    @property
    def ruin_fraction(self) -> float:
        """Fraction at which one down day wipes out the whole stake."""
        return 1.0 / self.down_rate


class AlternatingPath:
    """The price path of a `PathSpec` and the wealth it produces at a given stake."""

    def __init__(self, spec: PathSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> PathSpec:
        return self._spec

    def daily_returns(self) -> np.ndarray:
        """Signed simple return of each day, up on odd days and down on even days."""
        days = np.arange(self._spec.n_days)
        return np.where(days % 2 == 0, self._spec.up_rate, -self._spec.down_rate)

    def prices(self) -> np.ndarray:
        """Price on day 0 through day `n_days`, so the array is one longer than the return array."""
        growth = np.concatenate(([1.0], np.cumprod(1.0 + self.daily_returns())))
        return self._spec.initial_price * growth

    def wealth(self, fraction: float) -> np.ndarray:
        """Wealth on day 0 through day `n_days` when `fraction` of it is staked every day.

        A fraction of 0 leaves everything in cash, so the path stays flat at the initial wealth.
        """
        if fraction < 0.0:
            raise ValueError(f"fraction must not be negative; got {fraction}.")
        if fraction >= self._spec.ruin_fraction:
            raise ValueError(
                f"fraction {fraction} reaches ruin on a down day; "
                f"it must stay below {self._spec.ruin_fraction}."
            )
        step = 1.0 + fraction * self.daily_returns()
        return self._spec.initial_wealth * np.concatenate(([1.0], np.cumprod(step)))

    def cycle_multiplier(self, fraction: float) -> float:
        """Closed-form wealth multiplier of one up day followed by one down day."""
        return (1.0 + fraction * self._spec.up_rate) * (1.0 - fraction * self._spec.down_rate)


def build_wealth_frame(path: AlternatingPath, fractions: tuple[float, ...]) -> pd.DataFrame:
    """Long-format frame of price and wealth by day, one block of rows per fraction."""
    if not fractions:
        raise ValueError("fractions must not be empty.")
    if len(set(fractions)) != len(fractions):
        raise ValueError(f"fractions must be distinct; got {fractions}.")

    prices = path.prices()
    days = np.arange(prices.size)
    blocks = [
        pd.DataFrame(
            {
                Column.DAY: days,
                Column.PRICE: prices,
                Column.FRACTION: fraction,
                Column.WEALTH: path.wealth(fraction),
            }
        )
        for fraction in fractions
    ]
    return pd.concat(blocks, ignore_index=True)


def plot_paths(frame: pd.DataFrame, output_path: pathlib.Path) -> None:
    """Draw the price path and the wealth path of every fraction side by side."""
    fig, (ax_price, ax_wealth) = plt.subplots(1, 2, figsize=FIGSIZE)

    first = frame[frame[Column.FRACTION] == frame[Column.FRACTION].iloc[0]]
    ax_price.plot(first[Column.DAY], first[Column.PRICE], color=PRICE_COLOUR, linewidth=1.2)
    ax_price.set_xlabel('Day')
    ax_price.set_ylabel('Price')
    ax_price.set_title('(a) Price path')
    ax_price.grid(alpha=0.3)

    for index, (fraction, block) in enumerate(frame.groupby(Column.FRACTION, sort=True)):
        ax_wealth.plot(
            block[Column.DAY],
            block[Column.WEALTH],
            color=PALETTE[index % len(PALETTE)],
            linewidth=1.4,
            label=f"f = {fraction:.2f}",
        )
    ax_wealth.set_xlabel('Day')
    ax_wealth.set_ylabel('Wealth')
    ax_wealth.set_title('(b) Wealth by bet fraction')
    ax_wealth.grid(alpha=0.3)
    ax_wealth.legend(loc='lower left')

    fig.tight_layout()
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    """Read the command line, printing name and version when no option is given."""
    script_name = pathlib.Path(__file__).name
    if len(sys.argv) == 1:
        print(f"{script_name} {__version__}")
        print(f"\nRun `{script_name} --help` for the full option list.\n")
        sys.exit(0)

    parser = argparse.ArgumentParser(
        prog=script_name,
        description=f"{script_name} {__version__}\n\n"
                    "Trace wealth under a price path that alternates one up day with one down day, "
                    "for several fixed bet fractions at once.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-v', '--version', action='version', version=f"{script_name} {__version__}")
    parser.add_argument('--output-folder', type=pathlib.Path, required=True,
                        help=f'root folder for every output; results land in <output-folder>/{OUTPUT_STEM}/')
    parser.add_argument('--up-rate', type=float, default=DEFAULT_UP_RATE,
                        help='simple return of an up day')
    parser.add_argument('--down-rate', type=float, default=DEFAULT_DOWN_RATE,
                        help='size of the simple loss of a down day')
    parser.add_argument('--n-days', type=int, default=DEFAULT_N_DAYS,
                        help='length of the price path in days')
    parser.add_argument('--initial-price', type=float, default=DEFAULT_INITIAL_PRICE,
                        help='stock price on day 0')
    parser.add_argument('--initial-wealth', type=float, default=DEFAULT_INITIAL_WEALTH,
                        help='wealth on day 0')
    parser.add_argument('--fractions', type=float, nargs='+', default=list(DEFAULT_FRACTIONS),
                        help='bet fractions traced on the wealth panel; 0 draws the all-cash baseline')

    args = parser.parse_args()
    parent = args.output_folder.parent if args.output_folder.parent != pathlib.Path('') else pathlib.Path('.')
    if not parent.is_dir():
        parser.error(f"--output-folder {args.output_folder} cannot be created: {parent} is not a folder.")
    ruin_fraction = 1.0 / args.down_rate if args.down_rate > 0.0 else float('inf')
    out_of_range = [f for f in args.fractions if f < 0.0 or f >= ruin_fraction]
    if out_of_range:
        parser.error(f"--fractions {out_of_range} fall outside [0, {ruin_fraction}), the ruin fraction.")
    return args


def main() -> int:
    args = parse_args()

    spec = PathSpec(
        up_rate=args.up_rate,
        down_rate=args.down_rate,
        n_days=args.n_days,
        initial_price=args.initial_price,
        initial_wealth=args.initial_wealth,
    )
    path = AlternatingPath(spec)
    fractions = tuple(args.fractions)
    frame = build_wealth_frame(path, fractions)

    output_folder = args.output_folder / OUTPUT_STEM
    output_folder.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_folder / 'wealth_paths.csv', index=False)
    plot_paths(frame, output_folder / 'wealth_paths.png')

    summary = pd.DataFrame(
        {
            Column.FRACTION: fractions,
            Column.CYCLE_MULTIPLIER: [path.cycle_multiplier(f) for f in fractions],
            Column.FINAL_WEALTH: [path.wealth(f)[-1] for f in fractions],
            Column.TOTAL_RETURN_PCT: [
                100.0 * (path.wealth(f)[-1] / spec.initial_wealth - 1.0) for f in fractions
            ],
        }
    )
    summary.to_csv(output_folder / 'summary.csv', index=False)

    print(f"price on day {spec.n_days}: {path.prices()[-1]:.6f}")
    print(f"full cycles: {spec.n_days // 2}")
    print(summary.to_string(index=False, float_format=lambda v: f"{v:.6f}"))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
