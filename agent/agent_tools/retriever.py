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
    return None

@tool("sds_retriever")
def sds_retriever(query: str, material_name: str) -> List[Dict[str, Any]]:
    """
    Retrieve SDS chunks for a specific material. The `material_name` input must be the exact name of the material.
    Dynamically narrows to First Aid / Spill / Fire sections when the query implies them.
    Returns a list of dicts: {text, material, section, tag, page, source}.
    """
    # We no longer need to extract the material from the query string.
    # The agent will now be responsible for providing the exact material_name.
    tag = _infer_tag(query)

    # Primary search (strict when possible; your smart_search applies filters + reranks)
    # The `locked_material` is now the explicit `material_name` input
    docs = smart_search(query, k=8, locked_material=material_name, tag=tag)

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

    # Fallback: if a tag yielded 0, retry without tag
    if not results and tag:
        docs = smart_search(query, k=8, locked_material=material_name, tag=None)
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