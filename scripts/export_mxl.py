#!/usr/bin/env python3
"""
Export adjacent kern/JSON pairs to MusicXML
and combine into aggregate documents by species and/or book.

Usage:
python scripts/export_mxl.py ROOT [OUT_DIR]

Options:
--scheme modern original
--bars-per-system [S=]N ...
--only ID ...
--no-verify

ROOT contains corpus.json and I/sp1 ... III/sp5.
I, II and III contain two-, three- and four-voice exercises respectively.
Each .krn has an adjacent .json file (same-stem).
Directories identify book sections.

Outputs default to ROOT, or mirror that directory structure under a newly specified OUT_DIR:
    I/sp1/gap_005.mxl        individual exercise, modern-clef score (default)
    I/sp1/ex1sp1.mxl         all exercises in this section (part 1, species 1)
    I/ex1.mxl                all exercises in this part (part 1, all species)
    I/ex1_exercise.mxl       same whole-part file with only each cantus firmus (other parts blank for student)

Original-clef exports use .original.mxl instead of .mxl.
(Both schemes coexist.)

Whole-part exports also produce exercises
(`ex1_exercise.mxl`, ex2_exercise.mxl and ex3_exercise.mxl according to the parts present),
using the `utils.py` file.
Each exercise keeps the 1-based top-to-bottom `cantus_firmus.part` information from JSON;
other staves contain invisible rests, with pitches and note markings removed.
Clefs, labels, measure numbers, barlines and system breaks are preserved.
TODO This works well for species 1-3, review the handling of 4 and 5 wrt specific note durations.

No student copies are made for individuals or species sections,
but this could be added as needed.
Each selected clef scheme gets its own student copy,
e.g., `ex1_exercise.original.mxl`.

Original clefs come from the JSON clefs list (top voice first).
Modern exports use explicit `clefs.modern` when supplied
(based on a former version of this, TODO I'll probably remove this soon),
otherwise retain modern score clefs from the krn scores and convert any historical clefs found:
C1-C3 -> G2, C4 -> Gv2, C5/F -> F4.
(That said there shouldn't be any in the krn files: see `clef_check`).

Pitches are never transposed in any case (original or modern).
Original clef metadata supplies the opening clefs;
subsequent canonical clef changes are preserved.
If the canonical score has changes but a different opening clef,
original export is rejected because opening-only info
cannot specify the original change sequence.

`corpus.json` supplies composer, `opr_prefix` and `licences.statement`.
Each exercise starts a new system, with balanced systems of at most the
configured number of bars. Measures restart at 1 for each exercise.
Combined exercises end with double barlines; the last has a final barline.

Verification checks:
pitches, durations, ties, positions within measures, layout, labels, barlines and clefs.
Writes are atomic: a failed export leaves any prior file untouched.
`exports.json` records this run,
including failed or blocked outputs and whether an older file remains.

`--only` writes `exports.partial.json` instead.
A group is blocked if any member fails.
Exit status is 1 for any failed/skipped export; other exercises still run.

By: Mark Gotham
Repo: https://github.com/MarkGotham/species/
Licence: MIT
"""
import argparse
import copy
import json
import math
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from pathlib import Path

from music21 import bar, clef, converter, expressions, key, layout, meter, metadata, stream

from utils import write_exercise_mxl


PARTS = {"I": (1, 2), "II": (2, 3), "III": (3, 4)}
TOKEN_RE = re.compile(r"([CFG])(v|\^)?([1-5])\Z")
CUT_TIME = "*met(c|)"      # cut common time symbol (krn has is as a separate line after *M2/2)


# Bars per system, by species in relation to density.
# Experiment, or override on the command line,
# e.g. `--bars-per-system 1=6 2=5` or `--bars-per-system 4` (applied to all species)
BARS_PER_SYSTEM = {1: 6, 2: 5, 3: 4, 4: 4, 5: 4}


class ExportError(Exception):
    pass


class Skip(Exception):
    pass


# ---  small helpers

def fig_id(meta):
    f = meta["figure"]
    return f"{f['number']}{f.get('suffix', '')}" if f["number"] is not None else meta["id"]


