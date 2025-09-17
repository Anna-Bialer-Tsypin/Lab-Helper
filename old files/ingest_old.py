#Ingests PDFs → extracts text (PyMuPDF preferred, falls back to pypdf),
# heuristically extracts metadata (product name, synonyms, CAS, catalog number, manufacturer, revision date),
# splits into section-tagged subchunks, derives aliases (filename tokens + CAS + synonyms),
# saves aliases, and writes documents to Chroma with clean metadata.
#👍 Sensible section tagging (first_aid, fire_fighting, spill_response) and chunking with overlap; good metadata sanitizer; alias generation is practical.
#⚠️ No OCR for scanned PDFs; section header regex may miss non-standard layouts; manufacturer parsing is heuristic;
# alias derivation might be a bit permissive (could add a min len / blacklist).


# db/ingest.py - Parses PDFs (pypdf / PyMuPDF), extracts sections, metadata, aliases → stores them in Chroma as chunks.
import os
import re
import argparse
from typing import List, Dict, Any, Optional
from pypdf import PdfReader
from langchain.docstore.document import Document

from .schema import get_vectorstore
from .aliases import save_aliases  # alias index (JSON)

# ---------- helpers ----------

def _sanitize_md(md: Dict[str, Any]) -> Dict[str, str | int | float | bool]:
    """Chroma-safe metadata: drop None, stringify non-primitives, join lists."""
    clean: Dict[str, str | int | float | bool] = {}
    for k, v in (md or {}).items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            clean[k] = v
        elif isinstance(v, (list, tuple, set)):
            clean[k] = ",".join(str(x) for x in v)
        else:
            clean[k] = str(v)
    return clean

SECTION_PAT = re.compile(r"(?i)Section\s*([0-9]{1,2})\s*[:\-]?\s*(.+)")
CAS_PAT = re.compile(r"\b\d{2,7}-\d{2}-\d\b")

# Broad patterns for metadata seen across vendors
NAME_PAT = re.compile(r"(?i)\b(Product\s*name|Substance\s*name|Chemical\s*name)\s*[:\-]\s*(.+)")
SYN_LINE_PAT = re.compile(r"(?i)\bSynonyms?\s*[:\-]\s*(.+)")
DATE_PAT = re.compile(r"(?i)(Revision|Issue|Version)\s*(date)?\s*[:\-]\s*([0-9]{4}[./-][0-9]{1,2}[./-][0-9]{1,2})")

# denylist for junk tokens from filenames
DENY_TOKENS = {
    "sds","msds","sigma","merck","fisher","supelco","acros","alfa","honeywell","pdf",
    "v","ver","version","final","draft","copy"
}


# --- section tagging & sub-chunking ---
SECTION_TAG_MAP = {
    r"\bsection\s*4\b.*(first\s*aid|first-aid|aid\s*measures)": "first_aid",
    r"\bsection\s*5\b.*(fire|fire[-\s]*fighting|firefighting|extinguish)": "fire_fighting",
    r"\bsection\s*6\b.*(accidental\s*release|spill|leak|spillage|release\s*measures)": "spill_response",
}

def _label_section(section_header: str) -> str:
    h = (section_header or "").lower()
    for pat, tag in SECTION_TAG_MAP.items():
        if re.search(pat, h):
            return tag
    return "other"

def _label_by_text(text: str) -> str | None:
    t = text.lower()
    if re.search(r"\bfirst\s*aid\b", t): return "first_aid"
    if re.search(r"\bfire(\s|-)fighting|extinguish|flammable\b", t): return "fire_fighting"
    if re.search(r"\b(accidental\s*release|spill|spillage|leak)\b", t): return "spill_response"
    return None

# lazy splitter so you don’t pull in extra deps
def _subsplit(text: str, target=900, overlap=120):
    # split by paragraphs → sentences → words
    parts = re.split(r"\n{2,}", text)
    chunks = []
    buf = ""
    for part in parts:
        if len(part) > target * 1.5:
            for sent in re.split(r"(?<=[.!?])\s+", part):
                if len(buf) + len(sent) + 1 > target:
                    if buf:
                        chunks.append(buf.strip())
                        # overlap
                        buf = buf[-overlap:]
                buf += (" " if buf else "") + sent
        else:
            if len(buf) + len(part) + 2 > target:
                if buf:
                    chunks.append(buf.strip())
                    buf = buf[-overlap:]
            buf += ("\n\n" if buf else "") + part
    if buf.strip():
        chunks.append(buf.strip())
    return [c for c in chunks if c.strip()]



