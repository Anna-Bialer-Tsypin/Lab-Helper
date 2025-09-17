# File: components/molar_mass_search.py

import streamlit as st
import requests

def get_molar_mass_from_pubchem(material_name: str) -> float:
    """Retrieves molar mass from PubChem's PUG REST API."""
    try:
        # Search for the compound by name
        search_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{material_name}/property/MolecularWeight/JSON"
        response = requests.get(search_url, timeout=5)
        response.raise_for_status()

        data = response.json()

        # Parse the JSON response
        prop_table = data['PropertyTable']['Properties'][0]
        molar_mass = prop_table['MolecularWeight']

        return float(molar_mass)
    except Exception as e:
        raise ValueError(f"Could not retrieve molar mass for {material_name} from PubChem. Error: {e}")

def render_molar_mass_search():
    st.sidebar.title("Molar Mass Search 🧪")

    search_query = st.sidebar.text_input("Enter Material Name", key="molar_mass_search_input")

    if st.sidebar.button("Search", key="molar_mass_search_button"):
        if search_query:
            try:
                molar_mass = get_molar_mass_from_pubchem(search_query)
                st.sidebar.success(f"Molar Mass for {search_query}: **{molar_mass:.2f} g/mol**")
                st.session_state['last_molar_mass'] = molar_mass
            except ValueError as e:
                st.sidebar.error(f"Error: {e}")
        else:
            st.sidebar.warning("Please enter a material name to search.")