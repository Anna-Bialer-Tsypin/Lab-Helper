# File: pages/04_Mixture_Calculator.py

import streamlit as st
import json
from langchain.docstore.document import Document
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO

from db.query import _material_names, smart_search
from db.schema import get_vectorstore
from agent.llm_helper import summarize_guidance
from db.mixtures import save_mixture
from agent.agent_tools.calculator import unit_dilution_calculator as calculator_tool
from agent.agent_tools.chunk_summarizer import chunk_summarizer_tool
from components.molar_mass_search import render_molar_mass_search


# --- Helper function to create the PDF report ---
def create_pdf_report(mixture_name: str, total_final_volume: float, calculations: dict, llm_summary: str) -> BytesIO:
    """Generates a PDF report of the mixture calculations and safety plan."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Title
    story.append(Paragraph(f"<b>Mixture Report: {mixture_name}</b>", styles['Title']))
    story.append(Spacer(1, 12))

    # Total Volume
    story.append(Paragraph(f"<b>Total Final Volume:</b> {total_final_volume:.2f} mL", styles['Normal']))
    story.append(Spacer(1, 12))

    # Calculations
    story.append(Paragraph("<b>Calculaions</b>", styles['h2']))
    for item, calc_result in calculations.items():
        unit, value = list(calc_result.items())[0]
        story.append(Paragraph(f"<b>{item}</b>: {value:.4f} {unit}", styles['Normal']))
        story.append(Spacer(1, 6))

    story.append(Spacer(1, 12))

    # Safety Plan
    story.append(Paragraph("<b>Safety and Protective Methods</b>", styles['h2']))
    for line in llm_summary.split('\n'):
        story.append(Paragraph(line, styles['Normal']))

    doc.build(story)
    buffer.seek(0)
    return buffer


# --- State Management ---
if 'mixture_items' not in st.session_state:
    st.session_state.mixture_items = []

# Render the sidebar component (already imported from components/molar_mass_search.py)
render_molar_mass_search()

# --- UI for Core Mixture Info (placed at the top) ---
st.title("Mixture Calculator & Safety Plan")
st.markdown("""
    Create a new mixture by defining its total volume and components. The tool will calculate required volumes/masses and provide a consolidated safety plan.
