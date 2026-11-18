"""Build and load the four lookup tables used by the cleaner."""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from . import config as C
from . import io_utils as U
from .units import unit_conversion_rows

SYNONYM_COLUMNS = ["alias", "alias_type", "canonical_id", "canonical_name", "note"]
ALLERGEN_COLUMNS = [
    "canonical_id", "canonical_name", "category", "allergens",
    *[f"has_{a}" for a in C.ALLERGEN_COLUMNS],
    "is_animal", "is_meat_fish", "is_gluten_source", "note",
]
DIETARY_COLUMNS = ["flag", "rule", "derived_from", "verifiable", "conflict_policy", "note"]
UNIT_COLUMNS = ["raw_unit", "dimension", "canonical_unit", "factor_to_canonical",
                "gram_equivalent_per_unit", "basis"]


def canonical_name(raw: str) -> str:
    return C.CANONICAL_MERGE.get(raw.strip(), raw.strip())


def canonical_id(name: str) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")
    return "ING_" + slug


def build_mappings(raw_ingredients: list[dict[str, str]], out_dir: Path | None = None) -> dict[str, Any]:
    """Build all lookup tables from the raw ingredients and return them."""
    out_dir = out_dir or C.MAPPINGS
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_names = sorted({r["ingredient_name"].strip() for r in raw_ingredients})
    cat_votes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in raw_ingredients:
        cat_votes[r["ingredient_name"].strip()][r["category"].strip()] += 1

    canon_names = sorted({canonical_name(n) for n in raw_names})
    # Canonical category: explicit override, else majority vote of raw rows
    canon_cat: dict[str, str] = {}
    cat_conflicts: dict[str, list[str]] = {}
    for cn in canon_names:
        votes: dict[str, int] = defaultdict(int)
        merged = [n for n in raw_names if canonical_name(n) == cn]
        for n in merged:
            for cat, c in cat_votes[n].items():
                votes[cat] += c
        if cn in C.CATEGORY_OVERRIDE:
            canon_cat[cn] = C.CATEGORY_OVERRIDE[cn]
            if len(votes) > 1:
                cat_conflicts[cn] = sorted(votes)
        else:
            canon_cat[cn] = max(votes, key=lambda k: (votes[k], k)) if votes else C.DEFAULT_CATEGORY
            if len(votes) > 1:
                cat_conflicts[cn] = sorted(votes)

    # ---- ingredient_synonyms.csv ----
    syn: list[dict[str, str]] = []
    seen: set[str] = set()
    for n in raw_names:
        cn = canonical_name(n)
        key = n.lower()
        if key not in seen:
            seen.add(key)
            syn.append({
                "alias": n,
                "alias_type": "merge" if cn != n else "exact",
                "canonical_id": canonical_id(cn),
                "canonical_name": cn,
                "note": ("Synonym of %s (both wheat flour); one canonical id for indexing" % cn) if cn != n
                        else "Raw name present in the dataset",
            })
    for alias, cn in sorted(C.QUERY_ALIASES.items()):
        key = alias.lower()
        if key not in seen:
            seen.add(key)
            syn.append({
                "alias": alias, "alias_type": "query_alias",
                "canonical_id": canonical_id(cn), "canonical_name": cn,
                "note": "Query alias only; used for normalisation, not for merging",
            })
    # Case and punctuation variants
    for n in raw_names:
        key = re.sub(r"[^a-z0-9]", " ", n.lower()).strip()
        if key and key not in seen:
            seen.add(key)
            syn.append({
                "alias": key, "alias_type": "normalized",
                "canonical_id": canonical_id(canonical_name(n)),
                "canonical_name": canonical_name(n),
                "note": "Case / punctuation variant",
            })
    U.write_csv(out_dir / "ingredient_synonyms.csv", syn, SYNONYM_COLUMNS)

    # ---- allergen_map.csv ----
    amap: list[dict[str, str]] = []
    for cn in canon_names:
        # A canonical name inherits the union of its group's allergens
        allergens: set[str] = set()
        for n in raw_names:
            if canonical_name(n) == cn:
                allergens.update(C.ALLERGEN_BY_INGREDIENT.get(n, []))
        allergens = {a for a in allergens if a in C.ALLERGEN_COLUMNS}
        row: dict[str, str] = {
            "canonical_id": canonical_id(cn),
            "canonical_name": cn,
            "category": canon_cat[cn],
            "allergens": "|".join(sorted(allergens)) if allergens else "none",
            "is_animal": U.fmt_bool(cn in C.ANIMAL_INGREDIENTS),
            "is_meat_fish": U.fmt_bool(cn in C.NON_VEG_INGREDIENTS),
            "is_gluten_source": U.fmt_bool(cn in C.GLUTEN_INGREDIENTS),
            "note": "",
        }
        for a in C.ALLERGEN_COLUMNS:
            row[f"has_{a}"] = U.fmt_bool(a in allergens)
        if cn in cat_conflicts:
            row["note"] = "Conflicting raw categories: %s; resolved to %s" % ("/".join(cat_conflicts[cn]), canon_cat[cn])
        elif cn == "Fresh Coriander":
            row["note"] = "Coriander leaf; distinct from Coriander seed, not merged"
        elif cn == "Coriander":
            row["note"] = "Coriander seed; distinct from Fresh Coriander leaf, not merged"
        elif cn == "Tofu":
            row["note"] = "Soy product; contains soy allergen"
        elif cn == "Coconut Milk":
            row["note"] = "Not a tree nut under Codex practice; FDA classification needs a separate flag"
        amap.append(row)
    U.write_csv(out_dir / "allergen_map.csv", amap, ALLERGEN_COLUMNS)

    # ---- dietary_rules.csv ----
    rules = [
        {
            "flag": "is_vegetarian",
            "rule": "Canonical ingredient set is disjoint from NON_VEG={'Beef','Chicken','Fish','Mutton','Shrimp','Eggs'}",
            "derived_from": "recipe_ingredients.ingredient_name -> ingredient_synonyms",
            "verifiable": "true",
            "conflict_policy": "Recomputed value wins; the original is kept in recipes.is_vegetarian_raw and recipe_dietary_audit.csv",
            "note": "Eggs count as non-vegetarian; change the rule and rerun `make seed` if needed",
        },
        {
            "flag": "is_vegan",
            "rule": "Canonical ingredient set is disjoint from ANIMAL=NON_VEG + {Milk,Butter,Ghee,Cream,Yogurt,Paneer}",
            "derived_from": "recipe_ingredients.ingredient_name -> allergen_map.is_animal",
            "verifiable": "true",
            "conflict_policy": "Recomputed value wins; the original is kept in *_raw and the audit table",
            "note": "Vegan excludes all animal products; honey is absent from the dataset",
        },
        {
            "flag": "is_gluten_free",
            "rule": "Canonical ingredient set is disjoint from GLUTEN={'Wheat Flour','All-Purpose Flour','Semolina'}",
            "derived_from": "recipe_ingredients.ingredient_name -> allergen_map.has_gluten",
            "verifiable": "true",
            "conflict_policy": "Recomputed value wins; the original is kept in *_raw and the audit table",
            "note": "Chickpea Flour, Basmati Rice and Lentils (Dal) are gluten-free; cross-contamination is not modelled",
        },
        {
            "flag": "is_halal",
            "rule": "Conservative proxy: no pork or alcohol ingredients (both sets are empty here)",
            "derived_from": "recipe_ingredients.ingredient_name (insufficient information)",
            "verifiable": "false",
            "conflict_policy": "Keep the source label; write the proxy only to recipe_dietary_audit.halal_proxy",
            "note": "Slaughter and certification data are absent; the report marks this field unverifiable",
        },
    ]
    U.write_csv(out_dir / "dietary_rules.csv", rules, DIETARY_COLUMNS)

    # ---- unit_conversion.csv ----
    U.write_csv(out_dir / "unit_conversion.csv", unit_conversion_rows(), UNIT_COLUMNS)

    return {
        "raw_names": raw_names,
        "canon_names": canon_names,
        "canon_cat": canon_cat,
        "cat_conflicts": cat_conflicts,
        "synonym_count": len(syn),
        "alias_by_lower": {s["alias"].lower(): s for s in syn},
        "allergen_by_canon": {r["canonical_name"]: r for r in amap},
        "allergen_by_id": {r["canonical_id"]: r for r in amap},
    }


