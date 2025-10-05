# 🧠 Lab Helper – AI-Powered Lab Safety & SDS Assistant

<p align="center">
  <img src="logo.png" alt="Lab Helper Banner" width="220">
</p>

### Your intelligent laboratory companion for safer, smarter experiments.

---

## ⚠️ Safety Disclaimer (Read First)

**Lab Helper is an educational/assistant tool and is _not_ a substitute for official SDS documents, institutional SOPs, or professional judgment.**  
Do **not** rely on it as the sole source of safety guidance. Always verify with the original SDS (Sections 2, 4, 5, 6, 7, 8, 10), your lab’s SOPs, and your safety officer. If guidance conflicts, **follow the SDS and institutional policy**.

---

## 🚀 Overview
**Lab Helper** is an AI-driven laboratory assistant that helps researchers, students, and engineers safely handle chemicals and prepare mixtures.  
It extracts and analyzes information from **Safety Data Sheets (SDS)**, identifies potential hazards, and provides instant safety guidance for your experiments.

Built as a **Retrieval-Augmented Generation (RAG)** system with **LangChain**, **ChromaDB**, and modern **LLMs (Gemini/OpenAI)**, it offers a practical, interactive way to connect chemical safety data with real-world lab activities.

---

## ⚗️ Core Features

### 🧾 SDS Management
- Upload and parse **Safety Data Sheet (SDS) PDFs** (including OCR support)
- Automatically indexed into **ChromaDB** for semantic retrieval
- Query hazards, first aid, and emergency procedures via chat

### 🧮 Mixture Calculator & Safety Plan
- Define mixtures and concentrations
- Automatically analyze potential chemical incompatibilities
- Flag hazardous combinations (e.g., *Piranha solution*, *HF + H₂SO₄*)
- Consolidate all related safety information in one view

### ⚠️ Rapid SDS Guidance
- Chatbot trained on your local SDS library
- Context-aware LLM agent designed for concise, reliable responses
- Low hallucination tolerance and prompt-level safety filtering

### 📚 SDS Library & Viewer
- Organized viewer for all uploaded SDS documents
- Automatic alias mapping (CAS names, synonyms, and trade names)
- Easy access to full safety text excerpts

### 🧰 Modular Agent Architecture
- `mix_agent`, `chat_agent`, and specialized `agent_tools` for:
  - SDS retrieval (`retriever.py`)
  - Hazard summarization (`property_summarizer.py`)
  - Compatibility analysis (`compatibility_checker.py`)
  - Alias resolution and mixture flagging
  - Deterministic **extreme hazard checks** (`extreme_mix_checker.py`)

---

## 🧩 Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | Streamlit |
| **LLM Framework** | LangChain |
| **Vector Store** | ChromaDB |
| **Embeddings** | all-MiniLM-L6-v2 (HuggingFace) |
| **Language Models** | Gemini / OpenAI APIs |
| **Environment** | Python 3.11+ |
| **Visualization** | Streamlit Pages & Components |

---

## 🛠️ Installation

```bash
# 1️⃣ Clone this repository
git clone https://github.com/Anna-Bialer-Tsypin/Lab-Helper.git
cd Lab-Helper

# 2️⃣ Create a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 3️⃣ Install dependencies
pip install -r requirements.txt

# 4️⃣ Run the Streamlit app
streamlit run app.py
```
----

## 🧯 Fallbacks & Behavior When Unsure
- **Missing/low context or unclear concentration →** brief refusal + link to SDS sections.
- **Citations required;** uncited claims aren’t shown.
- **Deterministic flags first** (piranha, HF+acids, chlorine risks).
-------------------
## ❗ Known Limitations (Current State)
- OCR/vendor formatting can drop details; tables/lists often degrade.
- **Concentration-aware thresholds not fully parsed** (SCLs, M-factors, “≥/≤” ranges).
- Ingestion brittle on multi-column PDFs, scanned images, and vendor-specific layouts.
- Alias mapping may miss trade names/CAS variants.
- Not validated as a safety product—**don’t use as sole source**.
-----------
## 🛡️ Hardening Plan & Next Steps
- **Template-aware parsers** per vendor; layout-aware extraction for multi-column PDFs.
- Robust **numeric/units parser** (%, M, mg/L) to capture SCLs, M-factors, ranges.
- Preserve **tables** (e.g., hazards/first-aid) via table extractors; keep cell provenance.
- **Ingestion QA:** golden SDS set, unit tests, diff checks, and failure logs in UI.
- Stronger **alias index** (CAS ↔ synonyms ↔ product codes) + manual overrides.

----
## 👩‍🔬 About
Developed by Anna Bialer-Tsypin — a biotechnology and AI consultant
bridging wet-lab science and data-driven safety automation.

📍 Israel | ⚙️ Biotech | 🧬 Data Science | 🧠 AI Safety Tools  
[🧬 LinkedIn](https://www.linkedin.com/in/anna-bialer-tsypin-030725174/) | [💻 GitHub](https://github.com/Anna-Bialer-Tsypin)

----
## 💬 Acknowledgements
Special thanks to Valeria and the John Bryce Data Science Program
for guidance and inspiration throughout the project.
