# Lab Assist Agent — Minimal Core


Goal: a **lean** agent that answers lab incident questions strictly from **your** SDS PDFs. It includes:
- SDS ingestion → vector DB with light metadata
- Chat page → ask free text, get **citations** (Material | Section | Page)
- Incident Wizard → guided inputs + "unknown" toggles to stay safe with partial info


Intentionally **omitted** for minimalism: web search, mixture builder UI, alias resolver, local audit logging, docker-compose. You can add them later.


## Quickstart
```bash
python -m venv .venv && source .venv/bin/activate # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env # fill GOOGLE_API_KEY
streamlit run app/Home.py