def load_mappings(mapping_dir: Path | None = None) -> dict[str, Any]:
    """Load lookup tables from disk so all modules use identical values."""
    d = mapping_dir or C.MAPPINGS
    syn = U.read_csv(d / "ingredient_synonyms.csv")
    allerg = U.read_csv(d / "allergen_map.csv")
    return {
        "alias_by_lower": {s["alias"].lower(): s for s in syn},
        "allergen_by_canon": {r["canonical_name"]: r for r in allerg},
        "allergen_by_id": {r["canonical_id"]: r for r in allerg},
        "synonym_rows": syn,
        "allergen_rows": allerg,
    }


def resolve(name: str, mp: dict[str, Any]) -> dict[str, str]:
    """Resolve any ingredient name or alias to canonical id, name and category."""
    key = " ".join(name.strip().lower().split())
    s = mp["alias_by_lower"].get(key)
    if s is None:
        # Fallback: retry after punctuation normalisation
        key2 = re.sub(r"[^a-z0-9]", " ", key).strip()
        s = mp["alias_by_lower"].get(key2)
    if s is None:
        cn = canonical_name(name)
        cid = canonical_id(cn)
        a = mp["allergen_by_id"].get(cid, {})
        return {"canonical_id": cid, "canonical_name": cn,
                "category": a.get("category", C.DEFAULT_CATEGORY), "match_status": "UNMAPPED"}
    a = mp["allergen_by_id"].get(s["canonical_id"], {})
    return {"canonical_id": s["canonical_id"], "canonical_name": s["canonical_name"],
            "category": a.get("category", C.DEFAULT_CATEGORY), "match_status": s["alias_type"]}
