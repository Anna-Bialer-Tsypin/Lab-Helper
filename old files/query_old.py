
#“Smart” search helpers.
# _strict_filter_from_query builds a Chroma filter from: locked material → CAS in query → alias resolution.
# smart_first_aid_search prioritizes first-aid passages with strict filtering, then relaxes and re-ranks.
# smart_search generalizes with optional tag.
# A lightweight term-count reranker nudges relevant content up when filters aren’t strict.
# 👍 Good staged strategy: strict filter → tag → fallback + rerank. Material lock is exactly what you need to prevent cross-material bleed (HF vs FBS).
# ⚠️ Uses vdb._collection.get(...) to list materials (private attr); re-ranker is simple (works, but can be improved with material-name boosting/recency, etc.).

# db/query.py - Search helpers (smart_first_aid_search, smart_search) with reranking, alias resolution, and material locks.
import re
import pandas as pd
from .schema import get_vectorstore
from .aliases import resolve_alias

CAS_RE = re.compile(r"\b\d{2,7}-\d{2}-\d\b")

def _as_chroma_where(flt: dict | None):
    if not flt:
        return None
    if len(flt) == 1:
        k, v = next(iter(flt.items()))
        return {k: {"$eq": v}}
    return {"$and": [{k: {"$eq": v}} for k, v in flt.items()]}

def _material_names(vdb):
    col = getattr(vdb, "_collection", None)
    out = col.get(include=["metadatas"], limit=100000) if col else {"metadatas":[]}
    return sorted({md.get("material_name") for md in out.get("metadatas", []) if md.get("material_name")})

# ---- lightweight lexical reranker (only used when no strict filter) ----
def _rerank_by_terms(query, docs, pos_terms=(), neg_terms=()):
    q = query.lower()
    tokens = set(re.findall(r"[a-z]{2,}", q))
    pos = set(t.lower() for t in pos_terms) | tokens
    neg = set(t.lower() for t in neg_terms)
    scored = []
    for d in docs:
        text = (d.page_content or "")
        md = " ".join(str(v) for v in (d.metadata or {}).values())
        t = f"{text}\n{md}".lower()
        score = 0.0
        score += sum(1 for w in pos if w in t) * 2.0
        score -= sum(1 for w in neg if w in t) * 1.5
        scored.append((score, d))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored]

def _strict_filter_from_query(vdb, query: str, locked_material: str | None):
    """Return a Chroma filter dict when possible (CAS, locked material, alias)."""
    flt = {}
    if locked_material:
        flt["material_name"] = locked_material
        return flt
    m = CAS_RE.search(query)
    if m:
        flt["cas"] = m.group(0)
        return flt
    names = _material_names(vdb)
    resolved = resolve_alias(query, names) if names else None
    if resolved:
        flt["material_name"] = resolved
        return flt
    return None  # no strict filter possible

def smart_first_aid_search(query: str, k: int = 6, locked_material: str | None = None):
    vdb = get_vectorstore()
    base_filter = _strict_filter_from_query(vdb, query, locked_material)
    # 1) try: first aid + strict filter
    flt = {"section_tag": "first_aid"}
    if base_filter:
        flt.update(base_filter)
        docs = vdb.similarity_search(query, k=k, filter=_as_chroma_where(flt))
        if docs:
            return docs
    # 2) try: first aid only
    docs = vdb.similarity_search(query, k=k, filter=({"section_tag": "first_aid"}))
    if docs:
        # rerank gently in case wrong material snuck in
        if not base_filter:
            docs = _rerank_by_terms(query, docs, pos_terms=["first aid"])
        return docs
    # 3) last: unfiltered + rerank
    docs = vdb.similarity_search(query, k=k)
    return _rerank_by_terms(query, docs, pos_terms=["first aid"])

def smart_search(query: str, k: int = 6, locked_material: str | None = None, tag: str | None = None):
    vdb = get_vectorstore()
    base_filter = _strict_filter_from_query(vdb, query, locked_material)
    flt = dict(base_filter) if base_filter else {}
    if tag:
        flt["section_tag"] = tag
    if flt:
        docs = vdb.similarity_search(query, k=k, filter=_as_chroma_where(flt))
        if docs:
            return docs
    docs = vdb.similarity_search(query, k=k, filter=({"section_tag": tag}) if tag else None)
    if docs:
        if not base_filter:
            docs = _rerank_by_terms(query, docs)
        return docs
    docs = vdb.similarity_search(query, k=k)
    return _rerank_by_terms(query, docs)

