#!/usr/bin/env python3

#!/usr/bin/env python3
"""
Build one or more searchable HTML contents pages for the Gradus score collection.

Reads all pairs of gap_*.json and gap_*.krn files
which sit in adjacent pairs in directories from  I/sp1 to III/sp5
(I-III and sp1-sp5 in each).

Writes:
    species_contents.html       complete catalogue (all cases, others optional)
    I/ex1.html                  contents of the two-voice part
    ...
    I/sp1/ex1sp1.html           contents of the two-voice part, species 1 section
    ...                         corresponding II / III pages and for all species.

Usage (from repo top level):
    python scripts/build_contents.py .

Options:
`--output-dir docs`: changes where HTML lives, not where scores live.
`--catalogue-only`: skips the grouped pages, creating only the top level one.
`--raw-base-url`: if needed to adapt from/around https://raw.githubusercontent.com/OWNER/REPO/main
`--no-absolute-links`: restores relative file links (the default being direct, raw URLs).
`--page-base-url` https://OWNER.github.io/REPO

Design:
Each row describes an individual exercise.
Directories determine chapter membership;
JSON species[] describes musical content, including mixed species.
Only nonempty parts/sections get contents pages.

By default, all file links are absolute raw-repository URLs.
That way, each HTML page can be moved, hosted, shared freely.

Files ending `.mxl` only indicate the use of modern clefs;
the longer `.original.mxl` means original clefs.

Known failed/skipped/blocked outputs from exports.json or exports.partial.json
are not linked even if an older file remains.

Start positions come only from a written, existing matching aggregate in exports.json.
At catalogue level,
"Start" means the position in that part's combined score.
It never changes when the table is filtered or sorted.
No start positions are guessed or inferred, only read direcltly from the json.

Files for download and VHV links both use the public raw base URL by default.
To change, use --raw-base-url for another repository/branch, or use --no-vhv.
The raw repository must mirror ROOT's I/II/III paths;
this script does not publish files or check remote URLs,
it simply reports on what's there.

Requires Python 3.9+ and standard library only.
Invalid metadata is reported, other rows still build.
Exit status is 1 if an input or output error occurred.
"""

import argparse
from collections import defaultdict
from dataclasses import dataclass
from html import escape
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import quote, urlencode, urlsplit


PARTS = {"I": (1, 2), "II": (2, 3), "III": (3, 4)}
RAW_BASE = "https://raw.githubusercontent.com/MarkGotham/species/main"


@dataclass
class Entry:
    path: Path
    book: str
    section: str
    meta: dict

    @property
    def id(self):
        return self.meta["id"]


def h(value):
    return escape(str(value), quote=True)


def fig_sort(entry):
    f = entry.meta["figure"]
    number = f.get("number")
    return (PARTS[entry.book][0], number is None, number or 0, f.get("suffix", ""), entry.id)


def load_entries(root):
    entries, errors = [], []
    for book, (_, voices) in PARTS.items():
        for path in sorted((root / book).glob("sp*/gap_*.json")):
            try:
                if not re.fullmatch(r"sp[1-5]", path.parent.name):
                    raise ValueError("section directory must be sp1 through sp5")
                meta = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(meta, dict) or meta.get("id") != path.stem:
                    raise ValueError("JSON id must match its filename")
                if meta.get("voices") != voices:
                    raise ValueError(f"{book} requires {voices} voices")
                species = meta.get("species")
                if not isinstance(species, list) or not species or any(type(s) is not int or s not in range(1, 6) for s in species):
                    raise ValueError("species must be a nonempty list of integers 1-5")
                f = meta.get("figure")
                if not isinstance(f, dict):
                    raise ValueError("figure must be an object")
                number = f.get("number")
                if number is not None and (type(number) is not int or number < 1):
                    raise ValueError("figure.number must be a positive integer or null")
                if not isinstance(f.get("suffix", ""), str):
                    raise ValueError("figure.suffix must be a string")
                if type(meta.get("measures")) is not int or meta["measures"] < 1:
                    raise ValueError("measures must be a positive integer")
                cf = meta.get("cantus_firmus")
                if not isinstance(cf, dict) or type(cf.get("part")) is not int or not 1 <= cf["part"] <= voices:
                    raise ValueError("cantus_firmus.part must identify a voice, counted from the top")
                entries.append(Entry(path, book, path.parent.name, meta))
            except (ValueError, OSError, TypeError) as exc:
                errors.append(f"{path.relative_to(root)}: {exc}")
    seen = defaultdict(list)
    for entry in entries:
        seen[entry.id].append(entry)
    duplicates = {id_ for id_, matches in seen.items() if len(matches) > 1}
    for id_ in sorted(duplicates):
        errors.append(f"duplicate ID {id_}: " + ", ".join(str(e.path.relative_to(root)) for e in seen[id_]))
    entries = [e for e in entries if e.id not in duplicates]
    entries.sort(key=fig_sort)
    return entries, errors


