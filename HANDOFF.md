# Part B handoff: database, queries, evidence

For Person C (API and business logic) and Person D (report). Part A's column
contracts are in `part_a/docs/handoff.md` section 2; this file covers only what
Part B adds. Read section 1, then section 3.

Every number below was measured on this database and is traceable to a file
named next to it. Nothing here is a plan for future work.

## 1. Get a working database in one minute

The zip ships a `pg_dump` custom-format archive of the finished 10k database
(2.4 MB: schema, all 11 tables, all 16 indexes, 9,997 recipes):

```bash
createdb -h 127.0.0.1 recipe_db
pg_restore -h 127.0.0.1 -d recipe_db --no-owner --no-privileges db/recipe_db_x1.dump
psql -h 127.0.0.1 -d recipe_db -f sql/index.sql     # statistics only; indexes are in the dump
psql -h 127.0.0.1 -d recipe_db -c 'select count(*) from recipes'   # 9997
```

The third command matters for a reason that is not the indexes: `pg_restore`
does not carry column statistics (`pg_statistic` is not dumped), so until you
`ANALYZE` the planner is working on default selectivity guesses. On the shipped
dump q2 runs 0.61 ms on the composite index straight after the restore, and
0.30 ms once statistics exist - because the planner then notices the
`is_vegetarian AND is_gluten_free` predicates and switches to the much narrower
partial index `idx_recipes_veg_gf_time`. Same rows, same query text, half the
time. `sql/index.sql` is idempotent (`IF NOT EXISTS` throughout) and ends with
one `ANALYZE` per table, so re-running it is the supported way to refresh
statistics after a restore or a reload. Do not quote a timing taken before it.

To build from source instead: `docs/load_verification.md` section 1 is the
exact four commands (create, schema, load, index). It needs
`part_a/data/clean/*.csv`, which are in the repository but not in this zip.

## 2. What is frozen

schema v1.0: 11 tables, 125 columns, 10 foreign keys, 56 `CHECK` constraints,
5 secondary indexes (16 index objects including the 11 primary keys). Row counts
are in `docs/load_verification.md` section 2; every column is described in
`docs/data_dictionary.md`.