def fig_text(meta):
    f = meta["figure"]
    label = f"Fig. {fig_id(meta)}" if f["number"] is not None else meta["id"]
    return label + (f" ({f['note']})" if f.get("note") else "")


def sort_key(meta):
    f = meta["figure"]
    return (meta["voices"], f["number"] is None, f["number"] or 0,
            f.get("suffix", ""), meta["id"])


def display_composer(text):
    last, sep, first = text.partition(", ")
    return f"{first} {last}" if sep else text


def bars_for(meta, table):
    """Mixed-species exercises (e.g. [2, 3]) take the tightest setting among their species."""
    return min(table[s] for s in meta["species"])


def system_sizes(n, per):
    """Balanced systems of at most `per` bars: n=11, per=4 -> [4, 4, 3]."""
    k = max(1, math.ceil(n / per))
    base, extra = divmod(n, k)
    return [base + (1 if i < extra else 0) for i in range(k)]


def system_starts(n, per):
    starts, pos = [], 0
    for size in system_sizes(n, per):
        starts.append(pos)
        pos += size
    return starts


def token_tuple(token):
    """Kern clef token -> (sign, line, octave change), only used to check what was written."""
    m = TOKEN_RE.match(token)
    if not m:
        raise ExportError(f"invalid clef token {token!r}")
    return m.group(1), int(m.group(3)), {"v": -1, "^": 1, None: 0}[m.group(2)]


def signature(parts):
    """Per part and measure: offsets, durations, pitches and tie states."""
    result = []
    for part in parts:
        measures = []
        for measure in part.getElementsByClass(stream.Measure):
            events = []
            for el in measure.recurse().notesAndRests:
                pitches = tuple((n.pitch.nameWithOctave, n.tie.type if n.tie else None)
                                for n in (el.notes if el.isChord else [el])) if not el.isRest else ()
                events.append((str(el.getOffsetInHierarchy(measure)), str(el.quarterLength), pitches))
            measures.append(events)
        result.append(measures)
    return result

def canonical_opr(meta, prefix):
    """The !!!OPR value, generated from the JSON fields. Must reproduce the old on-score label."""
    fig = fig_text(meta)
    species = ",".join(str(x) for x in meta["species"])
    return (f"{prefix}; {fig}; Species: {species}; Modal final: {meta['modal_final']}; "
            f"Cantus firmus: {meta['cantus_firmus']['raw']}")

# ---  parse + prepare

def metadata_clefs(meta, scheme):
    value = meta.get("clefs")
    tokens = value.get(scheme) if isinstance(value, dict) else value if scheme == "original" else None
    if tokens is None or tokens == [] or (isinstance(tokens, list) and not any(tokens)):
        return None
    if not isinstance(tokens, list) or len(tokens) != meta["voices"]:
        raise ExportError(f"clefs for {scheme} must contain {meta['voices']} tokens")
    if not all(isinstance(t, str) and TOKEN_RE.fullmatch(t) for t in tokens):
        raise ExportError(f"invalid or incomplete {scheme} clefs: {tokens!r}")
    return tokens


def clef_tuple(obj):
    return obj.sign, obj.line, obj.octaveChange


def make_clef(token):
    sign, line, octave = token_tuple(token)
    return clef.clefFromString(f"{sign}{line}", octaveShift=octave)


def modern_clef(obj):
    """
    Map any no-longer-standard clefs to modern form.
    Should be redundant: all krn files should be in modern clefs.
    %TODO probably remove.
    """
    if obj.sign == "C":
        return make_clef("G2" if obj.line <= 3 else "Gv2" if obj.line == 4 else "F4")
    if obj.sign == "F":
        return make_clef("F4")
    if obj.sign == "G":
        return make_clef("Gv2" if obj.octaveChange == -1 else "G2")
    raise ExportError(f"cannot modernize clef {obj!r}")