def load_exports(root):
    """Latest per-file status plus full-run aggregate records; partials never invent starts."""
    statuses, aggregates, errors = {}, {}, []
    paths = sorted((p for p in (root / "exports.json", root / "exports.partial.json") if p.is_file()),
                   key=lambda p: p.stat().st_mtime_ns)
    for path in paths:
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            outputs = report.get("outputs")
            if not isinstance(outputs, list):
                raise ValueError("expected an outputs list from export_mxl.py")
            for record in outputs:
                if not isinstance(record, dict) or not isinstance(record.get("file"), str):
                    raise ValueError("invalid output record")
                rel = Path(record["file"])
                if rel.is_absolute() or ".." in rel.parts:
                    raise ValueError("output path must be relative to the corpus root")
                if record.get("kind") in ("part", "section") and record.get("status") == "written":
                    exercises = record.get("exercises")
                    if not isinstance(exercises, list) or not all(isinstance(e, dict) for e in exercises):
                        statuses[rel.as_posix()] = {"status": "failed"}
                        errors.append(f"{path.name}: invalid aggregate exercises for {rel}")
                        continue
                statuses[rel.as_posix()] = record
                if path.name == "exports.json" and record.get("kind") in ("part", "section"):
                    aggregates[rel.as_posix()] = record
        except (ValueError, OSError, TypeError, AttributeError) as exc:
            errors.append(f"{path.name}: {exc}")
    return statuses, aggregates, errors


def relative_url(target, page):
    return quote(Path(os.path.relpath(target, page.parent)).as_posix(), safe="/.-_")


def raw_url(target, root, base):
    return base.rstrip("/") + "/" + quote(target.relative_to(root).as_posix(), safe="/.-_")


def file_url(target, page, root, args):
    if args.absolute_links:
        return raw_url(target, root, args.raw_base_url)
    return relative_url(target, page)


def contents_url(target, page, page_paths, args):
    if args.page_base_url:
        output_root = page_paths[(None, None)].parent
        return raw_url(target, output_root, args.page_base_url)
    if not args.absolute_links:
        return relative_url(target, page)
    return None


def download_available(path, root, statuses):
    if not path.is_file():
        return False
    record = statuses.get(path.relative_to(root).as_posix())
    return record is None or record.get("status") == "written"


def anchor(label, href, title="", css="", download=False):
    attrs = f' href="{h(href)}"'
    if title:
        attrs += f' title="{h(title)}" aria-label="{h(title)}"'
    if css:
        attrs += f' class="{h(css)}"'
    if download:
        attrs += " download"
    if not download or urlsplit(href).scheme in ("http", "https"):
        attrs += ' target="_blank" rel="noopener noreferrer"'
    return f"<a{attrs}>{h(label)}</a>"


