# Ingest smoke test

# Expect: a positive chunk count; data/chroma/ created; data/alias_index.json created.
from db.ingest import ingest_path
n = ingest_path("data/sds")
print("chunks:", n)

# Inspect aliases
# Expect: aliases for each material (CAS, synonyms, filename tokens). “HF” or CAS should resolve to your HF file’s material name.
from db.aliases import dump, resolve_alias
count, pretty = dump()
print(count)
print(pretty)
print(resolve_alias("HF"))
print(resolve_alias("7664-39-3"))

#----------------------------------------------------------------------------------------------------------------

#Spot-check metadata & section tags
#Expect: section_tag = first_aid shows up; metadata fields are populated (not all will be present for every vendor).

from db.schema import get_vectorstore
vdb = get_vectorstore()
docs = vdb.similarity_search("first aid hydrofluoric acid", k=3)
for d in docs:
    md = d.metadata
    print(md.get("material_name"), md.get("section_tag"), md.get("page"),
          md.get("catalog_no"), md.get("revision_date"), md.get("cas"))

#----------------------------------------------------------------------------------------------------------------

#Functional retrieval (the real check)
from db.query import smart_first_aid_search, smart_search

# Unlocked (can the system pick HF first-aid on its own?)
res = smart_first_aid_search("HF splash in eye - what do I do?", k=5)
print([ (r.metadata["material_name"], r.metadata["section_tag"], r.metadata["page"]) for r in res ])

# Locked by material (should eliminate FBS confusion)
res2 = smart_first_aid_search("splash in eye", locked_material="HF SDS Sigma", k=5)
print([ (r.metadata["material_name"], r.metadata["section_tag"]) for r in res2 ])

# CAS-based strict filter
res3 = smart_search("7664-39-3 exposure first aid", tag="first_aid", k=5)
print([ r.metadata["material_name"] for r in res3 ])

#Expect:
# Unlocked: mostly HF first-aid chunks near the top; minimal contamination from other materials.
# Locked: only HF chunks.
# CAS query: strictly the correct material.

#----------------------------------------------------------------------------------------------------------------

#Negative / cross-material leak test
qs = [
  "how to treat chemical burn? (first aid)",           # vague
  "protein solution spill - what to do",               # should skew away from HF
  "hydrofluoric acid burns calcium gluconate gel"      # very HF-specific
]
from db.query import smart_first_aid_search
for q in qs:
    hits = smart_first_aid_search(q, k=8)
    print(q, [h.metadata["material_name"] for h in hits])

#Success metric: proportion of top-k belonging to the intended material (precision@k). You can hand-label 5–10 prompts and compute this quickly.
#----------------------------------------------------------------------------------------------------------------


#Alias resolution robustness

from db.aliases import resolve_alias
known = ["HF SDS Sigma","FBS SDS Sigma","NaOH SDS Sigma"]
print(resolve_alias("hydrofluoric acid", known))
print(resolve_alias("fetal bovine serum", known))
print(resolve_alias("HF SDS SIGMA", known))

# Expect: returns the canonical material names consistently.




#-----------------------------------------------------
# Query func
from db.query import smart_first_aid_search
docs = smart_first_aid_search("DMEM splash in eye", locked_material="DMEMF12 SDS Sigma")
for d in docs:
    print(d.metadata["material_name"], d.metadata["section_tag"], d.page_content[:])