""")

mixture_name = st.text_input("Name this mixture", value="My Mixture")
total_final_volume = st.number_input(
    "Total Final Volume of Mixture (mL)",
    min_value=0.01,
    format="%.2f",
    value=100.0
)
st.markdown("---")

# --- UI for Adding Materials (placed in a form) ---
vdb = get_vectorstore()
materials_list = sorted([m for m in _material_names(vdb) if m])
materials_list.insert(0, "Water")

st.subheader("Add Material to Mixture")
stock_type = st.radio("Stock Form", ["Liquid", "Powder"], key='stock_type_radio')

if stock_type == "Liquid":
    with st.form("liquid_material_form"):
        material_name = st.selectbox("Material Name", options=materials_list, key='liquid_material_name')
        stock_conc = st.text_input("Stock Concentration", key='liquid_stock_conc')
        stock_unit = st.selectbox("Stock Unit", ["M", "mM", "uM", "g/L", "mg/mL", "%"], key='liquid_stock_unit')
        final_conc = st.text_input("Desired Final Concentration", key='liquid_final_conc')
        final_unit = st.selectbox("Final Unit", ["M", "mM", "uM", "g/L", "mg/mL", "%"], key='liquid_final_unit')

        add_button = st.form_submit_button("Add to Mixture")

        if add_button:
            try:
                if not stock_conc or not final_conc:
                    st.error("Please enter both stock and final concentrations.")
                else:
                    new_item = {
                        "name": material_name,
                        "type": "liquid",
                        "stock_conc": float(stock_conc),
                        "stock_unit": stock_unit,
                        "final_conc": float(final_conc),
                        "final_unit": final_unit,
                        "molar_mass": None,
                        "mode": "solve_add_vol"
                    }
                    st.session_state.mixture_items.append(new_item)
                    st.success(f"Added {material_name} to the mixture.")
            except (ValueError, TypeError) as e:
                st.error(f"Invalid input: {e}")

else:  # stock_type == "Powder"
    with st.form("powder_material_form"):
        material_name = st.selectbox("Material Name", options=materials_list)
        final_conc = st.text_input("Desired Final Concentration (in molarity)")
        final_unit = st.selectbox("Final Unit", ["M", "mM", "uM"])

        molar_mass = st.number_input(
            "Molar Mass (g/mol)",
            min_value=0.01,
            format="%.2f",
            help="Copy the value from the sidebar after searching.",
            value=st.session_state.get('last_molar_mass', 0.01)
        )

        add_button = st.form_submit_button("Add to Mixture")

        if add_button:
            try:
                if not final_conc or not molar_mass:
                    st.error("Please enter both final concentration and molar mass.")
                else:
                    new_item = {
                        "name": material_name,
                        "type": "powder",
                        "stock_conc": None,
                        "stock_unit": None,
                        "final_conc": float(final_conc),
                        "final_unit": final_unit,
                        "molar_mass": molar_mass,
                        "mode": "solve_add_vol"
                    }
                    st.session_state.mixture_items.append(new_item)
                    st.success(f"Added {material_name} to the mixture.")
            except (ValueError, TypeError) as e:
                st.error(f"Invalid input: {e}")

st.markdown("---")

# --- Final Report Generation ---
if st.session_state.mixture_items:
    st.subheader("Current Mixture Components")
    st.table(st.session_state.mixture_items)

    if st.button("Generate Final Report"):
        st.subheader("Final Mixture Report")

        # 1. Calculation
        try:
            payload = {
                "items": [
                    {
                        **item,
                        "final_ml": total_final_volume
                    } for item in st.session_state.mixture_items
                ]
            }
            calculations_json = calculator_tool(json.dumps(payload))
            calculations = json.loads(calculations_json)
            st.markdown("#### Calculated Volumes/Masses to Add")
            total_added_volume = 0
            for item, calc_result in calculations.items():
                unit, value = list(calc_result.items())[0]
                st.info(f"**{item}**: {value:.4f} {unit}")
                if "add_vol" in unit:
                    total_added_volume += value

            if total_added_volume > 0:
                st.markdown(f"**Total Volume of Stocks to Add:** **{total_added_volume:.2f} mL**")
                st.markdown(
                    f"**Remaining Solvent (e.g., Water) to Add:** **{total_final_volume - total_added_volume:.2f} mL**")
        except Exception as e:
            st.error(f"Calculation failed: {e}")
            st.stop()

        # 2. Saving to database
        save_mixture(mixture_name, st.session_state.mixture_items)
        st.success(f"Mixture '{mixture_name}' saved to database!")
        st.markdown("---")

        # 3. Safety Analysis
        st.markdown("#### Safety & Protective Methods")
        retrieved_docs = []
        for item in st.session_state.mixture_items:
            material = item["name"]
            if material == "Water":
                continue

            docs_per_material = smart_search(
                f"{material} handling, protective equipment, and hazards",
                k=2, locked_material=material, tag="handling_and_storage"
            )
            docs_per_material += smart_search(
                f"{material} first aid measures",
                k=2, locked_material=material, tag="first_aid"
            )
            retrieved_docs.extend(docs_per_material)

        if not retrieved_docs:
            st.warning("No relevant SDS information found to generate a safety plan.")
        else:
            if len(retrieved_docs) > 10:
                st.info("Large mixture detected. Summarizing chunks to optimize LLM tokens.")
                summarize_prompt = """
                Summarize the key safety information from the following SDS excerpts.
                Focus on hazards, protective equipment, and emergency procedures.
                Context: {context}
                Summary:
                """
                chunk_texts = [d.page_content for d in retrieved_docs]
                summarized_context = chunk_summarizer_tool(chunk_texts, summarize_prompt)
                final_docs = [Document(page_content=summarized_context)]
            else:
                final_docs = retrieved_docs

            SAFETY_PROMPT = """
            You are a lab safety expert. Your task is to provide a consolidated safety plan for a mixture of materials.
            Based ONLY on the provided context, identify necessary protective methods, emergency procedures, and safety precautions.

            Instructions:
            1.  **Protective Methods:** List the required Personal Protective Equipment (PPE) for handling this mixture (e.g., gloves, goggles, lab coat).
            2.  **Emergency Procedures:** Summarize first-aid, fire-fighting, and spill cleanup guidance for the mixture.
            3.  **Handling:** Briefly list any special handling or storage precautions.

            Context (consolidated SDS excerpts):
            {context}

            Question:
            {question}

            Safety Plan:
            """
            llm_summary = summarize_guidance(
                question="Provide a safety plan for this mixture.",
                docs=final_docs,
                prompt_template=SAFETY_PROMPT
            )
            st.write(llm_summary)

            # --- Download Button for PDF ---
            pdf_bytes = create_pdf_report(mixture_name, total_final_volume, calculations, llm_summary)
            st.download_button(
                label="📥 Download Report as PDF",
                data=pdf_bytes,
                file_name=f"{mixture_name.replace(' ', '_')}_report.pdf",
                mime="application/pdf"
            )

            with st.expander("Show Raw SDS Sources"):
                unique_docs = []
                seen_metadata = set()
                for d in retrieved_docs:
                    identifier = (d.metadata.get('material_name'), d.metadata.get('page'))
                    if identifier not in seen_metadata:
                        unique_docs.append(d)
                        seen_metadata.add(identifier)
                for d in unique_docs:
                    md = d.metadata or {}
                    st.markdown(
                        f"- **{md.get('material_name', '?')}** | *{md.get('section_tag', '?')}* | p.{md.get('page', '?')}  \n> {d.page_content[:400]}…")