def figure_cell(entry):
    f = entry.meta["figure"]
    number = f.get("number")
    label = f"{number}{f.get('suffix', '')}" if number is not None else "Unassigned"
    full = f.get("note") or ""
    corrected = bool(f.get("corrected") or f.get("corrects") is not None)
    suffix = ""
    if corrected:
        target = f.get("corrects")
        short = "corr." if target is None else f"corr. {target}"
        full = full or ("Corrected version" if target is None else f"Corrected version of figure {target}")
        suffix = f' <span class="correction" title="{h(full)}">({h(short)})</span>'
    title = entry.id + (" — " + str(full) if full else "")
    content = f'<span class="figure" title="{h(title)}">{h(label)}</span>{suffix}'
    if number is None:
        content += f'<span class="sub-id">{h(entry.id)}</span>'
    return content, "" if number is None else label


def pdf_sources(entry, root):
    source = entry.meta.get("source") or {}
    if not isinstance(source, dict):
        return []
    records = [{"pdf_file": source.get("pdf_file"), "printed_page": entry.meta.get("page")}]
    systems = source.get("systems")
    if isinstance(systems, list):
        records.extend(s for s in systems if isinstance(s, dict))
    result, seen = [], set()
    for record in records:
        filename = record.get("pdf_file")
        if not isinstance(filename, str) or Path(filename).name != filename or filename in seen:
            continue
        path = root / "source_pdf" / filename
        if path.is_file():
            seen.add(filename)
            result.append((path, record.get("printed_page")))
    return result


def aggregate_starts(stem, members, root, statuses, aggregates):
    """Prefer modern, then original; require exact membership and metadata lengths."""
    expected = {e.id: e.meta["measures"] for e in members}
    for suffix in (".mxl", ".original.mxl"):
        rel = stem.as_posix() + suffix
        record = aggregates.get(rel)
        if not record or record.get("status") != "written" or not download_available(root / rel, root, statuses):
            continue
        exercises = record.get("exercises", [])
        if not isinstance(exercises, list) or len(exercises) != len(expected):
            continue
        starts = {}
        for exercise in exercises:
            if not isinstance(exercise, dict):
                break
            id_ = exercise.get("id")
            start = exercise.get("first_measure_in_set")
            if (not isinstance(id_, str) or id_ not in expected or id_ in starts or exercise.get("measures") != expected[id_]
                    or type(start) is not int or start < 1):
                break
            starts[id_] = {"measure": start, "file": rel}
        else:
            return starts
    return {}


