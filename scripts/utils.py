"""Create blank counterpoint worksheets from generated partwise MusicXML archives.

The cantus firmus can occupy a different part in each exercise. Source measures
are addressed by position, since their printed numbers restart per exercise.
Only the standard library is required; score layout is not regenerated.

By: Mark Gotham
Repo: https://github.com/MarkGotham/species/
Licence: MIT
"""

import copy
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
import zipfile


_KEEP = {"duration", "voice", "type", "dot", "time-modification", "staff"}


def _selection(exercises):
    """Validate metadata and return the part count and CF index for each measure."""
    if not isinstance(exercises, (list, tuple)) or not exercises:
        raise ValueError("exercises must be a nonempty ordered list of metadata objects")
    voices, selection = None, []
    for index, meta in enumerate(exercises, 1):
        if not isinstance(meta, dict):
            raise ValueError(f"exercise {index}: metadata must be an object")
        count, measures = meta.get("voices"), meta.get("measures")
        if type(count) is not int or count < 1:
            raise ValueError(f"exercise {index}: voices must be a positive integer")
        if voices is not None and count != voices:
            raise ValueError("all exercises must have the same number of voices")
        voices = count
        if type(measures) is not int or measures < 1:
            raise ValueError(f"exercise {index}: measures must be a positive integer")
        cf = meta.get("cantus_firmus")
        part = cf.get("part") if isinstance(cf, dict) else None
        if type(part) is not int or not 1 <= part <= voices:
            raise ValueError(f"exercise {index}: cantus_firmus.part must be an integer from 1 to {voices}")
        selection.extend([part - 1] * measures)
    return voices, selection


def _read_score(archive):
    try:
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        rootfile = container.find(".//{*}rootfile")
        if rootfile is None or not rootfile.get("full-path"):
            raise ValueError("MXL container has no root score")
        name = rootfile.get("full-path")
        root = ET.fromstring(archive.read(name))
    except (KeyError, ET.ParseError) as exc:
        raise ValueError(f"invalid MXL container or score XML: {exc}") from exc
    if root.tag != "score-partwise":
        raise ValueError("expected an unnamespaced score-partwise MusicXML score")
    return name, root


def _parts(root, voices, selection):
    parts = root.findall("part")
    if len(parts) != voices:
        raise ValueError(f"score has {len(parts)} parts; metadata requires {voices}")
    for index, part in enumerate(parts, 1):
        count = len(part.findall("measure"))
        if count != len(selection):
            raise ValueError(f"part {index} has {count} measures; metadata requires {len(selection)}")
    return parts


def _check_duration(note):
    durations = note.findall("duration")
    if len(durations) != 1:
        raise ValueError("each timed note must contain exactly one duration")
    try:
        duration = Decimal(durations[0].text or "")
    except InvalidOperation as exc:
        raise ValueError("a timed note has an invalid duration") from exc
    if not duration.is_finite() or duration <= 0:
        raise ValueError("a timed note must have a finite, positive duration")


def _rest(note):
    """Replace sounding data while retaining its exact MusicXML time advance."""
    _check_duration(note)
    attrs = {"print-object": "no", "print-spacing": "yes"}
    if "default-x" in note.attrib:
        attrs["default-x"] = note.get("default-x")
    result = ET.Element("note", attrs)
    result.tail = note.tail
    ET.SubElement(result, "rest")
    result.extend(copy.deepcopy(child) for child in note if child.tag in _KEEP)
    return result


def _transform(root, voices, selection):
    result = copy.deepcopy(root)
    for part_index, part in enumerate(_parts(result, voices, selection)):
        for measure_index, measure in enumerate(part.findall("measure")):
            if part_index == selection[measure_index]:
                continue
            children = []
            for child in measure:
                if child.tag != "note":
                    children.append(child)
                elif child.find("grace") is None and child.find("chord") is None:
                    children.append(_rest(child))
            measure[:] = children
    return result


def _canonical(element):
    """Compare XML content, ignoring formatting-only whitespace and attribute order."""
    text = element.text if element.text and element.text.strip() else None
    tail = element.tail if element.tail and element.tail.strip() else None
    return (element.tag, tuple(sorted(element.attrib.items())), text,
            tuple(_canonical(child) for child in element), tail)


def _verification_form(root, voices, selection, output):
    result = copy.deepcopy(root)
    for part_index, part in enumerate(_parts(result, voices, selection)):
        for measure_index, measure in enumerate(part.findall("measure")):
            if part_index == selection[measure_index]:
                continue
            children = []
            for child in measure:
                if child.tag != "note":
                    children.append(child)
                    continue
                if not output and (child.find("grace") is not None or child.find("chord") is not None):
                    continue
                _check_duration(child)
                if output:
                    rest = child.find("rest")
                    allowed_attrs = {"print-object", "print-spacing", "default-x"}
                    if (child.get("print-object") != "no" or child.get("print-spacing") != "yes"
                            or set(child.attrib) - allowed_attrs or len(child.findall("rest")) != 1
                            or rest is None or len(rest) or rest.attrib or (rest.text or "").strip()
                            or not len(child) or child[0].tag != "rest"
                            or any(item.tag not in _KEEP | {"rest"} for item in child)):
                        raise ValueError("a non-CF note is not an empty, hidden rest")
                masked = ET.Element("masked-note")
                if "default-x" in child.attrib:
                    masked.set("default-x", child.get("default-x"))
                masked.extend(copy.deepcopy(item) for item in child if item.tag in _KEEP)
                children.append(masked)
            measure[:] = children
    return result


def verify_exercise_mxl(source_path, destination_path, exercises):
    """Raise ValueError if CF music, timing, or non-note score content changed."""
    voices, selection = _selection(exercises)
    with zipfile.ZipFile(source_path) as archive:
        _, source = _read_score(archive)
    with zipfile.ZipFile(destination_path) as archive:
        _, output = _read_score(archive)
    expected = _verification_form(source, voices, selection, output=False)
    actual = _verification_form(output, voices, selection, output=True)
    if _canonical(expected) != _canonical(actual):
        raise ValueError("exercise score changed CF music, note timing, layout, or other non-note XML")


def write_exercise_mxl(source_path, destination_path, exercises, verify=True):
    """Atomically create a worksheet, preserving the selected CF in each exercise.

    Non-CF timed notes become invisible rests of their original duration;
    grace notes and chord followers disappear. No pitches are merely hidden.
    Semantic errors raise ValueError; file I/O errors propagate unchanged.
    """
    source_path, destination_path = Path(source_path), Path(destination_path)
    if (source_path.resolve() == destination_path.resolve()
            or (source_path.exists() and destination_path.exists()
                and os.path.samefile(source_path, destination_path))):
        raise ValueError("source and destination must be different files")
    voices, selection = _selection(exercises)
    with zipfile.ZipFile(source_path) as source:
        score_name, root = _read_score(source)
        transformed = _transform(root, voices, selection)
        xml = ET.tostring(transformed, encoding="utf-8", xml_declaration=True)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".exercise_mxl_", dir=destination_path.parent) as temporary:
            staged = Path(temporary) / destination_path.name
            with zipfile.ZipFile(staged, "w") as target:
                target.comment = source.comment
                for member in source.infolist():
                    target.writestr(member, xml if member.filename == score_name else source.read(member))
            if verify:
                verify_exercise_mxl(source_path, staged, exercises)
            os.replace(staged, destination_path)