def load_parts(kern_path, meta, scheme):
    text = kern_path.read_text(encoding="utf-8")
    tokens = metadata_clefs(meta, scheme)
    if scheme == "original" and tokens is None:
        raise Skip("original clefs are not provided in JSON")
    score = converter.parseData(text, format="humdrum")
    parts = list(score.parts)
    if len(parts) != meta["voices"]:
        raise ExportError(f"music21 found {len(parts)} parts, JSON says {meta['voices']}")
    part_line = next((line for line in text.splitlines() if line.startswith("*part")), None)
    if part_line is None:
        raise ExportError("kern has no *part row to identify top-to-bottom voices")
    try:
        numbers = [int(t.removeprefix("*part")) for t in part_line.split("\t")]
    except ValueError as exc:
        raise ExportError("invalid *part row") from exc
    if sorted(numbers) != list(range(1, meta["voices"] + 1)):
        raise ExportError("*part row must identify each voice exactly once")
    order = {f"spine_{i}": number for i, number in enumerate(numbers)}
    if any(p.id not in order for p in parts):
        raise ExportError("cannot associate parsed parts with kern spines")
    parts.sort(key=lambda p: order[p.id])
    for pi, part in enumerate(parts):
        ms = list(part.getElementsByClass(stream.Measure))
        if not ms:
            raise ExportError(f"part {pi + 1} has no measures")
        old = list(part.recurse().getElementsByClass(clef.Clef))
        if not old:
            raise ExportError(f"part {pi + 1} has no clef")
        if scheme == "original":
            target = make_clef(tokens[pi])
            if clef_tuple(target) != clef_tuple(old[0]):
                if any(clef_tuple(c) != clef_tuple(old[0]) for c in old[1:]):
                    raise ExportError("original opening differs from a score with clef changes; "
                                      "the original clef sequence is needed")
                # Repeated source-system declarations must not switch the
                # selected original clef back to the canonical display clef.
                for obj in old:
                    obj.activeSite.replace(obj, make_clef(tokens[pi]))
        else:
            for obj in old:
                replacement = make_clef(tokens[pi]) if tokens else modern_clef(obj)
                obj.activeSite.replace(obj, replacement)
    cut = CUT_TIME in text
    if cut:  # note: music21's Humdrum parser reads *M2/2 but ignores *met(c|), so re-entere as here
        for p in parts:
            for ts in p.recurse().getElementsByClass(meter.TimeSignature):
                if ts.ratioString == "2/2":
                    ts.symbol = "cut"
    return parts, cut


def describe_first(m):
    ts = m.getElementsByClass(meter.TimeSignature).first()
    ks = m.getElementsByClass(key.KeySignature).first()
    cl = m.getElementsByClass(clef.Clef).first()
    return {"ts": (ts.ratioString, ts.symbol) if ts else None,
            "ks": ks.sharps if ks else None,
            "clef": (cl.sign, cl.line, cl.octaveChange) if cl else None}


def describe_last(measures, initial):
    state = dict(initial)
    for m in measures:
        for obj in m.recurse():
            if isinstance(obj, meter.TimeSignature):
                state["ts"] = (obj.ratioString, obj.symbol)
            elif isinstance(obj, key.KeySignature):
                state["ks"] = obj.sharps
            elif isinstance(obj, clef.Clef):
                state["clef"] = clef_tuple(obj)
    return state


def clef_events(measures):
    return [[(str(obj.getOffsetInHierarchy(m)), clef_tuple(obj))
             for obj in m.recurse().getElementsByClass(clef.Clef)] for m in measures]


def prepare(parts, meta, corpus, table, cut=False):
    n = meta["measures"]
    starts = system_starts(n, bars_for(meta, table))
    prefix = corpus["opr_prefix"]
    label = canonical_opr(meta, prefix)[len(prefix) + 2:]  # "Fig. 5; Species: 1; Modal final: d; ..."
    measures, ctx, end_ctx, clefs = [], [], [], []
    for pi, part in enumerate(parts):
        ms = list(part.getElementsByClass(stream.Measure))
        if len(ms) != n:
            raise ExportError(f"part {pi + 1} has {len(ms)} measures, JSON says {n}")
        for j, m in enumerate(ms):
            m.number = j + 1
            # Replace any source system breaks with the selected export layout.
            # TODO may be inconsistent. Remove system breaks there, or encode throughout.
            m.removeByClass(layout.SystemLayout)
            if j in starts:
                m.insert(0, layout.SystemLayout(isNew=True))
        if pi == 0:
            te = expressions.TextExpression(label)
            te.placement = "above"
            ms[0].insert(0, te)
        measures.append(ms)
        ctx.append(describe_first(ms[0]))
        end_ctx.append(describe_last(ms, ctx[-1]))
        clefs.append(clef_events(ms))
    return {"meta": meta, "measures": measures, "ctx": ctx, "starts": starts, "cut": cut,
            "end_ctx": end_ctx, "clef_events": clefs,
            "label": label, "sig": signature(parts)}


