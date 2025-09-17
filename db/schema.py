# db/schema.py - Central definition of the Chroma vector store with HuggingFace embeddings.
# Sets up the vector DB (Chroma) and a local embedding model (all-MiniLM-L6-v2).
# Exposes get_vectorstore() that always returns the same persisted collection in data/chroma.


import os
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

DATA_DIR = os.getenv("DATA_DIR", "data")
VDB_DIR = os.path.join(DATA_DIR, "chroma")
os.makedirs(VDB_DIR, exist_ok=True)

# Local, no-API embeddings — good for quota-free ingest/query
EMB = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

def get_vectorstore():
    # Using langchain_community.Chroma here to stay compatible with your current stack.
    return Chroma(collection_name="sds_chunks",
                  embedding_function=EMB,
                  persist_directory=VDB_DIR)
