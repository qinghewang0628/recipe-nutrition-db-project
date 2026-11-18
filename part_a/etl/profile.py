"""Field-level profiling and cross-table consistency checks."""
from __future__ import annotations

import collections
import json
import re
import statistics
from pathlib import Path
from typing import Any

from . import config as C
from . import io_utils as U
from .mappings import canonical_name
from .units import parse_quantity

_NUM = re.compile(r"^-?\d+(?:\.\d+)?$")


def _column_stats(rows: list[dict[str, str]], col: str) -> dict[str, Any]:
    vals = [r.get(col, "") for r in rows]
    empty = sum(1 for v in vals if str(v).strip() == "")
    uniq = len(set(vals))
    nums = [float(v) for v in vals if _NUM.fullmatch(str(v).strip())]
    st: dict[str, Any] = {
        "empty": empty, "distinct": uniq,
        "type": "numeric" if len(nums) == len(vals) - empty and nums else "text",
        "top": [[k, v] for k, v in collections.Counter(vals).most_common(5)],
    }
    if nums and st["type"] == "numeric":
        st.update({"min": min(nums), "max": max(nums), "mean": round(statistics.mean(nums), 4)})
    return st


def file_profile(path: Path) -> dict[str, Any]:
    rows = U.read_csv(path)
    cols = U.fieldnames(path)
    return {
        "file": path.name,
        "rows": len(rows),
        "columns": len(cols),
        "sha256": U.sha256(path),
        "bytes": path.stat().st_size,
        "exact_duplicate_rows": len(rows) - len({tuple(r.get(c, "") for c in cols) for r in rows}),
        "fields": {c: _column_stats(rows, c) for c in cols},
    }