# ---  build

def drop_redundant(m, now, prev):
    for cls, k in ((meter.TimeSignature, "ts"), (key.KeySignature, "ks"), (clef.Clef, "clef")):
        if now[k] is not None and now[k] == prev[k]:
            for obj in list(m.getElementsByClass(cls)):
                if obj.offset == 0:
                    m.remove(obj)


def build_score(items, title, corpus):
    nv = items[0]["meta"]["voices"]
    parts = [stream.Part() for _ in range(nv)]
    for i, it in enumerate(items):
        last = i == len(items) - 1
        for pi in range(nv):
            ms = [copy.deepcopy(m) for m in it["measures"][pi]]  # items are reused for the set
            ms[-1].rightBarline = bar.Barline("final" if last else "double")
            if i:
                previous = items[i - 1]
                drop_redundant(ms[0], it["ctx"][pi],
                               previous.get("end_ctx", previous["ctx"])[pi])
            for m in ms:
                parts[pi].append(m)
    score = stream.Score()
    for p in parts:
        score.insert(0, p)
    if nv > 1:
        score.insert(0, layout.StaffGroup(parts, symbol="bracket", barTogether=True))
    md = metadata.Metadata()
    md.title = title
    md.composer = display_composer(corpus["composer"])
    md.copyright = corpus["licence"]["statement"]
    score.metadata = md
    return score


# ---  verify
def read_xml(path):
    with zipfile.ZipFile(path) as z:
        container = ET.fromstring(z.read("META-INF/container.xml"))
        root_path = container.find(".//{*}rootfile").get("full-path")
        return ET.fromstring(z.read(root_path))


def effective_clef_events(events):
    """Discard repeated clef declarations while preserving actual changes."""
    result, current = [], None
    for measure_index, changes in enumerate(events):
        for offset, value in changes:
            if value != current:
                result.append((measure_index, offset, value))
                current = value
    return result


def verify_mxl(path, items, scheme):
    """
    Read the file back. Returns a list of problems (empty = fine).
    TODO review overlap with match_check.py
    """
    problems = []
    nv = items[0]["meta"]["voices"]

    # note: music21 against what we put in
    back = converter.parse(str(path), forceSource=True)
    want = [sum((it["sig"][pi] for it in items), []) for pi in range(nv)]
    if signature(back.parts) != want:
        problems.append("pitches, durations, ties or note positions differ after write/read round trip")
    if len(back.parts) == nv:
        for pi, part in enumerate(back.parts):
            expected = sum((it["clef_events"][pi] for it in items), [])
            actual = clef_events(list(part.getElementsByClass(stream.Measure)))
            if effective_clef_events(actual) != effective_clef_events(expected):
                problems.append(f"part {pi + 1}: clef changes differ after write/read round trip")

    # layout etc.: from the XML that MuseScore will see
    root = read_xml(path)
    parts = root.findall("part")
    if len(parts) != nv:
        return problems + [f"{len(parts)} parts in file, expected {nv}"]

    total = sum(it["meta"]["measures"] for it in items)
    exp_numbers, exp_breaks, exp_bars, labels = [], set(), {}, [it["label"] for it in items]
    offset = 0
    for i, it in enumerate(items):
        n = it["meta"]["measures"]
        exp_numbers += range(1, n + 1)
        exp_breaks |= {offset + s for s in it["starts"]}
        exp_bars[offset + n - 1] = "light-heavy" if i == len(items) - 1 else "light-light"
        offset += n

    for pi, p in enumerate(parts):
        ms = p.findall("measure")
        tag = f"part {pi + 1}"
        if len(ms) != total:
            problems.append(f"{tag}: {len(ms)} measures, expected {total}")
            continue
        if [int(m.get("number")) for m in ms] != exp_numbers:
            problems.append(f"{tag}: measure numbers are not 1..N per exercise")
        breaks = {j for j, m in enumerate(ms)
                  if m.find("print") is not None and m.find("print").get("new-system") == "yes"}
        if breaks != exp_breaks:
            problems.append(f"{tag}: system breaks at {sorted(breaks)}, expected {sorted(exp_breaks)}")
        for j, style in exp_bars.items():
            got = [b.findtext("bar-style") for b in ms[j].findall("barline")]
            if not got or got[-1] != style:
                problems.append(f"{tag}: barline after measure {j + 1} is {got}, expected {style}")
        if items[0]["cut"]:
            t = next(ms[0].iter("time"), None)
            if t is None or t.get("symbol") != "cut":
                problems.append(f"{tag}: first time signature is not marked cut")
        if pi == 0:
            words = [w.text for w in p.iter("words")]
            if words != labels:
                problems.append(f"labels {words} != expected {labels}")
    return problems


