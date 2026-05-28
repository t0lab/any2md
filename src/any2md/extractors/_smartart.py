"""Shared SmartArt (OOXML diagram) parsing logic.

Both pptx and xlsx embed SmartArt via the same OOXML schema:
- Diagram data file (`dataN.xml`) — point list + connection list
- Diagram layout file (`layoutN.xml`) — visual layout template (used only for layout_kind detection)
- Diagram colors / quickStyle — ignored

Each shape (in pptx slides or xlsx drawings) references its diagram via a
`<dgm:relIds r:dm="..." r:lo="...">` element, where the relIds are resolved through
the host file's `_rels` directory.
"""
from __future__ import annotations

from typing import Any

from lxml import etree

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "dgm": "http://schemas.openxmlformats.org/drawingml/2006/diagram",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

# Substrings in <dgm:layoutNode @name="..."> → layout_kind. First match wins.
# Substrings are lowercased; we lowercase the name before checking.
LAYOUT_KIND_HINTS: list[tuple[str, str]] = [
    # Hierarchy / org chart
    ("hier", "hierarchy"),
    ("orgchart", "hierarchy"),
    ("organization", "hierarchy"),
    # Cycle
    ("cycle", "cycle"),
    ("circular", "cycle"),
    # Process / flow / arrows / steps
    ("process", "process"),
    ("flow", "process"),
    ("arrow", "process"),
    ("step", "process"),
    ("compost", "process"),
    ("lineartextimage", "process"),
    # List
    ("vlist", "list"),
    ("hlist", "list"),
    ("bullet", "list"),
    ("descendanttext", "list"),
    ("parenttext", "list"),
    # Matrix / relationship / pyramid
    ("matrix", "matrix"),
    ("relationship", "matrix"),
    ("pyramid", "matrix"),
]


def parse_rels(rels_xml: bytes) -> dict[str, str]:
    """Parse an OOXML `_rels` file into {relId: Target} mapping.

    Target paths are normalized to package-root paths (e.g. "../diagrams/data1.xml"
    appearing in `xl/drawings/_rels/drawing3.xml.rels` becomes "xl/diagrams/data1.xml").
    Caller passes the directory of the rels file so we can resolve relative paths.
    """
    out: dict[str, str] = {}
    try:
        tree = etree.fromstring(rels_xml)
        for rel in tree.findall("rel:Relationship", namespaces=NS):
            rid = rel.get("Id")
            target = rel.get("Target", "")
            if rid:
                out[rid] = target
    except Exception:
        pass
    return out


def normalize_rel_target(target: str, rels_file_dir: str) -> str:
    """Normalize a Target attribute from a rels file into a package-root path.

    Examples:
      target="../diagrams/data1.xml", rels_file_dir="xl/drawings"
        → "xl/diagrams/data1.xml"
      target="/xl/diagrams/data1.xml" (already absolute, leading slash)
        → "xl/diagrams/data1.xml"
      target="xl/diagrams/data1.xml" (already package-root)
        → unchanged
    """
    if target.startswith("/"):
        return target.lstrip("/")
    if target.startswith("../"):
        # Walk up from rels_file_dir
        parts = rels_file_dir.strip("/").split("/")
        rest = target
        while rest.startswith("../"):
            if parts:
                parts.pop()
            rest = rest[3:]
        return "/".join(parts + [rest]) if parts else rest
    if "/" not in target:
        # Same-directory reference
        return f"{rels_file_dir.rstrip('/')}/{target}" if rels_file_dir else target
    # Already a package-root-relative path
    return target


