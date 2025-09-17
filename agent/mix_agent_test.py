# File: agent/mix_agent.py

import json
from langchain.docstore.document import Document
from agent.llm_helper import summarize_guidance
from db.query import smart_search
from typing import List, Dict, Any
from agent.agent_tools.property_summarizer import get_material_properties

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
        "step_2": "Retrieving SDS excerpts and properties for each material.",
        "retrieved_documents": [],
        "material_properties": {}
    }

    retrieved_docs = []

    # NEW STEP: Get properties for each material and check for incompatibilities
    for material in material_names:
        # Step 2a: Get properties using the new tool
        properties_json = get_material_properties(material)
        properties_data = json.loads(properties_json)
        thought_process["material_properties"][material] = properties_data

        # Step 2b: Retrieve SDS documents
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

    # NEW STEP: Check for dangerous incompatibilities based on extracted properties
    incompatible_pairs = []
    for i in range(len(material_names)):
        for j in range(i + 1, len(material_names)):
            mat1 = material_names[i]
            mat2 = material_names[j]
            props1 = thought_process["material_properties"][mat1]
            props2 = thought_process["material_properties"][mat2]

            incompatibilities1 = props1.get('incompatibilities', [])
            incompatibilities2 = props2.get('incompatibilities', [])
            properties1 = props1.get('properties', [])
            properties2 = props2.get('properties', [])

            # Simplified check for demonstration
            if 'incompatible_with_acids' in incompatibilities1 and 'acid' in properties2:
                incompatible_pairs.append((mat1, mat2))
            if 'incompatible_with_acids' in incompatibilities2 and 'acid' in properties1:
                incompatible_pairs.append((mat2, mat1))
            if 'incompatible_with_bases' in incompatibilities1 and 'base' in properties2:
                incompatible_pairs.append((mat1, mat2))
            if 'incompatible_with_bases' in incompatibilities2 and 'base' in properties1:
                incompatible_pairs.append((mat2, mat1))
            if 'incompatible_with_oxidizers' in incompatibilities1 and 'oxidizer' in properties2:
                incompatible_pairs.append((mat1, mat2))
            if 'incompatible_with_oxidizers' in incompatibilities2 and 'oxidizer' in properties1:
                incompatible_pairs.append((mat2, mat1))

    if incompatible_pairs:
        # Found a potential reaction, craft a specific warning
        warning_messages = [
            f"**WARNING**: Mixing `{pair[0]}` and `{pair[1]}` is highly dangerous due to an incompatibility identified in their Safety Data Sheets."
            for pair in incompatible_pairs
        ]

        # Now, get the LLM to summarize the risks from the SDS data
        llm_response = summarize_guidance(
            question="Summarize the risks of mixing these materials.",
            docs=retrieved_docs,
            prompt_template=MIXTURE_PROMPT
        )

        # Combine the specific warnings with the general LLM summary
        final_response = "\n\n".join(warning_messages) + "\n\n---\n\n" + llm_response
        thought_process[
            "step_3"] = "Detected incompatibilities and generated a specific warning along with an LLM summary."
        thought_process["final_response"] = final_response
        return {"response": final_response, "thought_process": thought_process}

    if not retrieved_docs:
        response = "No relevant SDS information found for the selected materials."
        thought_process["step_3"] = response
        return {"response": response, "thought_process": thought_process}

    # OLD STEP: The failsafe check for non-hazardous materials
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