"""Build the small / medium / large datasets by seeded replication."""
from __future__ import annotations

import collections
import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from . import config as C
from . import io_utils as U
from .clean import (ALLERGEN_COLUMNS, CUISINE_COLUMNS, INGREDIENT_COLUMNS,
                    NUTRITION_COLUMNS, RECIPE_COLUMNS, STATS_COLUMNS, STEP_COLUMNS)


def _jitter(rng: random.Random, v: float, pct: float, lo: float, hi: float, nd: int = 0) -> str:
    x = v * (1.0 + rng.uniform(-pct, pct))
    x = max(lo, min(hi, x))
    return U.fnum(round(x, nd), nd) if nd else str(int(round(x)))


def _shift_date(rng: random.Random, s: str) -> str:
    d = date.fromisoformat(s)
    return (d + timedelta(days=rng.randint(-180, 180))).isoformat()


def build_scale(name: str, factor: int, clean_dir: Path, out_dir: Path | None = None,
                verbose: bool = True) -> dict[str, Any]:
    out = out_dir or (C.SCALES / name)
    out.mkdir(parents=True, exist_ok=True)

    recipes = U.read_csv(clean_dir / "recipes.csv")
    nutrition = {r["recipe_id"]: r for r in U.read_csv(clean_dir / "nutrition.csv")}
    ing_by: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    for r in U.read_csv(clean_dir / "ingredients.csv"):
        ing_by[r["recipe_id"]].append(r)
    steps_by: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    for r in U.read_csv(clean_dir / "steps.csv"):
        steps_by[r["recipe_id"]].append(r)
    cuisines = U.read_csv(clean_dir / "cuisines.csv")

    files = {t: out / f"{t}.csv" for t in C.SCALE_TABLES}
    handles: dict[str, Any] = {}
    writers: dict[str, csv.DictWriter] = {}
    try:
        for t, p in files.items():
            fh = open(p, "w", encoding="utf-8", newline="")
            handles[t] = fh
            cols = {
                "recipes": RECIPE_COLUMNS, "ingredients": INGREDIENT_COLUMNS,
                "nutrition": NUTRITION_COLUMNS, "steps": STEP_COLUMNS,
                "cuisines": CUISINE_COLUMNS, "recipe_allergens": ALLERGEN_COLUMNS,
                "ingredient_stats": STATS_COLUMNS,
            }[t]
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
            w.writeheader()
            writers[t] = w

        if factor == 1:
            # small is an exact copy of the cleaned baseline
            for t in ["recipes", "ingredients", "nutrition", "steps", "cuisines", "recipe_allergens"]:
                for r in U.read_csv(clean_dir / f"{t}.csv"):
                    writers[t].writerow(r)
            for r in U.read_csv(clean_dir / "ingredient_stats.csv"):
                writers["ingredient_stats"].writerow(r)
            counts = {t: len(U.read_csv(clean_dir / f"{t}.csv")) for t in
                      ["recipes", "ingredients", "nutrition", "steps", "cuisines", "recipe_allergens"]}
            counts["ingredient_stats"] = len(U.read_csv(clean_dir / "ingredient_stats.csv"))
        else:
            counts = collections.Counter()
            df: collections.Counter[str] = collections.Counter()
            grams: dict[str, float] = collections.defaultdict(float)
            name_by_id: dict[str, str] = {}
            n_total = len(recipes) * factor
            for copy in range(factor):
                rng = random.Random(C.RANDOM_SEED + copy * 9973 + len(name) * 131)
                for r in recipes:
                    orig = r["recipe_id"]
                    seq = int(orig[3:]) + copy * 100000
                    rid = f"RCP{seq:07d}" if copy > 0 else orig
                    ings = [dict(x) for x in ing_by[orig]]
                    # Drop one non-core ingredient in 15% of copies (keep at least 5)
                    if len(ings) > 5 and rng.random() < 0.15:
                        ings.pop(rng.randrange(len(ings)))
                    for x in ings:
                        if x["qty_approx_g"]:
                            k = 1.0 + rng.uniform(-0.10, 0.10)
                            x["qty_approx_g"] = U.fnum(float(x["qty_approx_g"]) * k, 4)
                            if x["qty_canonical_value"]:
                                x["qty_canonical_value"] = U.fnum(float(x["qty_canonical_value"]) * k, 4)
                    ings.sort(key=lambda x: int(x["ingredient_number"]))
                    for i, x in enumerate(ings, 1):
                        x["ingredient_number"] = str(i)

                    servings = int(r["servings"])
                    if copy > 0 and rng.random() < 0.25:
                        servings = max(2, min(7, servings + rng.choice([-1, 1])))
                    total_g = sum(float(x["qty_approx_g"]) for x in ings if x["qty_approx_g"])
                    per_serving = total_g / servings
                    clipped = per_serving > C.CAP_G_PER_SERVING
                    scale = C.CAP_G_PER_SERVING / per_serving if clipped else 1.0
                    if clipped:
                        for x in ings:
                            if x["qty_approx_g"]:
                                x["qty_approx_g"] = U.fnum(float(x["qty_approx_g"]) * scale, 4)
                                if x["qty_canonical_value"]:
                                    x["qty_canonical_value"] = U.fnum(float(x["qty_canonical_value"]) * scale, 4)
                            x["qty_clipped"] = "true"

                    allergens = sorted({a for x in ings for a in x["allergen_flags"].split("|")
                                       if a and a != "none"})
                    for x in ings:
                        x["recipe_id"] = rid
                        writers["ingredients"].writerow(x)
                        df[x["canonical_id"]] += 1
                        name_by_id[x["canonical_id"]] = x["canonical_name"]
                        if x["qty_approx_g"]:
                            grams[x["canonical_id"]] += float(x["qty_approx_g"])
                    counts["ingredients"] += len(ings)

                    # Perturb only independent fields, preserving cross-table invariants
                    rr = dict(r)
                    rr["recipe_id"] = rid
                    if copy > 0:
                        rr["rating"] = _jitter(rng, float(r["rating"]), 0.03, 3.5, 5.0, 1)
                        rr["review_count"] = _jitter(rng, float(r["review_count"]), 0.15, 10, 4999)
                        rr["estimated_cost_usd"] = _jitter(rng, float(r["estimated_cost_usd"]), 0.10, 2, 25, 2)
                        rr["date_added"] = _shift_date(rng, r["date_added"])
                        rr["calories_per_serving"] = _jitter(rng, float(r["calories_per_serving"]), 0.05, 150, 799)
                    rr["servings"] = str(servings)
                    rr["ingredient_count"] = str(len(ings))
                    rr["allergen_count"] = str(len(allergens))
                    rr["estimated_total_g"] = U.fnum(total_g * scale, 2)
                    rr["estimated_g_per_serving"] = U.fnum(min(per_serving, C.CAP_G_PER_SERVING), 2)
                    rr["qty_clipped_recipe"] = U.fmt_bool(clipped)
                    writers["recipes"].writerow(rr)
                    counts["recipes"] += 1

                    nr = dict(nutrition[orig]); nr["recipe_id"] = rid
                    if copy > 0:
                        nr["calories"] = rr["calories_per_serving"]
                        for c in ["protein_g", "carbohydrates_g", "fat_g", "fiber_g", "sugar_g",
                                  "sodium_mg", "cholesterol_mg", "vitamin_a_percent",
                                  "vitamin_c_percent", "calcium_percent", "iron_percent"]:
                            nr[c] = _jitter(rng, float(nr[c]), 0.05, 0, 2000)
                    writers["nutrition"].writerow(nr)
                    counts["nutrition"] += 1

                    for s in steps_by[orig]:
                        ss = dict(s); ss["recipe_id"] = rid
                        writers["steps"].writerow(ss)
                        counts["steps"] += 1

                    ar = {"recipe_id": rid, "allergens": "|".join(allergens) if allergens else "none",
                          "allergen_count": str(len(allergens))}
                    for a in C.ALLERGEN_COLUMNS:
                        ar[f"has_{a}"] = U.fmt_bool(a in allergens)
                    writers["recipe_allergens"].writerow(ar)
                    counts["recipe_allergens"] += 1

            # Scale the dimension counts to stay consistent with the master table
            for cu in cuisines:
                cc = dict(cu)
                if factor > 1:
                    cc["recipe_count"] = str(int(cu["recipe_count"]) * factor)
                writers["cuisines"].writerow(cc)
                counts["cuisines"] += 1

            idfs = {cid: math.log((n_total + 1) / (d + 1)) + 1.0 for cid, d in df.items()}
            lo, hi = min(idfs.values()), max(idfs.values())
            ranked = sorted(idfs, key=lambda k: (-idfs[k], k))
            rank = {cid: i + 1 for i, cid in enumerate(ranked)}
            for cid in sorted(df, key=lambda k: (-df[k], k)):
                writers["ingredient_stats"].writerow({
                    "canonical_id": cid, "canonical_name": name_by_id.get(cid, ""),
                    "doc_freq": str(df[cid]), "total_recipes": str(n_total),
                    "idf": U.fnum(idfs[cid], 6),
                    "idf_norm": U.fnum((idfs[cid] - lo) / (hi - lo) if hi > lo else 1.0, 6),
                    "rarity_rank": str(rank[cid]),
                    "avg_approx_g": U.fnum(grams[cid] / df[cid], 2),
                    "share_pct": U.fnum(df[cid] / n_total * 100, 3),
                })
                counts["ingredient_stats"] += 1
            counts = dict(counts)
    finally:
        for fh in handles.values():
            fh.close()

    if verbose:
        U.log(f"Scale {name} (x{factor}): recipes={counts['recipes']:,}, "
              f"ingredients={counts['ingredients']:,}, steps={counts['steps']:,}")
    return {"name": name, "factor": factor, "counts": counts,
            "files": {t: {"path": str(p.relative_to(C.ROOT)).replace("\\", "/"),
                          "rows": counts[t], "sha256": U.sha256(p)} for t, p in files.items()}}