def parse_smartart_tree(data_xml: bytes) -> list[dict[str, Any]]:
    """Parse a diagrams/dataN.xml into a hierarchical node tree.

    Schema (simplified):
      - <dgm:ptLst><dgm:pt modelId="..." type="...">...<a:t>text</a:t>...
        type ∈ {"doc", "node", "asst", "parTrans", "sibTrans", "pres"}; we keep
        doc/node/asst as real nodes.
      - <dgm:cxnLst><dgm:cxn type="parOf" srcId="..." destId="..." srcOrd="..." destOrd="...">
        type defaults to "parOf" when absent (parent-child relationship).

    Returns a list of root nodes, each: {"text": str, "level": int, "children": [...]}.
    The 'doc' root is flattened away when it has no text — its children are lifted.
    """
    tree = etree.fromstring(data_xml)

    pt_info: dict[str, dict[str, Any]] = {}
    for pt in tree.xpath("//dgm:pt", namespaces=NS):
        mid = pt.get("modelId")
        if not mid:
            continue
        pt_type = pt.get("type") or "node"
        t_elems = pt.xpath(".//a:t", namespaces=NS)
        text = "".join(t.text or "" for t in t_elems).strip()
        pt_info[mid] = {"type": pt_type, "text": text}

    real_types = {"doc", "node", "asst"}

    # parent → ordered children
    children_of: dict[str, list[tuple[int, str]]] = {}
    for cxn in tree.xpath("//dgm:cxn", namespaces=NS):
        ctype = cxn.get("type") or "parOf"
        if ctype != "parOf":
            continue
        src = cxn.get("srcId")
        dest = cxn.get("destId")
        if not src or not dest:
            continue
        if pt_info.get(src, {}).get("type") not in real_types:
            continue
        if pt_info.get(dest, {}).get("type") not in real_types:
            continue
        try:
            ord_ = int(cxn.get("destOrd") or cxn.get("srcOrd") or 0)
        except ValueError:
            ord_ = 0
        children_of.setdefault(src, []).append((ord_, dest))

    for src in children_of:
        children_of[src].sort(key=lambda x: x[0])

    # Root: type='doc'; fallback to nodes not referenced as destinations
    roots = [mid for mid, info in pt_info.items() if info["type"] == "doc"]
    if not roots:
        referenced = {d for items in children_of.values() for _, d in items}
        roots = [
            mid for mid, info in pt_info.items()
            if mid not in referenced and info["type"] in real_types
        ]

    out: list[dict[str, Any]] = []
    visited: set[str] = set()

    def build(mid: str, level: int) -> dict[str, Any] | None:
        if mid in visited:
            return None
        visited.add(mid)
        info = pt_info.get(mid, {})
        kids: list[dict[str, Any]] = []
        for _, child_mid in children_of.get(mid, []):
            child = build(child_mid, level + 1)
            if child is not None:
                kids.append(child)
        return {"text": info.get("text", "").strip(), "level": level, "children": kids}

    for root_id in roots:
        root_node = build(root_id, 0)
        if root_node is None:
            continue
        # Flatten empty doc root: lift its children up
        if not root_node["text"] and root_node["children"]:
            for child in root_node["children"]:
                out.append(_renumber_levels(child, 0))
        else:
            out.append(root_node)

    # Fallback: flat list of all real-typed nodes with non-empty text
    if not out:
        for mid, info in pt_info.items():
            if info["type"] in real_types and info["text"]:
                out.append({"text": info["text"], "level": 0, "children": []})

    return out


def _renumber_levels(node: dict[str, Any], level: int) -> dict[str, Any]:
    node["level"] = level
    for c in node.get("children", []):
        _renumber_levels(c, level + 1)
    return node


def detect_layout_kind(layout_xml: bytes) -> str:
    """Inspect layoutNode names in a diagrams/layoutN.xml → return layout_kind hint."""
    try:
        tree = etree.fromstring(layout_xml)
        names = tree.xpath("//dgm:layoutNode/@name", namespaces=NS)
        combined = " ".join(n.lower() for n in names if n)
        for hint, kind in LAYOUT_KIND_HINTS:
            if hint in combined:
                return kind
    except Exception:
        pass
    return "other"
