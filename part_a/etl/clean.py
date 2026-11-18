"""Clean the raw tables and write data/clean/*.csv.

Raw files are read-only. Every step keeps audit columns. With a fixed
config.RANDOM_SEED the output is byte-identical across runs.
"""
from __future__ import annotations

import collections
import math
from pathlib import Path
from typing import Any

from . import config as C
from . import io_utils as U
from . import mappings as M
from .units import canon_per_gram, parse_quantity

RECIPE_COLUMNS = [
    "recipe_id", "recipe_name", "cuisine", "category", "cooking_method", "difficulty",
    "prep_time_minutes", "cook_time_minutes", "total_time_minutes", "servings",
    "spice_level", "meal_type",
    "is_vegetarian", "is_vegan", "is_gluten_free", "is_halal",
    "is_vegetarian_raw", "is_vegan_raw", "is_gluten_free_raw", "is_halal_raw",
    "is_halal_verifiable", "dietary_conflict_count",
    "rating", "review_count", "calories_per_serving", "estimated_cost_usd",
    "date_added", "is_traditional", "is_festival_special",
    "ingredient_count", "step_count", "allergen_count",
    "estimated_total_g", "estimated_g_per_serving", "qty_clipped_recipe",
]
INGREDIENT_COLUMNS = [
    "recipe_id", "ingredient_number", "canonical_id", "canonical_name",
    "ingredient_name_raw", "category", "quantity_raw",
    "qty_value", "qty_unit_raw", "qty_unit_norm", "qty_dimension",
    "qty_canonical_value", "qty_canonical_unit", "qty_approx_g",
    "qty_is_placeholder", "qty_placeholder_code", "qty_parse_status",
    "merged_row_count", "merged_units", "qty_clipped", "allergen_flags", "match_status",
]
NUTRITION_COLUMNS = [
    "recipe_id", "calories", "protein_g", "carbohydrates_g", "fat_g", "fiber_g",
    "sugar_g", "sodium_mg", "cholesterol_mg", "vitamin_a_percent",
    "vitamin_c_percent", "calcium_percent", "iron_percent",
]
STEP_COLUMNS = ["recipe_id", "step_number", "step_description", "estimated_time_minutes"]
CUISINE_COLUMNS = ["cuisine", "categories", "recipe_count", "category_count"]
CUISINE_CATEGORY_COLUMNS = ["cuisine", "category"]
ALLERGEN_COLUMNS = ["recipe_id", "allergens", "allergen_count",
                    *[f"has_{a}" for a in C.ALLERGEN_COLUMNS]]
AUDIT_COLUMNS = [
    "recipe_id",
    "is_vegetarian_raw", "is_vegetarian_calc",
    "is_vegan_raw", "is_vegan_calc",
    "is_gluten_free_raw", "is_gluten_free_calc",
    "is_halal_raw", "halal_proxy", "halal_proxy_conflict",
    "conflict_count", "conflict_flags",
]
MASTER_COLUMNS = ["canonical_id", "canonical_name", "category", "allergens",
                  "is_animal", "is_meat_fish", "is_gluten_source", "note"]
STATS_COLUMNS = ["canonical_id", "canonical_name", "doc_freq", "total_recipes",
                 "idf", "idf_norm", "rarity_rank", "avg_approx_g", "share_pct"]
SEARCH_COLUMNS = ["recipe_id", "search_document", "doc_length"]


def _empty_approx(r: dict[str, Any]) -> bool:
    return r["qty_is_placeholder"] == "true" or r["qty_approx_g"] == ""


