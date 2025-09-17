# app.py - Main Streamlit entrypoint, sets up UI and quick usage instructions.
# # Main entry for Streamlit. Loads env, shows intro + quick health checks.
import os  # # used for simple environment checks
import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # # loads .env so keys like GOOGLE_API_KEY / LANGCHAIN_* are available

st.set_page_config(
    page_title="Lab Assist (Core)",
    page_icon="🧪",
    layout="wide",
)

# # --- Header
st.title("Lab Assist Agent — Minimal Core")  # # single big title (kept minimal)
st.caption("Gemini (LLM) + Local HF embeddings + Chroma • No web search • Safe-by-default")

# # --- Quick usage
st.markdown(
    """
**How to use**
- Open **Chat** (sidebar) for free text Q&A grounded to your SDS with citations.
- Open **Incident Wizard** (sidebar) for a guided, conservative checklist.

**Index SDS PDFs**
```bash
python -m db.ingest --src data/sds
"""
)

