# File: agent/agent_tools/property_summarizer.py
# File: agent/agent_tools/property_summarizer.py

import json
from typing import List, Dict
from langchain.tools import tool
from db.query import smart_search
from db.schema import get_vectorstore


@tool("get_material_properties")
def get_material_properties(material_name: str) -> str:
    """
    Analyzes an SDS to return a JSON summary of its key properties (e.g., acid, base, oxidizer).
    Input should be the exact name of the material.
    Returns a JSON string of a dictionary containing a 'properties' list.
    """
    print(f"DEBUG: Searching properties for material: {material_name}") # <-- ADD THIS
    vdb = get_vectorstore()

    search_queries = [
        f"{material_name} hazards identification",
        f"{material_name} physical and chemical properties",
        f"{material_name} stability and reactivity",
        f"{material_name} pH",
        f"{material_name} incompatibilities",
        f"{material_name} oxidizer",
    ]

    relevant_docs = []
    for query in search_queries:
        docs = smart_search(query, k=2, locked_material=material_name)
        relevant_docs.extend(docs)

    if not relevant_docs:
        print(f"DEBUG: No documents found for {material_name}") # <-- ADD THIS
        return json.dumps({"properties": ["No properties found in SDS"]})
    # Concatenate the content of the retrieved documents for analysis
    context = " ".join([doc.page_content for doc in relevant_docs]).lower()

    # --- Rule-Based Property Identification ---
    # This is a robust and deterministic way to identify properties
    # without relying on a full LLM model's reasoning.
    properties = set()

    # Incompatibility Checks
    incompatibilities = []
    if "incompatible with acids" in context:
        incompatibilities.append("incompatible_with_acids")
    if "incompatible with bases" in context:
        incompatibilities.append("incompatible_with_bases")
    if "incompatible with oxidizers" in context:
        incompatibilities.append("incompatible_with_oxidizers")
    if "incompatible with organic materials" in context:
        incompatibilities.append("incompatible_with_organic_materials")

    # Property Checks
    if any(s in context for s in ["strong acid", "ph<7"]):
        properties.add("acid")
    if any(s in context for s in ["strong base", "alkaline", "ph>7"]):
        properties.add("base")
    if "oxidizer" in context:
        properties.add("oxidizer")
    if "flammable" in context:
        properties.add("flammable")
    if "corrosive" in context:
        properties.add("corrosive")
    if "toxic" in context:
        properties.add("toxic")
    if "reacts violently with water" in context:
        properties.add("reacts_violently_with_water")

    if not properties and not incompatibilities:
        return json.dumps({"properties": ["No specific hazard properties found"], "incompatibilities": []})

    # Return the properties and incompatibilities in a JSON object
    return json.dumps({
        "properties": list(properties),
        "incompatibilities": list(set(incompatibilities))
    })