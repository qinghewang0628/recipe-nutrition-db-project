# recipe-nutrition-db-project

Database course project (DSC5003): a recipe retrieval and nutrition
recommendation system built on a cleaned South Asian recipe corpus.

The work is split into four parts. Part A (data engineering) is complete and
delivered as a reproducible package under `part_a/`. Part B (database design,
indexes and the three core queries) is delivered in `sql/`; the design rationale,
the ER diagram and the load/scale verification live in `docs/`.

## Repository layout

| Path       | Owner | Contents                                                              |
| ---------- | ----- | --------------------------------------------------------------------- |
| `part_a/`  | A     | Delivered ETL package: cleaning pipeline, 11 cleaned tables, docs     |
| `sql/`     | B     | `schema.sql` (DDL), `index.sql` (indexes), `queries.sql` (core queries) |
| `scale/`   | B     | Derivation of the 4 missing tier tables + the x1/x5/x20 experiment   |
| `docs/`    | B/D   | `schema-design.md` (ER + 3NF), `data_dictionary.md` (physical: keys, CHECKs, indexes), `load_verification.md`, `scale_experiment.md`, consolidated report |
| `docs/figures/` | B | Rendered ER diagram (`er-diagram.png` / `.svg`) and index timings (`timings.png` / `.svg`) |
| `tools/`   | B     | Generators for `docs/data_dictionary.md` and `docs/figures/timings.*` |
| `report/`  | D     | Final report and figures                                              |
| `dataset/` | -     | Raw course CSVs, local only (licence unconfirmed), not committed      |

## Data flow

```
archive-datasets/*.csv            (5 raw CSVs, read-only, not committed)
  -> part_a/etl/clean.py          -> part_a/data/clean/*.csv   (11 tables)
  -> part_a/etl/scale.py          -> part_a/data/scales/{small,medium,large}
  -> part_a/sql/load_clean.sql    -> PostgreSQL tables (schema in sql/schema.sql)
  -> sql/queries.sql              -> the three core retrieval queries
```


## Prerequisites

- PostgreSQL 17 (Postgres.app on macOS), server on `127.0.0.1:5432`
- `psql` on `PATH`; always connect with an explicit host (`-h 127.0.0.1`)
- Python 3.9+ standard library only (Part A pipeline); no third-party packages

## Rebuild Part A outputs

```bash
cd part_a
python make.py seed     # 8 steps: clean, scale, catalogue, profile, dictionary, loaders, manifest, verify
python make.py test     # 25 unit tests
```

Row counts and SHA-256 values of every output are in `part_a/data/manifest.json`;
the 50 executable assertions are in `part_a/docs/verification_report.md`.

## Create and load the database

```bash
createdb -h 127.0.0.1 recipe_db                       # once
psql -h 127.0.0.1 -d recipe_db -v ON_ERROR_STOP=1 -f sql/schema.sql

cd part_a                                             # \copy paths are relative to CWD
psql -h 127.0.0.1 -d recipe_db -v ON_ERROR_STOP=1 -f sql/load_clean.sql
cd ..

psql -h 127.0.0.1 -d recipe_db -v ON_ERROR_STOP=1 -f sql/index.sql   # after the load
```

`part_a/sql/load_*.sql` copies `recipes` before `cuisines`, so every foreign key
in `sql/schema.sql` is declared `DEFERRABLE INITIALLY DEFERRED`; the loader wraps
its `\copy` calls in a single transaction and the constraints are checked at
`COMMIT`. `sql/index.sql` runs last because the composite index is cheaper to
build in bulk and because its closing `ANALYZE` gives the planner statistics.

## Run the three core queries

`sql/queries.sql` holds q1 (reverse ingredient search), q2 (multi-condition
filter) and q3 (full-text search). Each one is a standalone statement whose
parameters are literals inside the statement (a one-row `WITH input` block for
q1/q3, a one-row FROM subquery for q2), so it can be run as-is:

```bash
psql -h 127.0.0.1 -d recipe_db -f sql/queries.sql          # all three, in order
```

