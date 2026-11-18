"""Parse a free-text quantity into value, unit, dimension and grams."""
from __future__ import annotations

import re
from typing import Any

from . import config as C

QTY_FIELDS = [
    "qty_value", "qty_unit_raw", "qty_unit_norm", "qty_dimension",
    "qty_canonical_value", "qty_canonical_unit", "qty_approx_g",
    "qty_is_placeholder", "qty_placeholder_code", "qty_parse_status",
]

_NUM_UNIT = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([A-Za-z]+)\.?\s*$")
_NUM_ONLY = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*$")


def normalize_unit(token: str) -> str:
    return C.UNIT_ALIASES.get(token.strip().lower(), token.strip().lower())


def parse_quantity(raw: str) -> dict[str, Any]:
    """Return a QTY_FIELDS dict; every input has a defined result."""
    s = (raw or "").strip()
    out: dict[str, Any] = {k: "" for k in QTY_FIELDS}
    out["qty_is_placeholder"] = "false"
    out["qty_parse_status"] = "OK"
    out["qty_unit_raw"] = s

    low = " ".join(s.lower().split())
    if low in C.PLACEHOLDER_CODES or not low:
        code = C.PLACEHOLDER_CODES.get(low, "UNSPECIFIED")
        out.update({
            "qty_is_placeholder": "true",
            "qty_placeholder_code": code,
            "qty_unit_norm": code,
            "qty_dimension": "na",
            "qty_canonical_unit": code,
            "qty_parse_status": "PLACEHOLDER",
        })
        return out

    m = _NUM_UNIT.match(s)
    if not m:
        if _NUM_ONLY.match(s):
            out.update({
                "qty_value": str(float(_NUM_ONLY.match(s).group(1))),
                "qty_unit_norm": "piece", "qty_dimension": "count",
                "qty_canonical_value": str(float(_NUM_ONLY.match(s).group(1))),
                "qty_canonical_unit": "piece",
                "qty_approx_g": str(float(_NUM_ONLY.match(s).group(1)) * C.UNIT_GRAM_EQUIV["piece"]),
                "qty_parse_status": "OK_UNITLESS",
            })
            return out
        out["qty_parse_status"] = "UNPARSEABLE"
        return out

    value = float(m.group(1))
    unit = normalize_unit(m.group(2))
    if unit not in C.UNIT_DIMENSION:
        out.update({"qty_value": str(value), "qty_unit_norm": unit, "qty_parse_status": "UNKNOWN_UNIT"})
        return out

    canon_unit, factor = C.UNIT_CANONICAL[unit]
    gram_factor = C.UNIT_GRAM_EQUIV[unit]
    out.update({
        "qty_value": str(value),
        "qty_unit_norm": unit,
        "qty_dimension": C.UNIT_DIMENSION[unit],
        "qty_canonical_value": str(round(value * factor, 4)),
        "qty_canonical_unit": canon_unit,
        "qty_approx_g": str(round(value * gram_factor, 4)),
    })
    return out


def canon_per_gram(unit: str) -> float:
    """Return the canonical value per estimated gram for a raw unit.

    qty_canonical_value = qty_approx_g * canon_per_gram(unit)
    Used after merging and clipping to recover the canonical value.
    """
    canon_factor = C.UNIT_CANONICAL[unit][1]
    gram_factor = C.UNIT_GRAM_EQUIV[unit]
    return canon_factor / gram_factor if gram_factor else 1.0


def unit_conversion_rows() -> list[dict[str, str]]:
    """Write data/mappings/unit_conversion.csv for downstream cost roll-ups."""
    rows = []
    for unit in ["g", "kg", "ml", "l", "tbsp", "tsp", "cup", "cloves", "medium", "piece"]:
        canon, factor = C.UNIT_CANONICAL[unit]
        rows.append({
            "raw_unit": unit,
            "dimension": C.UNIT_DIMENSION[unit],
            "canonical_unit": canon,
            "factor_to_canonical": str(factor),
            "gram_equivalent_per_unit": str(C.UNIT_GRAM_EQUIV[unit]),
            "basis": {
                "g": "SI mass base", "kg": "1 kg = 1000 g",
                "ml": "SI volume base (density ~ 1 g/ml)", "l": "1 L = 1000 ml",
                "tbsp": "1 tablespoon = 15 ml ~ 15 g", "tsp": "1 teaspoon = 5 ml ~ 5 g",
                "cup": "1 cup = 240 ml ~ 240 g",
                "cloves": "1 garlic clove ~ 3 g",
                "medium": "1 medium vegetable ~ 100 g",
                "piece": "1 piece ~ 100 g (fallback)",
            }[unit],
        })
    return rows