CSS = r"""
:root{color-scheme:light;--ink:#202d3c;--muted:#647180;--line:#dce3e9;--blue:#285b85;--paper:#f7f8fa;--accent:#e9f0f7}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
a{color:var(--blue);text-underline-offset:3px}a:hover{color:#123c61}button,input,select{font:inherit}button,a,input,select{touch-action:manipulation}
:focus-visible{outline:3px solid #679dcb;outline-offset:3px}main{max-width:1480px;margin:auto;padding:30px 32px 46px}
.masthead{display:flex;align-items:baseline;justify-content:space-between;gap:18px;border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:18px}
.eyebrow{font-size:11px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin:0 0 4px}
h1{font:400 clamp(25px,3vw,36px)/1.18 Georgia,"Times New Roman",serif;margin:0}.subtitle{color:var(--muted);margin:7px 0 0}
.collection-tag{font-size:12px;color:var(--muted);white-space:nowrap}.nav{display:flex;flex-wrap:wrap;gap:7px;margin:0 0 18px}
.nav a{border:1px solid var(--line);border-radius:5px;padding:5px 10px;text-decoration:none;background:white;font-size:12px}.nav a[aria-current=page]{background:var(--ink);color:white;border-color:var(--ink)}
.group-downloads{display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin:0 0 18px;font-size:13px}.group-downloads>span{color:var(--muted);margin-right:3px}
.controls{display:flex;flex-wrap:wrap;align-items:end;gap:12px;padding:16px;background:white;border:1px solid var(--line);border-radius:8px 8px 0 0}
.control{display:flex;flex-direction:column;gap:5px}.control label{font-size:11px;letter-spacing:.035em;font-weight:650;color:var(--muted)}.search-control{flex:1;min-width:220px}
input,select{height:36px;border:1px solid #bdc9d5;border-radius:5px;background:white;color:var(--ink);padding:6px 10px}input{width:100%}input::placeholder{color:#7c8793}
.reset{height:36px;border:1px solid var(--line);background:var(--paper);border-radius:5px;padding:6px 12px;cursor:pointer;color:var(--ink)}.reset:hover{background:var(--accent)}
.status{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px;font-size:12px;color:var(--muted);padding:11px 2px}.legend{margin:0}.table-wrap{overflow-x:auto;background:white;border:1px solid var(--line);border-radius:0 0 8px 8px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;table-layout:auto}th,td{text-align:left;vertical-align:middle;border-bottom:1px solid #e8edf1;padding:10px 11px}
thead{background:#edf1f5}th{font-size:11px;font-weight:700;color:#4c5e70;white-space:nowrap}th button{border:0;background:none;color:inherit;cursor:pointer;padding:0;display:inline-flex;align-items:center;gap:5px;font-weight:inherit;font-size:inherit;min-height:24px}
th button::after{content:"↕";font-size:11px;color:#8394a4}th[aria-sort=ascending] button::after{content:"↑";color:var(--blue)}th[aria-sort=descending] button::after{content:"↓";color:var(--blue)}
tbody tr:last-child td{border-bottom:0}tbody tr:nth-child(even){background:#fafbfd}tbody tr:hover{background:#f0f5fa}td{font-size:13px}.num{white-space:nowrap}.figure{font-weight:700}.figure-cell{max-width:185px}.correction{font-size:11px;color:#665222;white-space:nowrap}.sub-id{display:block;font-size:10px;font-weight:400;overflow-wrap:anywhere;color:var(--muted);max-width:155px}
.downloads{display:flex;flex-wrap:wrap;gap:5px;max-width:260px}.file-link{display:inline-block;text-decoration:none;border:1px solid #ccd9e5;border-radius:4px;background:#f5f8fb;padding:3px 6px;font-size:11px;line-height:1.3;white-space:nowrap}.file-link:hover{background:#e7eff7;border-color:#7a9fbd}.muted{color:#94a0ac}.source-links{display:flex;flex-wrap:wrap;gap:5px}.view-link{font-size:12px;white-space:nowrap}
.empty{display:none;margin:0;padding:32px;text-align:center;color:var(--muted);background:white;border:1px solid var(--line);border-top:0}.footer{font-size:11px;color:var(--muted);margin-top:14px;display:flex;flex-wrap:wrap;gap:5px 18px}.visually-hidden{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:1050px){main{padding:22px 18px}th,td{padding:9px 8px}.collection-tag{display:none}.downloads{max-width:230px}}
@media(max-width:700px){main{padding:18px 12px}.masthead{display:block}.controls{padding:12px;gap:9px}.search-control{flex-basis:100%}.control select{max-width:140px}th,td{padding:9px 7px}td{font-size:12px}.figure-cell{min-width:88px}.downloads{min-width:146px}.legend{max-width:100%}}
@media print{body{background:white}main{max-width:none;padding:0}.controls,.nav,.group-downloads,.view-column,.footer{display:none}.table-wrap{overflow:visible;border:0}.status{padding:8px 0}th,td{padding:6px}a{color:inherit;text-decoration:none}.file-link{border:0;padding:0}thead{display:table-header-group}tr{break-inside:avoid}}
"""