`docs/evidence/query_results.txt` is the recorded output of exactly that command
on the x1 tier: 10 / 14 / 20 rows, i.e. the `LIMIT` is filled by real data rather
than the statements merely parsing.

Load verification, integrity checks, constraint tests and the before/after index
timings are recorded in `docs/load_verification.md`, with the raw psql output in
`docs/evidence/`.

To run a single query, select its block and feed it to psql, e.g. q1:

```bash
sed -n '/^-- q1 /,/^LIMIT (SELECT row_limit FROM input);$/p' sql/queries.sql | psql -h 127.0.0.1 -d recipe_db
```

## Scale experiment (x1 / x5 / x20)

Part A ships three tiers (9,997 / 49,985 / 199,940 recipes) but only the x1 tier
carries all 11 tables. `scale/derive_missing_tables.sql` rebuilds the four
missing ones from the seven that every tier does ship, applying Part A's own
rules, so the queries under test are the shipped ones rather than a rewrite.
`scale/check_equivalence.sql` proves the rebuild is exact on the one tier where
both versions exist (0 differing rows on all four tables).

```bash
createdb -h 127.0.0.1 recipe_scale
python3 scale/run_experiment.py                  # builds t_{small,medium,large} + _noidx schemas
```

The script rebuilds both configurations of every tier, measures q1-q3 in
alternating blocks (four runs each, three blocks) and writes
`docs/evidence/scale_build.csv`, `scale_timings.csv` and `scale_plans.txt`. Use a
scratch database: it drops and recreates the `t_*` schemas. Results and the
reading of them are in `docs/scale_experiment.md`.

In one line: q3's GIN index is worth 15x / 20x / 22x across the three tiers -
without it a search takes 5.5 s at x20; q2's b-trees hold 2.8x / 2.5x / 2.2x;
q1's index is a tie at x1 and only 1.3-1.4x at x5/x20, because q1 spends its
time aggregating ingredient postings (79k of them at x20) rather than reading
the heap - which is the finding that feeds Part C's API design.

## Figures and the data dictionary

Both figures are generated from the same files the text quotes, so neither can
drift from the numbers:

| File | What it shows | Produced by |
|---|---|---|
| `docs/figures/er-diagram.png` / `.svg` | all 11 tables and 10 relationships, exported from the Mermaid source in `docs/schema-design.md` §2 | `npx @mermaid-js/mermaid-cli` |
| `docs/figures/timings.png` / `.svg` | q1-q3 median time with and without the four secondary indexes, at x1 / x5 / x20 | `python3 tools/plot_timings.py` |

`docs/data_dictionary.md` is the *physical* data dictionary - 11 tables, 125
columns, 10 foreign keys, 56 CHECK constraints, 5 indexes - generated from
`pg_catalog` by `python3 tools/gen_data_dictionary.py` (it exits non-zero if a
column has no description, so it cannot silently fall behind `schema.sql`). The
*logical* dictionary, with the domain and provenance of every source column,
stays in `part_a/docs/data_dictionary.md`.

## Contracts inherited from Part A

Part A fixes the column names and six usage rules
(`part_a/docs/handoff.md`). In particular:

- join ingredients on `canonical_id`, never on the raw name (57 canonical ids);
- use `ingredient_stats.idf` for rarity-weighted overlap, not a hand-rolled weight;
- use `recipe_allergens.has_*` for allergen exclusion;
- use `recipe_search_document.search_document` for full-text search;
- `steps.estimated_time_minutes` is not a duration metric;
- `is_halal` is not corrected — see `recipe_dietary_audit.halal_proxy`.

## Status

| Part | Scope                            | State       |
| ---- | -------------------------------- | ----------- |
| A    | Cleaning, profiling, scale tiers | Delivered   |
| B    | Schema, indexes, core queries    | Delivered (10k tier verified; x1/x5/x20 experiment recorded) |
| C    | API and business logic           | Not started |
| D    | Report and integration           | Not started |