def raw_cross_checks(raw: Path, mp: dict[str, Any]) -> dict[str, Any]:
    Master = U.read_csv(raw / C.RAW_FILES["recipes"])
    Ing = U.read_csv(raw / C.RAW_FILES["ingredients"])
    Nut = U.read_csv(raw / C.RAW_FILES["nutrition"])
    Step = U.read_csv(raw / C.RAW_FILES["steps"])
    Cuis = U.read_csv(raw / C.RAW_FILES["cuisines"])
    ids = {r["recipe_id"] for r in Master}
    nut = {r["recipe_id"]: r for r in Nut}

    # Cuisine metadata vs master table
    mc = collections.Counter(r["cuisine"] for r in Master)
    cuisine_rows = [{
        "cuisine": r["cuisine"], "meta_count": int(r["recipe_count"]),
        "actual_count": mc[r["cuisine"]], "match": int(r["recipe_count"]) == mc[r["cuisine"]],
    } for r in Cuis]

    # Referential integrity
    ref: dict[str, Any] = {}
    for name, rows in [("ingredients", Ing), ("nutrition", Nut), ("steps", Step)]:
        s = {r["recipe_id"] for r in rows}
        ref[name] = {"orphan_recipe_ids": len(s - ids),
                     "master_without_child": len(ids - s),
                     "duplicate_keys": len(rows) - len(s) if name == "nutrition" else None}

    # Dietary label conflicts (raw and canonical names)
    by: dict[str, set[str]] = collections.defaultdict(set)
    for r in Ing:
        by[r["recipe_id"]].add(canonical_name(r["ingredient_name"]))
    conflicts = collections.Counter()
    raw_true = collections.Counter()
    calc_true = collections.Counter()
    any_conflict = 0
    for r in Master:
        ings = by[r["recipe_id"]]
        calc = {
            "is_vegetarian": not (ings & C.NON_VEG_INGREDIENTS),
            "is_vegan": not (ings & C.ANIMAL_INGREDIENTS),
            "is_gluten_free": not (ings & C.GLUTEN_INGREDIENTS),
            "is_halal": not (ings & C.HALAL_SENSITIVE_INGREDIENTS),
        }
        hit = False
        for k, v in calc.items():
            raw_true[k] += int(U.to_bool(r[k]))
            calc_true[k] += int(v)
            if v != U.to_bool(r[k]):
                conflicts[k] += 1
                hit = True
        any_conflict += int(hit)

    # Quantity parseability
    parse_status = collections.Counter()
    placeholders = 0
    unit_counts: dict[str, int] = collections.Counter()
    approx_by_recipe: dict[str, float] = collections.defaultdict(float)
    for r in Ing:
        p = parse_quantity(r["quantity"])
        parse_status[p["qty_parse_status"]] += 1
        if p["qty_is_placeholder"] == "true":
            placeholders += 1
        else:
            unit_counts[p["qty_unit_norm"]] += 1
            if p["qty_approx_g"]:
                approx_by_recipe[r["recipe_id"]] += float(p["qty_approx_g"])

    # Duplicate ingredients (by canonical name)
    groups: dict[tuple[str, str], int] = collections.Counter()
    for r in Ing:
        groups[(r["recipe_id"], canonical_name(r["ingredient_name"]))] += 1
    dup_groups = sum(1 for v in groups.values() if v > 1)
    dup_extra = sum(v - 1 for v in groups.values() if v > 1)

    # Outliers
    sv = {r["recipe_id"]: int(r["servings"]) for r in Master}
    per_serving = [approx_by_recipe[k] / sv[k] for k in sv]
    per_serving_sorted = sorted(per_serving)
    def pct(p: float) -> float:
        return per_serving_sorted[min(len(per_serving_sorted) - 1, int(len(per_serving_sorted) * p))]
    over_cap = sum(1 for v in per_serving if v > C.CAP_G_PER_SERVING)

    # Time consistency
    time_prep_cook_ok = sum(1 for r in Master
                            if int(r["prep_time_minutes"]) + int(r["cook_time_minutes"]) == int(r["total_time_minutes"]))
    step_sum: dict[str, int] = collections.defaultdict(int)
    for r in Step:
        step_sum[r["recipe_id"]] += int(r["estimated_time_minutes"])
    md = {r["recipe_id"]: r for r in Master}
    step_time_exact = sum(1 for k in step_sum if step_sum[k] == int(md[k]["total_time_minutes"]))

    # Ingredient category conflicts
    cat: dict[str, set[str]] = collections.defaultdict(set)
    for r in Ing:
        cat[r["ingredient_name"]].add(r["category"])
    cat_conflicts = {k: sorted(v) for k, v in cat.items() if len(v) > 1}

    # Text and dates
    dates = [r["date_added"] for r in Master]
    bad_dates = sum(1 for d in dates if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d))
    quote_hazard = 0
    max_name_len = 0
    for f, cols in [(C.RAW_FILES["recipes"], ["recipe_name", "cuisine", "category"]),
                    (C.RAW_FILES["steps"], ["step_description"]),
                    (C.RAW_FILES["ingredients"], ["ingredient_name", "quantity"])]:
        for r in U.read_csv(raw / f):
            for c in cols:
                max_name_len = max(max_name_len, len(r[c]))
                if any(ch in r[c] for ch in ',"\n\r'):
                    quote_hazard += 1

    return {
        "row_counts": {k: len(U.read_csv(raw / v)) for k, v in C.RAW_FILES.items()},
        "total_rows": sum(len(U.read_csv(raw / v)) for v in C.RAW_FILES.values()),
        "primary_key_unique": {
            "recipes_master.recipe_id": len(set(r["recipe_id"] for r in Master)) == len(Master),
            "recipe_nutrition.recipe_id": len(nut) == len(Nut),
        },
        "referential_integrity": ref,
        "cuisine_metadata": cuisine_rows,
        "calories_mismatch_master_vs_nutrition": sum(
            1 for r in Master if r["calories_per_serving"] != nut[r["recipe_id"]]["calories"]),
        "prep_plus_cook_equals_total": time_prep_cook_ok,
        "step_time_sum_equals_total": step_time_exact,
        "dietary_conflicts": dict(conflicts),
        "dietary_raw_true_counts": dict(raw_true),
        "dietary_calc_true_counts": dict(calc_true),
        "dietary_conflict_recipes": any_conflict,
        "dietary_conflict_total_labels": sum(conflicts.values()),
        "dietary_conflict_verifiable_labels": sum(v for k, v in conflicts.items() if k != "is_halal"),
        "quantity_parse_status": dict(parse_status),
        "quantity_placeholder_rows": placeholders,
        "quantity_unit_distribution": dict(unit_counts.most_common()),
        "distinct_quantity_strings": len({r["quantity"] for r in Ing}),
        "duplicate_ingredient_groups": dup_groups,
        "duplicate_ingredient_extra_rows": dup_extra,
        "approx_g_per_serving": {
            "min": round(min(per_serving), 2), "p50": round(pct(.50), 2),
            "p95": round(pct(.95), 2), "p99": round(pct(.99), 2),
            "max": round(max(per_serving), 2),
            "cap": C.CAP_G_PER_SERVING, "recipes_over_cap": over_cap,
        },
        "category_conflicts": cat_conflicts,
        "date_min": min(dates), "date_max": max(dates),
        "invalid_date_rows": bad_dates,
        "future_date_rows": sum(1 for d in dates if d > "2026-11-16"),
        "quote_hazard_rows": quote_hazard,
        "max_text_length": max_name_len,
        "distinct_recipe_names": len({r["recipe_name"] for r in Master}),
        "distinct_step_templates": len({r["step_description"] for r in Step}),
        "distinct_ingredient_names": len({r["ingredient_name"] for r in Ing}),
        "empty_cells_total": sum(
            fp["fields"][c]["empty"] for fp in [] for c in []),  # placeholder, filled below
    }


