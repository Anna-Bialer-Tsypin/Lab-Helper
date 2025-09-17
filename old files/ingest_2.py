# Ingests PDFs → extracts text (PyMuPDF preferred, OCR fallback),
# heuristically extracts metadata (product name, synonyms, CAS, catalog number, manufacturer, revision date),
# splits into section-tagged subchunks, derives aliases, and writes documents to Chroma.

import os
import re
import argparse
from typing import List, Dict, Any, Optional
from langchain.docstore.document import Document
import sys
import pytesseract
from PIL import Image
import io
import fitz  # PyMuPDF
from pypdf import PdfReader  # Fallback import

from .schema import get_vectorstore
from .aliases import save_aliases, set_aliases


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

NAME_PAT = re.compile(r"(?i)\b(Product\s*name|Substance\s*name|Chemical\s*name)\s*[:\-]\s*(.+)")
SYN_LINE_PAT = re.compile(r"(?i)\bSynonyms?\s*[:\-]\s*(.+)")

DATE_PAT = re.compile(
    r"(?i)(Revision|Issue|Version)\s*(date)?\s*[:\-]?\s*([0-9]{4}[./-][0-9]{1,2}[./-][0-9]{1,2})"
)
DATE_PAT_GENERIC = re.compile(
    r"(?i)\b(rev(?:ised)?|updated|version)\s*(date)?\s*[:\-]?\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{4})"
)
DATE_PAT_MON = re.compile(
    r"(?i)(revised|updated|version\s*date)\s*[:\-]?\s*([0-3]?\d\s*[A-Za-z]{3,9}\s*\d{4}|[A-Za-z]{3,9}\s*[0-3]?\d,\s*\d{4})"
)

DENY_TOKENS = {
    "sds", "msds", "sigma", "merck", "fisher", "supelco", "acros", "alfa", "honeywell", "pdf",
    "v", "ver", "version", "final", "draft", "copy"
}

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


def _subsplit(text: str, target=900, overlap=120):
    parts = re.split(r"\n{2,}", text)
    chunks = []
    buf = ""
    for part in parts:
        if len(part) > target * 1.5:
            for sent in re.split(r"(?<=[.!?])\s+", part):
                if len(buf) + len(sent) + 1 > target:
                    if buf:
                        chunks.append(buf.strip())
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
    pages = []
    try:
        doc = fitz.open(pdf_path)
        for i in range(len(doc)):
            text = doc[i].get_text("text") or ""
            if text.strip():
                pages.append({"page": i + 1, "text": text})
            else:
                pix = doc[i].get_pixmap()
                img_bytes = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_bytes))
                text_ocr = pytesseract.image_to_string(img)
                pages.append({"page": i + 1, "text": text_ocr or ""})
        doc.close()
        return pages
    except ImportError:
        print("Warning: PyMuPDF or Tesseract not installed. Falling back to pypdf.", file=sys.stderr)
        reader = PdfReader(pdf_path)
        return [{"page": i + 1, "text": (page.extract_text() or "")} for i, page in enumerate(reader.pages)]
    except Exception as e:
        print(f"Error: OCR failed on {pdf_path}: {e}. Skipping file.", file=sys.stderr)
        return []


def _guess_section_headers(text: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for line in text.splitlines():
        m = SECTION_PAT.search(line)
        if m:
            out.append({"sec_no": m.group(1), "sec_title": m.group(2).strip()})
    return out


def _split_into_section_chunks(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
        out["synonyms"] = list(dict.fromkeys(syns))

    m = DATE_PAT.search(text)
    if m:
        out["revision_date"] = m.group(3)

    if not out["revision_date"]:
        m2 = DATE_PAT_GENERIC.search(text)
        if m2:
            out["revision_date"] = m2.group(3)

    if not out["revision_date"]:
        m3 = DATE_PAT_MON.search(text)
        if m3:
            out["revision_date"] = m3.group(2)

    manuf_block: Optional[str] = None
    for block in re.split(r"\n{2,}", text):
        if re.search(r"(?i)\b(Manufacturer|Supplier|Company)\b", block):
            manuf_block = " ".join(line.strip() for line in block.splitlines()[:6])
            break
    if manuf_block:
        out["manufacturer"] = re.sub(r"\s{2,}", " ", manuf_block).strip()

    m = re.search(r"(?i)\b(Cat(?:alog)?(?:\.| number)?|Product\s*No\.?)\s*[:\-]\s*([A-Z0-9\-._/]+)", text)
    if m:
        out["catalog_no"] = m.group(2).strip()

    if not out["catalog_no"]:
        m4 = re.search(
            r"(?i)\b(cat(?:alog|alogue)?\s*(?:no\.?|number)|product\s*(?:no\.?|code|number)|article\s*(?:no\.?|number)|material\s*(?:no\.?|number)|sku)\b\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_/.]+)",
            text)
        if m4:
            out["catalog_no"] = m4.group(2).strip()

    if not out["catalog_no"]:
        m5 = re.search(r"(?i)\border(?:ing)?\s*(?:code|no\.?|number)\b\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_/.]+)", text)
        if m5:
            out["catalog_no"] = m5.group(1).strip()

    if not out["catalog_no"] and filename:
        m6 = re.search(r"([A-Z0-9]{3,}-?[A-Z0-9]{1,})", filename, re.I)
        if m6:
            out["catalog_no"] = m6.group(1).strip()

    return out


def _derive_aliases(material_name: str, meta0: Dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for t in re.findall(r"[A-Za-z0-9]+", material_name):
        tl = t.lower()
        if tl in DENY_TOKENS:
            continue
        tu = t.upper()
        if 2 <= len(tu) <= 12 and tu[0].isalpha():
            out.add(tu)
    if meta0.get("cas"):
        out.add(str(meta0["cas"]))
    m = CAS_PAT.search(material_name)
    if m:
        out.add(m.group(0))
    if meta0.get("product_name"):
        out.add(meta0["product_name"].upper())
    for s in meta0.get("synonyms", []):
        stripped_s = s.strip()
        if stripped_s:
            out.add(stripped_s.upper())
    return out


# --- UPDATED: New ingest_file function signature ---
def ingest_file(path: str, material_name: str, aliases: List[str]) -> int:
    """Ingests a single file, using a user-provided material name and aliases."""
    pages = _extract_text_with_pages(path)
    if not pages:
        return 0

    first_text = " \n".join(ch["text"] for ch in pages[:5])
    meta0 = _extract_meta_blob(first_text, os.path.basename(path))

    # Save the user-provided aliases to your alias store
    set_aliases(material_name, aliases)

    # Heuristically derive additional aliases from the document's content
    derived_aliases = _derive_aliases(material_name, meta0)
    # Combine the user-provided aliases with the derived ones
    # You might want to save them all to the alias file here as well
    combined_aliases = list(set(aliases) | derived_aliases)
    save_aliases(material_name, combined_aliases)

    sect_chunks = _split_into_section_chunks(pages)
    vdb = get_vectorstore()
    docs: List[Document] = []

    for ch in sect_chunks:
        raw_meta = {
            "material_name": material_name,  # Use the user-provided name
            "canonical_name": meta0.get("product_name") or material_name,
            "synonyms": ",".join(meta0.get("synonyms", [])),
            "aliases_str": ",".join(combined_aliases),
            "section": ch["section"],
            "section_tag": ch["section_tag"],
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
    return len(docs)


# This function is now for command-line use and no longer needed for the Streamlit app
def ingest_path(src: str) -> int:
    total = 0
    for root, _, files in os.walk(src):
        for f in files:
            if f.lower().endswith(".pdf"):
                # This call now needs material_name and aliases, so it's not directly usable
                # The Streamlit app handles this logic instead.
                pass
    return total


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="Folder with SDS PDFs")
    args = ap.parse_args()
    # The command-line script now requires a name and aliases, which is not practical.
    # It's better to use the Streamlit app for ingestion.
    print("Use the Streamlit app to ingest files.")