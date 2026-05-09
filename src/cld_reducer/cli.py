"""Command-line interface for cld-reducer."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .api import reduce_letters


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="cld-reduce",
        description="Reduce compact letter displays from pairwise post-hoc results.",
    )
    parser.add_argument("pairs", type=Path, help="CSV with pairwise post-hoc comparisons")
    parser.add_argument("--means", type=Path, help="Optional CSV with group and mean columns")
    parser.add_argument("--out", type=Path, required=True, help="Output CSV path")
    parser.add_argument("--group1", default="group1", help="First group column")
    parser.add_argument("--group2", default="group2", help="Second group column")
    parser.add_argument("--significant", default="significant", help="Significance column")
    parser.add_argument(
        "--method",
        default="assignment_minimum",
        choices=["assignment_minimum", "assignment-minimum"],
        help="Reduction method",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    args = build_parser().parse_args(argv)
    pairs = pd.read_csv(args.pairs)
    means = pd.read_csv(args.means) if args.means else None
    result = reduce_letters(
        pairs,
        means,
        method=args.method,
        group1=args.group1,
        group2=args.group2,
        significant=args.significant,
    )
    frame = result.to_frame()
    for key, value in result.stats.items():
        if isinstance(value, int | float | str | bool):
            frame[f"stat_{key}"] = value
    args.out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.out, index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
