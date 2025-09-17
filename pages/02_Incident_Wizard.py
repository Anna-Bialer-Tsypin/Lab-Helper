# File: pages/02_Incident_Wizard.py

import streamlit as st
from db.query import _material_names, smart_search
from db.schema import get_vectorstore
# Import the new LLM helper
from agent.llm_helper import summarize_guidance

if "locked_material" not in st.session_state:
    st.session_state.locked_material = None

st.title("Incident Wizard")

st.markdown("""
    This tool helps you quickly find relevant safety and emergency information from your Safety Data Sheets (SDS).
    Select a material and a scenario to get specific guidance on first-aid, fire response, or spill cleanup.
""")

SCENARIO_MAP = {
    "First Aid": "first_aid",
    "Fire Response": "fire_fighting",
    "Spill Cleanup": "spill_response"
}

vdb = get_vectorstore()
materials = sorted([m for m in _material_names(vdb) if m])

m_sel = st.selectbox("Material involved", options=["(select)"] + materials, index=0)
if m_sel != "(select)":
    st.session_state.locked_material = m_sel

scenario = st.selectbox("Scenario", options=list(SCENARIO_MAP.keys()))
tag_to_search = SCENARIO_MAP[scenario]

details = st.text_area("What happened?", placeholder=f"Briefly describe the {scenario.lower()} incident…")

if st.button("Get Guidance"):
    q = f"{details}"
    docs = smart_search(q, k=6, locked_material=st.session_state.locked_material, tag=tag_to_search)

    unique_docs = []
    seen_metadata = set()
    for d in docs:
        identifier = (d.metadata.get('material_name'), d.metadata.get('page'), d.page_content[:100])
        if identifier not in seen_metadata:
            unique_docs.append(d)
            seen_metadata.add(identifier)

    # Get the LLM's summary
    llm_response = summarize_guidance(question=q, docs=unique_docs)

    st.markdown(f"**Locked material:** {st.session_state.locked_material or 'not locked'}")
    st.subheader("Summary")
    st.write(llm_response)

    st.subheader(f"{scenario} Excerpts")
    for d in unique_docs:
        md = d.metadata or {}
        st.markdown(f"- **{md.get('material_name','?')}** | *{md.get('section_tag','?')}* | p.{md.get('page','?')}  \n> {d.page_content[:400]}…")