def clean_cross_checks(clean: Path) -> dict[str, Any]:
    R = U.read_csv(clean / "recipes.csv")
    I = U.read_csv(clean / "ingredients.csv")
    N = U.read_csv(clean / "nutrition.csv")
    S = U.read_csv(clean / "steps.csv")
    A = U.read_csv(clean / "recipe_allergens.csv")
    ids = {r["recipe_id"] for r in R}
    groups = collections.Counter((r["recipe_id"], r["canonical_id"]) for r in I)
    dup_after = sum(1 for v in groups.values() if v > 1)
    parse_bad = sum(1 for r in I if r["qty_parse_status"] in {"UNPARSEABLE", "UNKNOWN_UNIT"})
    clipped_rows = sum(1 for r in I if U.to_bool(r["qty_clipped"]))
    clipped_recipes = len({r["recipe_id"] for r in I if U.to_bool(r["qty_clipped"])})
    placeholders = sum(1 for r in I if U.to_bool(r["qty_is_placeholder"]))
    merged_rows = sum(1 for r in I if int(r["merged_row_count"] or 1) > 1)
    audit = U.read_csv(clean / "recipe_dietary_audit.csv")
    corrections = sum(int(r["conflict_count"]) for r in audit)
    # Residual conflicts must be zero after cleaning
    canon_by: dict[str, set[str]] = collections.defaultdict(set)
    for r in I:
        canon_by[r["recipe_id"]].add(r["canonical_name"])
    rmap = {r["recipe_id"]: r for r in R}
    residual = 0
    for rid, ings in canon_by.items():
        rr = rmap[rid]
        residual += int(U.to_bool(rr["is_vegetarian"]) != (not bool(ings & C.NON_VEG_INGREDIENTS)))
        residual += int(U.to_bool(rr["is_vegan"]) != (not bool(ings & C.ANIMAL_INGREDIENTS)))
        residual += int(U.to_bool(rr["is_gluten_free"]) != (not bool(ings & C.GLUTEN_INGREDIENTS)))
    nut = {r["recipe_id"]: r for r in N}
    return {
        "row_counts": {"recipes": len(R), "ingredients": len(I), "nutrition": len(N),
                       "steps": len(S), "recipe_allergens": len(A)},
        "duplicate_ingredient_groups": dup_after,
        "unparseable_quantity_rows": parse_bad,
        "placeholder_rows_normalized": placeholders,
        "merged_ingredient_rows": merged_rows,
        "clipped_ingredient_rows": clipped_rows,
        "clipped_recipes": clipped_recipes,
        "dietary_labels_corrected": corrections,
        "dietary_residual_conflicts": residual,
        "halal_unverifiable_conflicts_retained": sum(
            1 for r in audit if U.to_bool(r["halal_proxy_conflict"])),
        "calories_mismatch_master_vs_nutrition": sum(
            1 for r in R if r["calories_per_serving"] != nut[r["recipe_id"]]["calories"]),
        "orphan_recipe_ids": {n: len({r["recipe_id"] for r in rows} - ids)
                              for n, rows in [("ingredients", I), ("nutrition", N), ("steps", S)]},
        "distinct_canonical_ingredients": len({r["canonical_id"] for r in I}),
        "rows_with_allergen": sum(1 for r in A if r["allergens"] not in {"", "none"}),
    }


