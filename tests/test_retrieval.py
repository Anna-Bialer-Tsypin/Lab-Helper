# test_retrieval.py

from db.query import smart_search
from db.schema import get_vectorstore

# Initialize the vector store
vdb = get_vectorstore()

# Test with a known name
results = smart_search("Fetal Bovine Serum safety", k=5, locked_material="Fetal Bovine Serum")

if results:
    print("Success! Documents found.")
    for doc in results:
        print("-" * 20)
        print(f"Material: {doc.metadata.get('material_name')}")
        print(f"Section: {doc.metadata.get('section')}")
        print(f"Page: {doc.metadata.get('page')}")
        print(f"Content: {doc.page_content[:200]}...")
else:
    print("Failure! No documents found for 'Fetal Bovine Serum'.")

# Repeat for the other material
results_dmem = smart_search("DMEM/F12 safety", k=5, locked_material="DMEM/F12")

if results_dmem:
    print("\nSuccess! Documents found for DMEM/F12.")
else:
    print("\nFailure! No documents found for 'DMEM/F12'.")