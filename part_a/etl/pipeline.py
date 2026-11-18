"""CLI entry point for the eight-step rebuild pipeline."""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from . import config as C
from . import io_utils as U
from . import mappings as M
from . import profile as P
from . import dictionary as D
from . import clean as CL
from . import scale as SC
from . import seed as SD
from . import verify as V
from . import pack as PK


def _do_mappings() -> dict:
    raw = C.raw_dir()
    ing = U.read_csv(raw / C.RAW_FILES["ingredients"])
    mp = M.build_mappings(ing)
    U.log(f"Lookup tables: {len(mp['canon_names'])} canonical ingredients, {mp['synonym_count']} aliases, "
          f"{len(mp['cat_conflicts'])} category conflicts")
    return mp


def _do_profile() -> tuple[dict, dict, list[dict[str, str]]]:
    raw = C.raw_dir()
    mp = M.load_mappings()
    raw_p = P.build_raw_profile(raw, mp)
    clean_p = P.build_clean_profile(C.CLEAN)
    U.write_json(C.PROFILE / "profile_raw.json", raw_p)
    U.write_json(C.PROFILE / "profile_clean.json", clean_p)
    summary = P.quality_summary(raw_p, clean_p)
    U.write_csv(C.PROFILE / "quality_summary.csv", summary,
                ["metric", "before", "after", "note"])
    U.write_text(C.DOCS / "profile_metrics.md", P.render_markdown(raw_p, clean_p, summary))
    U.log("Profile -> docs/profile_metrics.md, data/profile/*.json, quality_summary.csv")
    return raw_p, clean_p, summary


def _do_scale(factors: dict[str, int] | None = None) -> dict:
    f = factors or C.SCALE_FACTORS
    out = {}
    for s in C.SCALE_ORDER:
        out[s] = SC.build_scale(s, f[s], C.CLEAN)
    U.write_json(C.SCALES / "scales_manifest.json", {"scales": out, "random_seed": C.RANDOM_SEED})
    return out


def _do_demo() -> None:
    rp = C.PROFILE / "profile_raw.json"
    cp = C.PROFILE / "profile_clean.json"
    if not rp.is_file():
        U.die("Run `make seed` first to build the profile")
    import json
    r = json.loads(rp.read_text(encoding="utf-8"))["cross_checks"]
    c = json.loads(cp.read_text(encoding="utf-8"))["cross_checks"]
    U.section("Before / after cleaning (source: docs/profile_metrics.md)")
    rows = [
        ("Raw rows", f"{r['total_rows']:,} rows / 5 CSV", "-"),
        ("Empty cells", r["empty_cells_total"], 0),
        ("Dietary label conflicts", r["dietary_conflict_total_labels"], "0"),
        ("Recipes with a conflict", r["dietary_conflict_recipes"], "0"),
        ("Distinct quantity strings", r["distinct_quantity_strings"], "g / ml / piece + TO_TASTE"),
        ("'to taste' rows", r["quantity_placeholder_rows"], c["placeholder_rows_normalized"]),
        ("Surplus duplicate rows", r["duplicate_ingredient_extra_rows"], "0"),
        ("Recipes above 1200 g/serving", r["approx_g_per_serving"]["recipes_over_cap"], 0),
        ("Ingredient rows", r["row_counts"]["ingredients"], c["row_counts"]["ingredients"]),
        ("Unparseable quantities", sum(v for k, v in r["quantity_parse_status"].items()
                        if k in {"UNPARSEABLE", "UNKNOWN_UNIT"}), c["unparseable_quantity_rows"]),
    ]
    print(f"{'Metric':<32}{'Before':>26}{'After':>34}")
    print("-" * 96)
    for a, b, d in rows:
        print(f"{a:<32}{str(b):>26}{str(d):>34}")
    print("-" * 96)
    print("Command: make seed   (python -m etl.pipeline all)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DSC5003 data engineering pipeline")
    ap.add_argument("command", nargs="?", default="all",
                    choices=["all", "mappings", "dictionary", "profile", "clean",
                             "scale", "seed", "verify", "demo", "pack", "unpack"])
    ap.add_argument("--factors", default=None,
                    help="Three scale factors, comma separated (default 1,5,20)")
    ap.add_argument("--raw", default=None, help="Override the raw CSV directory")
    args = ap.parse_args(argv)
    t0 = time.time()
    C.ensure_dirs()
    if args.raw:
        C.RAW_DIR_COURSE = Path(args.raw).resolve()

    factors = None
    if args.factors:
        vals = [int(x) for x in args.factors.split(",")]
        if len(vals) != 3:
            U.die("--factors needs 3 integers, e.g. 1,5,20")
        factors = dict(zip(C.SCALE_ORDER, vals))

    cmd = args.command
    if cmd == "demo":
        _do_demo()
        return 0
    if cmd == "pack":
        PK.pack(); return 0
    if cmd == "unpack":
        U.log(f"Restored {PK.unpack()} large files"); return 0
    if cmd == "mappings":
        _do_mappings(); return 0
    if cmd == "dictionary":
        D.build(); U.log("Column dictionary -> docs/data_dictionary.md"); return 0
    if cmd == "clean":
        if not (C.MAPPINGS / "ingredient_synonyms.csv").is_file():
            _do_mappings()
        CL.run(); return 0
    if cmd == "profile":
        if not (C.MAPPINGS / "ingredient_synonyms.csv").is_file():
            _do_mappings()
        _do_profile(); return 0
    if cmd == "scale":
        _do_scale(factors); return 0
    if cmd == "seed":
        SD.build(); return 0
    if cmd == "verify":
        V.run(); return 0

    # ---------------- all / make seed ----------------
    U.section("make seed - data engineering rebuild")
    U.log("STEP 1/8  Build lookup tables (synonyms / allergens / dietary rules / units)")
    _do_mappings()
    U.log("STEP 2/8  Generate the column dictionary")
    D.build()
    U.log("STEP 3/8  Profile the raw data")
    raw_p = P.build_raw_profile(C.raw_dir(), M.load_mappings())
    U.write_json(C.PROFILE / "profile_raw.json", raw_p)
    U.log("STEP 4/8  Clean: relabel / parse / merge / clip / code placeholders")
    stats = CL.run()
    U.log("STEP 5/8  Profile the cleaned data and compare")
    clean_p = P.build_clean_profile(C.CLEAN)
    U.write_json(C.PROFILE / "profile_clean.json", clean_p)
    summary = P.quality_summary(raw_p, clean_p)
    U.write_csv(C.PROFILE / "quality_summary.csv", summary, ["metric", "before", "after", "note"])
    U.write_text(C.DOCS / "profile_metrics.md", P.render_markdown(raw_p, clean_p, summary))
    U.log("STEP 6/8  Build three scale tiers (1x / 5x / 20x)")
    scales = _do_scale(factors)
    U.log("STEP 7/8  Write psql loaders and the manifest (SHA-256)")
    SD.build(scales)
    U.log("STEP 8/8  Verify correctness")
    V.run()
    U.section(f"make seed finished in {time.time() - t0:.1f}s")
    print(f"  Ingredient rows {stats['raw_ingredient_rows']:,} -> {stats['clean_ingredient_rows']:,}")
    print(f"  Labels corrected {stats['relabelled_flags']:,}; recipes clipped {stats['clipped_recipes']}")
    print("  See README.md, report/ and video/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
