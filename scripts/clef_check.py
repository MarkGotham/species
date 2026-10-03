#!/usr/bin/env python3
"""
clef_check.py

Analyse all parts in all score files
to establish the most suitable clef for each,
bringing the musical range of the source in line with that of the clef.

The user provides a set of candidate clefs.
The script considers these and
each clef is scored against all pitches in a part using three criteria, in this order:

    1. Total number of actual ledger lines required.
    2. Worst ledger-line excursion for any individual note.
    3. Total diatonic distance of notes outside the five-line staff.

The third criterion distinguishes, for example,
a note in the space immediately above the staff
from one on the staff.
Neither uses a ledger line,
but the latter is marginally preferable
when the first two criteria are otherwise equal.

Scores are tuples and are compared lexicographically.
This deliberately avoids arbitrary weighting:
reducing actual ledger lines is always more important than the secondary criteria.

Only parts for which one of the allowed clefs has a strictly better score
than the current clef are reported. At the end, the total number of cases
requiring review is printed.

Usage:

```
python clef_check.py ./I -e krn --clefs treble treble8vb bass
```

This specifies:
- the part I source files
- in krn format
- checking against treble, treble8vb, bass
(the only ones that are generally common today)

The default is set for that specific configuration, so it's equivalent to simply:

```
python clef_check.py
```

"""

import argparse
import sys
from pathlib import Path

from music21 import converter, clef


CLEFS = {
    "treble": clef.TrebleClef,
    "treble8vb": clef.Treble8vbClef,
    "bass": clef.BassClef,
    "alto": clef.AltoClef,
    "tenor": clef.TenorClef,
    "soprano": clef.SopranoClef,
}

DEFAULT_CLEFS = [
    "treble",
    "treble8vb",
    "bass",
]


def staff_position(p, c):
    """
    Return the diatonic position of a pitch relative to the bottom staff line.

    Positions on a conventional five-line staff are:

        0   bottom line
        1   first space
        2   second line
        ...
        8   top line

    Negative values are below the staff; values greater than 8 are above it.
    """
    return p.diatonicNoteNum - c.lowestLine


def ledger_lines(p, c):
    """
    Return the number of actual ledger lines required for a pitch.

    The spaces immediately above and below the staff require no ledger line.

    Thus, above a treble staff:

        F5  -> 0
        G5  -> 0
        A5  -> 1
        B5  -> 1
        C6  -> 2

    and the equivalent behaviour applies below the staff.
    """
    pos = staff_position(p, c)

    if pos < 0:
        return (-pos) // 2

    if pos > 8:
        return (pos - 8) // 2

    return 0


def outside_staff_distance(p, c):
    """
    Return the diatonic distance by which a pitch lies outside the staff.

    A pitch on the staff has distance 0. The space immediately outside the
    staff has distance 1, the first ledger line distance 2, and so on.

    This is used only as a tie-breaker after actual ledger-line usage.
    """
    pos = staff_position(p, c)

    if pos < 0:
        return -pos

    if pos > 8:
        return pos - 8

    return 0


def clef_score(pitches, c):
    """
    Prepare a "score" for a sequence of pitches and a clef.

    Tuple ordering relates to the criteria priority (see top of module):
        1. total ledger lines
        2. worst individual ledger-line excursion
        3. total distance outside the staff

    Clearly, lower scores are better.
    """
    ledgers = [ledger_lines(p, c) for p in pitches]
    outside = [outside_staff_distance(p, c) for p in pitches]

    return (
        sum(ledgers),
        max(ledgers, default=0),
        sum(outside),
    )


def clef_name(c):
    """
    Return our command-line name for a music21 Clef object.
    Exact type comparison matters here:
    "Treble8vbClef" is a subclass of TrebleClef
    and must not be reported simply as "treble".
    """
    for name, cls in CLEFS.items():
        if type(c) is cls:
            return name

    return c.__class__.__name__


def analyse_part(filename, part, allowed_clefs):
    # Notes only for now; chord pitches are not included.
    pitches = [
        n.pitch
        for n in part.recurse().notes
        if n.isNote
    ]

    if not pitches:
        return 0

    clefs_found = list(part.recurse().getElementsByClass(clef.Clef))

    if not clefs_found:
        return 0

    current = clefs_found[0]

    # Exact type comparison. See `clef_name`
    allowed_types = {CLEFS[name] for name in allowed_clefs}
    unapproved = sorted({
        clef_name(c) for c in clefs_found
        if type(c) not in allowed_types
    })

    candidates = [CLEFS[name]() for name in allowed_clefs]

    current_score = clef_score(pitches, current)

    best = min(candidates, key=lambda c: clef_score(pitches, c))
    best_score = clef_score(pitches, best)

    better = best_score < current_score

    if not better and not unapproved:
        return 0

    reasons = []
    if unapproved:
        reasons.append(f"clef not allowed: {', '.join(unapproved)}")
    if better:
        reasons.append("fewer ledger lines")

    part_name = (
        part.partName
        or part.partAbbreviation
        or part.id
        or "Unknown part"
    )

    low = min(pitches, key=lambda p: p.ps)
    high = max(pitches, key=lambda p: p.ps)

    print(
        f"{filename} | "
        f"{part_name} | "
        f"range {low.nameWithOctave}-{high.nameWithOctave} | "
        f"{clef_name(current)} -> {clef_name(best)} | "
        f"score {current_score} -> {best_score} | "
        f"{'; '.join(reasons)}"
    )

    return 1


def analyse_file(path, allowed_clefs):
    try:
        score = converter.parse(path)
    except Exception as exc:
        print(f"ERROR | {path} | {exc}")
        return 0

    return sum(
        analyse_part(path, part, allowed_clefs)
        for part in score.parts
    )

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check score parts and suggest clefs that reduce ledger-line usage."
    )
    parser.add_argument(
        "directory", nargs="?", type=Path, default=Path("./I"),
        help="Score directory (default: %(default)s)",
    )
    parser.add_argument(
        "-e", "--extension", default="krn",
        help="File extension (default: %(default)s)",
    )
    parser.add_argument(
        "-c", "--clefs", nargs="+", choices=sorted(CLEFS), metavar="CLEF",
        default=DEFAULT_CLEFS,
        help=f"Allowed clefs (default: {' '.join(DEFAULT_CLEFS)})",
    )
    parser.add_argument(
        "-r", "--recursive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Search subdirectories recursively (default: %(default)s)",
    )
    return parser

def find_files(directory: Path, extension: str, recursive: bool) -> list[Path]:
    pattern = f"*.{extension.lstrip('.')}"
    files = directory.rglob(pattern) if recursive else directory.glob(pattern)
    return sorted(files)

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.directory.is_dir():
        parser.error(f"directory not found: {args.directory}")

    files = find_files(args.directory, args.extension, args.recursive)
    if not files:
        print(f"warning: no *.{args.extension.lstrip('.')} files in {args.directory}",
              file=sys.stderr)

    case_count = 0
    for path in files:
        try:
            case_count += analyse_file(path, args.clefs)
        except Exception as exc:
            print(f"warning: skipping {path}: {exc}", file=sys.stderr)

    print(f"\n{case_count} case{'s' if case_count != 1 else ''} to review "
          f"({len(files)} file{'s' if len(files) != 1 else ''} scanned).")
    return 1 if case_count else 0

if __name__ == "__main__":
    raise SystemExit(main())