JS = r"""
(() => {
  const table = document.getElementById('scores');
  const tbody = table.tBodies[0];
  const rows = [...tbody.rows];
  const search = document.getElementById('search');
  const filters = [...document.querySelectorAll('[data-filter]')];
  const count = document.getElementById('result-count');
  const empty = document.getElementById('empty');
  const collator = new Intl.Collator(undefined, {numeric: true, sensitivity: 'base'});
  let active = null, direction = 1;
  function filter() {
    const words = search.value.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
    let shown = 0;
    for (const row of rows) {
      const text = row.dataset.search.toLocaleLowerCase();
      const match = words.every(word => text.includes(word)) && filters.every(select => {
        const value = select.value;
        if (!value) return true;
        const actual = row.dataset[select.dataset.filter];
        return select.dataset.filter === 'species' ? actual.split(',').includes(value) : actual === value;
      });
      row.hidden = !match;
      if (match) shown++;
    }
    count.textContent = `${shown} of ${rows.length} exercises`;
    empty.hidden = shown !== 0;
    empty.style.display = shown === 0 ? 'block' : 'none';
  }
  function sort(button) {
    const key = button.dataset.key;
    direction = active === key ? -direction : 1;
    active = key;
    const column = button.closest('th').cellIndex;
    rows.sort((a,b) => {
      const av = a.cells[column].dataset.sort || '';
      const bv = b.cells[column].dataset.sort || '';
      if (!av && bv) return 1;
      if (av && !bv) return -1;
      return direction * collator.compare(av,bv) || Number(a.dataset.order) - Number(b.dataset.order);
    });
    for (const row of rows) tbody.appendChild(row);
    for (const th of table.tHead.rows[0].cells) th.removeAttribute('aria-sort');
    button.closest('th').setAttribute('aria-sort', direction === 1 ? 'ascending' : 'descending');
  }
  search.addEventListener('input', filter);
  filters.forEach(select => select.addEventListener('change', filter));
  document.querySelectorAll('th button[data-key]').forEach(button => button.addEventListener('click', () => sort(button)));
  document.getElementById('reset').addEventListener('click', () => {
    search.value = ''; filters.forEach(select => select.value = '');
    rows.sort((a,b) => Number(a.dataset.order) - Number(b.dataset.order));
    rows.forEach(row => tbody.appendChild(row));
    for (const th of table.tHead.rows[0].cells) th.removeAttribute('aria-sort');
    active = null; direction = 1; filter(); search.focus();
  });
  filter();
})();
"""


def options(values):
    return "".join(f'<option value="{h(value)}">{h(label)}</option>' for value, label in values)


def th(label, key=None, title=""):
    title_attr = f' title="{h(title)}"' if title else ""
    content = f'<button type="button" data-key="{h(key)}" aria-label="Sort by {h(label)}">{h(label)}</button>' if key else h(label)
    return f"<th scope=\"col\"{title_attr}>{content}</th>"


def td(content, sort="", css=""):
    return f'<td data-sort="{h(sort)}" class="{h(css)}">{content}</td>'


