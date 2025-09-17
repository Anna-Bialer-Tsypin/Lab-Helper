# db/query.py - Search helpers (smart_first_aid_search, smart_search) with reranking, alias resolution, and material locks.

import re
import sys
from typing import List, Dict, Any, Optional

from langchain.docstore.document import Document
from .schema import get_vectorstore
from .aliases import resolve_alias

CAS_RE = re.compile(r"\b\d{2,7}-\d{2}-\d\b")

def _as_chroma_where(flt: dict | None) -> Optional[Dict[str, Any]]:
    """Converts a dictionary filter to a Chroma-compatible query."""
    if not flt:
        return None
    if len(flt) == 1:
        k, v = next(iter(flt.items()))
        return {k: {"$eq": v}}
    return {"$and": [{k: {"$eq": v}} for k, v in flt.items()]}

def _material_names(vdb: Any) -> List[str]:
    """Retrieves all unique material names from the vector database."""
    col = getattr(vdb, "_collection", None)
    out = col.get(include=["metadatas"], limit=100000) if col else {"metadatas": []}
    return sorted({md.get("material_name") for md in out.get("metadatas", []) if md.get("material_name")})

def _rerank_by_terms(query: str, docs: List[Document], pos_terms: tuple = (), neg_terms: tuple = ()) -> List[Document]:
    """Reranks documents based on keyword, section, and material name matches."""
    q = query.lower()
    tokens = set(re.findall(r"[a-z]{2,}", q))
    pos = set(t.lower() for t in pos_terms) | tokens
    neg = set(t.lower() for t in neg_terms)

    vdb = get_vectorstore()
    try:
        names = _material_names(vdb)
        resolved_material = resolve_alias(query, names) if names else None
    except Exception as e:
        print(f"Warning: Could not resolve material names for reranking. {e}", file=sys.stderr)
        resolved_material = None

    scored = []
    for d in docs:
        text = (d.page_content or "")
        md = " ".join(str(v) for v in (d.metadata or {}).values())
        t = f"{text}\n{md}".lower()
        score = 0.0

        # Major boost for material name match
        if resolved_material and d.metadata.get("material_name") == resolved_material:
            score += 10.0

        # Minor boost for section tag match
        if "section_tag" in d.metadata and d.metadata["section_tag"] in pos_terms:
            score += 2.0

        # Keyword-based score
        score += sum(1 for w in pos if w in t) * 2.0
        score -= sum(1 for w in neg if w in t) * 1.5
        scored.append((score, d))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored]

def _strict_filter_from_query(vdb: Any, query: str, locked_material: str | None) -> Optional[Dict[str, str]]:
    """Return a strict Chroma filter when possible (CAS, locked material, alias)."""
    flt: Dict[str, str] = {}
    if locked_material:
        flt["material_name"] = locked_material
        return flt
    m = CAS_RE.search(query)
    if m:
        flt["cas"] = m.group(0)
        return flt
    try:
        names = _material_names(vdb)
        resolved = resolve_alias(query, names) if names else None
        if resolved:
            flt["material_name"] = resolved
            return flt
    except Exception as e:
        print(f"Warning: Alias resolution failed. {e}", file=sys.stderr)
        pass
    return None

def smart_first_aid_search(query: str, k: int = 6, locked_material: str | None = None) -> List[Document]:
    """Searches for first-aid information using a staged strategy."""
    vdb = get_vectorstore()
    base_filter = _strict_filter_from_query(vdb, query, locked_material)

    # Stage 1: Try with a strict filter if one exists.
    if base_filter:
        flt = {"section_tag": "first_aid"}
        flt.update(base_filter)
        docs = vdb.similarity_search(query, k=k, filter=_as_chroma_where(flt))
        return docs
    else:
        # Stage 2: Fallback to broader search and rerank.
        docs = vdb.similarity_search(query, k=k * 2, filter=_as_chroma_where({"section_tag": "first_aid"}))
        if not docs:
            # Final fallback: Unfiltered search
            docs = vdb.similarity_search(query, k=k * 2)
        return _rerank_by_terms(query, docs, pos_terms=["first aid"])


def smart_search(query: str, k: int = 6, locked_material: str | None = None, tag: str | None = None) -> List[Document]:
    """A general-purpose smart search with optional tag and material locking."""
    vdb = get_vectorstore()
    base_filter = _strict_filter_from_query(vdb, query, locked_material)

    # Stage 1: Try with a strict filter if one exists.
    if base_filter:
        flt = dict(base_filter)
        if tag:
            flt["section_tag"] = tag
        docs = vdb.similarity_search(query, k=k, filter=_as_chroma_where(flt))
        return docs
    else:
        # Stage 2: Fallback to broader search and rerank.
        flt = {"section_tag": tag} if tag else None
        docs = vdb.similarity_search(query, k=k * 2, filter=_as_chroma_where(flt))
        if not docs:
            # Final fallback: Unfiltered search
            docs = vdb.similarity_search(query, k=k * 2)
        return _rerank_by_terms(query, docs, pos_terms=[tag] if tag else [])