def _extract_text_with_pages(pdf_path: str) -> List[Dict[str, Any]]:
    """Prefer PyMuPDF (if installed), fallback to pypdf. Returns list of {page, text}."""
    # Try PyMuPDF first (robust for many layouts)
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        pages = []
        for i in range(len(doc)):
            text = doc[i].get_text("text") or ""
            pages.append({"page": i + 1, "text": text})
        doc.close()
        if any(p["text"].strip() for p in pages):
            return pages
    except Exception:
        pass

    # Fallback: pypdf
    reader = PdfReader(pdf_path)
    return [{"page": i + 1, "text": (page.extract_text() or "")} for i, page in enumerate(reader.pages)]

def _guess_section_headers(text: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for line in text.splitlines():
        m = SECTION_PAT.search(line)
        if m:
            out.append({"sec_no": m.group(1), "sec_title": m.group(2).strip()})
    return out

def _split_into_section_chunks(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Returns list of dicts with keys: section, section_tag, page, text
    - Tracks the most recent section header on each page
    - Sub-splits page text to ~900-char chunks for better retrieval
    """
    current = {"sec_no": "unknown", "sec_title": "unknown"}
    chunks: List[Dict[str, Any]] = []
    for p in pages:
        headers = _guess_section_headers(p["text"])
        if headers:
            current = headers[0]
        section_header = f"Section {current['sec_no']} {current['sec_title']}"
        section_tag = _label_section(section_header)
        for sub in _subsplit(p["text"], target=900, overlap=120):
            tag = section_tag
            if tag == "other":
                t2 = _label_by_text(sub)
                if t2: tag = t2
            chunks.append({
                "section": section_header,
                "section_tag": tag,
                "page": int(p["page"]),
                "text": sub,
            })
    return chunks


def _extract_meta_blob(text: str, filename: str) -> Dict[str, Any]:
    """Heuristic metadata scan across first few pages' text."""
    out: Dict[str, Any] = {
        "product_name": None, "synonyms": [], "manufacturer": None,
        "catalog_no": None, "revision_date": None, "cas": None
    }

    m = CAS_PAT.search(text)
    if m:
        out["cas"] = m.group(0)

    m = NAME_PAT.search(text)
    if m:
        out["product_name"] = m.group(2).strip()

    syns = []
    for line in text.splitlines():
        sm = SYN_LINE_PAT.search(line)
        if sm:
            syns += [s.strip() for s in re.split(r"[;,]", sm.group(1)) if s.strip()]
    if syns:
        out["synonyms"] = list(dict.fromkeys(syns))  # dedupe keep order

    # Manufacturer: pick a short block mentioning Manufacturer/Supplier/Company
    manuf_block: Optional[str] = None
    for block in re.split(r"\n{2,}", text):
        if re.search(r"(?i)\b(Manufacturer|Supplier|Company)\b", block):
            manuf_block = " ".join(line.strip() for line in block.splitlines()[:6])
            break
    if manuf_block:
        out["manufacturer"] = re.sub(r"\s{2,}", " ", manuf_block).strip()

    m = re.search(r"(?i)(Cat(?:alog)?(?:\.| number)?|Product\s*No\.?)\s*[:\-]\s*([A-Z0-9\-._/]+)", text)
    if m:
        out["catalog_no"] = m.group(2).strip()

    m = DATE_PAT.search(text)
    if m:
        out["revision_date"] = m.group(3)
    # --- revision date fallbacks ---
    if not out["revision_date"]:
        # e.g., "Revision date: 2023-08-19" or "Issue Date: 2021/03/07"
        m2 = re.search(
            r"(?i)\b(rev(?:ision)?|issue|updated|last\s*revised)\s*(?:date)?\b\s*[:\-]?\s*([0-9]{4}[./-][0-9]{1,2}[./-][0-9]{1,2})",
            text)
        if m2:
            out["revision_date"] = m2.group(2).strip()

    if not out["revision_date"]:
        # e.g., "Revised: 03 Aug 2021" or "Updated: Aug 3, 2021"
        m3 = re.search(
            r"(?i)\b(revised|updated|version\s*date)\b\s*[:\-]?\s*([0-3]?\d\s*[A-Za-z]{3,9}\s*\d{4}|[A-Za-z]{3,9}\s*[0-3]?\d,\s*\d{4})",
            text)
        if m3:
            out["revision_date"] = m3.group(2).strip()

    # --- catalog/product/article/material code fallbacks ---
    if not out["catalog_no"] :
        # Common vendor labels: Cat. No., Catalogue No., Product No., Article No., Material Number, SKU
        m4 = re.search(
            r"(?i)\b(cat(?:alog|alogue)?\s*(?:no\.?|number)|product\s*(?:no\.?|code|number)|article\s*(?:no\.?|number)|material\s*(?:no\.?|number)|sku)\b\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_/.]+)",
            text
        )
        if m4:
            out["catalog_no"] = m4.group(2).strip()

    if not out["catalog_no"]:
        # Sometimes shown near "Order"/"Ordering"
        m5 = re.search(r"(?i)\border(?:ing)?\s*(?:code|no\.?|number)\b\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_/.]+)", text)
        if m5:
            out["catalog_no"] = m5.group(1).strip()

    # --- filename-based fallback (was using text; now use filename) ---
    if not out["catalog_no"] and filename:
        m6 = re.search(r"([A-Z0-9]{3,}-?[A-Z0-9]{1,})", filename, re.I)
        if m6:
            out["catalog_no"] = m6.group(1).strip()


    return out

def _derive_aliases(material_name: str, meta0: Dict[str, Any]) -> set[str]:
    """Union of: useful filename tokens, CAS, product_name, and synonyms (uppercased)."""
    out: set[str] = set()

    # tokens from filename (letters/digits only)
    for t in re.findall(r"[A-Za-z0-9]+", material_name):
        tl = t.lower()
        if tl in DENY_TOKENS:
            continue
        tu = t.upper()
        if 2 <= len(tu) <= 12 and tu[0].isalpha():
            out.add(tu)

    # CAS (from meta or filename)
    if meta0.get("cas"):
        out.add(str(meta0["cas"]))
    m = CAS_PAT.search(material_name)
    if m:
        out.add(m.group(0))

    # product_name + synonyms
    if meta0.get("product_name"):
        out.add(meta0["product_name"].upper())
    for s in meta0.get("synonyms", []):
        if s.strip():
            out.add(s.strip().upper())

    return out

# ---------- ingest ----------

def ingest_file(path: str) -> int:
    material_name = os.path.splitext(os.path.basename(path))[0]

    pages = _extract_text_with_pages(path)
    # If PDFs are scanned with no text layer, this will be empty → needs OCR
    first_text = " \n".join(ch["text"] for ch in pages[:5])
    meta0 = _extract_meta_blob(first_text, os.path.basename(path))

    # aliases: filename tokens + CAS + product_name + synonyms
    aka = _derive_aliases(material_name, meta0)
    save_aliases(material_name, sorted(aka))  # persist alias index

    sect_chunks = _split_into_section_chunks(pages)
    vdb = get_vectorstore()
    docs: List[Document] = []
    for ch in sect_chunks:
        raw_meta = {
            "material_name": material_name,
            "canonical_name": meta0.get("product_name") or material_name,
            "synonyms": ",".join(meta0.get("synonyms", [])),
            "aliases_str": ",".join(sorted(aka)),
            "section": ch["section"],
            "section_tag": ch["section_tag"],  # ← add this
            "page": int(ch["page"]),
            "source_path": path,
            "manufacturer": meta0.get("manufacturer"),
            "catalog_no": meta0.get("catalog_no"),
            "revision_date": meta0.get("revision_date"),
            "cas": meta0.get("cas"),
        }

        docs.append(Document(page_content=ch["text"], metadata=_sanitize_md(raw_meta)))

    if docs:
        vdb.add_documents(docs)
        vdb.persist()
    return len(docs)

def ingest_path(src: str) -> int:
    total = 0
    for root, _, files in os.walk(src):
        for f in files:
            if f.lower().endswith(".pdf"):
                total += ingest_file(os.path.join(root, f))
    return total

# ---------- CLI ----------

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="Folder with SDS PDFs")
    args = ap.parse_args()
    print(f"Chunks added: {ingest_path(args.src)}")