def render_page(root, page, entries, all_entries, page_paths, statuses, starts, args, book=None, section=None):
    catalogue = book is None
    scope_title = "Score catalogue" if catalogue else f"Part {book} · {PARTS[book][1]} voices" + (f" · Species {section[2:]}" if section else "")
    nav = []
    for key, destination in page_paths.items():
        href = contents_url(destination, page, page_paths, args)
        if href is None:
            continue
        nav_book, nav_section = key
        if nav_section and nav_book != book:
            continue
        if nav_book is None:
            label = "All exercises"
        elif nav_section is None:
            label = f"{nav_book} · {PARTS[nav_book][1]} voices"
        else:
            label = f"Species {nav_section[2:]}"
        current = ' aria-current="page"' if destination == page else ""
        nav.append(f'<a href="{h(href)}"{current}>{h(label)}</a>')

    combined = ""
    if book:
        number = PARTS[book][0]
        stem = Path(book) / section / f"ex{number}{section}" if section else Path(book) / f"ex{number}"
        links = []
        for suffix, label in ((".mxl", "MXL · modern"), (".original.mxl", "MXL · original")):
            target = root / (str(stem) + suffix)
            if download_available(target, root, statuses):
                links.append(anchor(label, file_url(target, page, root, args), f"Download combined score: {label}", "file-link", True))
        if links:
            combined = '<div class="group-downloads"><span>Combined score</span>' + " ".join(links) + "</div>"

    columns = [th("Figure", "figure")]
    if catalogue:
        columns.append(th("Part", "part"))
    columns += [th("Species", "species"), th("Final", "final", "Modal final"), th("CF", "cf", "Cantus firmus; voice numbers are counted from the top"),
                th("Start", "start", "Position in the combined part score" if catalogue else "Position in this combined score"),
                th("Bars", "bars", "Measure count"), th("Page", "page", "Printed book page; click to open a source scan"), th("Downloads")]
    if not args.no_vhv:
        columns.append(th("View"))
    rendered_rows = []
    for index, entry in enumerate(entries):
        meta = entry.meta
        figure, figure_key = figure_cell(entry)
        species = ", ".join(map(str, meta["species"]))
        part = meta["cantus_firmus"]["part"]
        cf = ("Upper" if part == 1 else "Lower") if meta["voices"] == 2 else str(part)
        start = starts.get(entry.id)
        start_content = '<span class="muted">—</span>'
        if start:
            scheme = "original" if start["file"].endswith(".original.mxl") else "modern"
            start_content = anchor(str(start["measure"]), file_url(root / start["file"], page, root, args),
                                   f'Position {start["measure"]} in {start["file"]} ({scheme} clefs); download combined score', download=True)
        pages = pdf_sources(entry, root)
        page_content = " ".join(anchor(str(printed) if printed is not None else "PDF", file_url(target, page, root, args), f"Source scan: {target.name}") for target, printed in pages)
        if not page_content:
            page_content = h(meta.get("page")) if meta.get("page") is not None else '<span class="muted">—</span>'
        files = []
        for suffix, label, description in ((".mxl", "MXL", "MusicXML, modern clefs"), (".original.mxl", "Orig.", "MusicXML, original clefs"),
                                           (".krn", "KRN", "Humdrum kern score"), (".json", "JSON", "Canonical metadata")):
            target = entry.path.with_name(entry.id + suffix)
            if download_available(target, root, statuses):
                files.append(anchor(label, file_url(target, page, root, args), f"{entry.id}: {description}", "file-link", True))
        row = [td(figure, figure_key, "figure-cell")]
        if catalogue:
            part_page = page_paths.get((entry.book, None))
            part_href = contents_url(part_page, page, page_paths, args) if part_page else None
            part_html = f'<a href="{h(part_href)}" title="{meta["voices"]} voices">{entry.book}</a>' if part_href else entry.book
            row.append(td(part_html, PARTS[entry.book][0], "num"))
        row += [td(h(species), ",".join(map(str, meta["species"])), "num"), td(h(meta.get("modal_final", "—")), meta.get("modal_final", ""), "num"),
                td(f'<span title="Voice {part} of {meta["voices"]}, counted from the top">{h(cf)}</span>', part, "num"),
                td(start_content, start["measure"] if start else "", "num"),
                td(str(meta["measures"]), meta["measures"], "num"), td('<span class="source-links">' + page_content + '</span>', meta.get("page") or "", "num"),
                td('<div class="downloads">' + "".join(files) + "</div>")]
        if not args.no_vhv:
            kern = entry.path.with_suffix(".krn")
            view = '<span class="muted">—</span>'
            if kern.is_file():
                raw = raw_url(kern, root, args.raw_base_url)
                vhv = "https://verovio.humdrum.org/?" + urlencode({"file": raw})
                view = anchor("VHV ↗", vhv, f"View {entry.id} in Verovio Humdrum Viewer", "view-link")
            row.append(td(view, css="view-column"))
        figure_meta = meta["figure"]
        correction_search = "corrected corr." if figure_meta.get("corrected") or figure_meta.get("corrects") is not None else ""
        source = meta.get("source") if isinstance(meta.get("source"), dict) else {}
        search = " ".join(str(value) for value in [entry.id, entry.book, entry.section,
                          str(meta["voices"]) + " voices", cf, meta["cantus_firmus"].get("raw", ""),
                          species, meta.get("modal_final", ""),
                          meta.get("page", ""), figure_meta.get("number", ""), figure_meta.get("suffix", ""),
                          figure_meta.get("note") or "", correction_search, figure_meta.get("corrects") or "",
                          source.get("example_id", ""), source.get("pdf_file", "")] if value is not None)
        rendered_rows.append(f'<tr data-order="{index}" data-search="{h(search)}" data-part="{entry.book}" data-species="{h(",".join(map(str, meta["species"])))}" data-final="{h(meta.get("modal_final", ""))}">' + "".join(row) + "</tr>")
    part_filter = ""
    if catalogue:
        part_filter = '<div class="control"><label for="part-filter">Part / voices</label><select id="part-filter" data-filter="part"><option value="">All parts</option>' + options((p, f"{p} · {PARTS[p][1]} voices") for p in PARTS if any(e.book == p for e in entries)) + '</select></div>'
    species_values = sorted({s for e in entries for s in e.meta["species"]})
    final_values = sorted({str(e.meta.get("modal_final", "")) for e in entries} - {""})
    legend = "Start = position in the combined part score." if catalogue else "Start = position in this combined score."
    navigation = '<nav class="nav" aria-label="Contents pages">' + "".join(nav) + '</nav>' if nav else ""
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{h(scope_title)} · Gradus ad Parnassum</title><style>{CSS}</style></head>
<body><main>
<header class="masthead"><div><p class="eyebrow">fourscoreandmore.org presents</p><h1>Fux's: Gradus ad Parnassum</h1>
<p class="subtitle">{h(scope_title)}</p>
<p>
Click any column header to sort; use the search box to filter (across any field).    
</p>


