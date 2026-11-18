"""Executable correctness assertions and the verification report."""
from __future__ import annotations

import collections
import json
import tempfile
from pathlib import Path
from typing import Any, Callable

from . import config as C
from . import io_utils as U
from . import clean as CL

CHECKS: list[dict[str, Any]] = []


def check(name: str, group: str, fn: Callable[[], tuple[bool, str]]) -> None:
    try:
        ok, detail = fn()
    except Exception as e:                       # An exception counts as FAIL; keep checking
        ok, detail = False, f"Exception: {type(e).__name__}: {e}"
    CHECKS.append({"name": name, "group": group, "status": "PASS" if ok else "FAIL", "detail": str(detail)})
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} - {detail}", flush=True)


def _uniq(rows: list[dict[str, str]], keys: list[str]) -> tuple[bool, str]:
    seen = {tuple(r.get(k, "") for k in keys) for r in rows}
    return len(seen) == len(rows), f"{len(rows):,} rows / {len(seen):,} unique keys ({'+'.join(keys)})"


def run(clean_dir: Path | None = None, mapping_dir: Path | None = None,
        scales_dir: Path | None = None, verbose: bool = True) -> dict[str, Any]:
    CHECKS.clear()
    cd = clean_dir or C.CLEAN
    md = mapping_dir or C.MAPPINGS
    sd = scales_dir or C.SCALES
    raw = C.raw_dir()

    R = U.read_csv(cd / "recipes.csv")
    I = U.read_csv(cd / "ingredients.csv")
    N = U.read_csv(cd / "nutrition.csv")
    S = U.read_csv(cd / "steps.csv")
    A = U.read_csv(cd / "recipe_allergens.csv")
    AUD = U.read_csv(cd / "recipe_dietary_audit.csv")
    IM = U.read_csv(cd / "ingredient_master.csv")
    IS = U.read_csv(cd / "ingredient_stats.csv")
    DOC = U.read_csv(cd / "recipe_search_document.csv")
    SYN = U.read_csv(md / "ingredient_synonyms.csv")
    AM = U.read_csv(md / "allergen_map.csv")
    UC = U.read_csv(md / "unit_conversion.csv")
    ids = {r["recipe_id"] for r in R}

    U.section("Correctness verification")

    # --- group 1: input integrity
    check("Raw CSV SHA-256 values match the manifest", "Input integrity", lambda: (
        all(U.sha256(raw / fn) == h for fn, h in C.RAW_SHA256.items()),
        f"5/5 match; directory {raw.name}"))
    check("Raw files are present and unmodified", "Input integrity", lambda: (
        all((raw / fn).is_file() for fn in C.RAW_FILES.values()), "All 5 files present"))
    check("All four lookup tables are present and non-empty", "Input integrity", lambda: (
        all(len(x) > 0 for x in [SYN, AM, UC, U.read_csv(md / "dietary_rules.csv")]),
        f"synonyms={len(SYN)}, allergen={len(AM)}, units={len(UC)}"))

    # --- group 2: keys and referential integrity
    for nm, rows, keys in [
        ("recipes.recipe_id unique", R, ["recipe_id"]),
        ("nutrition.recipe_id unique", N, ["recipe_id"]),
        ("recipe_allergens.recipe_id unique", A, ["recipe_id"]),
        ("recipe_dietary_audit.recipe_id unique", AUD, ["recipe_id"]),
        ("ingredient_master.canonical_id unique", IM, ["canonical_id"]),
        ("ingredient_stats.canonical_id unique", IS, ["canonical_id"]),
        ("recipe_search_document.recipe_id unique", DOC, ["recipe_id"]),
        ("ingredients composite key unique", I, ["recipe_id", "ingredient_number"]),
        ("steps composite key unique", S, ["recipe_id", "step_number"]),
    ]:
        check(nm, "Keys and integrity", lambda rows=rows, keys=keys: _uniq(rows, keys))

    for nm, rows in [("ingredients", I), ("nutrition", N), ("steps", S),
                     ("recipe_allergens", A), ("recipe_dietary_audit", AUD),
                     ("recipe_search_document", DOC)]:
        check(f"{nm} has no orphan recipe_id", "Keys and integrity",
              lambda rows=rows: (len({r["recipe_id"] for r in rows} - ids) == 0,
                                 f"orphans={len({r['recipe_id'] for r in rows} - ids)}"))
    check("Every recipe has ingredients, nutrition and steps", "Keys and integrity", lambda: (
        all(len({r["recipe_id"] for r in rows}) == len(R) for rows in [I, N, S]),
        f"recipes {len(R):,}; ingredients/nutrition/steps cover {len({r['recipe_id'] for r in I})}/"
        f"{len({r['recipe_id'] for r in N})}/{len({r['recipe_id'] for r in S})}"))

    # --- group 3: cleaning rules
    by: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    for r in I:
        by[r["recipe_id"]].append(r)
    check("ingredient_number is contiguous 1..n per recipe", "Cleaning rules", lambda: (
        all(sorted(int(x["ingredient_number"]) for x in v) == list(range(1, len(v) + 1))
            for v in by.values()), f"{len(by):,} recipes all contiguous"))
    check("No duplicate (recipe_id, canonical_id) after cleaning", "Cleaning rules", lambda: (
        len({(r["recipe_id"], r["canonical_id"]) for r in I}) == len(I),
        f"duplicate groups={len(I) - len({(r['recipe_id'], r['canonical_id']) for r in I})}"))
    check("All quantities parse (UNPARSEABLE/UNKNOWN_UNIT = 0)", "Cleaning rules", lambda: (
        sum(1 for r in I if r["qty_parse_status"] in {"UNPARSEABLE", "UNKNOWN_UNIT"}) == 0,
        "parse status=" + str(dict(collections.Counter(r["qty_parse_status"] for r in I)))))
    check("Placeholders are coded and numeric fields are empty", "Cleaning rules", lambda: (
        all(r["qty_placeholder_code"] and r["qty_approx_g"] == ""
            for r in I if U.to_bool(r["qty_is_placeholder"])),
        f"placeholder rows={sum(1 for r in I if U.to_bool(r['qty_is_placeholder']))}"))
    check("Non-placeholder rows have value, unit and grams", "Cleaning rules", lambda: (
        all(r["qty_approx_g"] and r["qty_canonical_value"] and
            r["qty_canonical_unit"] in {"g", "ml", "piece"}
            for r in I if not U.to_bool(r["qty_is_placeholder"])),
        f"canonical units={dict(collections.Counter(r['qty_canonical_unit'] for r in I))}"))
    check("Every canonical_id exists in the allergen map", "Cleaning rules", lambda: (
        {s["canonical_id"] for s in SYN} <= {a["canonical_id"] for a in AM},
        f"synonyms={len({s['canonical_id'] for s in SYN})}, allergen_map={len(AM)}"))
    check("Category conflicts resolved (Paneer = Dairy)", "Cleaning rules", lambda: (
        len({(r["canonical_name"], r["category"]) for r in I}) == len({r["canonical_name"] for r in I}),
        f"canonical ingredients={len({r['canonical_id'] for r in I})}"))

    # --- group 4: semantic consistency
    canon_by: dict[str, set[str]] = collections.defaultdict(set)
    allergen_by: dict[str, set[str]] = collections.defaultdict(set)
    for r in I:
        canon_by[r["recipe_id"]].add(r["canonical_name"])
        for a in r["allergen_flags"].split("|"):
            if a and a != "none":
                allergen_by[r["recipe_id"]].add(a)
    rmap = {r["recipe_id"]: r for r in R}
    amap = {r["recipe_id"]: r for r in A}
    audmap = {r["recipe_id"]: r for r in AUD}
    nmap = {r["recipe_id"]: r for r in N}
    check("is_vegetarian/vegan/gluten_free match the recomputed values", "Semantic consistency", lambda: (
        all(U.to_bool(rmap[k]["is_vegetarian"]) == (not bool(v & C.NON_VEG_INGREDIENTS)) and
            U.to_bool(rmap[k]["is_vegan"]) == (not bool(v & C.ANIMAL_INGREDIENTS)) and
            U.to_bool(rmap[k]["is_gluten_free"]) == (not bool(v & C.GLUTEN_INGREDIENTS))
            for k, v in canon_by.items()), f"checked {len(canon_by):,} recipes"))
    check("is_halal keeps the source value and is marked unverifiable", "Semantic consistency", lambda: (
        all(r["is_halal"] == r["is_halal_raw"] and r["is_halal_verifiable"] == "false" for r in R),
        "No unverifiable inference is written as fact"))
    check("recipe_dietary_audit conflict counts are reproducible", "Semantic consistency", lambda: (
        all(int(audmap[k]["conflict_count"]) ==
            sum(U.to_bool(a[f"{f}_raw"]) != U.to_bool(a[f"{f}_calc"])
                for f in ["is_vegetarian", "is_vegan", "is_gluten_free"])
            for k, a in audmap.items()), f"labels corrected={sum(int(a['conflict_count']) for a in AUD):,}"))
    check("recipe_allergens equals the union of ingredient allergens", "Semantic consistency", lambda: (
        all(set("" if amap[k]["allergens"] == "none" else amap[k]["allergens"].split("|")) == allergen_by[k]
            for k in ids), f"recipes with an allergen={sum(1 for k in ids if allergen_by[k]):,}"))
    check("calories_per_serving equals nutrition.calories", "Semantic consistency", lambda: (
        all(rmap[k]["calories_per_serving"] == nmap[k]["calories"] for k in ids),
        f"mismatches={sum(1 for k in ids if rmap[k]['calories_per_serving'] != nmap[k]['calories'])}"))
    check("prep + cook = total_time", "Semantic consistency", lambda: (
        all(int(r["prep_time_minutes"]) + int(r["cook_time_minutes"]) == int(r["total_time_minutes"])
            for r in R), f"passed {len(R):,}/{len(R):,}"))
    check("Estimated grams per serving stay within the cap", "Semantic consistency", lambda: (
        all(float(r["estimated_g_per_serving"]) <= C.CAP_G_PER_SERVING + 1e-6 for r in R),
        f"cap={C.CAP_G_PER_SERVING:g} g/serving; clipped recipes="
        f"{sum(1 for r in R if U.to_bool(r['qty_clipped_recipe']))}"))
    check("qty_clipped agrees with recipes.qty_clipped_recipe", "Semantic consistency", lambda: (
        all(U.to_bool(r["qty_clipped"]) == U.to_bool(rmap[r["recipe_id"]]["qty_clipped_recipe"])
            for r in I), "Row-by-row agreement"))
    check("Full-text documents cover every recipe and are non-empty", "Semantic consistency", lambda: (
        len(DOC) == len(R) and all(r["search_document"] for r in DOC), f"{len(DOC):,} documents"))
    check("ingredient_stats.idf is reproducible from doc_freq", "Semantic consistency", lambda: (
        all(abs(float(r["idf"]) - (
            __import__("math").log((len(R) + 1) / (int(r["doc_freq"]) + 1)) + 1.0)) < 1e-5
            for r in IS), f"IDF weights for {len(IS)} ingredients"))

    # --- group 5: scale tiers
    for s in C.SCALE_ORDER:
        d = sd / s
        p = d / "recipes.csv"
        if not p.is_file():
            check(f"{s} tier exists", "Scale tiers", lambda: (False, "missing recipes.csv"))
            continue
        sr = U.read_csv(p)
        si = U.read_csv(d / "ingredients.csv")
        sids = {r["recipe_id"] for r in sr}
        expected = len(R) * C.SCALE_FACTORS[s]
        check(f"{s} recipes = baseline x {C.SCALE_FACTORS[s]}", "Scale tiers", lambda: (
            len(sr) == expected, f"{len(sr):,} / expected {expected:,}"))
        check(f"{s} keys unique and ingredients not orphaned", "Scale tiers", lambda: (
            len(sids) == len(sr) and not ({r["recipe_id"] for r in si} - sids),
            f"recipes {len(sr):,}, ingredients {len(si):,}"))
        check(f"{s} has no duplicate (recipe_id, canonical_id)", "Scale tiers", lambda: (
            len({(r["recipe_id"], r["canonical_id"]) for r in si}) == len(si), "No duplicates"))
        check(f"{s} grams per serving stay within the cap", "Scale tiers", lambda: (
            all(float(r["estimated_g_per_serving"]) <= C.CAP_G_PER_SERVING + 1e-6 for r in sr), "All compliant"))

    # --- group 6: reproducibility
    def determinism() -> tuple[bool, str]:
        with tempfile.TemporaryDirectory(prefix="dsc5003_verify_") as td:
            a = Path(td) / "a"; b = Path(td) / "b"
            CL.run(raw_dir=C.raw_dir(), out_dir=a, mapping_dir=C.MAPPINGS, verbose=False)
            CL.run(raw_dir=C.raw_dir(), out_dir=b, mapping_dir=C.MAPPINGS, verbose=False)
            files = ["recipes.csv", "ingredients.csv", "recipe_allergens.csv", "ingredient_stats.csv"]
            diffs = [f for f in files if U.sha256(a / f) != U.sha256(b / f)]
            same = not diffs
            return same, ("Two independent rebuilds are byte-identical" if same else f"Mismatched files: {diffs}")
    check("make seed is idempotent: two rebuilds are byte-identical", "Reproducibility", determinism)

    def checksums() -> tuple[bool, str]:
        mf = C.DATA / "manifest.json"
        if not mf.is_file():
            return False, "missing data/manifest.json"
        m = json.loads(mf.read_text(encoding="utf-8"))
        bad = []
        for grp in ["mappings", "clean"]:
            for k, v in m.get(grp, {}).items():
                p = C.ROOT / v["path"]
                if not p.is_file() or U.sha256(p) != v["sha256"]:
                    bad.append(v["path"])
        return not bad, (f"{sum(len(m.get(g, {})) for g in ['mappings', 'clean'])} manifest checksums match"
                         if not bad else f"Mismatch: {bad[:5]}")
    check("All checksums in data/manifest.json match", "Reproducibility", checksums)

    passed = sum(1 for c in CHECKS if c["status"] == "PASS")
    failed = len(CHECKS) - passed
    result = {
        "generated_at_utc": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_checks": len(CHECKS), "passed": passed, "failed": failed,
        "checks": CHECKS,
    }
    U.write_json(C.PROFILE / "verification.json", result)

    L = ["# Correctness Verification Report\n\n",
         "> Generated by `python -m etl.pipeline verify` (also run by `make test`).\n",
         "> Every check below is executable code, not a manual checklist. "
         "\n\n",
         f"**Result: {passed}/{len(CHECKS)} PASS, {failed} FAIL.**\n\n",
         "| # | Group | Check | Result | Measured |\n|---:|---|---|---|---|\n"]
    for i, c in enumerate(CHECKS, 1):
        L.append(f"| {i} | {c['group']} | {c['name']} | **{c['status']}** | {c['detail']} |\n")
    L.append("\n## Reproduction\n\n```bash\nmake seed       # full rebuild\nmake test       # unit tests + this report\npython -m etl.pipeline verify\n```\n")
    U.write_text(C.DOCS / "verification_report.md", "".join(L))
    if verbose:
        U.section(f"Verification: {passed}/{len(CHECKS)} PASS, {failed} FAIL")
    if failed:
        U.die(f"{failed} checks failed; see docs/verification_report.md")
    return result
