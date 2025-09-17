# File: pages/06_Mixture_Calculator.py

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
from agent.agent_tools.property_summarizer import get_material_properties as properties_tool
from components.molar_mass_search import render_molar_mass_search

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
                try:
                    st.image(NO_HAZARD_PICTOGRAM, width=80, caption="No Hazard Found")
                except Exception:
                    st.warning("Could not load the 'No Hazard' image.")
        st.markdown(text)


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
    story.append(Paragraph("<b>Calculations</b>", styles['h2']))
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
if 'last_molar_mass' not in st.session_state:
    st.session_state.last_molar_mass = 0.01

# --- UI for Core Mixture Info (placed at the top) ---
st.title("Mixture Calculator & Safety Plan")
st.markdown("""
    Create a new mixture by defining its total volume and components. The tool will calculate required volumes/masses and provide a consolidated safety plan.
""")

# --- New: Restart button and mixture name/volume ---
col1, col2 = st.columns([3, 1])
with col1:
    mixture_name = st.text_input("Name this mixture", value="My Mixture")
with col2:
    if st.button("Start New Mixture 🔄"):
        st.session_state.mixture_items = []
        st.rerun()  # Replaced st.experimental_rerun()

total_final_volume = st.number_input(
    "Total Final Volume of Mixture (mL)",
    min_value=0.01,
    format="%.2f",
    value=100.0
)
st.markdown("---")

# Render the sidebar component
render_molar_mass_search()

# --- UI for Adding Materials (placed in a form) ---
vdb = get_vectorstore()
materials_list = sorted([m for m in _material_names(vdb) if m])
materials_list.insert(0, "Water")

st.subheader("Add Material to Mixture")
material_name = st.selectbox("Material Name", options=materials_list, key='material_name_main')

stock_type = st.radio("Stock Form", ["Liquid", "Powder"], key='stock_type_radio')

# --- New: Checkbox to designate a liquid as a solvent ---
is_solvent = False
if stock_type == "Liquid":
    is_solvent = st.checkbox("Is this the solvent?", key='is_solvent_checkbox',
                             help="Check this if this liquid will be used to fill the remaining volume of the mixture.")

# --- Logic for non-solvent materials ---
if not is_solvent:
    calc_mode = st.radio(
        "Calculation Mode",
        ["Solve for added amount (volume/mass)", "I know the amount to add"],
        key="calc_mode_radio"
    )
    st.markdown("---")

    if stock_type == "Liquid":
        with st.form("liquid_material_form"):
            molar_mass_input = st.number_input(
                "Molar Mass (g/mol)",
                min_value=0.01,
                format="%.2f",
                help="Needed if converting between molarity and mass/volume units.",
                value=st.session_state.get('last_molar_mass', 0.01),
                key='liquid_molar_mass'
            )
            if calc_mode == "Solve for added amount (volume/mass)":
                stock_conc = st.text_input("Stock Concentration", key='liquid_stock_conc')
                stock_unit = st.selectbox("Stock Unit", ["M", "mM", "uM", "g/L", "mg/mL", "%"], key='liquid_stock_unit')
                final_conc = st.text_input("Desired Final Concentration", key='liquid_final_conc')
                final_unit = st.selectbox("Final Unit", ["M", "mM", "uM", "g/L", "mg/mL", "%"], key='liquid_final_unit')
                add_button_label = "Add to Mixture"
            else:
                stock_conc = st.text_input("Stock Concentration", key='liquid_stock_conc_2')
                stock_unit = st.selectbox("Stock Unit", ["M", "mM", "uM", "g/L", "mg/mL", "%"],
                                          key='liquid_stock_unit_2')
                added_amount = st.number_input("Amount to Add (mL)", min_value=0.01, format="%.2f",
                                               key='liquid_added_ml')
                final_unit = st.selectbox("Desired Final Unit (for display)", ["M", "mM", "uM", "g/L", "mg/mL", "%"],
                                          key='liquid_final_unit_2')
                add_button_label = "Calculate Final Concentration & Add"

            add_button = st.form_submit_button(add_button_label)

            if add_button:
                try:
                    if calc_mode == "Solve for added amount (volume/mass)":
                        if not stock_conc or not final_conc:
                            st.error("Please enter both stock and final concentrations.")
                            st.stop()
                        new_item = {
                            "name": material_name,
                            "type": "liquid",
                            "stock_conc": float(stock_conc),
                            "stock_unit": stock_unit,
                            "final_conc": float(final_conc),
                            "final_unit": final_unit,
                            "molar_mass": molar_mass_input,
                            "mode": "solve_add_vol",
                            "is_solvent": is_solvent
                        }
                    else:
                        if not stock_conc or not added_amount:
                            st.error("Please enter both stock concentration and the amount to add.")
                            st.stop()
                        new_item = {
                            "name": material_name,
                            "type": "liquid",
                            "stock_conc": float(stock_conc),
                            "stock_unit": stock_unit,
                            "added_ml": added_amount,
                            "final_unit": final_unit,
                            "molar_mass": molar_mass_input,
                            "mode": "solve_final_conc",
                            "is_solvent": is_solvent
                        }
                    st.session_state.mixture_items.append(new_item)
                    st.success(f"Added {material_name} to the mixture.")
                except (ValueError, TypeError) as e:
                    st.error(f"Invalid input: {e}")

    else:  # stock_type == "Powder"
        with st.form("powder_material_form"):
            molar_mass_input = st.number_input(
                "Molar Mass (g/mol)",
                min_value=0.01,
                format="%.2f",
                help="Copy the value from the sidebar after searching.",
                value=st.session_state.get('last_molar_mass', 0.01),
                key='powder_molar_mass'
            )

            if calc_mode == "Solve for added amount (volume/mass)":
                final_conc = st.text_input("Desired Final Concentration", key='powder_final_conc')
                final_unit = st.selectbox("Final Unit", ["M", "mM", "uM"], key='powder_final_unit')
                add_button_label = "Add to Mixture"
            else:
                added_amount = st.number_input("Mass to Add (mg)", min_value=0.01, format="%.2f", key='powder_added_mg')
                final_unit = st.selectbox("Desired Final Unit (for display)", ["M", "mM", "uM"],
                                          key='powder_final_unit_2')
                add_button_label = "Calculate Final Concentration & Add"

            add_button = st.form_submit_button(add_button_label)

            if add_button:
                try:
                    if calc_mode == "Solve for added amount (volume/mass)":
                        if not final_conc or not molar_mass_input:
                            st.error("Please enter both final concentration and molar mass.")
                            st.stop()
                        new_item = {
                            "name": material_name,
                            "type": "powder",
                            "final_conc": float(final_conc),
                            "final_unit": final_unit,
                            "molar_mass": molar_mass_input,
                            "mode": "solve_add_mass",
                            "is_solvent": is_solvent
                        }
                    else:
                        if not added_amount or not molar_mass_input:
                            st.error("Please enter both the amount to add and molar mass.")
                            st.stop()
                        new_item = {
                            "name": material_name,
                            "type": "powder",
                            "added_mg": added_amount,
                            "final_unit": final_unit,
                            "molar_mass": molar_mass_input,
                            "mode": "solve_final_conc",
                            "is_solvent": is_solvent
                        }

                    st.session_state.mixture_items.append(new_item)
                    st.success(f"Added {material_name} to the mixture.")
                except (ValueError, TypeError) as e:
                    st.error(f"Invalid input: {e}")

