# File: agent/mix_agent.py

import json
from langchain.docstore.document import Document
from agent.llm_helper import summarize_guidance
from db.query import smart_search
from typing import List, Dict, Any

# A predefined prompt template for mixture analysis
MIXTURE_PROMPT = """
You are a highly skilled safety expert. Your task is to analyze the provided Safety Data Sheet (SDS) excerpts for a mixture of materials. 
Based ONLY on the provided context, identify potential safety issues and provide consolidated, clear guidance for first aid and emergency handling.

Instructions:
1.  **Identify Hazards:** Based on the context, what are the primary hazards of this mixture? List them using a consistent vocabulary such as Flammable, Corrosive, Oxidizer, Toxicity, Health Hazard, Explosive, Gas under pressure, or Environmental.
2.  **First Aid:** Consolidate the first aid instructions for skin, eye, inhalation, and ingestion exposures from all materials. Provide a single, easy-to-read list.
3.  **Fire & Spill:** Summarize the recommended procedures for handling a fire or a spill involving these materials.

Context (consolidated SDS excerpts):
{context}

Question:
{question}

Consolidated Guidance:
"""

# NEW: A simplified prompt to check for hazards
HAZARD_CHECK_PROMPT = """
You are a highly skilled safety expert. Your task is to analyze the provided Safety Data Sheet (SDS) excerpts.
Based ONLY on the provided context, determine if there are any significant hazards.
If any hazards are mentioned (e.g., Flammable, Corrosive, Toxicity, etc.), list them.
If the context explicitly states "not classified as hazardous" or provides no hazard information, respond with "NO_HAZARDS_FOUND".

Context (consolidated SDS excerpts):
{context}

Response:
"""


def analyze_mixture(material_names: List[str]) -> Dict[str, Any]:
    """
    Analyzes a mixture of materials by retrieving and summarizing relevant SDS data,
    filtering documents based on metadata for accuracy.

    Args:
        material_names (List[str]): A list of material names in the mixture.

    Returns:
        Dict[str, Any]: A dictionary containing the LLM's response and thought process.
    """
    thought_process = {
        "step_1": "Received request to analyze a mixture.",
        "step_2": "Retrieving and filtering SDS excerpts for each material.",
        "retrieved_documents": []
    }

    retrieved_docs = []

    for material in material_names:
        docs_per_material = smart_search(
            f"{material} safety information",
            k=5,
            locked_material=material,
        )

        filtered_docs = [
            doc for doc in docs_per_material
            if doc.metadata.get('material_name', '').strip().lower() == material.strip().lower()
        ]

        retrieved_docs.extend(filtered_docs)

        thought_process["retrieved_documents"].append({
            "material": material,
            "count_before_filter": len(docs_per_material),
            "count_after_filter": len(filtered_docs),
            "filtered_out_names": [d.metadata.get('material_name') for d in docs_per_material if d not in filtered_docs]
        })

    if not retrieved_docs:
        response = "No relevant SDS information found for the selected materials."
        thought_process["step_3"] = response
        return {"response": response, "thought_process": thought_process}

    # NEW STEP: Use the simplified prompt to check for hazards first
    hazard_check_response = summarize_guidance(
        question="Check for hazards.",
        docs=retrieved_docs,
        prompt_template=HAZARD_CHECK_PROMPT
    ).strip()

    if "NO_HAZARDS_FOUND" in hazard_check_response:
        response = f"""
        **Consolidated Safety Guidance for {', '.join(material_names)}**

        No significant hazards were found for this mixture based on the available SDS information. Please follow general laboratory safety practices when handling.
        """
        thought_process["step_3"] = "Failsafe: LLM confirmed no hazards were found in context."
        return {"response": response, "thought_process": thought_process}

    # If hazards are present, proceed with the full summary
    response = summarize_guidance(
        question="Summarize safety guidance for this mixture.",
        docs=retrieved_docs,
        prompt_template=MIXTURE_PROMPT
    )

    thought_process["step_3"] = "Generated full summary from filtered documents."
    thought_process["final_response"] = response

    return {"response": response, "thought_process": thought_process}