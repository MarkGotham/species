#!/usr/bin/env python3
"""
Compare two music21-readable files by their written notes and rests.

Install: python -m pip install music21
Usage: python match_check.py a.mxl b.krn
Options: --ties --slurs --dynamics --bar-numbers
Exit codes: 0 same, 1 different, 2 parsing/comparison error.

Default:
- onset, duration for notes and rests;
- also pitch for notes only.

Ignored/untested:
- chord-versus-voice encoding (chords are split into individual notes and checked as such),
- part/voice assignment,
- metadata,
- layout,
- clefs,
- keys,
- meter and tempo.

Enharmonic spellings match unless --pitch-spelling is supplied.

Duplicate notes/rests count.

Times are quarter-note units (rounded).

Note the focys on written notation:
- ties are not merged,
- repeats are not expanded, and
- transposing instruments are not converted to concert pitch.

Explicit rests must be present in both files.

Optional checks compare only elements represented by each format's music21 importer;
(they cannot recover unsupported annotations).

Slurs compare all recorded anchors, not engraving.
Dynamics checks include hairpins.
Bar numbers include suffixes and measure positions.

Multi-work Opus files are rejected; select one work.

By: Mark Gotham
Repo: https://github.com/MarkGotham/species/
Licence: MIT

"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys

from music21 import chord, converter, dynamics, harmony, note, spanner, stream


def _number(value, dps: int = 9):
    """
    Absorb tiny importer rounding differences without altering rhythm.
    Set `dps` for the number of decimal places (deafult 9)
    """
    return round(float(value), dps)


def signature(score, *, ties=False, slurs=False, dynamics_check=False,
              bar_numbers=False, pitch_spelling=False):
    """Return a Counter of canonical events for an already parsed Stream."""
    if isinstance(score, stream.Opus):
        raise ValueError('Opus contains multiple works; select a single work first')
    result = Counter()

    def onset(element):
        return _number(element.getOffsetInHierarchy(score))

    def pitch_key(pitch):
        return pitch.nameWithOctave if pitch_spelling else _number(pitch.ps)

    def anchors(element):
        start = onset(element)
        length = _number(element.duration.quarterLength)

        if isinstance(element, note.Rest):
            return ((start, 'rest', length),)
        if isinstance(element, note.Note):
            return ((start, 'note', pitch_key(element.pitch), length),)
        if isinstance(element, chord.Chord) and not isinstance(element, harmony.Harmony):
            return tuple(sorted((start, 'note', pitch_key(n.pitch), length)
                                for n in element.notes))
        raise ValueError(f'Unsupported note/slur anchor: {type(element).__name__}')

    for element in score.recurse().notesAndRests:
        # ChordSymbol/FiguredBass are annotations, not sounding note events.
        if isinstance(element, harmony.Harmony):
            continue
        keys = anchors(element)
        members = element.notes if isinstance(element, chord.Chord) else (element,)
        # Use individual members here because chord tones can have different ties.
        for member in members:
            if isinstance(element, chord.Chord):
                key = (
                    'onset ' + str(onset(element)),
                    'note',
                    'pitch ' + pitch_key(member.pitch),
                    _number(element.duration.quarterLength),
                    'measure ' + member.measureNumber
                )
            else:
                key = keys[0]
            if ties:
                key += ('tie', member.tie.type if member.tie else None)
            result[('event',) + key] += 1

    if slurs or dynamics_check:
        for item in score.spannerBundle:
            if slurs and isinstance(item, spanner.Slur):
                result[('slur', tuple(anchors(e) for e in item.getSpannedElements()))] += 1
            if dynamics_check and isinstance(item, dynamics.DynamicWedge):
                endpoints = tuple(onset(e) for e in item.getSpannedElements())
                result[('hairpin', type(item).__name__, endpoints)] += 1
    if dynamics_check:
        for item in score.recurse().getElementsByClass(dynamics.Dynamic):
            result[('dynamic', onset(item), item.value)] += 1
    if bar_numbers:
        for item in score.recurse().getElementsByClass(stream.Measure):
            result[('measure', onset(item), str(item.number), item.numberSuffix or '')] += 1
    return result


def compare_files(first, second, **options):
    """Return (same, only_in_first, only_in_second), with Counter differences."""
    # Force parsing so music21's cache cannot mask edits to an input file.
    left = signature(converter.parse(str(first), forceSource=True), **options)
    right = signature(converter.parse(str(second), forceSource=True), **options)
    return left == right, left - right, right - left


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('first', type=Path)
    parser.add_argument('second', type=Path)
    parser.add_argument('--ties', action='store_true')
    parser.add_argument('--slurs', action='store_true')
    parser.add_argument('--dynamics', dest='dynamics_check', action='store_true')
    parser.add_argument('--bar-numbers', action='store_true')
    parser.add_argument('--pitch-spelling', action='store_true',
                        help='distinguish enharmonic spellings such as C# and D-flat')
    parser.add_argument('--max-differences', type=int, default=10)
    args = parser.parse_args(argv)
    if args.max_differences < 0:
        parser.error('--max-differences must be nonnegative')
    for path in (args.first, args.second):
        if not path.is_file():
            parser.error(f'not a file: {path}')
    options = {name: getattr(args, name) for name in
               ('ties', 'slurs', 'dynamics_check', 'bar_numbers', 'pitch_spelling')}
    try:
        same, left, right = compare_files(args.first, args.second, **options)
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2
    print('SAME' if same else 'DIFFERENT')
    if not same:
        for path, difference in ((args.first, left), (args.second, right)):
            print(f'Only in {path}: {sum(difference.values())} event(s)')
            for key, count in sorted(difference.items(), key=lambda x: repr(x[0]))[:args.max_differences]:
                print(f'  {count} x {key}')
            if len(difference) > args.max_differences:
                print(f'  ... {len(difference) - args.max_differences} more distinct event(s)')
    return 0 if same else 1


if __name__ == '__main__':
    sys.exit(main())