<p>
  Choose <strong>MusicXML (.mxl)</strong> to open and edit scores in notation software.
  <strong>Kern (.krn)</strong> is also available for users of Humdrum tools.
</p>
<p>The table also provides these links:</p>
<ul>
  <li>
    <strong>VHV</strong>: view and edit an individual score online in the
    <a href="https://verovio.humdrum.org/"
       target="_blank" rel="noopener noreferrer">Verovio Humdrum Viewer</a>.
    Use the link in the score’s row to load that exercise.
  </li>
  <li>
    <strong>Start</strong>: the exercise’s starting measure in a combined
    score. Select the measure number to open the combined MusicXML file
    for the relevant part or species.
  </li>
  <li>
    <strong>Page</strong>: the printed page number in the source book.
    Where linked, select it to open the corresponding scanned PDF page.
  </li>
</ul>
<p>
We hope you enjoy this resource!
</p>
<p>
<a href="https://markgotham.github.io/" target="_blank" rel="noopener">Mark Gotham</a>,
on behalf of the fourscoreandmore.org team.
</p>
</div><span class="collection-tag">Scores · metadata · source scans</span></header>
{navigation}{combined}
<div class="controls"><div class="control search-control"><label for="search">Search exercises</label><input id="search" type="search" placeholder="Figure, correction, file ID…" autocomplete="off"></div>{part_filter}
<div class="control"><label for="species-filter">Species</label><select id="species-filter" data-filter="species"><option value="">All species</option>{options((s, f"Species {s}") for s in species_values)}</select></div>
<div class="control"><label for="final-filter">Modal final</label><select id="final-filter" data-filter="final"><option value="">All finals</option>{options((f, f.upper()) for f in final_values)}</select></div>
<button id="reset" class="reset" type="button">Reset</button></div>
<div class="status"><span id="result-count" role="status" aria-live="polite">{len(entries)} exercises</span><p class="legend">{legend} Click a column heading to sort.</p></div>
<div class="table-wrap"><table id="scores"><caption class="visually-hidden">{h(scope_title)}: individual exercises and downloads</caption><thead><tr>{"".join(columns)}</tr></thead><tbody>{"".join(rendered_rows)}</tbody></table></div>
<p id="empty" class="empty" hidden>No exercises match these filters. Try another search or reset.</p>
<div class="footer"><span>MXL: modern clefs · Orig.: original clefs · KRN: score · JSON: metadata</span><span>CF: cantus firmus · corr.: corrected · Page: printed book page</span></div>
<noscript><p>All exercises are listed. Enable JavaScript to search, filter and sort.</p></noscript>
</main><script>{JS}</script></body></html>'''


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".contents_", dir=path.parent) as temporary:
        staged = Path(temporary) / path.name
        staged.write_text(text, encoding="utf-8")
        os.replace(staged, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", nargs="?", default=".", help="corpus root, default current directory")
    parser.add_argument("--output-dir", type=Path, help="write HTML here; default corpus root")
    parser.add_argument("--raw-base-url", default=RAW_BASE, help="public raw repository root for file and VHV links")
    parser.add_argument("--absolute-links", action=argparse.BooleanOptionalAction, default=True,
                        help="use absolute raw file URLs (default); --no-absolute-links uses local relative paths")
    parser.add_argument("--page-base-url", help="optional HTML hosting URL for navigation between contents pages")
    parser.add_argument("--no-vhv", action="store_true", help="omit external viewer links")
    parser.add_argument("--catalogue-only", action="store_true", help="write the whole catalogue contents only.")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    output = args.output_dir.resolve() if args.output_dir else root
    if not root.is_dir():
        parser.error(f"corpus root does not exist: {root}")
    raw = urlsplit(args.raw_base_url)
    if (args.absolute_links or not args.no_vhv) and (raw.scheme not in ("http", "https") or not raw.netloc or raw.query or raw.fragment or raw.username or raw.password):
        parser.error("--raw-base-url must be an HTTP(S) repository URL without credentials, query or fragment")
    if args.page_base_url:
        hosted = urlsplit(args.page_base_url)
        if hosted.scheme not in ("http", "https") or not hosted.netloc or hosted.query or hosted.fragment or hosted.username or hosted.password:
            parser.error("--page-base-url must be an HTTP(S) URL without credentials, query or fragment")
    entries, errors = load_entries(root)
    statuses, aggregates, export_errors = load_exports(root)
    errors.extend(export_errors)
    if not entries:
        errors.append("no usable metadata found under I/II/III/spN/gap_*.json")
    for error in errors:
        print(f"ERROR {error}", file=sys.stderr)
    if not entries:
        return 1
    groups = defaultdict(list)
    for entry in entries:
        groups[(entry.book, None)].append(entry)
        groups[(entry.book, entry.section)].append(entry)
    page_paths = {(None, None): output / "species_contents.html"}
    for book, section in groups:
        number = PARTS[book][0]
        if not args.catalogue_only:
            page_paths[(book, section)] = output / book / section / f"ex{number}{section}.html" if section else output / book / f"ex{number}.html"
    part_starts = {}
    for book in PARTS:
        members = groups.get((book, None), [])
        if members:
            part_starts.update(aggregate_starts(Path(book) / f"ex{PARTS[book][0]}", members, root, statuses, aggregates))
    written = 0
    for (book, section), page in page_paths.items():
        members = groups[(book, section)] if book else entries
        if book:
            number = PARTS[book][0]
            stem = Path(book) / section / f"ex{number}{section}" if section else Path(book) / f"ex{number}"
            starts = aggregate_starts(stem, members, root, statuses, aggregates)
        else:
            starts = part_starts
        try:
            text = render_page(root, page, members, entries, page_paths, statuses, starts, args, book, section)
            atomic_write(page, text)
            written += 1
            print(f"WROTE {page.relative_to(output)} ({len(members)} exercises)")
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"{page}: {exc}")
            print(f"ERROR {page}: {exc}", file=sys.stderr)
    print(f"{written} contents pages; {len(entries)} individual exercises")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
