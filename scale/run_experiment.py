#!/usr/bin/env python3
"""Build the three scale tiers and measure q1-q3 on each, with and without indexes.

Why this exists
---------------
Part A publishes 7 CSVs per scale tier (recipes, ingredients, nutrition, steps,
cuisines, recipe_allergens, ingredient_stats) and only the 10k tier gets the
other 4 tables. scale/derive_missing_tables.sql rebuilds those 4 from the 7 with
Part A's own rules, so the *same* sql/schema.sql, sql/index.sql and
sql/queries.sql run unmodified on every tier.

Measurement protocol
--------------------
Dropping the indexes between two runs biases the result on a laptop: the first
group runs on a cold CPU and the second group after the CPU has been throttled,
so "no index" always looks slower. The script therefore builds every tier twice,
`t_<tier>` (shipping configuration, sql/index.sql applied) and
`t_<tier>_noidx` (same data, no secondary indexes, ANALYZEd), and then measures
the two schemas in alternating blocks. Reported figures are the median and the
minimum over all runs of all blocks.

Usage (from the repository root):
    python3 scale/run_experiment.py                  # small medium large
    python3 scale/run_experiment.py --tiers medium --reps 6 --blocks 3
    python3 scale/run_experiment.py --skip-noindex   # indexed configuration only

It rebuilds the t_<tier>* schemas in the target database, so point it at a
scratch database - never at recipe_db, which holds the verified 10k build.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PART_A = ROOT / "part_a"
EVIDENCE = ROOT / "docs" / "evidence"

PSQL = shutil.which("psql") or "/Applications/Postgres.app/Contents/Versions/latest/bin/psql"
BASE_ENV = {"PATH": os.path.dirname(PSQL) + ":/usr/bin:/bin:/usr/sbin:/sbin",
            "PGCLIENTENCODING": "UTF8"}

FACTOR = {"small": 1, "medium": 5, "large": 20}
TABLES = [
    "cuisines", "cuisine_category", "recipes", "ingredient_master", "ingredients",
    "steps", "nutrition", "recipe_allergens", "recipe_dietary_audit",
    "ingredient_stats", "recipe_search_document",
]


def run_psql(schema: str | None, args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(BASE_ENV)
    if schema:
        env["PGOPTIONS"] = f"--search_path={schema}"
    proc = subprocess.run([PSQL, "-h", "127.0.0.1", *args], cwd=str(cwd or ROOT),
                          capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        sys.exit(f"psql failed: {' '.join(args)}\n{proc.stdout}\n{proc.stderr}")
    return proc


def query(schema: str | None, database: str, sql: str) -> str:
    return run_psql(schema, ["-d", database, "-At", "-q", "-c", sql]).stdout.strip()


def run_file(schema: str, database: str, path: Path, cwd: Path | None = None) -> tuple[float, str]:
    start = time.perf_counter()
    proc = run_psql(schema, ["-d", database, "-v", "ON_ERROR_STOP=1", "-q", "-f", str(path)],
                    cwd=cwd)
    return time.perf_counter() - start, proc.stdout + proc.stderr


def statement_list(path: Path) -> list[str]:
    """Split a .sql file into statements the same way the README describes."""
    raw = path.read_text(encoding="utf-8")
    body = "\n".join(l for l in raw.splitlines() if not l.lstrip().startswith("--"))
    return [s.strip() for s in body.split(";") if s.strip()]


def analyze_statements() -> list[str]:
    """The per-table ANALYZE calls at the end of sql/index.sql.

    The no-index schema needs the same statistics as the indexed one, otherwise
    the two plans cannot be compared; only the CREATE INDEX lines are skipped.
    """
    return [l.strip() for l in (ROOT / "sql" / "index.sql").read_text(encoding="utf-8").splitlines()
            if l.strip().upper().startswith("ANALYZE ")]


def plan_summary(plan: dict, limit: int = 8) -> str:
    parts: list[str] = []

    def walk(node: dict) -> None:
        if len(parts) >= limit:
            return
        label = node.get("Node Type", "?")
        if node.get("Relation Name"):
            label += f"({node['Relation Name']}"
            label += f" idx={node['Index Name']}" if node.get("Index Name") else ""
            label += ")"
        parts.append(label)
        for child in node.get("Plans", []):
            walk(child)

    walk(plan)
    return " > ".join(parts)


def explain(schema: str, database: str, stmt: str, reps: int, warmup: int = 1) -> dict:
    """EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) `reps` times after `warmup` runs."""
    times: list[float] = []
    last: dict = {}
    for i in range(reps + warmup):
        proc = run_psql(schema, ["-d", database, "-At", "-q", "-c",
                                 "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + stmt])
        entry = json.loads(proc.stdout)[0]
        last = entry
        if i >= warmup:
            times.append(entry["Execution Time"])
    return {"times": times, "rows": last["Plan"].get("Actual Rows"),
            "plan": plan_summary(last["Plan"]), "json": last}


def build_tier(tier: str, database: str, with_indexes: bool) -> dict:
    """schema -> ingredient_master -> 7 published tables -> 4 derived -> indexes/ANALYZE."""
    schema = f"t_{tier}" if with_indexes else f"t_{tier}_noidx"
    run_psql(None, ["-d", database, "-q", "-c",
                    f"DROP SCHEMA IF EXISTS {schema} CASCADE; CREATE SCHEMA {schema};"])

    steps: dict[str, float] = {}
    steps["schema_s"], _ = run_file(schema, database, ROOT / "sql" / "schema.sql")
    steps["master_s"], _ = run_file(schema, database,
                                    ROOT / "scale" / "load_ingredient_master.sql", cwd=PART_A)
    steps["load_s"], _ = run_file(schema, database, PART_A / "sql" / f"load_{tier}.sql", cwd=PART_A)
    steps["derive_s"], out = run_file(schema, database,
                                      ROOT / "scale" / "derive_missing_tables.sql", cwd=PART_A)
    if with_indexes:
        steps["index_s"], _ = run_file(schema, database, ROOT / "sql" / "index.sql")
    else:
        start = time.perf_counter()
        run_psql(schema, ["-d", database, "-q", "-c", "\n".join(analyze_statements())])
        steps["index_s"] = 0.0
        steps["analyze_s"] = time.perf_counter() - start

    checks = " ".join(f"{m.group(1)}={m.group(2)}"
                      for m in re.finditer(r"^\s*(\w+)\s*\n-+\n\s*(-?\d+)", out, re.M))
    counts = {t: int(query(schema, database, f"SELECT count(*) FROM {t}")) for t in TABLES}
    size_mb = int(query(None, database, f"""
        SELECT COALESCE(sum(pg_total_relation_size(c.oid)), 0)
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = '{schema}' AND c.relkind IN ('r', 'i')""")) / 2**20

    return {"tier": tier, "schema": schema, "steps": steps, "counts": counts,
            "checks": checks, "size_mb": round(size_mb, 1)}


def write_merged(path: Path, new_rows: list[dict], measured: list[str]) -> None:
    """Write rows, keeping the ones already in the file for tiers not measured.

    A partial run (`--tiers large`) must not silently delete the x1/x5
    evidence from a previous full run, so rows are merged on the tier column.
    """
    fieldnames = list(new_rows[0].keys())
    kept: list[dict] = []
    if path.exists():
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames == fieldnames:
                kept = [r for r in reader if r["tier"] not in measured]
            else:
                print(f"  note: {path.name} has an older header; rewriting it")
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept + new_rows)


def merge_plan_text(path: Path, new_chunks: list[str], measured: list[str]) -> None:
    """Same idea for scale_plans.txt: sections start with '===== <tier> q<i> ...'."""
    kept: list[str] = []
    if path.exists():
        for chunk in path.read_text(encoding="utf-8").split("\n\n"):
            head = chunk.lstrip().split(" ", 2)
            if len(head) > 1 and head[0] == "=====" and head[1] not in measured:
                kept.append(chunk.rstrip("\n"))
    path.write_text("\n\n".join(kept + new_chunks) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--database", default="recipe_scale")
    ap.add_argument("--tiers", nargs="+", default=["small", "medium", "large"],
                    choices=["small", "medium", "large"])
    ap.add_argument("--reps", type=int, default=4, help="runs per block")
    ap.add_argument("--blocks", type=int, default=3, help="alternating blocks")
    ap.add_argument("--skip-noindex", action="store_true",
                    help="only measure the shipping (indexed) configuration")
    args = ap.parse_args()

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    stmts = statement_list(ROOT / "sql" / "queries.sql")
    if len(stmts) != 3:
        sys.exit(f"expected 3 statements in sql/queries.sql, found {len(stmts)}")

    build_rows: list[dict] = []
    timing_rows: list[dict] = []
    plan_chunks: list[str] = []

    for tier in args.tiers:
        print(f"\n===== {tier} (x{FACTOR[tier]}) =====", flush=True)
        idx = build_tier(tier, args.database, with_indexes=True)
        configs = [("indexed", idx)]
        if not args.skip_noindex:
            configs.append(("noindex", build_tier(tier, args.database, with_indexes=False)))

        for label, built in configs:
            print(f"  {label:8} schema {built['schema']:14} "
                  f"load {built['steps']['load_s']:6.2f}s "
                  f"derive {built['steps']['derive_s']:6.2f}s "
                  f"index {built['steps']['index_s']:6.2f}s | {built['size_mb']:8.1f} MB "
                  f"| recipes {built['counts']['recipes']:,}", flush=True)
            print(f"  {label:8} derive checks: {built['checks']}", flush=True)
            build_rows.append({
                "tier": tier, "factor": FACTOR[tier], "config": label,
                "schema": built["schema"], "size_mb": built["size_mb"],
                "schema_s": round(built["steps"]["schema_s"], 2),
                "master_s": round(built["steps"]["master_s"], 2),
                "load_s": round(built["steps"]["load_s"], 2),
                "derive_s": round(built["steps"]["derive_s"], 2),
                "index_s": round(built["steps"]["index_s"], 2),
                **{f"rows_{t}": built["counts"][t] for t in TABLES},
            })

        collected = {label: {i: [] for i in range(1, 4)} for label, _ in configs}
        plans: dict[tuple[str, int], dict] = {}
        for label, built in configs:                     # burn-in, then alternate
            for i, stmt in enumerate(stmts, 1):
                explain(built["schema"], args.database, stmt, reps=1, warmup=0)
        for block in range(1, args.blocks + 1):
            for label, built in configs:
                for i, stmt in enumerate(stmts, 1):
                    res = explain(built["schema"], args.database, stmt, reps=args.reps)
                    collected[label][i].extend(res["times"])
                    plans[(label, i)] = res
            print(f"  block {block}/{args.blocks} done", flush=True)

        for i in range(1, 4):
            row = {"tier": tier, "factor": FACTOR[tier], "query": f"q{i}",
                   "rows_returned": plans[("indexed", i)]["rows"]}
            for label, _ in configs:
                times = sorted(collected[label][i])
                row[f"{label}_median_ms"] = round(statistics.median(times), 3)
                row[f"{label}_min_ms"] = round(times[0], 3)
                row[f"{label}_max_ms"] = round(times[-1], 3)
                row[f"{label}_runs"] = len(times)
                row[f"plan_{label}"] = plans[(label, i)]["plan"]
            if len(configs) == 2:
                row["speedup"] = round(row["noindex_median_ms"] / row["indexed_median_ms"], 2)
            row["speedup_min"] = (round(row["noindex_min_ms"] / row["indexed_min_ms"], 2)
                                 if len(configs) == 2 else "")
            timing_rows.append(row)
            print(f"  q{i}: indexed {row['indexed_median_ms']:9.3f} ms "
                  f"(min {row['indexed_min_ms']:8.3f}) | noindex "
                  f"{row.get('noindex_median_ms', float('nan')):9.3f} ms "
                  f"(min {row.get('noindex_min_ms', float('nan')):8.3f}) "
                  f"| rows {row['rows_returned']}", flush=True)
            for label, _ in configs:
                plan_chunks.append(f"===== {tier} q{i} {label} =====\n"
                                   f"runs_ms={collected[label][i]}\n"
                                   f"plan: {plans[(label, i)]['plan']}")

    write_merged(EVIDENCE / "scale_build.csv", build_rows, args.tiers)
    write_merged(EVIDENCE / "scale_timings.csv", timing_rows, args.tiers)
    merge_plan_text(EVIDENCE / "scale_plans.txt", plan_chunks, args.tiers)

    print(f"\nwrote scale_build.csv, scale_timings.csv, scale_plans.txt "
          f"(in {EVIDENCE.relative_to(ROOT)}; tiers not in this run are kept)")


if __name__ == "__main__":
    main()