def write_score(score, path, items, scheme, verify):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".export_mxl_", dir=path.parent) as td:
        staged = Path(td) / path.name
        score.write("mxl", fp=str(staged), makeNotation=False)
        if verify:
            problems = verify_mxl(staged, items, scheme)
            if problems:
                raise ExportError("; ".join(problems))
        os.replace(staged, path)


# ---  main
def validate_meta(meta, kern_path, voices):
    if not isinstance(meta, dict) or meta.get("id") != kern_path.stem:
        raise ExportError("JSON id must equal the kern filename stem")
    if meta.get("voices") != voices:
        raise ExportError(f"directory requires {voices} voices, JSON says {meta.get('voices')!r}")
    if type(meta.get("measures")) is not int or meta["measures"] < 1:
        raise ExportError("measures must be a positive integer")
    species = meta.get("species")
    if not isinstance(species, list) or not species or any(type(s) is not int or s not in BARS_PER_SYSTEM for s in species):
        raise ExportError("species must be a nonempty list of integers from 1 to 5")
    figure = meta.get("figure")
    if not isinstance(figure, dict) or "number" not in figure:
        raise ExportError("figure.number is required (null is allowed while unassigned)")
    number = figure["number"]
    if number is not None and (type(number) is not int or number < 1):
        raise ExportError("figure.number must be a positive integer or null")
    if not isinstance(figure.get("suffix", ""), str):
        raise ExportError("figure.suffix must be a string")
    if not isinstance(meta.get("cantus_firmus"), dict) or "raw" not in meta["cantus_firmus"]:
        raise ExportError("cantus_firmus.raw is required")
    if "modal_final" not in meta:
        raise ExportError("modal_final is required")


def discover(in_dir):
    entries = []
    for book, (_, voices) in PARTS.items():
        book_dir = in_dir / book
        candidates = set(book_dir.glob("sp*/*.krn"))
        candidates.update(p.with_suffix(".krn") for p in book_dir.glob("sp*/gap_*.json"))
        for kp in sorted(candidates):
            entry = {"kern": kp, "id": kp.stem, "book": book,
                     "section": kp.parent.name, "meta": None, "error": None}
            try:
                if not re.fullmatch(r"sp[1-5]", kp.parent.name):
                    raise ExportError("section directory must be sp1 through sp5")
                if not kp.is_file():
                    raise ExportError(f"missing canonical kern file {kp.name}")
                mp = kp.with_suffix(".json")
                if not mp.is_file():
                    raise ExportError(f"missing JSON sidecar {mp.name}")
                meta = json.loads(mp.read_text(encoding="utf-8"))
                validate_meta(meta, kp, voices)
                entry["meta"] = meta
            except Exception as exc:
                entry["error"] = f"{type(exc).__name__}: {exc}"
            entries.append(entry)
    by_id = defaultdict(list)
    for entry in entries:
        by_id[entry["id"]].append(entry)
    for id_, matches in by_id.items():
        if len(matches) > 1:
            for entry in matches:
                entry["error"] = f"duplicate canonical ID {id_} in multiple directories"
    return entries


