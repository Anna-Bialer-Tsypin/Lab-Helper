# File: agent/agent_tools/compatibility_checker.py

from typing import List
from langchain.tools import tool

# A simple, hardcoded database of known hazardous chemical pairs.
# This list can be expanded with more pairs over time.
# The chemical names should be a standardized format to ensure matches.
INCOMPATIBLE_PAIRS = {
    frozenset(["Sodium hypochlorite",
               "Hydrogen peroxide"]): "⚠️ **SEVERE HAZARD: VIOLENT, EXOTHERMIC REACTION** ⚠️\n\nMixing these two chemicals can produce a violent, highly exothermic reaction that releases oxygen gas, which can pose an explosion and fire risk. **DO NOT MIX.** This mixture is highly unstable and can cause thermal burns.",
    frozenset(["Sulfuric acid",
               "Acetone"]): "⚠️ **EXTREME HAZARD: EXPLOSIVE DECOMPOSITION** ⚠️\n\nMixing these two chemicals can lead to the formation of explosive peroxides. The reaction is highly exothermic and can cause a violent detonation. **DO NOT MIX.**",
    frozenset(["Ammonia",
               "Bleach"]): "⚠️ **SEVERE HAZARD: TOXIC CHLORAMINE GAS** ⚠️\n\nMixing these two chemicals releases toxic chloramine gas, which can cause severe respiratory damage and be fatal. **DO NOT MIX.**",
}


@tool("chemical_compatibility_checker")
def chemical_compatibility_checker(materials: List[str]) -> str | None:
    """
    Checks for dangerous incompatibilities between a list of two or more chemicals.
    Returns a prominent hazard warning if a known incompatible pair is found.
    """
    if len(materials) < 2:
        return None

    # Standardize names for lookup
    material_names = [m.lower().replace('-', ' ') for m in materials]

    # Check for any hazardous pair within the list of materials
    for pair, warning in INCOMPATIBLE_PAIRS.items():
        if all(m.lower() in material_names for m in pair):
            return warning

    return None