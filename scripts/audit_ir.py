"""Audit IR outputs against unpacked source files.

Produces a comparison report at samples/_ir/AUDIT.md showing what's in the source
file vs what made it into ir.json.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from lxml import etree

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLES = REPO_ROOT / "samples"
IR_ROOT = SAMPLES / "_ir"
REPORT_PATH = IR_ROOT / "AUDIT.md"

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "dgm": "http://schemas.openxmlformats.org/drawingml/2006/diagram",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def section(title: str) -> str:
    return f"\n\n## {title}\n"


# ---------------- PPTX audit ----------------

def audit_pptx(source: Path, ir_dir: Path) -> str:
    out: list[str] = [f"## 1. {source.name}\n"]
    ir_path = ir_dir / "ir.json"
    ir = json.loads(ir_path.read_text(encoding="utf-8"))

    with zipfile.ZipFile(source) as z:
        names = z.namelist()
        slide_files = sorted(
            [n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)],
            key=lambda s: int(re.search(r"(\d+)", s).group(1)),
        )
        dgm_data_files = sorted([n for n in names if n.startswith("ppt/diagrams/data") and n.endswith(".xml")])
        dgm_layout_files = sorted([n for n in names if n.startswith("ppt/diagrams/layout") and n.endswith(".xml")])
        chart_files = sorted([n for n in names if n.startswith("ppt/charts/chart") and n.endswith(".xml")])
        media_files = sorted([n for n in names if n.startswith("ppt/media/")])

        out.append("### File structure (raw zip)\n")
        out.append(f"- Slides: {len(slide_files)}  ")
        out.append(f"- Diagram data files: {len(dgm_data_files)}  ")
        out.append(f"- Diagram layout files: {len(dgm_layout_files)}  ")
        out.append(f"- Chart files: {len(chart_files)}  ")
        out.append(f"- Media files: {len(media_files)}\n")

        # ---- Per-slide raw count
        out.append("\n### Per-slide raw shape count vs IR\n")
        out.append("| Slide | XML shapes | Text | Pic | Chart | SmartArt | Table | Connector | Group | IR shapes |")
        out.append("|---|---|---|---|---|---|---|---|---|---|")
        ir_slides = {s["index"]: s for s in ir.get("slides", [])}

        # Per slide _rels for diagram lookup
        slide_rels = {}
        for n in names:
            m = re.match(r"ppt/slides/_rels/slide(\d+)\.xml\.rels$", n)
            if m:
                slide_rels[int(m.group(1))] = z.read(n)

        smartart_unique_targets: set[str] = set()
        connectors_missed: list[tuple[int, str]] = []  # (slide, name)

        for idx, sf in enumerate(slide_files, start=1):
            xml = z.read(sf)
            tree = etree.fromstring(xml)
            counts = Counter()
            shapes_root = tree.findall(".//p:spTree", namespaces=NS)
            if not shapes_root:
                continue
            sp_tree = shapes_root[0]

            # text shapes
            for sp in sp_tree.findall("p:sp", namespaces=NS):
                counts["text"] += 1
            # pictures
            for pic in sp_tree.findall("p:pic", namespaces=NS):
                counts["pic"] += 1
            # graphic frames: chart / smartart / table
            for gf in sp_tree.findall("p:graphicFrame", namespaces=NS):
                gd = gf.find(".//a:graphicData", namespaces=NS)
                uri = gd.get("uri") if gd is not None else ""
                if "chart" in uri:
                    counts["chart"] += 1
                elif "diagram" in uri:
                    counts["smartart"] += 1
                    # Track which dataN.xml this resolves to via relId
                    rel = gd.find(".//dgm:relIds", namespaces=NS)
                    if rel is not None and idx in slide_rels:
                        dm_rid = rel.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}dm")
                        if dm_rid:
                            try:
                                rels_tree = etree.fromstring(slide_rels[idx])
                                for r in rels_tree.findall("rel:Relationship", namespaces=NS):
                                    if r.get("Id") == dm_rid:
                                        smartart_unique_targets.add(r.get("Target", ""))
                                        break
                            except Exception:
                                pass
                elif "table" in uri:
                    counts["table"] += 1
                else:
                    counts["other_gf"] += 1
            # connectors
            for cxn in sp_tree.findall("p:cxnSp", namespaces=NS):
                counts["connector"] += 1
                # Find their name
                cnv = cxn.find(".//p:cNvPr", namespaces=NS)
                name = cnv.get("name", "?") if cnv is not None else "?"
                connectors_missed.append((idx, name))
            # groups
            for grp in sp_tree.findall("p:grpSp", namespaces=NS):
                counts["group"] += 1

            total_xml = sum(counts.values())
            ir_slide = ir_slides.get(idx)
            ir_count = len(ir_slide["shapes"]) if ir_slide else 0
            out.append(
                f"| {idx} | {total_xml} | {counts['text']} | {counts['pic']} | "
                f"{counts['chart']} | {counts['smartart']} | {counts['table']} | "
                f"{counts['connector']} | {counts['group']} | {ir_count} |"
            )

        # ---- SmartArt analysis
        out.append("\n### SmartArt analysis\n")
        out.append(f"- Unique diagram data files referenced via rels: **{len(smartart_unique_targets)}**")
        out.append(f"- Total diagram data XMLs in zip: **{len(dgm_data_files)}**")
        out.append(f"- IR shows **{sum(1 for s in ir.get('slides', []) for sh in s['shapes'] if sh.get('type') == 'smartart')}** SmartArt shapes total\n")
        if smartart_unique_targets:
            out.append("\nUnique targets:\n")
            for t in sorted(smartart_unique_targets):
                out.append(f"  - `{t}`")

        # Read first data file and count nodes
        if dgm_data_files:
            sample_data = z.read(dgm_data_files[0])
            tree = etree.fromstring(sample_data)
            node_texts = []
            for pt in tree.xpath("//dgm:pt", namespaces=NS):
                if pt.get("type") in ("pres", "presOf", "asst"):
                    continue
                ts = pt.xpath(".//a:t", namespaces=NS)
                text = "".join(t.text or "" for t in ts).strip()
                if text:
                    node_texts.append(text)
            out.append(f"\nFirst data file (`{dgm_data_files[0]}`) has **{len(node_texts)}** node texts:")
            for t in node_texts[:15]:
                out.append(f"  - {t!r}")
            if len(node_texts) > 15:
                out.append(f"  - ... and {len(node_texts) - 15} more")

        # ---- Connectors analysis
        out.append("\n### Connectors analysis\n")
        if connectors_missed:
            ir_connector_count = sum(1 for s in ir.get('slides', []) for sh in s['shapes'] if sh.get('type') == 'connector')
            out.append(f"- Raw connectors in XML: **{len(connectors_missed)}**")
            out.append(f"- IR detected connectors (top-level): **{ir_connector_count}**")
            if ir_connector_count < len(connectors_missed):
                out.append(f"- **GAP**: {len(connectors_missed) - ir_connector_count} connectors missed (likely inside groups or because cxnSp tag not detected)")
            out.append("\nFirst 10 connectors:")
            for s, n in connectors_missed[:10]:
                out.append(f"  - slide {s}: `{n}`")
        else:
            out.append("- No `cxnSp` elements in any slide → no connectors in this deck")

        # ---- Text content coverage
        out.append("\n### Text content coverage\n")
        # Count text characters in raw XML vs IR
        raw_text_chars = 0
        for sf in slide_files:
            xml = z.read(sf)
            tree = etree.fromstring(xml)
            for t in tree.xpath("//a:t", namespaces=NS):
                raw_text_chars += len(t.text or "")
        ir_text_chars = 0
        for s in ir.get("slides", []):
            for shp in s["shapes"]:
                if shp.get("type") == "text":
                    for p in shp.get("paragraphs", []):
                        for r in p.get("runs", []):
                            ir_text_chars += len(r.get("text", ""))
                elif shp.get("type") == "table":
                    for row in shp.get("rows", []):
                        for cell in row:
                            ir_text_chars += len(cell or "")
                elif shp.get("type") == "chart":
                    ir_text_chars += sum(len(c) for c in shp.get("categories", []))
                    ir_text_chars += sum(len(s.get("name", "") or "") for s in shp.get("series", []))
                elif shp.get("type") == "smartart":
                    for n in shp.get("nodes", []):
                        ir_text_chars += len(n.get("text", ""))
        out.append(f"- Raw text chars in slide XMLs: **{raw_text_chars}**")
        out.append(f"- IR-captured text chars: **{ir_text_chars}**")
        pct = 100 * ir_text_chars / raw_text_chars if raw_text_chars else 0
        out.append(f"- Coverage: **{pct:.1f}%**")

    return "\n".join(out)


# ---------------- XLSX audit ----------------

def audit_xlsx(source: Path, ir_dir: Path) -> str:
    out: list[str] = [f"## 2. {source.name}\n"]
    ir = json.loads((ir_dir / "ir.json").read_text(encoding="utf-8"))

    with zipfile.ZipFile(source) as z:
        names = z.namelist()
        sheet_files = sorted([n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n)])
        shared_strings_file = "xl/sharedStrings.xml"
        drawing_files = sorted([n for n in names if n.startswith("xl/drawings/") and n.endswith(".xml")])
        chart_files = sorted([n for n in names if n.startswith("xl/charts/") and n.endswith(".xml")])
        media_files = sorted([n for n in names if n.startswith("xl/media/")])
        diagram_data_files = sorted([n for n in names if n.startswith("xl/diagrams/data") and n.endswith(".xml")])

        out.append("### File structure (raw zip)\n")
        out.append(f"- Worksheets: {len(sheet_files)}  ")
        out.append(f"- Drawing files: {len(drawing_files)}  ")
        out.append(f"- Chart files: {len(chart_files)}  ")
        out.append(f"- Diagram data files: {len(diagram_data_files)}  ")
        out.append(f"- Media files: {len(media_files)}  ")
        out.append(f"- sharedStrings.xml: {'yes' if shared_strings_file in names else 'no'}\n")

        # Per-sheet raw stats
        out.append("\n### Per-sheet shape inventory\n")
        out.append("| Sheet idx | XML cell count | Merged ranges | Drawing? | Charts in sheet | SmartArts in drawing | IR tables | IR images | IR charts | IR smartart |")
        out.append("|---|---|---|---|---|---|---|---|---|---|")

        # workbook.xml maps sheetN to name
        wb_xml = z.read("xl/workbook.xml")
        wb_tree = etree.fromstring(wb_xml)
        sheet_names = [s.get("name") for s in wb_tree.findall(".//s:sheet", namespaces=NS)]

        ir_sheets = {s["index"]: s for s in ir.get("sheets", [])}

        for i, sf in enumerate(sheet_files, start=1):
            xml = z.read(sf)
            tree = etree.fromstring(xml)
            cells = tree.xpath("//s:c", namespaces=NS)
            merged = tree.xpath("//s:mergeCell", namespaces=NS)
            drawing_ref = tree.find(".//s:drawing", namespaces=NS) is not None

            # Find drawing target for this sheet from sheet rels
            sheet_rels_path = f"xl/worksheets/_rels/sheet{i}.xml.rels"
            drawing_path: str | None = None
            if sheet_rels_path in names:
                try:
                    sr = etree.fromstring(z.read(sheet_rels_path))
                    for r in sr.findall("rel:Relationship", namespaces=NS):
                        t = r.get("Target", "")
                        if "drawings/drawing" in t:
                            # Normalize
                            if t.startswith("/"):
                                drawing_path = t.lstrip("/")
                            elif t.startswith("../"):
                                drawing_path = "xl/" + t[3:]
                            else:
                                drawing_path = t
                            break
                except Exception:
                    pass

            # Inspect drawing for charts and smartarts
            charts_in_sheet = 0
            smartarts_in_sheet = 0
            if drawing_path and drawing_path in names:
                # Charts via drawing's _rels
                dr_path = drawing_path.rsplit("/", 1)[0] + "/_rels/" + drawing_path.rsplit("/", 1)[1] + ".rels"
                if dr_path in names:
                    try:
                        rtree = etree.fromstring(z.read(dr_path))
                        for r in rtree.findall("rel:Relationship", namespaces=NS):
                            t = r.get("Type", "")
                            if "chart" in t:
                                charts_in_sheet += 1
                            if "diagramData" in t:
                                smartarts_in_sheet += 1
                    except Exception:
                        pass

            ir_sheet = ir_sheets.get(i, {})
            ir_tables = len(ir_sheet.get("tables", []))
            ir_images = len(ir_sheet.get("images", []))
            ir_charts = len(ir_sheet.get("charts", []))
            ir_smartart = len(ir_sheet.get("smartart", []))
            out.append(
                f"| {i} ({sheet_names[i-1] if i-1 < len(sheet_names) else '?'}) | "
                f"{len(cells)} | {len(merged)} | {'yes' if drawing_ref else 'no'} | "
                f"{charts_in_sheet} | {smartarts_in_sheet} | "
                f"{ir_tables} | {ir_images} | {ir_charts} | {ir_smartart} |"
            )

        # ---- Header detection accuracy: look at sheet 1 raw rows
        out.append("\n### Header detection accuracy (sheet 1)\n")
        if sheet_files:
            xml = z.read(sheet_files[0])
            tree = etree.fromstring(xml)
            # shared strings
            shared = []
            if shared_strings_file in names:
                ss_tree = etree.fromstring(z.read(shared_strings_file))
                for si in ss_tree.findall("s:si", namespaces=NS):
                    parts = [t.text or "" for t in si.findall(".//s:t", namespaces=NS)]
                    shared.append("".join(parts))
            # First 5 rows
            rows = tree.xpath("//s:row[position()<=5]", namespaces=NS)
            out.append("\nFirst 5 rows (raw values):")
            for r in rows:
                row_idx = r.get("r")
                vals = []
                for c in r.findall("s:c", namespaces=NS):
                    t = c.get("t")
                    v_el = c.find("s:v", namespaces=NS)
                    v = v_el.text if v_el is not None else ""
                    if t == "s":
                        try:
                            v = shared[int(v)]
                        except Exception:
                            pass
                    vals.append(str(v)[:30])
                out.append(f"  - Row {row_idx}: {vals}")
            out.append("\nIR header_row picked (sheet 1):")
            if ir.get("sheets") and ir["sheets"][0].get("tables"):
                h = ir["sheets"][0]["tables"][0].get("header_row")
                out.append(f"  - {h}")

    return "\n".join(out)


# ---------------- PDF audit ----------------

def audit_pdf(source: Path, ir_dir: Path) -> str:
    import pymupdf  # type: ignore[import-not-found]
    out: list[str] = [f"## {source.name}\n"]
    ir = json.loads((ir_dir / "ir.json").read_text(encoding="utf-8"))

    doc = pymupdf.open(source)
    out.append("### Raw PDF structure (pymupdf)\n")
    out.append(f"- Total pages: **{doc.page_count}**")
    out.append(f"- Encrypted: {doc.needs_pass}")
    out.append(f"- IR page_count: {ir.get('page_count')}")
    out.append(f"- IR is_scanned: {ir.get('is_scanned')}")

    out.append("\n### Per-page audit\n")
    out.append("| Page | Raw text chars | Raw images | Raw tables | IR text blocks | IR images | IR tables | Notes |")
    out.append("|---|---|---|---|---|---|---|---|")

    ir_pages = {p["index"]: p for p in ir.get("pages", [])}
    total_raw_text = 0
    total_ir_text = 0

    for page in doc:
        idx = page.number + 1
        raw_text = page.get_text("text") or ""
        raw_text_chars = len(raw_text)
        total_raw_text += raw_text_chars
        raw_images = len(page.get_images(full=True))
        try:
            raw_tables = len(page.find_tables().tables)
        except Exception:
            raw_tables = 0

        ir_page = ir_pages.get(idx, {})
        ir_text_blocks = len(ir_page.get("text_blocks", []))
        ir_text_chars = sum(len(tb.get("text", "")) for tb in ir_page.get("text_blocks", []))
        total_ir_text += ir_text_chars
        ir_images = len(ir_page.get("images_on_page", []))
        ir_tables = len(ir_page.get("tables", []))

        notes = []
        if raw_text_chars > 0 and ir_text_chars < raw_text_chars * 0.5:
            notes.append("text under-capture")
        if raw_images != ir_images:
            notes.append(f"img diff ({raw_images}->{ir_images})")
        if raw_tables != ir_tables:
            notes.append(f"table diff ({raw_tables}->{ir_tables})")

        out.append(
            f"| {idx} | {raw_text_chars} | {raw_images} | {raw_tables} | "
            f"{ir_text_blocks} ({ir_text_chars}c) | {ir_images} | {ir_tables} | "
            f"{', '.join(notes) or 'OK'} |"
        )

    out.append(f"\n- **Total raw text chars**: {total_raw_text}")
    out.append(f"- **Total IR-captured text chars**: {total_ir_text}")
    pct = 100 * total_ir_text / total_raw_text if total_raw_text else 0
    out.append(f"- **Coverage**: {pct:.1f}%")

    doc.close()
    return "\n".join(out)


# ---------------- HTML audit ----------------

def audit_html(source: Path, ir_dir: Path) -> str:
    out: list[str] = [f"## 5. {source.name}\n"]
    size = source.stat().st_size
    out.append(f"- File size: {size} bytes")
    if size == 0:
        out.append("- File is empty → IR correctly emits 0 blocks + 1 warning")
        return "\n".join(out)
    # If non-empty, do BS4 audit similar to extractor
    text = source.read_text(encoding="utf-8", errors="replace")
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(text, "lxml")
    raw_headings = sum(len(soup.find_all(t)) for t in ("h1","h2","h3","h4","h5","h6"))
    raw_paragraphs = len(soup.find_all("p"))
    raw_images = len(soup.find_all("img"))
    raw_tables = len(soup.find_all("table"))
    ir = json.loads((ir_dir / "ir.json").read_text(encoding="utf-8"))
    ir_blocks = ir.get("blocks", [])
    out.append(f"- Raw: {raw_headings} headings, {raw_paragraphs} paragraphs, {raw_images} images, {raw_tables} tables")
    out.append(f"- IR blocks: {len(ir_blocks)}")
    return "\n".join(out)


# ---------------- main ----------------

def main() -> int:
    report = ["# IR Audit Report\n"]
    report.append(f"Generated by `scripts/audit_ir.py` against samples in `{SAMPLES}`.\n")

    samples_map = {
        "logic_tree_lending.pptx": ("pptx", audit_pptx),
        "logic_tree_lending.xlsx": ("xlsx", audit_xlsx),
        "c4611_sample_explain.pdf": ("pdf", audit_pdf),
        "Naac_appLetter.pdf": ("pdf", audit_pdf),
        "test.html": ("html", audit_html),
    }

    for i, (name, (fmt, fn)) in enumerate(samples_map.items(), start=1):
        src = SAMPLES / name
        ir_dir = IR_ROOT / f"{src.stem}.{fmt}"
        if not src.exists():
            report.append(f"\n## {name} — MISSING\n")
            continue
        try:
            block = fn(src, ir_dir)
            report.append("\n" + block)
        except Exception as e:
            import traceback
            report.append(f"\n## {name} — AUDIT FAILED\n```\n{traceback.format_exc()}\n```\n")

    REPORT_PATH.write_text("\n".join(report), encoding="utf-8")
    print(f"Report written to {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
