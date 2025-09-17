from __future__ import annotations
import math
import streamlit as st
import pandas as pd
from typing import Dict, Any, List, Tuple

# Make sure these imports match your file structure
from db.schema import get_vectorstore
from db.aliases import get_aliases_for, add_alias, remove_alias, set_aliases

st.set_page_config(page_title="SDS Library & Aliases", layout="wide")
st.title("📚 SDS Library — Viewer & Alias Editor")


@st.cache_data(show_spinner=False)
def _load_all_docs() -> Tuple[List[Dict[str, Any]], bool]:
    """Pull metadatas for all docs from Chroma. Falls back to a big similarity query if needed."""
    vdb = get_vectorstore()
    docs: List[Any] = []
    used_private_get = False
    try:
        raw = vdb._collection.get(include=["metadatas", "documents"], where=None)  # type: ignore[attr-defined]
        used_private_get = True
        for i, md in enumerate(raw.get("metadatas", []) or []):
            docs.append({"metadata": md, "text": (raw.get("documents", [""])[i] if raw.get("documents") else "")})
    except Exception:
        hits = vdb.similarity_search("Section", k=2000)
        docs = [{"metadata": h.metadata or {}, "text": h.page_content or ""} for h in hits]
    return docs, used_private_get


def _aggregate_materials(docs: List[Dict[str, Any]]) -> pd.DataFrame:
    by_mat: Dict[str, Dict[str, Any]] = {}
    for d in docs:
        md = d.get("metadata") or {}
        name = md.get("material_name", "unknown")
        if name not in by_mat:
            by_mat[name] = {
                "material_name": name,
                "manufacturer": md.get("manufacturer"),
                "catalog_no": md.get("catalog_no"),
                "revision_date": md.get("revision_date"),
                "cas": md.get("cas"),
                "n_chunks": 0,
                "n_pages_est": set(),
                "sections": set(),
                "paths": set(),
            }
        by_mat[name]["n_chunks"] += 1
        if md.get("page"): by_mat[name]["n_pages_est"].add(md.get("page"))
        if md.get("section"): by_mat[name]["sections"].add(md.get("section"))
        if md.get("source_path"): by_mat[name]["paths"].add(md.get("source_path"))
        for k in ("manufacturer", "catalog_no", "revision_date", "cas"):
            if not by_mat[name].get(k) and md.get(k):
                by_mat[name][k] = md.get(k)
    rows = []
    for name, agg in by_mat.items():
        rows.append({
            "material_name": name,
            "manufacturer": agg.get("manufacturer"),
            "catalog_no": agg.get("catalog_no"),
            "revision_date": agg.get("revision_date"),
            "cas": agg.get("cas"),
            "est_pages": len(agg["n_pages_est"]) or None,
            "sections_found": ", ".join(sorted(list(agg["sections"]))[:8]) + ("…" if len(agg["sections"]) > 8 else ""),
            "files": ", ".join(sorted(list(agg["paths"]))[:3]) + ("…" if len(agg["paths"]) > 3 else ""),
        })
    df = pd.DataFrame(sorted(rows, key=lambda r: r["material_name"].lower()))
    return df


def _display_material_details(material: str, docs: List[Dict[str, Any]]):
    """Displays the metadata, aliases, and sample chunks for a selected material."""
    sel_rows = df[df["material_name"] == material]
    if sel_rows.empty:
        st.warning("Selection not found.")
        return

    sel = sel_rows.iloc[0].to_dict()

    col_details, col_aliases = st.columns([2, 2])

    with col_details:
        st.markdown("### SDS Metadata")
        st.json({
            "material_name": sel["material_name"],
            "manufacturer": sel.get("manufacturer"),
            "catalog_no": sel.get("catalog_no"),
            "revision_date": sel.get("revision_date"),
            "cas": sel.get("cas"),
            "est_pages": sel.get("est_pages"),
            "files": sel.get("files"),
            "sections_found": sel.get("sections_found"),
        })

    with col_aliases:
        st.markdown("### Aliases")
        aliases = get_aliases_for(material)
        st.write("Current aliases:", ", ".join(aliases) if aliases else "—")

        # Use st.form for seamless updates without rerunning the whole app
        with st.form(key="alias_editor"):
            edited_aliases = st.text_area(
                "Add or remove aliases (comma-separated)",
                value=", ".join(aliases)
            )
            submit_button = st.form_submit_button("💾 Save Aliases")

            if submit_button:
                new_list = [x.strip() for x in edited_aliases.split(",") if x.strip()]
                set_aliases(material, new_list)
                st.success("Aliases saved successfully!")
                st.session_state.aliases_updated = True  # Trigger an update without full rerun

    with st.expander("🔎 View Sample Chunks"):
        vdb = get_vectorstore()
        steering = " Section 4 First Aid 6 Accidental Release 8 Exposure 7 Storage 5 Fire 10 Stability Reactivity"
        hits = vdb.similarity_search(f"{material} {steering}", k=10)
        rows = []
        for h in hits:
            md = h.metadata or {}
            rows.append({
                "section": md.get("section"),
                "page": md.get("page"),
                "preview": (h.page_content[:200] + "…") if h.page_content and len(h.page_content) > 200 else (
                            h.page_content or "")
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# Main app logic
docs, used_private = _load_all_docs()
df = _aggregate_materials(docs)

# ---- Sidebar for filters and configuration ----
with st.sidebar:
    st.subheader("Filter & Pages")
    search_query = st.text_input("Search material / CAS", "").strip().lower()
    page_size = st.number_input("Rows per page", 5, 100, 15, step=5)

    st.markdown("---")
    st.caption("Using private Chroma get: **{}**".format("yes" if used_private else "no"))
    if st.button("Reload Data", help="Reload all SDS data from the database"):
        st.cache_data.clear()
        st.experimental_rerun()

# Apply search filter
if search_query:
    mask = (
            df["material_name"].str.lower().str.contains(search_query, na=False) |
            df["manufacturer"].fillna("").str.lower().str.contains(search_query, na=False) |
            df["catalog_no"].fillna("").str.lower().str.contains(search_query, na=False) |
            df["cas"].fillna("").str.lower().str.contains(search_query, na=False)
    )
    df_filtered = df[mask].reset_index(drop=True)
else:
    df_filtered = df.copy()

# ---- Main content area ----
st.subheader("Materials Overview")
n_materials = len(df_filtered)
st.metric("Total Materials", n_materials)

# Pagination controls
pgs = max(1, math.ceil(n_materials / page_size))
page = st.number_input(f"Page (1 to {pgs})", min_value=1, max_value=pgs, value=1)
start, end = (page - 1) * page_size, page * page_size
st.dataframe(df_filtered.iloc[start:end], use_container_width=True, hide_index=True)

# ---- Details & Alias Editor Section ----
st.subheader("Material Details & Aliases")
materials_list = df_filtered["material_name"].tolist()
if not materials_list:
    st.info("No materials found with the current filter.")
    st.stop()

selected_material = st.selectbox("Select a Material to Edit", materials_list, index=0)
_display_material_details(selected_material, docs)