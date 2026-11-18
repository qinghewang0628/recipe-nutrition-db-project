# recipe-nutrition-db-project

Database course project (DSC5003): a recipe retrieval and nutrition
recommendation system built on a cleaned South Asian recipe corpus.

The work is split into four parts. Part A (data engineering) is complete and
delivered as a reproducible package under `part_a/`. Part B (database design and
core queries) is in progress in `db/`.

## Repository layout

| Path       | Owner | Contents                                                              |
| ---------- | ----- | --------------------------------------------------------------------- |
| `part_a/`  | A     | Delivered ETL package: cleaning pipeline, 11 cleaned tables, docs     |
| `db/`      | B     | `schema.sql` (DDL), `index.sql` (indexes), `queries.sql` (core queries) |
| `docs/`    | B/D   | ER diagram, load verification, scale experiment, consolidated report  |
| `report/`  | D     | Final report and figures                                              |
| `dataset/` | -     | Raw course CSVs, local only (licence unconfirmed), not committed      |

## Data flow

```
archive-datasets/*.csv            (5 raw CSVs, read-only, not committed)
  -> part_a/etl/clean.py          -> part_a/data/clean/*.csv   (11 tables)
  -> part_a/etl/scale.py          -> part_a/data/scales/{small,medium,large}
  -> part_a/sql/load_clean.sql    -> PostgreSQL tables (schema in db/schema.sql)
  -> db/queries.sql               -> the three core retrieval queries
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
psql -h 127.0.0.1 -d recipe_db -v ON_ERROR_STOP=1 -f db/schema.sql
psql -h 127.0.0.1 -d recipe_db -v ON_ERROR_STOP=1 -f db/index.sql

cd part_a                                             # \copy paths are relative to CWD
psql -h 127.0.0.1 -d recipe_db -v ON_ERROR_STOP=1 -f sql/load_clean.sql
```

`part_a/sql/load_*.sql` copies `recipes` before `cuisines`, so every foreign key
in `db/schema.sql` is declared `DEFERRABLE INITIALLY DEFERRED`; the loader wraps
its `\copy` calls in a single transaction and the constraints are checked at
`COMMIT`.

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
| B    | Schema, indexes, core queries    | In progress |
| C    | API and business logic           | Not started |
| D    | Report and integration           | Not started |

