# agent/agent_tools/retriever.py
import re
from typing import List, Dict, Any
from langchain.tools import tool
from db.query import smart_search
from db.aliases import resolve_alias

CAS_RE = re.compile(r"\b\d{2,7}-\d{2}-\d\b")
MATERIAL_LINE_RE = re.compile(r"(?im)^\s*material\s*:\s*(.+)$")

# Map question → section tag (only tags you actually index in ingest.py)
SECTION_HINTS = [
    (re.compile(r"\b(first aid|burn|splash|exposure|rinse|flush|wash|ingestion|inhalation|eye|skin)\b", re.I), "first_aid"),
    (re.compile(r"\b(spill|leak|accidental release|contain|absorb|neutralize|clean[-\s]?up)\b", re.I), "spill_response"),
    (re.compile(r"\b(fire|flame|extinguish|combustible|ignition)\b", re.I), "fire_fighting"),
]

def _infer_tag(question: str | None) -> str | None:
    q = question or ""
    for rx, tag in SECTION_HINTS:
        if rx.search(q):
            return tag
    return None  # storage/PPE/reactivity -> no dedicated tag in your index → leave None

def _extract_material(text: str) -> str | None:
    """Prefer explicit 'Material:' line; else CAS; else short alias-like token."""
    # 1) explicit line
    m = MATERIAL_LINE_RE.search(text or "")
    line = m.group(1).strip() if m else text.strip()

    # 2) CAS beats everything
    cas = CAS_RE.search(line)
    if cas:
        hit = resolve_alias(cas.group(0))
        if hit:
            return hit

    # 3) short alias (HF/HCl etc.)
    if len(line) <= 6:
        hit = resolve_alias(line)
        if hit:
            return hit

    # 4) broader exact alias/name resolution
    return resolve_alias(line) or None

@tool("sds_retriever")
def sds_retriever(query: str) -> List[Dict[str, Any]]:
    """
    Retrieve SDS chunks for the question. Understands:
      - 'Material: ...' lines
      - CAS numbers (e.g., 7664-39-3)
      - Short aliases (HF, HCl)
    Dynamically narrows to First Aid / Spill / Fire sections when the question implies them.
    Returns a list of dicts: {text, material, section, tag, page, source}.
    """
    material = _extract_material(query)
    tag = _infer_tag(query)

    # Primary search (strict when possible; your smart_search applies filters + reranks)
    docs = smart_search(query, k=8, locked_material=material, tag=tag)

    results: List[Dict[str, Any]] = []
    for d in docs:
        md = d.metadata or {}
        results.append({
            "text": d.page_content,
            "material": md.get("material_name"),
            "section": md.get("section"),
            "tag": md.get("section_tag"),
            "page": md.get("page"),
            "source": md.get("source_path"),
        })

    # Fallback: if a tag yielded 0, retry without tag (for storage/PPE/reactivity)
    if not results and tag:
        docs = smart_search(query, k=8, locked_material=material, tag=None)
        for d in docs:
            md = d.metadata or {}
            results.append({
                "text": d.page_content,
                "material": md.get("material_name"),
                "section": md.get("section"),
                "tag": md.get("section_tag"),
                "page": md.get("page"),
                "source": md.get("source_path"),
            })

    return results
