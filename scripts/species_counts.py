#!/usr/bin/env python3
"""
Prepare and print markdown count tables from I/II/III species JSON metadata
for use in the README.

Usage: python3 species_counts.py /path/to/species > counts.md

Uses only Python's standard library.
Read-only (reads files without changing them).
Each JSON file counts as one exercise.
Part and species come from its folders;
only `modal_final` is actually read from the JSON data due to some ambiguity wrt combined species.
The .json metadata has no pitches, so melody/octave variants are not reported.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys


PARTS = ("I", "II", "III")
FINALS = ("D", "E", "F", "G", "A", "C")


def table(headers, rows):
    lines = ["| " + " | ".join(map(str, headers)) + " |",
             "| " + " | ".join(["---"] * len(headers)) + " |"]
    lines.extend("| " + " | ".join(map(str, row)) + " |" for row in rows)
    return "\n".join(lines)


def make_tables(root):
    species_counts = {part: Counter() for part in PARTS}
    final_counts = {part: Counter() for part in PARTS}
    totals = Counter()
    for part in PARTS:
        for path in sorted((root / part).glob("sp*/gap_*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if path.parent.name not in {f"sp{s}" for s in range(1, 6)}:
                    raise ValueError("species folder must be sp1–sp5")
                species = int(path.parent.name[2:])
                final = data["modal_final"].upper()
                if final not in FINALS:
                    raise ValueError(f"unexpected modal final: {final!r}")
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                raise ValueError(f"{path}: {exc}") from exc
            species_counts[part][species] += 1
            final_counts[part][final] += 1
            totals[part] += 1

    if not sum(totals.values()):
        raise ValueError(f"No metadata found under {root} (sp*/gap_*.json)")

    species_rows = [[p, *[species_counts[p][s] for s in range(1, 6)], totals[p]]
                    for p in PARTS]
    species_rows.append(["Total", *[sum(species_counts[p][s] for p in PARTS)
                                   for s in range(1, 6)], sum(totals.values())])
    final_rows = [[f, *[final_counts[p][f] for p in PARTS],
                   sum(final_counts[p][f] for p in PARTS)] for f in FINALS]
    final_rows.append(["Total", *[totals[p] for p in PARTS], sum(totals.values())])
    result = "## Counts by species\n\n" + table(
        ["Part", *[f"Species {s}" for s in range(1, 6)], "Total exercises"], species_rows)
    result += "\n\n## Counts by modal final\n\n" + table(
        ["Modal final", *[f"Part {p} ({totals[p]})" for p in PARTS], "Total"], final_rows)
    return result + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(".."),
                        help="repository root (default: current directory)")
    args = parser.parse_args()
    try:
        print(make_tables(args.root), end="")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
