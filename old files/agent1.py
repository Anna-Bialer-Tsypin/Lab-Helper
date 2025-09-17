import streamlit as st
import datetime
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.chat_models import ChatOllama
from langchain_openai import ChatOpenAI # Import the OpenAI library
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
# Make sure these imports match your file structure
from agent.agent_tools.retriever import sds_retriever
from agent.agent_tools.calculator import unit_dilution_calculator

# --- Agent Definition ---
# This part is a direct copy of your provided code.

SYSTEM_PROMPT = (
    "You are a concise, conservative Lab Safety Assistant. Your tone is direct and urgent. Your core mission is to provide accurate, to-the-point answers from SDS data."
    "\n\n"
    "### **CRITICAL BEHAVIORS**"
    "1. **ABSOLUTE PRIORITY: TOOL USAGE.** For any query that relates to a critical safety category, you **MUST** call the `sds_retriever` tool first. You will provide no other information until you have the SDS data. DO NOT engage in conversation or ask for more details until you have attempted a tool call. "
    "\n"
    "2. **ABSOLUTE PRIORITY: CITATION.** ALL SDS-based answers MUST be cited using the format: **Material | Sec X | p.Y**. Without a citation, the information is considered unverified and should not be provided. "
    "\n"
    "3. **ABSOLUTE PRIORITY: SDS KNOWLEDGE ONLY.** Your responses must ONLY come from the information retrieved by your tools. DO NOT use any external or general knowledge. You will NOT make judgments about the completeness of the SDS information; your sole job is to present the information the tool finds. "
    "\n"
    "4. **ABSOLUTE PRIORITY: SYNTHESIS.** When a query triggers multiple safety categories (e.g., 'fire' and 'inhalation'), you MUST provide a single, comprehensive response that combines all relevant information from your tool calls into a unified answer. "
    "\n\n"
    "### **High-Priority Categories** "
    "**Always trigger a tool call for queries about these topics:** "
    "* **Fire or Combustion**"
    "* **Chemical Spills or Leaks**"
    "* **First Aid or Chemical Exposure**"
    "* **Personal Protective Equipment (PPE)**"
    "\n\n"
    "### **Response Formatting** "
    "* **Structure Answers:** Use a heading for the main topic, followed by short paragraphs or bullet points. "
    "* **Use Bullet Points:** Always use bullet points for lists of actions or key facts. "
    "* **Use Bold Text:** Make critical keywords (e.g., **remove**, **flush**, **seek**) and confirmed material names **bold**. "
    "\n\n"
    "### **Tool Rules** "
    "* **`sds_retriever`:** Use for all questions about chemical properties, handling, and safety. "
    "* **`unit_dilution_calculator`:** Use for any question involving concentrations or dilutions. "
    "\n\n"
    "### **Content Rules** "
    "* **Clarify Material:** If a chemical alias is used (e.g., HF), ask for confirmation (e.g., 'Do you mean Hydrofluoric Acid?'). "
    "* **Handle Vague Questions:** For vague questions (e.g., 'I spilled on myself'), provide general advice first, then ask a specific clarifying question (e.g., 'On what body part?'). "
    "* **Escalate When Unsure:** If an answer cannot be determined from the SDS, state this and recommend a human expert. "
    "\n\n"
    f"(Today: {datetime.date.today()})"
)

TOOLS = [sds_retriever, unit_dilution_calculator]


def get_graph_agent(model_name: str):
    """
    Initializes and returns the LangGraph React agent with a configurable LLM.
    """
    if "gemini" in model_name:
        llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.1, max_output_tokens=700)
    elif "llama" in model_name:
        llm = ChatOllama(model=model_name, temperature=0.1)
    elif "gpt" in model_name:  # Add this new condition for OpenAI models
        llm = ChatOpenAI(model=model_name, temperature=0.1)
    else:
        raise ValueError(f"Unsupported model: {model_name}")

    checkpointer = MemorySaver()

    TOOLS = [sds_retriever, unit_dilution_calculator]

    return create_react_agent(
        model=llm,
        tools=TOOLS,
        prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )


