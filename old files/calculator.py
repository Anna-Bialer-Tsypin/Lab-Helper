# calculator.py
# # Tiny dilution calculator, exposed as a LangChain tool via @tool
import json
import re
from typing import Dict
from langchain.tools import tool


# # --- helpers
def parse_stock(s: str):
    s = s.strip().replace("µM", "uM")
    m = re.match(r"^(?P<val>\d+(?:\.\d+)?)\s*(?P<unit>%|mg/mL|g/L|M|mM|uM|ppm)", s)
    if not m:
        raise ValueError(f"Unrecognized stock format: {s}")
    return float(m.group("val")), m.group("unit")


def dilute(stock_val: float, stock_unit: str, add_ml: float, final_ml: float) -> Dict[str, float]:
    frac = add_ml / final_ml
    if stock_unit == "%":       return {"%": stock_val * frac}
    if stock_unit == "mg/mL":   return {"mg/mL": stock_val * frac}
    if stock_unit == "g/L":     return {"mg/mL": stock_val * frac}  # 1 g/L == 1 mg/mL
    if stock_unit == "M":       return {"M": stock_val * frac}
    if stock_unit == "mM":      return {"mM": stock_val * frac}
    if stock_unit in ("uM", "ppm"):
        return {stock_unit: stock_val * frac}
    raise ValueError(f"Unsupported unit: {stock_unit}")


def _calc(payload: Dict) -> Dict:
    out = {}
    for it in payload.get("items", []):
        val, unit = parse_stock(it["stock"])
        out[it["name"]] = dilute(val, unit, float(it["add_ml"]), float(it["final_ml"]))
    return out


# # --- LangChain tool
@tool("unit_dilution_calculator")
def unit_dilution_calculator(payload: str) -> str:
    """
    Compute final concentrations.

    # Input
    JSON string: {"items":[{"name":"A","stock":"10 mg/mL","add_ml":1,"final_ml":100}]}

    # Output
    JSON string mapping item name -> computed concentration dict.
    """
    try:
        data = json.loads(payload) if isinstance(payload, str) else payload
    except Exception:
        raise ValueError(
            'Expected JSON like: {"items":[{"name":"A","stock":"10 mg/mL","add_ml":1,"final_ml":100}]}'
        )

    return json.dumps(_calc(data))