Do not rename or retype a column, do not relax a `CHECK`: Part A's eleven CSVs,
the loaders and the scale experiment all sit on top of them, and the report
quotes them. If Part C genuinely needs a change, add a row to the change record
(`docs/schema-design.md` section 7) and tell A and D the same day, so the report
and the video do not describe a schema that no longer exists. Additive objects
(views, the API's own tables, extra indexes) need no ceremony.

## 3. The three queries and the index each one owns

All three are in `sql/queries.sql`, runnable as-is, and each header explains the
ranking decision rather than only the syntax.

| | Question | Index it uses | x1 | x5 | x20 | speed-up |
|---|---|---|---:|---:|---:|---|
| q1 | what can I cook with these ingredients? | `idx_ingredients_canonical` (`canonical_id` `INCLUDE recipe_id`) | 17.4 ms | 54.7 ms | 270 ms | 0.99x / 1.43x / 1.34x |
| q2 | filter by cuisine, category, time, cost, calories, spice, difficulty, rating, diet, allergens | `idx_recipes_cuisine_category_time` + partial `idx_recipes_veg_gf_time` | 0.60 ms | 2.6 ms | 3.7 ms | 2.78x / 2.55x / 2.22x |
| q3 | full-text search over the composite document | `idx_search_document_fts` (GIN on the `to_tsvector` expression) | 29 ms | 98 ms | 245 ms | 15.0x / 20.4x / 22.4x |

(medians of 12 runs, indexed vs identical data without secondary indexes;
`docs/evidence/scale_timings.csv`, discussion in `docs/scale_experiment.md`
sections 4-6.)

What this means for the API layer:

- **q1 is a tie at x1 and only worth 1.3x at x20.** The cost is the aggregate
  over `ingredients`, not the scan. Do not "optimise" it by dropping the
  index - and do not build the UI on a fresh call per keystroke; the honest
  options are a cache or a precomputed overlap table, and either is a
  documented design decision, not a hidden one.
- **q2 is already sub-millisecond.** Bind the parameters, do not rewrite the SQL.
  `NULL` means "no constraint" for every parameter; the API must pass `NULL`
  rather than an empty string for "not specified".
- **q3 must be called with the exact expression** `to_tsvector('english', ...)`.
  Any change of configuration (`simple`, `unaccent`, a different function) makes
  PostgreSQL silently stop using the GIN index - the query still returns rows,
  it just becomes 15-22x slower. `plainto_tsquery` is used so that user input
  cannot produce a syntax error; keep it, and keep `ts_headline` inside the
  final `LIMIT 20`.
- **Keep q1's tie-break.** With equal weighted scores the order is
  `matched_share DESC, total_time_minutes, recipe_id`. Dropping `recipe_id`
  makes pagination unstable (rows repeat or vanish between pages); it is in the
  `ORDER BY` for that reason, not for taste.

## 4. Reading order for Part C

1. `docs/schema-design.md` sections 1 and 3 - what each table is a fact about.
2. `docs/data_dictionary.md` - one line per column; section 6 is the list of
   traps, read it before writing any formatter.
3. `sql/queries.sql` - the three queries plus the parameter interface in the
   file header (replace the literal CTE with `$1::text[]`, ...; `LIMIT` as `$n`).
4. `part_a/docs/handoff.md` section 2 - the rules that came with the data
   (quantities, placeholders, dietary conventions, audit columns).
5. `docs/load_verification.md` sections 5-7 - index inventory, timings, plans.
6. `docs/scale_experiment.md` sections 5-6 - why q1 and q3 behave differently
   from q2 as the data grows.

## 5. Traps that will bite the API

- `qty_is_placeholder = true` rows have `qty_value` and `qty_approx_g` `NULL` by
  `CHECK`. Render `qty_placeholder_code` (`to taste`), never `0`.
- Display allergens from `recipe_allergens.allergens` (a `|`-joined label) but
  filter on the `has_*` booleans. Splitting the label at query time defeats both
  the index and the `CHECK` that keeps `allergen_count` equal to the flag sum.
- `is_vegetarian` / `is_vegan` / `is_gluten_free` are recomputed; the `*_raw`
  columns keep the source claim. Show the recomputed value, and keep
  `dietary_conflict_count` for the audit view.
- `is_halal` is a source flag with `is_halal_verifiable = false` in
  `recipe_dietary_audit`. Never present it as a verified fact.
- `steps.estimated_time_minutes` is not a duration (20 templates). Use
  `prep_time_minutes + cook_time_minutes = total_time_minutes`.
- Never filter on `cuisines.categories`; the 1NF home of that fact is
  `cuisine_category`.
- `ingredient_stats` embeds `total_recipes`, so it is per tier. On the 10k
  database it is consistent; after any reload, rebuild it (Part A's loader does).

## 6. What backs each claim in the report

| Claim | Evidence file |
|---|---|
| Every row arrived, nothing lost in dedup | `docs/evidence/integrity_checks.txt`, `docs/load_verification.md` section 2 |
| Constraints actually reject bad rows | `docs/evidence/constraint_tests.txt` (raw `ERROR` text) |
| Denormalised counters equal their base tables | `docs/evidence/derivation_equivalence.txt` (0 rows differing) |
| Index enabled / disabled plans | `docs/evidence/explain_indexed.txt`, `explain_noindex.txt` |
| Timings at x1 | `docs/evidence/timings.csv` |
| Timings at x1/x5/x20 and per-tier build cost | `docs/evidence/scale_timings.csv`, `scale_build.csv`, `scale_plans.txt` |
| What the queries return | `docs/evidence/query_results.txt` (10 / 14 / 20 rows) |
| Schema, keys, indexes, dictionary | `docs/schema-design.md`, `docs/data_dictionary.md` |
| Figures | `docs/figures/er-diagram.{png,svg}`, `timings.{png,svg}` |

The two `docs/figures/timings.*` files and `docs/data_dictionary.md` are
generated, not typed: `python3 tools/plot_timings.py` (reads
`scale_timings.csv`) and `python3 tools/gen_data_dictionary.py` (reads
`pg_catalog`, exits non-zero if a column has no curated description). Run
`gen_data_dictionary.py --check` after touching `sql/schema.sql`.

## 7. Out of scope for Part B

The API, the front end, the merged report and the video belong to C and D. Part
B adds no triggers, no stored procedures, no roles or grants and no streaming
ingest: the database is loaded in bulk and read-only afterwards, which is why
`ANALYZE` after load is the whole statistics story.

