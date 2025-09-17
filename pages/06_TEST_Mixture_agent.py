# File: streamlit.py

import streamlit as st
from db.query import _material_names, smart_search
from db.schema import get_vectorstore
from agent.mix_agent_test import analyze_mixture
from typing import List
import os
import re

st.set_page_config(
    page_title="Mixture Builder",
    layout="wide",
)

st.title("Mixture Builder")

st.markdown("""
    Select multiple materials from your SDS library to identify potential safety issues and get consolidated emergency guidance for a mixture.
""")

# --- GHS Pictogram mapping ---
GHS_PICTOGRAMS = {
    "Flammable": "static/ghs_signs/flammable.tif",
    "Corrosive": "static/ghs_signs/corrosive.tif",
    "Oxidizer": "static/ghs_signs/oxidizer.tif",
    "Irritant": "static/ghs_signs/irritant.tif",
    "Toxicity": "static/ghs_signs/toxic.tif",
    "Health Hazard": "static/ghs_signs/health_hazard.tif",
    "Explosive": "static/ghs_signs/explosive.tif",
    "Gas under pressure": "static/ghs_signs/gas.tif",
    "Environmental": "static/ghs_signs/environmental.tif",
}

# --- New Icon for "No Hazard" ---
NO_HAZARD_PICTOGRAM = "static/ghs_signs/safe.png"


def display_guidance_with_hazards(text: str):
    """
    Parses LLM output to display GHS pictograms and formats the text.
    """
    with st.expander("Show Consolidated Safety Guidance", expanded=True):
        st.subheader("Consolidated Safety Guidance")
        st.markdown("### 1. Hazards")

        with st.container():
            present_keywords = [
                (keyword, path)
                for keyword, path in GHS_PICTOGRAMS.items()
                if keyword.lower() in text.lower()
            ]

            if present_keywords:
                cols = st.columns(len(present_keywords))
                for i, (keyword, img_path) in enumerate(present_keywords):
                    with cols[i]:
                        try:
                            st.image(img_path, width=80, caption=keyword)
                        except Exception:
                            st.warning(f"Could not load image for: {keyword}")
            else:
                # --- NEW: Display a "No Hazard" icon if no keywords are found ---
                try:
                    st.image(NO_HAZARD_PICTOGRAM, width=80, caption="No Hazard Found")
                except Exception:
                    st.warning("Could not load the 'No Hazard' image.")
        st.markdown(text)


# --- NEW: Initialize session state for history ---
if 'analysis_history' not in st.session_state:
    st.session_state.analysis_history = []
if 'selected_analysis_index' not in st.session_state:
    st.session_state.selected_analysis_index = None

# --- NEW: Display previous tests in the sidebar ---
with st.sidebar:
    st.header("Previous Mixtures")
    if st.session_state.analysis_history:
        history_options = [
            f"Mixture: {', '.join(item['materials'])}" for item in st.session_state.analysis_history
        ]
        selected_option = st.selectbox(
            "Select a past analysis:",
            options=history_options,
            index=st.session_state.selected_analysis_index or 0,
            key='history_selector'
        )
        st.session_state.selected_analysis_index = history_options.index(selected_option)
    else:
        st.info("No mixtures analyzed yet.")

# -----------------------------------

# Retrieve all available materials from your database
vdb = get_vectorstore()
materials = sorted([m for m in _material_names(vdb) if m])

# Allow the user to select multiple materials
selected_materials = st.multiselect("Select materials for the mixture", options=materials)

if st.button("Analyze Mixture"):
    if len(selected_materials) < 2:
        st.warning("Please select at least two materials to analyze.")
    else:
        with st.spinner("Analyzing mixture..."):
            try:
                # Call the new, direct analysis function
                analysis_result = analyze_mixture(selected_materials)

                # --- NEW: Store the result in session state ---
                new_analysis_entry = {
                    "materials": selected_materials,
                    "result": analysis_result,
                }
                st.session_state.analysis_history.append(new_analysis_entry)

                # Set the selected index to the new entry
                st.session_state.selected_analysis_index = len(st.session_state.analysis_history) - 1

                # Re-run the app to update the display with the new entry selected
                st.rerun()

            except Exception as e:
                st.error(f"An error occurred: {e}")
                st.warning("Please try again or select different materials.")

# --- NEW: Display the selected analysis from history ---
if st.session_state.analysis_history:
    st.subheader("Analysis Results")
    current_analysis = st.session_state.analysis_history[st.session_state.selected_analysis_index]
    llm_summary = current_analysis['result'].get("response", "An error occurred during analysis.")

    display_guidance_with_hazards(llm_summary)

    with st.expander("Show Agent's Thought Process"):
        st.json(current_analysis['result'].get("thought_process", {}))