def _merge_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge rows sharing (recipe_id, canonical_id)."""
    base = dict(rows[0])
    base["merged_row_count"] = str(len(rows))
    base["merged_units"] = "|".join(sorted({r["qty_unit_norm"] for r in rows if r["qty_unit_norm"]}))
    base["quantity_raw"] = " | ".join(r["quantity_raw"] for r in rows)
    base["ingredient_name_raw"] = " | ".join(sorted({r["ingredient_name_raw"] for r in rows}))
    base["allergen_flags"] = "|".join(sorted({a for r in rows for a in r["allergen_flags"].split("|") if a and a != "none"}))
    base["match_status"] = "|".join(sorted({r["match_status"] for r in rows}))
    non_ph = [r for r in rows if not _empty_approx(r)]
    if not non_ph:
        # All rows are placeholders: keep the code, leave numeric fields empty
        for k in ["qty_value", "qty_canonical_value", "qty_canonical_unit", "qty_approx_g"]:
            base[k] = ""
        base["qty_dimension"] = "na"
        base["qty_parse_status"] = "PLACEHOLDER"
        return base
    dominant = max(non_ph, key=lambda r: float(r["qty_approx_g"]))
    total_g = sum(float(r["qty_approx_g"]) for r in non_ph)
    base["qty_value"] = dominant["qty_value"]
    base["qty_unit_raw"] = dominant["qty_unit_raw"]
    base["qty_unit_norm"] = dominant["qty_unit_norm"]
    base["qty_dimension"] = dominant["qty_dimension"]
    base["qty_canonical_unit"] = dominant["qty_canonical_unit"]
    base["qty_canonical_value"] = U.fnum(total_g * canon_per_gram(dominant["qty_unit_norm"]), 4)
    base["qty_approx_g"] = U.fnum(total_g, 4)
    base["qty_is_placeholder"] = "false"
    base["qty_placeholder_code"] = ""
    base["qty_parse_status"] = "OK"
    return base


def run(raw_dir: Path | None = None, out_dir: Path | None = None,
        mapping_dir: Path | None = None, verbose: bool = True) -> dict[str, Any]:
    from . import config as C
    raw = raw_dir or C.raw_dir()
    out = out_dir or C.CLEAN
    mp = M.load_mappings(mapping_dir)
    out.mkdir(parents=True, exist_ok=True)
    for fn in C.RAW_FILES.values():
        if not (raw / fn).is_file():
            U.die(f"Missing raw file: {raw / fn} (place the 5 CSVs in archive-datasets/ or data/raw/)")

    Master = U.read_csv(raw / C.RAW_FILES["recipes"])
    Ing = U.read_csv(raw / C.RAW_FILES["ingredients"])
    Nut = U.read_csv(raw / C.RAW_FILES["nutrition"])
    Step = U.read_csv(raw / C.RAW_FILES["steps"])
    Cuis = U.read_csv(raw / C.RAW_FILES["cuisines"])
    allergen_rows = mp["allergen_by_canon"]

    if verbose:
        U.log(f"Read raw data: recipes={len(Master)}, ingredients={len(Ing)}, "
              f"nutrition={len(Nut)}, steps={len(Step)}, cuisines={len(Cuis)}")

    # --- 1. parse quantities and resolve canonical names
    parsed: list[dict[str, Any]] = []
    for r in Ing:
        q = parse_quantity(r["quantity"])
        res = M.resolve(r["ingredient_name"], mp)
        a = allergen_rows.get(res["canonical_name"], {})
        flags = [k for k in C.ALLERGEN_COLUMNS if U.to_bool(a.get(f"has_{k}", "false"))]
        row = {
            "recipe_id": r["recipe_id"],
            "ingredient_number": r["ingredient_number"],
            "canonical_id": res["canonical_id"],
            "canonical_name": res["canonical_name"],
            "ingredient_name_raw": r["ingredient_name"],
            "category": res["category"],
            "quantity_raw": r["quantity"],
            **q,
            "merged_row_count": "1", "merged_units": q["qty_unit_norm"],
            "qty_clipped": "false",
            "allergen_flags": "|".join(flags) if flags else "none",
            "match_status": res["match_status"],
        }
        parsed.append(row)

    # --- 2. merge duplicate ingredients
    groups: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for r in parsed:
        groups[(r["recipe_id"], r["canonical_id"])].append(r)
    merged = [_merge_group(v) for v in groups.values()]
    merged.sort(key=lambda r: (r["recipe_id"], int(r["ingredient_number"])))
    by_recipe: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for r in merged:
        by_recipe[r["recipe_id"]].append(r)
    for rid, rows in by_recipe.items():
        rows.sort(key=lambda r: int(r["ingredient_number"]))
        for i, r in enumerate(rows, 1):
            r["ingredient_number"] = str(i)
    if verbose:
        U.log(f"Merged duplicates: {len(parsed)} -> {len(merged)} rows (-{len(parsed) - len(merged)})")

    # --- 3. winsorise outliers
    sv = {r["recipe_id"]: int(r["servings"]) for r in Master}
    clipped_recipes: list[dict[str, str]] = []
    total_g_by_recipe: dict[str, float] = collections.defaultdict(float)
    for r in merged:
        if r["qty_approx_g"]:
            total_g_by_recipe[r["recipe_id"]] += float(r["qty_approx_g"])
    for rid, rows in by_recipe.items():
        per_serving = total_g_by_recipe[rid] / sv[rid]
        if per_serving <= C.CAP_G_PER_SERVING:
            continue
        scale = C.CAP_G_PER_SERVING / per_serving
        for r in rows:
            if r["qty_approx_g"]:
                r["qty_approx_g"] = U.fnum(float(r["qty_approx_g"]) * scale, 4)
            if r["qty_canonical_value"]:
                r["qty_canonical_value"] = U.fnum(float(r["qty_canonical_value"]) * scale, 4)
            r["qty_clipped"] = "true"
        clipped_recipes.append({
            "recipe_id": rid, "before_g_per_serving": U.fnum(per_serving, 2),
            "after_g_per_serving": U.fnum(C.CAP_G_PER_SERVING, 2),
            "scale_factor": U.fnum(scale, 6), "ingredient_rows": str(len(rows)),
        })
    U.write_csv(C.PROFILE / "clipped_recipes.csv", clipped_recipes,
                ["recipe_id", "before_g_per_serving", "after_g_per_serving",
                 "scale_factor", "ingredient_rows"])
    if verbose:
        U.log(f"Clipped {len(clipped_recipes)} recipes above {C.CAP_G_PER_SERVING:g} g/serving")

    # --- 4. recompute dietary flags
    canon_by_recipe: dict[str, set[str]] = collections.defaultdict(set)
    allergen_by_recipe: dict[str, set[str]] = collections.defaultdict(set)
    for r in merged:
        canon_by_recipe[r["recipe_id"]].add(r["canonical_name"])
        for a in r["allergen_flags"].split("|"):
            if a and a != "none":
                allergen_by_recipe[r["recipe_id"]].add(a)
    audit_rows: list[dict[str, str]] = []
    conflict_by_recipe: dict[str, int] = {}
    recipes_out: list[dict[str, Any]] = []
    step_count: dict[str, int] = collections.Counter(r["recipe_id"] for r in Step)
    for r in Master:
        rid = r["recipe_id"]
        ings = canon_by_recipe[rid]
        calc = {
            "is_vegetarian": not bool(ings & C.NON_VEG_INGREDIENTS),
            "is_vegan": not bool(ings & C.ANIMAL_INGREDIENTS),
            "is_gluten_free": not bool(ings & C.GLUTEN_INGREDIENTS),
        }
        halal_proxy = not bool(ings & C.HALAL_SENSITIVE_INGREDIENTS)
        raw_flags = {k: U.to_bool(r[k]) for k in C.DIETARY_FLAGS}
        diff = [k for k, v in calc.items() if raw_flags[k] != v]
        conflict_by_recipe[rid] = len(diff)
        audit_rows.append({
            "recipe_id": rid,
            "is_vegetarian_raw": U.fmt_bool(raw_flags["is_vegetarian"]),
            "is_vegetarian_calc": U.fmt_bool(calc["is_vegetarian"]),
            "is_vegan_raw": U.fmt_bool(raw_flags["is_vegan"]),
            "is_vegan_calc": U.fmt_bool(calc["is_vegan"]),
            "is_gluten_free_raw": U.fmt_bool(raw_flags["is_gluten_free"]),
            "is_gluten_free_calc": U.fmt_bool(calc["is_gluten_free"]),
            "is_halal_raw": U.fmt_bool(raw_flags["is_halal"]),
            "halal_proxy": U.fmt_bool(halal_proxy),
            "halal_proxy_conflict": U.fmt_bool(raw_flags["is_halal"] != halal_proxy),
            "conflict_count": str(len(diff)),
            "conflict_flags": "|".join(diff),
        })
        total_g = total_g_by_recipe[rid]
        rr = dict(r)
        for k in ["is_vegetarian", "is_vegan", "is_gluten_free"]:
            rr[k] = U.fmt_bool(calc[k])
        rr["is_halal"] = U.fmt_bool(raw_flags["is_halal"])   # unverifiable: keep the source label
        for k in C.DIETARY_FLAGS:
            rr[k + "_raw"] = U.fmt_bool(raw_flags[k])
        rr["is_halal_verifiable"] = "false"
        rr["dietary_conflict_count"] = str(len(diff))
        rr["ingredient_count"] = str(len(by_recipe[rid]))
        rr["step_count"] = str(step_count[rid])
        rr["allergen_count"] = str(len(allergen_by_recipe[rid]))
        per_serving = total_g / sv[rid] if sv[rid] else 0.0
        clipped = per_serving > C.CAP_G_PER_SERVING
        scale = (C.CAP_G_PER_SERVING / per_serving) if clipped else 1.0
        rr["estimated_total_g"] = U.fnum(total_g * scale, 2)
        rr["estimated_g_per_serving"] = U.fnum(min(per_serving, C.CAP_G_PER_SERVING), 2)
        rr["qty_clipped_recipe"] = U.fmt_bool(clipped)
        recipes_out.append(rr)
    if verbose:
        U.log(f"Recomputed 3 verifiable flags, corrected "
              f"{sum(int(a['conflict_count']) for a in audit_rows)} labels; is_halal retained as unverifiable")

    # --- 5. derived tables
    allergen_rows_out: list[dict[str, str]] = []
    for r in Master:
        rid = r["recipe_id"]
        a = sorted(allergen_by_recipe[rid])
        row = {"recipe_id": rid, "allergens": "|".join(a) if a else "none",
               "allergen_count": str(len(a))}
        for k in C.ALLERGEN_COLUMNS:
            row[f"has_{k}"] = U.fmt_bool(k in a)
        allergen_rows_out.append(row)

    master_rows = [{k: r.get(k, "") for k in MASTER_COLUMNS}
                   for r in mp["allergen_rows"]]

    N = len(Master)
    df: dict[str, int] = collections.Counter()
    grams: dict[str, float] = collections.defaultdict(float)
    for r in merged:
        df[r["canonical_id"]] += 1
        if r["qty_approx_g"]:
            grams[r["canonical_id"]] += float(r["qty_approx_g"])
    idfs = {cid: math.log((N + 1) / (d + 1)) + 1.0 for cid, d in df.items()}
    lo, hi = min(idfs.values()), max(idfs.values())
    ranked = sorted(idfs, key=lambda k: (-idfs[k], k))
    rank = {cid: i + 1 for i, cid in enumerate(ranked)}
    stats_rows: list[dict[str, str]] = []
    name_by_id = {r["canonical_id"]: r["canonical_name"] for r in mp["allergen_rows"]}
    for cid in sorted(df, key=lambda k: (-df[k], k)):
        stats_rows.append({
            "canonical_id": cid, "canonical_name": name_by_id.get(cid, ""),
            "doc_freq": str(df[cid]), "total_recipes": str(N),
            "idf": U.fnum(idfs[cid], 6),
            "idf_norm": U.fnum((idfs[cid] - lo) / (hi - lo) if hi > lo else 1.0, 6),
            "rarity_rank": str(rank[cid]),
            "avg_approx_g": U.fnum(grams[cid] / df[cid], 2),
            "share_pct": U.fnum(df[cid] / N * 100, 3),
        })

    steps_by_recipe: dict[str, list[str]] = collections.defaultdict(list)
    for r in sorted(Step, key=lambda x: (x["recipe_id"], int(x["step_number"]))):
        steps_by_recipe[r["recipe_id"]].append(r["step_description"])
    ing_by_recipe_names: dict[str, list[str]] = collections.defaultdict(list)
    for r in merged:
        ing_by_recipe_names[r["recipe_id"]].append(r["canonical_name"])
    search_rows = []
    for r in Master:
        rid = r["recipe_id"]
        doc = " ".join([
            r["recipe_name"], r["cuisine"], r["category"], r["cooking_method"],
            " ".join(sorted(set(ing_by_recipe_names[rid]))),
            " ".join(steps_by_recipe[rid]),
        ])
        search_rows.append({"recipe_id": rid, "search_document": doc,
                            "doc_length": str(len(doc))})

    cuisine_rows, cuisine_cat_rows = [], []
    for r in Cuis:
        cats = [x.strip() for x in r["categories"].split(",") if x.strip()]
        cuisine_rows.append({"cuisine": r["cuisine"], "categories": r["categories"],
                             "recipe_count": r["recipe_count"], "category_count": str(len(cats))})
        for c in cats:
            cuisine_cat_rows.append({"cuisine": r["cuisine"], "category": c})

    # --- 6. write output
    U.write_csv(out / "recipes.csv", recipes_out, RECIPE_COLUMNS)
    U.write_csv(out / "ingredients.csv", merged, INGREDIENT_COLUMNS)
    U.write_csv(out / "nutrition.csv", Nut, NUTRITION_COLUMNS)
    U.write_csv(out / "steps.csv", Step, STEP_COLUMNS)
    U.write_csv(out / "cuisines.csv", cuisine_rows, CUISINE_COLUMNS)
    U.write_csv(out / "cuisine_category.csv", cuisine_cat_rows, CUISINE_CATEGORY_COLUMNS)
    U.write_csv(out / "recipe_allergens.csv", allergen_rows_out, ALLERGEN_COLUMNS)
    U.write_csv(out / "recipe_dietary_audit.csv", audit_rows, AUDIT_COLUMNS)
    U.write_csv(out / "ingredient_master.csv", master_rows, MASTER_COLUMNS)
    U.write_csv(out / "ingredient_stats.csv", stats_rows, STATS_COLUMNS)
    U.write_csv(out / "recipe_search_document.csv", search_rows, SEARCH_COLUMNS)
    if verbose:
        U.log(f"Wrote {len(C.CLEAN_TABLES)} cleaned tables to {out}")
    return {
        "raw_ingredient_rows": len(Ing), "clean_ingredient_rows": len(merged),
        "clipped_recipes": len(clipped_recipes),
        "relabelled_flags": sum(int(a["conflict_count"]) for a in audit_rows),
        "canonical_ingredients": len(df),
    }
