# db/aliases.py - Manages mapping of synonyms (HF, hydrofluoric acid, CAS numbers, etc.) to a canonical material.
#Tiny alias service backed by data/alias_index.json.
# Normalizes keys to lowercase, stores alias → material_name.
# Provides CRUD-ish helpers and a resolver with fallbacks (exact, contains/contained-in).
#👍 Thread-safe writes, easy to inspect, no DB dependency.
#⚠️ In-memory cache _cache never refreshes if the file changes outside this process.
# Consider an explicit reload() or time-based invalidation if you’ll edit it externally.

import json
import os
import threading
from typing import Dict, List, Optional, Tuple

# Storage: one flat mapping alias(lowercased) -> material_name (original case preserved)
_DATA_DIR = os.getenv("DATA_DIR", "data")
_ALIAS_PATH = os.path.join(_DATA_DIR, "alias_index.json")

_lock = threading.Lock()
_cache: Optional[Dict[str, str]] = None  # alias(lower) -> material_name


# ---------------- internals ----------------

def _ensure_dir() -> None:
    os.makedirs(os.path.dirname(_ALIAS_PATH), exist_ok=True)


def _load() -> Dict[str, str]:
    """Load alias map into memory (once) and return it."""
    global _cache
    if _cache is None:
        if os.path.exists(_ALIAS_PATH):
            with open(_ALIAS_PATH, "r", encoding="utf-8") as f:
                _cache = json.load(f)
        else:
            _cache = {}
    return _cache


def _save(data: Dict[str, str]) -> None:
    """Persist alias map to disk."""
    _ensure_dir()
    with open(_ALIAS_PATH, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(data.items())), f, ensure_ascii=False, indent=2)


def _norm(s: str) -> str:
    return s.strip().lower()


# ---------------- queries ----------------

def resolve_alias(q: str, known_materials: Optional[List[str]] = None) -> Optional[str]:
    """
    Return the canonical material_name for a query alias.
    1) Exact hit in alias index (case-insensitive).
    2) If not found and known_materials provided, try a lightweight fallback:
       - exact case-insensitive match to a known material
       - 'contains' / 'contained-in' loose match
    """
    if not q:
        return None
    q_norm = q.strip()
    if not q_norm:
        return None

    # 1) exact alias hit
    hit = _load().get(_norm(q_norm))
    if hit:
        return hit

    # 2) fallback against provided names
    if known_materials:
        q_up = q_norm.upper()
        # exact
        for name in known_materials:
            if q_up == name.upper():
                return name
        # loose contains / contained-in
        for name in known_materials:
            n_up = name.upper()
            if q_up in n_up or n_up in q_up:
                return name

    return None


def get_aliases_for(material_name: str) -> List[str]:
    """List all aliases currently mapped to this material (original alias case not stored)."""
    m = material_name.strip()
    return sorted([alias for alias, mat in _load().items() if mat == m])


def list_all_by_material() -> Dict[str, List[str]]:
    """Return a material->sorted aliases mapping (useful for admin/UI)."""
    out: Dict[str, List[str]] = {}
    for alias, mat in _load().items():
        out.setdefault(mat, []).append(alias)
    for mat in out:
        out[mat].sort()
    return out


# ---------------- mutations ----------------

def add_alias(material_name: str, alias: str) -> None:
    """Add/overwrite a single alias -> material mapping."""
    if not alias or not alias.strip():
        return
    with _lock:
        data = _load()
        data[_norm(alias)] = material_name.strip()
        _save(data)


def add_aliases(material_name: str, aliases: List[str]) -> None:
    """Add/overwrite multiple aliases for the same material."""
    with _lock:
        data = _load()
        m = material_name.strip()
        for a in aliases:
            if a and a.strip():
                data[_norm(a)] = m
        _save(data)


def remove_alias(alias: str, material_name: Optional[str] = None) -> bool:
    """
    Remove a single alias. If material_name is provided, only remove if it maps to that material.
    Returns True if removed, False if not present or material mismatch.
    """
    if not alias or not alias.strip():
        return False
    al = _norm(alias)
    with _lock:
        data = _load()
        if al not in data:
            return False
        if material_name is not None and data[al] != material_name.strip():
            return False
        del data[al]
        _save(data)
        return True


def move_alias(alias: str, new_material_name: str) -> bool:
    """
    Reassign an existing alias to a different material (create if missing).
    Returns True if changed/created.
    """
    if not alias or not alias.strip():
        return False
    al = _norm(alias)
    with _lock:
        data = _load()
        data[al] = new_material_name.strip()
        _save(data)
        return True


def rename_material(old_material: str, new_material: str) -> int:
    """
    Re-point all aliases that currently map to old_material so they map to new_material.
    Returns the number of aliases updated.
    """
    old = old_material.strip()
    new = new_material.strip()
    if not old or not new or old == new:
        return 0
    changed = 0
    with _lock:
        data = _load()
        for a, mat in list(data.items()):
            if mat == old:
                data[a] = new
                changed += 1
        _save(data)
    return changed


def set_aliases(material_name: str, aliases: List[str]) -> None:
    """
    Overwrite ALL aliases for this material with the provided list.
    (Removes any existing aliases that currently point to this material and not in 'aliases'.)
    """
    m = material_name.strip()
    with _lock:
        data = _load()
        # drop existing mappings to this material
        to_delete = [a for a, mat in data.items() if mat == m]
        for a in to_delete:
            del data[a]
        # add the new ones
        for a in aliases:
            if a and a.strip():
                data[_norm(a)] = m
        _save(data)


def save_aliases(material_name: str, aliases: List[str]) -> None:
    """
    Backwards-compatible union-add semantics (used by ingest).
    Adds aliases without removing existing ones for this material.
    """
    add_aliases(material_name, aliases)


# ---------------- utilities (optional) ----------------

def dump() -> Tuple[int, str]:
    """
    Utility for debugging / logging: returns (count, pretty_json_string)
    """
    data = _load()
    pretty = json.dumps(dict(sorted(data.items())), ensure_ascii=False, indent=2)
    return len(data), pretty