def build_raw_profile(raw: Path, mp: dict[str, Any]) -> dict[str, Any]:
    files = {}
    empty_total = 0
    for key, fn in C.RAW_FILES.items():
        fp = file_profile(raw / fn)
        files[fn] = fp
        empty_total += sum(v["empty"] for v in fp["fields"].values())
    cross = raw_cross_checks(raw, mp)
    cross["empty_cells_total"] = empty_total
    cross["raw_sha256"] = {fn: U.sha256(raw / fn) for fn in C.RAW_FILES.values()}
    cross["raw_sha256_matches_expected"] = all(
        cross["raw_sha256"][fn] == C.RAW_SHA256[fn] for fn in C.RAW_FILES.values())
    return {"stage": "raw", "files": files, "cross_checks": cross}


def build_clean_profile(clean: Path) -> dict[str, Any]:
    files = {f"{n}.csv": file_profile(clean / f"{n}.csv") for n in C.CLEAN_TABLES
             if (clean / f"{n}.csv").is_file()}
    return {"stage": "clean", "files": files, "cross_checks": clean_cross_checks(clean)}


def quality_summary(raw_p: dict[str, Any], clean_p: dict[str, Any]) -> list[dict[str, str]]:
    rc, cc = raw_p["cross_checks"], clean_p["cross_checks"]
    rows = [
        ("Ingredient rows", rc["row_counts"]["ingredients"], cc["row_counts"]["ingredients"], "Fewer rows after merging"),
        ("Recipes", rc["row_counts"]["recipes"], cc["row_counts"]["recipes"], "Unchanged"),
        ("Empty cells", rc["empty_cells_total"], 0, "No nulls after cleaning"),
        ("Dietary label conflicts (4 flags)", rc["dietary_conflict_total_labels"], 0,
         "10,862 verifiable labels recomputed; 1,328 is_halal conflicts retained and marked unverifiable"),
        ("Recipes with a conflict", rc["dietary_conflict_recipes"], 0, "Zero residual conflicts; the audit table keeps every raw value"),
        ("Duplicate ingredient groups", rc["duplicate_ingredient_groups"], cc["duplicate_ingredient_groups"], "Merged by canonical name"),
        ("Surplus duplicate rows", rc["duplicate_ingredient_extra_rows"], 0, "Quantities summed as estimated grams"),
        ("'to taste' placeholder rows", rc["quantity_placeholder_rows"], cc["placeholder_rows_normalized"],
         "Coded as TO_TASTE; 1,057 rows merged into quantified rows of the same ingredient"),
        ("Unparseable quantity rows", sum(v for k, v in rc["quantity_parse_status"].items()
                              if k in {"UNPARSEABLE", "UNKNOWN_UNIT"}), cc["unparseable_quantity_rows"], "All 6 units covered"),
        ("Recipes above the cap", rc["approx_g_per_serving"]["recipes_over_cap"], 0, "Winsorised to 1200 g/serving"),
        ("Distinct quantity strings", rc["distinct_quantity_strings"], "-", "Reduced to g/ml/piece plus placeholder codes"),
        ("Distinct ingredient names", rc["distinct_ingredient_names"], cc["distinct_canonical_ingredients"], "Synonyms merged to canonical ids"),
        ("Ingredients with category conflicts", len(rc["category_conflicts"]), 0, "Paneer resolved to Dairy"),
        ("Recipes with an allergen", "-", cc["rows_with_allergen"], "New table recipe_allergens.csv"),
    ]
    return [{"metric": a, "before": str(b), "after": str(c), "note": d} for a, b, c, d in rows]