def output_path(out_dir, relative_stem, scheme):
    suffix = ".original.mxl" if scheme == "original" else ".mxl"
    return out_dir / (str(relative_stem) + suffix)


def write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".export_report_", dir=path.parent) as td:
        staged = Path(td) / path.name
        staged.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(staged, path)


def run(args):
    in_dir = Path(args.in_dir).resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else in_dir
    try:
        corpus = json.loads((in_dir / "corpus.json").read_text(encoding="utf-8"))
        for name in ("composer", "opr_prefix"):
            if not isinstance(corpus.get(name), str):
                raise ExportError(f"corpus.json requires a string {name}")
        if not isinstance(corpus.get("licence"), dict) or not isinstance(corpus["licence"].get("statement"), str):
            raise ExportError("corpus.json requires licence.statement")
        entries = discover(in_dir)
    except Exception as exc:
        print(f"ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    failures, input_errors = 0, []
    if args.only:
        requested = set(args.only)
        for id_ in sorted(requested - {e["id"] for e in entries}):
            message = f"requested ID not found: {id_}"
            input_errors.append(message)
            print(f"ERROR {message}", file=sys.stderr)
            failures += 1
        entries = [e for e in entries if e["id"] in requested]
    if not entries:
        print("ERROR nothing to export; expected ROOT/I|II|III/spN/*.krn", file=sys.stderr)
        return 1

    report = {"format_version": 1, "scope": "selected" if args.only else "full",
              "groups_rebuilt": not bool(args.only), "input_errors": input_errors, "outputs": []}

    def record(path, scheme, kind, status, members, message=None):
        start, exercises = 1, []
        for entry in members:
            meta = entry["meta"]
            item = {"id": entry["id"], "source": entry["kern"].relative_to(in_dir).as_posix()}
            if meta:
                item.update({"figure": fig_text(meta), "measures": meta["measures"]})
                if status == "written":
                    item["first_measure_in_set"] = start
                    start += meta["measures"]
            exercises.append(item)
        result = {"file": path.relative_to(out_dir).as_posix(), "scheme": scheme,
                  "kind": kind, "status": status, "verified": status == "written" and not args.no_verify,
                  "previous_file_retained": status != "written" and path.exists(), "exercises": exercises}
        if message:
            result["message"] = message
        report["outputs"].append(result)

    for scheme in dict.fromkeys(args.scheme):
        ready, written, failed = {}, 0, 0
        for entry in entries:
            kp, meta = entry["kern"], entry["meta"]
            path = output_path(out_dir, kp.relative_to(in_dir).with_suffix(""), scheme)
            try:
                if entry["error"]:
                    raise ExportError(entry["error"])
                parts, cut = load_parts(kp, meta, scheme)
                item = prepare(parts, meta, corpus, args.bars_per_system, cut)
                single = build_score([item], f"Gradus ad Parnassum, {fig_text(meta)}", corpus)
                write_score(single, path, [item], scheme, not args.no_verify)
                ready[kp] = item
                written += 1
                record(path, scheme, "individual", "written", [entry])
            except Exception as exc:
                failed += 1
                status = "skipped" if isinstance(exc, Skip) else "failed"
                message = f"{type(exc).__name__}: {exc}"
                print(f"ERROR [{scheme}] {entry['id']}: {message}", file=sys.stderr)
                record(path, scheme, "individual", status, [entry], message)
        print(f"[{scheme}] {written} exercises written, {failed} failed/skipped")
        failures += failed

        if not args.only:
            groups = defaultdict(list)
            for entry in entries:
                book, section = entry["book"], entry["section"]
                number, _ = PARTS[book]
                if re.fullmatch(r"sp[1-5]", section):
                    groups[("section", Path(book) / section / f"ex{number}{section}")].append(entry)
                groups[("part", Path(book) / f"ex{number}")].append(entry)
            for (kind, stem), members in sorted(groups.items(), key=lambda pair: str(pair[0][1])):
                members.sort(key=lambda e: sort_key(e["meta"]) if e["meta"] else (99, True, 0, "", e["id"]))
                path = output_path(out_dir, stem, scheme)
                exercise_path = (output_path(out_dir, stem.with_name(stem.name + "_exercise"), scheme)
                                 if kind == "part" else None)
                missing = [e["id"] for e in members if e["kern"] not in ready]
                if missing:
                    message = "members not exported: " + ", ".join(missing)
                    record(path, scheme, kind, "blocked", members, message)
                    if exercise_path is not None:
                        record(exercise_path, scheme, "part_exercise", "blocked", members, message)
                    print(f"BLOCK [{scheme}] {stem}: {message}", file=sys.stderr)
                    continue
                items = [ready[e["kern"]] for e in members]
                number, nv = PARTS[members[0]["book"]]
                title = f"Gradus ad Parnassum:\nPart {number} ({nv} voices)"
                if kind == "section":
                    title += f", Species {members[0]['section'][2:]}"
                try:
                    write_score(build_score(items, title, corpus), path, items, scheme, not args.no_verify)
                    record(path, scheme, kind, "written", members)
                    print(f"[{scheme}] {stem}: {len(items)} exercises")
                except Exception as exc:
                    failures += 1
                    message = f"{type(exc).__name__}: {exc}"
                    record(path, scheme, kind, "failed", members, message)
                    print(f"ERROR [{scheme}] {stem}: {message}", file=sys.stderr)
                    if exercise_path is not None:
                        record(exercise_path, scheme, "part_exercise", "blocked", members,
                               "whole-part score not exported: " + message)
                    continue
                if exercise_path is not None:
                    try:
                        write_exercise_mxl(path, exercise_path, [it["meta"] for it in items],
                                           verify=not args.no_verify)
                        record(exercise_path, scheme, "part_exercise", "written", members)
                        print(f"[{scheme}] {exercise_path.relative_to(out_dir)}: "
                              f"{len(items)} cantus-firmus exercises")
                    except Exception as exc:
                        failures += 1
                        message = f"{type(exc).__name__}: {exc}"
                        record(exercise_path, scheme, "part_exercise", "failed", members, message)
                        print(f"ERROR [{scheme}] {exercise_path.relative_to(out_dir)}: {message}",
                              file=sys.stderr)
    report["success"] = failures == 0
    try:
        name = "exports.partial.json" if args.only else "exports.json"
        write_report(out_dir / name, report)
    except Exception as exc:
        print(f"ERROR writing export report: {type(exc).__name__}: {exc}", file=sys.stderr)
        failures += 1
    return 1 if failures else 0


def bars_table(items):
    table = dict(BARS_PER_SYSTEM)
    for item in items:
        sp, sep, n = item.partition("=")
        if sep:
            if not sp.isdigit() or int(sp) not in BARS_PER_SYSTEM:
                raise ExportError("--bars-per-system species must be 1 through 5")
            table[int(sp)] = int(n)
        else:
            table = {k: int(item) for k in table}
    if any(v < 1 for v in table.values()):
        raise ExportError("--bars-per-system values must be >= 1")
    return table


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("in_dir", nargs="?", default="..", help="corpus root (default: up one level)")
    ap.add_argument("out_dir", nargs="?", help="optional output root (default: export beside sources)")
    ap.add_argument("--scheme", nargs="+", choices=["modern", "original"], default=["modern"])
    ap.add_argument("--bars-per-system", nargs="*", default=[], metavar="[S=]N",
                    help="bars per system: S=N sets species S, a bare N sets all (defaults in BARS_PER_SYSTEM)")
    ap.add_argument("--only", nargs="+", metavar="ID", help="export just these ids (no sets)")
    ap.add_argument("--no-verify", action="store_true", help="skip the read-back verification")
    args = ap.parse_args()
    try:
        args.bars_per_system = bars_table(args.bars_per_system)
    except (ValueError, ExportError) as exc:
        ap.error(str(exc))
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
