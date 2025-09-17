# File: calculator.py (Updated)

import json
import re
from typing import Dict, List
from langchain.tools import tool

# Base units for normalization
UNIT_CONVERSIONS = {
    'M': 1, 'mM': 1e-3, 'uM': 1e-6,
    'g/L': 1, 'mg/mL': 1, 'ppm': 1e-3,  # assuming ppm is equivalent to mg/L
}


def _convert_to_base_units(val: float, unit: str) -> (float, str):
    """Converts a value to a base unit for calculation."""
    unit = unit.strip().replace("µM", "uM").replace("g/L", "mg/mL")
    if unit in ('M', 'mM', 'uM'):
        base_unit = 'M'
        return val * UNIT_CONVERSIONS[unit], base_unit
    if unit in ('g/L', 'mg/mL', 'ppm'):
        base_unit = 'mg/mL'
        if unit == 'ppm':  # assuming ppm is mg/L
            return val * UNIT_CONVERSIONS['ppm'], base_unit
        return val, base_unit
    raise ValueError(f"Unsupported unit: {unit}")


def _convert_from_base_units(val: float, base_unit: str, target_unit: str) -> float:
    """Converts a base unit value to a target unit."""
    target_unit = target_unit.strip().replace("µM", "uM")
    if base_unit == 'M' and target_unit in UNIT_CONVERSIONS:
        return val / UNIT_CONVERSIONS[target_unit]
    if base_unit == 'mg/mL' and target_unit in UNIT_CONVERSIONS:
        if target_unit == 'g/L' or target_unit == 'ppm':
            return val / UNIT_CONVERSIONS[target_unit]
        return val
    raise ValueError(f"Unsupported conversion from {base_unit} to {target_unit}")


def calculate_dilution(
        stock_conc: float,
        stock_unit: str,
        final_conc: float = None,
        final_unit: str = None,
        add_vol: float = None,
        final_vol: float = None,
        mode: str = "solve_final_conc"
) -> Dict[str, float]:
    """
    Performs dilution calculation based on C1V1 = C2V2.
    Modes:
    - 'solve_final_conc': (C1, V1, V2) -> C2
    - 'solve_add_vol': (C1, C2, V2) -> V1
    """
    s_val, s_unit = _convert_to_base_units(stock_conc, stock_unit)

    if mode == "solve_final_conc":
        if add_vol is None or final_vol is None:
            raise ValueError("Volumes are required for 'solve_final_conc' mode.")
        final_val = s_val * (add_vol / final_vol)
        return {s_unit: final_val}

    elif mode == "solve_add_vol":
        if final_conc is None or final_unit is None or final_vol is None:
            raise ValueError("Final concentration and volume are required for 'solve_add_vol' mode.")
        f_val, _ = _convert_to_base_units(final_conc, final_unit)
        add_vol = (f_val * final_vol) / s_val
        return {"add_vol": add_vol}

    raise ValueError("Invalid calculation mode.")


def _calc(payload: Dict) -> Dict:
    out = {}
    for it in payload.get("items", []):
        mode = it.get("mode", "solve_final_conc")
        out[it["name"]] = calculate_dilution(
            stock_conc=float(it["stock_conc"]),
            stock_unit=it["stock_unit"],
            final_conc=float(it.get("final_conc", 0)),
            final_unit=it.get("final_unit"),
            add_vol=float(it.get("add_ml", 0)),
            final_vol=float(it["final_ml"]),
            mode=mode
        )
    return out


@tool("unit_dilution_calculator")
def unit_dilution_calculator(payload: str) -> str:
    """
    Computes final concentrations or required volumes for dilutions.

    Input (JSON string):
    Mode 'solve_final_conc': {"items":[{"name":"A","stock_conc":10,"stock_unit":"mg/mL","add_ml":1,"final_ml":100}]}
    Mode 'solve_add_vol': {"items":[{"name":"B","stock_conc":1,"stock_unit":"M","final_conc":0.1,"final_unit":"M","final_ml":500}]}
    """
    try:
        data = json.loads(payload) if isinstance(payload, str) else payload
    except Exception:
        raise ValueError('Invalid JSON payload.')

    return json.dumps(_calc(data))