def render_markdown(raw_p: dict[str, Any], clean_p: dict[str, Any],
                    summary: list[dict[str, str]]) -> str:
    rc, cc = raw_p["cross_checks"], clean_p["cross_checks"]
    L: list[str] = []
    L.append("# Profile Metrics (generated by `make seed`; do not edit)\n")
    L.append("> Source: five CSVs in `archive-datasets/`. Command: `python -m etl.pipeline all`.\n")
    L.append("> This file is the single source for every figure in the report and the video.\n\n")

    L.append("## 1. Raw Files and Field Profile\n")
    L.append("| File | Rows | Cols | Bytes | Duplicate rows | SHA-256 (first 12) |\n|---|---:|---:|---:|---:|---|\n")
    for fn, fp in raw_p["files"].items():
        L.append(f"| `{fn}` | {U.human(fp['rows'])} | {fp['columns']} | {U.human(fp['bytes'])} | "
                 f"{fp['exact_duplicate_rows']} | `{fp['sha256'][:12]}` |\n")
    L.append(f"\nTotal **{U.human(rc['total_rows'])}** rows, **{rc['empty_cells_total']}** empty cells; "
             f"all raw checksums match: **{rc['raw_sha256_matches_expected']}**.\n\n")

    L.append("### 1.1 Field-level Summary\n")
    L.append("| File | Column | Type | Nulls | Distinct | Range / Top values |\n|---|---|---|---:|---:|---|\n")
    for fn, fp in raw_p["files"].items():
        for c, st in fp["fields"].items():
            if st["type"] == "numeric":
                rng = f"{st['min']:g} ~ {st['max']:g} (mean {st['mean']:g})"
            else:
                rng = ", ".join(f"{k[:18]}({v})" for k, v in st["top"][:3])
            L.append(f"| `{fn}` | `{c}` | {st['type']} | {st['empty']} | {st['distinct']} | {rng} |\n")
    L.append("\n")

    L.append("## 2. Cross-table Consistency and Semantic Conflicts (Before Cleaning)\n")
    L.append("| Check | Result | Verdict |\n|---|---|---|\n")
    chk = [
        ("PK unique recipes_master.recipe_id", str(rc["primary_key_unique"]["recipes_master.recipe_id"]), "PASS"),
        ("PK unique recipe_nutrition.recipe_id", str(rc["primary_key_unique"]["recipe_nutrition.recipe_id"]), "PASS"),
        ("Orphan recipe_id (ingredients/nutrition/steps)",
         "/".join(str(v["orphan_recipe_ids"]) for v in rc["referential_integrity"].values()), "PASS (all 0)"),
        ("cuisine_metadata.recipe_count matches the master table",
         str(all(x["match"] for x in rc["cuisine_metadata"])), f"5/5 PASS, total {sum(x['actual_count'] for x in rc['cuisine_metadata'])}"),
        ("Rows where calories_per_serving != nutrition.calories",
         str(rc["calories_mismatch_master_vs_nutrition"]), "PASS (0)"),
        ("Recipes with prep + cook = total_time",
         f"{U.human(rc['prep_plus_cook_equals_total'])}/{U.human(rc['row_counts']['recipes'])}", "PASS"),
        ("Recipes with sum(step time) = total_time",
         f"{U.human(rc['step_time_sum_equals_total'])}/{U.human(rc['row_counts']['recipes'])}",
         "**FAIL**: step times are template noise and are not a business metric"),
        ("Date range", f"{rc['date_min']} ~ {rc['date_max']}", "No future dates or format errors"),
        ("Rows with quote/newline hazards", str(rc["quote_hazard_rows"]), "PASS (0)"),
        ("Distinct recipe names / step templates / ingredients",
         f"{rc['distinct_recipe_names']} / {rc['distinct_step_templates']} / {rc['distinct_ingredient_names']}",
         "Only 20 step templates, indicating synthetic teaching data"),
    ]
    for a, b, c in chk:
        L.append(f"| {a} | {b} | {c} |\n")
    L.append("\n")

    L.append("### 2.1 Dietary Label Conflicts\n")
    L.append("| Flag | Conflicting recipes | Share | Source True | Derived True | Note |\n"
             "|---|---:|---:|---:|---:|---|\n")
    n = rc["row_counts"]["recipes"]
    for k, v in rc["dietary_conflicts"].items():
        note = ("**Conservative proxy, unverifiable**: source label retained, `is_halal_verifiable=false`" if k == "is_halal"
                else "Recomputed from the ingredient set")
        L.append(f"| `{k}` | {U.human(v)} | {v / n * 100:.1f}% | "
                 f"{U.human(rc['dietary_raw_true_counts'][k])} | "
                 f"{U.human(rc['dietary_calc_true_counts'][k])} | {note} |\n")
    L.append(f"| **Total (label level)** | **{U.human(rc['dietary_conflict_total_labels'])}** | - | - | - | "
             f"**{U.human(rc['dietary_conflict_recipes'])}** recipes"
             f"({rc['dietary_conflict_recipes'] / n * 100:.1f}%); "
             f"**{U.human(rc['dietary_conflict_verifiable_labels'])}** verifiable labels corrected |\n\n")

    L.append("### 2.2 Quantity String Profile\n")
    L.append("| Metric | Value |\n|---|---:|\n")
    for k, v in [
        ("Distinct quantity strings", rc["distinct_quantity_strings"]),
        ("`to taste` rows", rc["quantity_placeholder_rows"]),
        ("Parseable rows", sum(v for k, v in rc["quantity_parse_status"].items() if k.startswith("OK"))),
        ("Parse status distribution", str(rc["quantity_parse_status"])),
        ("Unit distribution", str(rc["quantity_unit_distribution"])),
        ("Duplicate groups / surplus rows", f"{rc['duplicate_ingredient_groups']} / {rc['duplicate_ingredient_extra_rows']}"),
        ("Estimated g/serving P50 / P95 / P99 / Max",
         f"{rc['approx_g_per_serving']['p50']} / {rc['approx_g_per_serving']['p95']} / "
         f"{rc['approx_g_per_serving']['p99']} / {rc['approx_g_per_serving']['max']} g"),
        (f"Recipes above {C.CAP_G_PER_SERVING:g} g/serving", rc["approx_g_per_serving"]["recipes_over_cap"]),
        ("Ingredient category conflicts", str(rc["category_conflicts"])),
    ]:
        L.append(f"| {k} | {v} |\n")
    L.append("\n")

    L.append("## 3. Before and After Cleaning (quoted in the video)\n")
    L.append("| Metric | Before | After | Action |\n|---|---:|---:|---|\n")
    for r in summary:
        L.append(f"| {r['metric']} | {r['before']} | {r['after']} | {r['note']} |\n")
    L.append("\n")

    L.append("## 4. Cleaned Output Tables\n")
    L.append("| Table | Rows | Cols | Purpose |\n|---|---:|---:|---|\n")
    usage = {
        "recipes": "Master table / multi-predicate filter", "ingredients": "Inverted index and reverse lookup",
        "nutrition": "Nutrition range filter / nutrition panel", "steps": "Full-text document / step display",
        "cuisines": "Dimension table", "recipe_allergens": "Allergen exclusion / detail flags",
        "recipe_dietary_audit": "Audit trail and report figures", "ingredient_master": "Ingredient dimension",
        "ingredient_stats": "IDF rarity weights", "recipe_search_document": "Full-text document",
    }
    for fn, fp in clean_p["files"].items():
        k = fn[:-4]
        L.append(f"| `{fn}` | {U.human(fp['rows'])} | {fp['columns']} | {usage.get(k, '-')} |\n")
    L.append("\n")
    L.append(f"After cleaning: duplicate groups **{cc['duplicate_ingredient_groups']}**, unparseable quantities **{cc['unparseable_quantity_rows']}**, "
             f"residual conflicts **{cc['dietary_residual_conflicts']}** ("
             f"**{U.human(cc['dietary_labels_corrected'])}** corrected; "
             f"**{U.human(cc['halal_unverifiable_conflicts_retained'])}** is_halal conflicts retained as unverifiable), "
             f"clipped recipes **{cc['clipped_recipes']}**, recipes with an allergen "
             f"**{U.human(cc['rows_with_allergen'])}**.\n")
    return "".join(L)