else:  # is_solvent is True
    # New logic for adding a solvent
    add_button = st.button("Add as Solvent")
    if add_button:
        # Check if another solvent already exists
        if any(item.get("is_solvent") for item in st.session_state.mixture_items):
            st.error("Only one solvent can be added per mixture. Please remove the existing solvent first.")
            st.stop()

        new_item = {
            "name": material_name,
            "type": "liquid",
            "is_solvent": True,
            "mode": "solvent",
            "added_ml": "auto"
        }
        st.session_state.mixture_items.append(new_item)
        st.success(f"Added {material_name} as the solvent.")

st.markdown("---")

# --- Final Report Generation ---
if st.session_state.mixture_items:
    st.subheader("Current Mixture Components")
    editable_df = st.data_editor(st.session_state.mixture_items,
                                 column_config={
                                     "name": st.column_config.TextColumn("Material"),
                                     "type": st.column_config.TextColumn("Form"),
                                     "stock_conc": st.column_config.NumberColumn("Stock Conc."),
                                     "stock_unit": st.column_config.TextColumn("Stock Unit"),
                                     "final_conc": st.column_config.NumberColumn("Final Conc."),
                                     "final_unit": st.column_config.TextColumn("Final Unit"),
                                     "molar_mass": st.column_config.NumberColumn("Molar Mass (g/mol)"),
                                     "mode": st.column_config.TextColumn("Mode"),
                                     "added_ml": st.column_config.NumberColumn("Added Vol (mL)"),
                                     "added_mg": st.column_config.NumberColumn("Added Mass (mg)"),
                                 },
                                 hide_index=True,
                                 num_rows="fixed")

    if editable_df != st.session_state.mixture_items:
        st.session_state.mixture_items = editable_df
        st.success("Mixture components updated!")
        st.rerun()  # Replaced st.experimental_rerun()

    if st.button("Generate Final Report"):
        st.subheader("Final Mixture Report")

        # 1. Calculation
        try:
            # Separate the solvent from the solutes
            solvent_item = next((item for item in st.session_state.mixture_items if item.get("is_solvent")), None)
            solute_items = [item for item in st.session_state.mixture_items if not item.get("is_solvent")]

            # Perform calculations for non-solvent items (solutes)
            payload = {
                "items": [
                    {
                        **item,
                        "final_ml": total_final_volume
                    } for item in solute_items
                ]
            }
            calculations_json = calculator_tool(json.dumps(payload))
            calculations = json.loads(calculations_json)

            st.markdown("#### Calculated Volumes/Masses to Add")
            total_added_volume = 0
            for item_name, calc_result in calculations.items():
                unit, value = list(calc_result.items())[0]
                st.info(f"**{item_name}**: {value:.4f} {unit}")
                # We only count liquid solutes for total volume
                solute_entry = next((item for item in solute_items if item['name'] == item_name), None)
                if solute_entry and solute_entry.get("type") == "liquid":
                    total_added_volume += value

            # Calculate and display the volume of the solvent to add
            if solvent_item:
                solvent_volume = total_final_volume - total_added_volume
                if solvent_volume < 0:
                    st.error(
                        f"The total volume of added solutes ({total_added_volume:.2f} mL) exceeds the final volume ({total_final_volume:.2f} mL). Please adjust your mixture.")
                    st.stop()
                else:
                    st.info(f"**{solvent_item['name']} to Add:** **{solvent_volume:.2f} mL**")
                    calculations[solvent_item['name']] = {"add_vol_ml": solvent_volume}
            else:
                st.warning("No solvent was specified. The sum of all components should equal the total volume.")


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
            # Exclude solvents that are just diluents from the safety search
            if item.get("is_solvent") and item["name"] in ["Water", "Ethanol", "Acetone", "DMSO"]:
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

            display_guidance_with_hazards(llm_summary)

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