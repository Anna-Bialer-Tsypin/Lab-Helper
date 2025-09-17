from db.schema import get_vectorstore
from db.query import _material_names

vdb = get_vectorstore()
materials = sorted([m for m in _material_names(vdb) if m])

print("Materials found in the database:")
for m in materials:
    print(f"- {m}")