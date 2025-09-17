# File: agent/agent_tools/calculator.py

import json
import re
import requests
from typing import Dict, List
from langchain.tools import tool


# --- PubChem API for Molar Mass ---
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


# Base units for normalization
UNIT_CONVERSIONS = {
    'M': 1, 'mM': 1e-3, 'uM': 1e-6,
    'g/L': 1, 'mg/mL': 1, 'ppm': 1e-3,
}


def _convert_to_base_units(val: float, unit: str) -> (float, str):
    """Converts a value to a base unit for calculation."""
    unit = unit.strip().replace("µM", "uM")

    if unit in ('M', 'mM', 'uM'):
        base_unit = 'M'
        return val * UNIT_CONVERSIONS[unit], base_unit
    if unit in ('g/L', 'mg/mL'):
        base_unit = 'mg/mL'
        return val, base_unit
    if unit == '%':
        # Assuming % w/v (grams per 100 mL) for conversion
        base_unit = 'g/100mL'
        return val, base_unit

    raise ValueError(f"Unsupported unit: {unit}")


def calculate_volume_to_add(stock_conc: float, stock_unit: str, final_conc: float, final_unit: str,
                            final_vol: float, molar_mass: float = None) -> float:
    """Calculates V1 from C1V1 = C2V2, with unit conversions."""
    s_val, s_unit = _convert_to_base_units(stock_conc, stock_unit)
    f_val, f_unit = _convert_to_base_units(final_conc, final_unit)

    # Normalize units to Molarity
    if s_unit != f_unit:
        if molar_mass is None:
            raise ValueError("Molar mass is required to convert between molar and mass-based units.")

        # Example conversion: convert final mass-based concentration to Molarity
        if f_unit == 'mg/mL':
            f_val = (f_val / 1000) / molar_mass  # mg/mL -> g/mL -> mol/mL
            f_unit = 'M'  # This is not strictly correct, but simplifies the calculation. Let's assume Molarity.
            f_val *= 1000  # mol/mL -> mol/L

        # Add more conversion logic here for other units if needed

    # Final calculation
    if s_val == 0:
        raise ValueError("Stock concentration cannot be zero.")

    return (f_val * final_vol) / s_val


def calculate_mass_to_add(final_conc: float, final_unit: str, final_vol: float, molar_mass: float) -> float:
    """Calculates mass (g) from concentration and volume."""
    f_val, f_unit = _convert_to_base_units(final_conc, final_unit)

    # Normalizing concentration to Molarity for calculation
    if f_unit != 'M':
        if f_unit == 'mg/mL':
            # This is a direct mass concentration, no molar mass needed for this step.
            return f_val * final_vol  # mg/mL * mL = mg. Let's return in grams.
            # return f_val * final_vol / 1000
        raise ValueError(
            "Mass calculation requires final concentration in molarity (M, mM, uM) or mass/volume (g/L, mg/mL).")

    final_vol_L = final_vol / 1000  # Convert mL to L
    return f_val * molar_mass * final_vol_L


# --- NEW FUNCTIONS for inverse calculation ---
def calculate_final_concentration_liquid(stock_conc: float, stock_unit: str, added_vol: float, final_vol: float,
                                         molar_mass: float) -> (float, str):
    """Calculates the final concentration when volume added is known."""
    s_val, s_unit = _convert_to_base_units(stock_conc, stock_unit)

    # Calculate C2 from C2 = C1V1 / V2
    calculated_final_conc_base_unit = (s_val * added_vol) / final_vol

    # We can't know the output unit without more information. Let's assume we want to return it in the base unit.
    return calculated_final_conc_base_unit, s_unit


def calculate_final_concentration_powder(added_mass: float, final_vol: float, molar_mass: float) -> (float, str):
    """Calculates the final molarity when mass added is known."""
    added_mass_g = added_mass / 1000  # Convert mg to g
    final_vol_L = final_vol / 1000  # Convert mL to L

    if molar_mass == 0:
        raise ValueError("Molar mass cannot be zero.")

    moles = added_mass_g / molar_mass
    final_molarity = moles / final_vol_L

    return final_molarity, 'M'


# --- The core logic function ---
def _calc(payload: Dict) -> Dict:
    out = {}
    for it in payload.get("items", []):
        final_vol = float(it["final_ml"])
        material_name = it["name"]

        # Handle the new 'mode' key
        mode = it.get("mode")

        if mode == "solve_add_vol":
            # Original liquid calculation
            out[material_name] = {
                "add_vol_ml": calculate_volume_to_add(
                    stock_conc=float(it["stock_conc"]),
                    stock_unit=it["stock_unit"],
                    final_conc=float(it["final_conc"]),
                    final_unit=it["final_unit"],
                    final_vol=final_vol,
                    molar_mass=it.get("molar_mass")
                )
            }
        elif mode == "solve_add_mass":
            # Original powder calculation
            try:
                # Use the API call instead of the local lookup
                molar_mass = get_molar_mass_from_pubchem(material_name)
            except ValueError:
                # Fallback to user-provided molar mass if API fails
                molar_mass = float(it["molar_mass"])

            out[material_name] = {
                "mass_to_add_g": calculate_mass_to_add(
                    final_conc=float(it["final_conc"]),
                    final_unit=it["final_unit"],
                    final_vol=final_vol,
                    molar_mass=molar_mass
                )
            }
        elif mode == "solve_final_conc":
            # New inverse calculation mode
            if it["type"] == "liquid":
                calculated_conc, calculated_unit = calculate_final_concentration_liquid(
                    stock_conc=float(it["stock_conc"]),
                    stock_unit=it["stock_unit"],
                    added_vol=float(it["added_ml"]),
                    final_vol=final_vol,
                    molar_mass=it.get("molar_mass")
                )
                out[material_name] = {
                    f"final_conc_{calculated_unit}": calculated_conc
                }

            elif it["type"] == "powder":
                calculated_conc, calculated_unit = calculate_final_concentration_powder(
                    added_mass=float(it["added_mg"]),
                    final_vol=final_vol,
                    molar_mass=float(it["molar_mass"])
                )
                out[material_name] = {
                    f"final_conc_{calculated_unit}": calculated_conc
                }
        else:
            raise ValueError(f"Unknown calculation mode: {mode}")

    return out


@tool("unit_dilution_calculator")
def unit_dilution_calculator(payload: str) -> str:
    """
    Computes required volumes for liquid stocks or masses for powder stocks.
    Can also compute final concentrations when the amount to add is known.

    Input (JSON string):
    Mode 'solve_add_vol': {"items":[{"name":"A","type":"liquid","stock_conc":1,"stock_unit":"M","final_conc":0.1,"final_unit":"M","final_ml":500, "mode":"solve_add_vol"}]}
    Mode 'solve_add_mass': {"items":[{"name":"B","type":"powder","final_conc":0.1,"final_unit":"M","final_ml":500,"molar_mass":58.44, "mode":"solve_add_mass"}]}
    Mode 'solve_final_conc' (Liquid): {"items":[{"name":"C","type":"liquid","stock_conc":1,"stock_unit":"M","final_unit":"M","final_ml":500,"added_ml":50, "mode":"solve_final_conc"}]}
    Mode 'solve_final_conc' (Powder): {"items":[{"name":"D","type":"powder","final_unit":"M","final_ml":500,"added_mg":500,"molar_mass":58.44, "mode":"solve_final_conc"}]}
    """
    try:
        data = json.loads(payload) if isinstance(payload, str) else payload
    except Exception:
        raise ValueError('Invalid JSON payload.')

    return json.dumps(_calc(data))