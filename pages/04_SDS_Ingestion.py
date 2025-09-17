import streamlit as st
import os
import tempfile
from db.ingest import ingest_file
from db.aliases import set_aliases

# Define the target directory for SDS files
SDS_DIR = "data/sds"
os.makedirs(SDS_DIR, exist_ok=True)

st.set_page_config(page_title="SDS Ingestion", layout="wide")
st.title("➕ Add New SDS Documents")
st.caption("Upload new SDS documents and provide metadata for accurate search.")


def _ingest_file_with_metadata(uploaded_file, material_name, aliases, revision_date, manufacturer):
    """Processes a single uploaded file with user-provided metadata."""
    try:
        # Save the uploaded file to the final directory
        final_file_path = os.path.join(SDS_DIR, uploaded_file.name)
        with open(final_file_path, "wb") as f:
            f.write(uploaded_file.getvalue())

        # Call the ingest function with the material name, aliases, revision date, and manufacturer
        chunks_added = ingest_file(final_file_path, material_name, aliases, revision_date, manufacturer)

        st.success(f"Successfully processed and saved '{uploaded_file.name}'!")
        st.success(f"Material Name: {material_name}")
        st.success(f"Aliases: {', '.join(aliases) if aliases else 'None'}")
        st.success(f"Revision Date: {revision_date or 'Not specified'}")
        st.success(f"Manufacturer: {manufacturer or 'Not specified'}")
        st.info(f"Added {chunks_added} chunks to the knowledge base.")

    except Exception as e:
        st.error(f"Failed to process '{uploaded_file.name}': {e}")


# Main UI
st.subheader("1. Upload Files")
uploaded_files = st.file_uploader(
    "Choose SDS PDF files",
    type="pdf",
    accept_multiple_files=True
)

if uploaded_files:
    st.subheader("2. Enter Details for Each File")

    # Use a form to capture details for all files at once
    with st.form(key="ingestion_form"):
        material_details = []
        for i, uploaded_file in enumerate(uploaded_files):
            st.markdown(f"**File {i + 1}: {uploaded_file.name}**")
            material_name = st.text_input(
                "Material Name",
                key=f"material_name_{i}",
                help="This name will be used as the primary identifier.",
                value=os.path.splitext(uploaded_file.name)[0]  # Pre-fill with the file name
            )
            aliases = st.text_input(
                "Aliases (comma-separated)",
                key=f"aliases_{i}",
                help="Add common names or abbreviations for better searchability."
            )
            revision_date = st.text_input(
                "Revision Date (optional)",
                key=f"revision_date_{i}",
                help="Manually specify the date (e.g., 'YYYY-MM-DD')."
            )
            manufacturer = st.text_input(
                "Manufacturer (optional)",
                key=f"manufacturer_{i}",
                help="A concise name for the company (e.g., 'Sigma-Aldrich')."
            )

            material_details.append({
                "file": uploaded_file,
                "name": material_name,
                "aliases": [a.strip() for a in aliases.split(',') if a.strip()],
                "revision_date": revision_date.strip() or None,
                "manufacturer": manufacturer.strip() or None
            })
            st.markdown("---")

        submit_button = st.form_submit_button("Ingest All Files", type="primary", use_container_width=True)

    if submit_button:
        with st.spinner("Processing documents..."):
            for details in material_details:
                _ingest_file_with_metadata(
                    details["file"],
                    details["name"],
                    details["aliases"],
                    details["revision_date"],
                    details["manufacturer"]
                )
        st.balloons()