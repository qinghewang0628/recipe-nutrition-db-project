# Load verification and index benchmark (Part B, schema v1.0)

Sections 1-5 and 7 come from a clean `recipe_db` built by running the three
scripts in `sql/` against the eleven cleaned tables delivered by Part A. Section
6 measures the same data twice, on the x1 tier of the scale experiment; §8 says
why. Raw outputs are in `docs/evidence/`.

| Item | Value |
|---|---|
| Date | 2026-11-18 |
| Server | PostgreSQL 17.12 (Postgres.app), `127.0.0.1:5432` |
| Database | `recipe_db` (recreated for this run) |
| Data | `part_a/data/clean/*.csv` (11 tables, SHA-256 pinned in `part_a/data/manifest.json`) |
| Scripts | `sql/schema.sql`, `part_a/sql/load_clean.sql`, `sql/index.sql` |
| Database size | 52 MB (heap 43 MB, indexes 5.6 MB) |

## 1. What was executed

```bash
createdb -h 127.0.0.1 recipe_db
psql -h 127.0.0.1 -d recipe_db -v ON_ERROR_STOP=1 -f sql/schema.sql        # 11 tables, 10 FKs, 56 CHECKs
cd part_a
psql -h 127.0.0.1 -d recipe_db -v ON_ERROR_STOP=1 -f sql/load_clean.sql    # 1.77 s wall clock, 0 errors
cd ..
psql -h 127.0.0.1 -d recipe_db -v ON_ERROR_STOP=1 -f sql/index.sql         # 1.19 s, 4 indexes + ANALYZE
```

The load needed no change to Part A's loader. His script copies `recipes` before
`cuisines`/`ingredient_master` inside a single transaction, which only works
because every foreign key is declared `DEFERRABLE INITIALLY DEFERRED`. The
`CHECK` constraints are validated per row, so a narrowed type or a wrong domain
would have failed the load instead of silently producing a wrong database.

## 2. Reconciliation with Part A's manifest

| Table | Rows in `recipe_db` | `manifest.json` | Match |
|---|---:|---:|---|
| `cuisines` | 5 | 5 | yes |
| `cuisine_category` | 25 | 25 | yes |
| `recipes` | 9,997 | 9,997 | yes |
| `ingredient_master` | 57 | 57 | yes |
| `ingredients` | 95,912 | 95,912 | yes |
| `steps` | 84,616 | 84,616 | yes |
| `nutrition` | 9,997 | 9,997 | yes |
| `recipe_allergens` | 9,997 | 9,997 | yes |
| `recipe_dietary_audit` | 9,997 | 9,997 | yes |
| `ingredient_stats` | 57 | 57 | yes |
| `recipe_search_document` | 9,997 | 9,997 | yes |

`sum(ingredients.merged_row_count) = 103,908`, i.e. the 95,912 cleaned lines still
account for every raw ingredient row: Part A's duplicate merge is lossless and
the database can prove it.

## 3. Integrity checks (`docs/evidence/integrity_checks.txt`)

| # | Check | Result |
|---|---|---|
| 1 | Row counts against the manifest | 11/11 match |
| 2 | Lossless merge | `95912` lines, `103908` raw rows, `matches_raw_source = t` |
| 3 | Orphan rows across all 8 FK references | 0 in every column |
| 4 | Every recipe has exactly one `nutrition` / `recipe_allergens` / `recipe_search_document` row | 0 missing |
| 5 | Denormalised counters vs child tables (`ingredient_count`, `step_count`) | 0 disagreements in 9,997 rows |
| 6 | Quantity placeholders | 8,940 placeholder lines, 0 inconsistent, 0 parsed rows without grams |
| 7 | IDF weights | min 1.000000, max 3.737794, 3 ingredients at 1.0 (salt, onion, garlic) |
| 8 | Dietary audit | 10,862 conflicts over 9,997 recipes, matches Part A's 3,259/1,740/5,863 split |

## 4. Constraint enforcement (negative tests, `docs/evidence/constraint_tests.txt`)

Each case runs inside a transaction that is rolled back, so the database is left
unchanged. Because the foreign keys are deferred, case (a) additionally runs
`SET CONSTRAINTS ALL IMMEDIATE` to make the violation surface inside the block.

| Case | Statement | Error raised |
|---|---|---|
| a | ingredient line for a non-existent recipe | `violates foreign key constraint "ingredients_recipe_id_fkey"` / `Key (recipe_id)=(RCP99999) is not present in table "recipes"` |
| b | `total_time_minutes` changed without touching prep/cook | `violates check constraint "total_time_is_prep_plus_cook"` |
| c | `spice_level = 'Extreme'` | `violates check constraint "recipes_spice_level_check"` |
| d | numeric value written into a placeholder line | `violates check constraint "placeholder_has_no_value"` |
| e | `allergen_count` incremented without setting a flag | `violates check constraint "allergen_count_matches_flags"` |

These are the evidence for the "dirty data cannot get back in" argument in the
report: the constraints are not decorative, they are the reason a future import
cannot reintroduce the defects Part A cleaned.

## 5. Index inventory

| Index | Table | Definition | Size |
|---|---|---|---:|
| `idx_ingredients_canonical` | `ingredients` | `btree (canonical_id) INCLUDE (recipe_id)` | 4.0 MB |
| `idx_recipes_cuisine_category_time` | `recipes` | `btree (cuisine, category, total_time_minutes) INCLUDE (calories_per_serving, estimated_cost_usd, rating)` | 584 kB |
| `idx_recipes_veg_gf_time` | `recipes` | `btree (total_time_minutes) WHERE is_vegetarian AND is_gluten_free` | 40 kB |
| `idx_search_document_fts` | `recipe_search_document` | `gin (to_tsvector('english', search_document))` | 1.1 MB |

Primary keys cover the remaining access paths (`ingredients (recipe_id, ...)`,
the 1:1 extension tables, the two dimensions), so no further index was added.
The list of deliberately unindexed columns and the reason for each is in
`sql/index.sql`.

## 6. Timing on the 10k tier (`docs/evidence/timings.csv`)

Two schemas with identical data - `t_small` (all 4 indexes) and `t_small_noidx`
(same rows, no secondary index, same statistics) - measured in alternating
blocks, 12 runs per query per configuration. Median of
`EXPLAIN (ANALYZE)` execution time; both configurations return the same rows
(`docs/scale_experiment.md` §4 records the plans).

| Query | No indexes | All 4 indexes | Speed-up | Plan change |
|---|---:|---:|---:|---|
| q1 reverse ingredient search | 17.30 ms | 17.41 ms | 1.0x | `Seq Scan on ingredients` (95,912 rows) becomes `Index Only Scan using idx_ingredients_canonical` (1,338 rows per probe, 3 probes) |
| q2 multi-condition filter | 1.68 ms | 0.60 ms | 2.8x | `Seq Scan on recipes` becomes `Bitmap Index Scan on idx_recipes_veg_gf_time` (496 rows), then `Index Cond: total_time_minutes <= 90` |
| q3 full-text search | 429.14 ms | 28.57 ms | 15.0x | `Seq Scan on recipe_search_document` with 9,997 `to_tsvector` calls becomes `Bitmap Index Scan on idx_search_document_fts` (415 rows) |

**Correction.** An earlier version of this table measured the indexed
configuration first and then dropped the indexes for the second group. That
reported q1 as 8.850 ms -> 2.644 ms (3.3x), which does not survive a fair
measurement: on a laptop the second group always runs on a throttled CPU, and
the x1 `ingredients` heap (15 MB) is small enough to scan. Re-measured with the
two configurations interleaved, q1 is a tie at x1 and the plan is the only
visible difference. The index does pay on the bigger tiers (1.4x at x5; at x20,
269.8 ms indexed against 361.2 ms unindexed) - see `docs/scale_experiment.md`
finding 3.

Two observations worth carrying into the report:

- The 10k tier is small enough that q1 and q2 are already fast without any
  index (17.3 ms and 1.7 ms). The indexes reduce the number of rows *read*; they
  do not remove work that grows with the table - except for q3, where the
  unindexed cost is one `to_tsvector` per row (429 ms) and only the GIN index
  removes it.
- Both `recipes` indexes are needed, and each is chosen for a different filter
  shape. With the vegetarian + gluten-free filter supplied the planner picks
  the partial index (`Bitmap Index Scan on idx_recipes_veg_gf_time`); with
  `cuisine = 'Indian' AND category = 'Main Course'` supplied and no dietary
  flag it picks the composite one (`Index Cond: (cuisine = 'Indian' AND
  category = 'Main Course' AND total_time_minutes <= 90)`). Flip the parameter
  row in `sql/queries.sql` and re-run `EXPLAIN` to see both.

## 7. Plan shapes (`docs/evidence/explain_indexed.txt`, `explain_noindex.txt`)

The two files are full `EXPLAIN (ANALYZE, BUFFERS)` captures from `recipe_db`.
Only the node types and row estimates are quoted here - the per-node timings in
those captures predate the interleaved protocol of §6, so §6's totals are the
ones to trust.

q1, without indexes:

```
->  Seq Scan on ingredients i  (cost=0.00..2839.12 rows=95912 width=21) (actual time=0.008..5.509 rows=95912 loops=1)
```

q1, with indexes:

```
->  Index Only Scan using idx_ingredients_canonical on ingredients i
      (cost=0.42..132.37 rows=1683 width=21) (actual time=0.034..0.162 rows=1338 loops=3)
```

The `INCLUDE (recipe_id)` matters here: the result is an index-only scan, so the
15 MB heap of `ingredients` is never touched after the index probe.

q3, with indexes:

```
->  Bitmap Index Scan on idx_search_document_fts
      (cost=0.00..13.05 rows=50 width=0) (actual time=0.127..0.127 rows=415 loops=1)
->  Bitmap Heap Scan on recipe_search_document d_1
      (cost=13.06..182.14 rows=50 width=483) (actual time=0.151..0.585 rows=415 loops=1)
```

## 8. Caveats

- These numbers describe the 10k tier only. The 50k (x5) and 200k (x20) tiers are
  measured separately in `docs/scale_experiment.md`, which is where the
  index/scale interaction actually shows up (q1 is a tie at x1 and only 1.3-1.4x
  at x5/x20, q3 goes from 15x to 22x).
- The timings were taken on `recipe_scale`'s `t_small`, not on `recipe_db`,
  because the comparison needs two copies of the same data and `recipe_db` is
  the deliverable. The two are the same data: `part_a/data/scales/small/*.csv`
  is byte-identical to `part_a/data/clean/*.csv` (7/7 files, md5), the 4
  derived tables were proven equal to Part A's with `EXCEPT ALL`
  (`docs/evidence/derivation_equivalence.txt`), and the plans in §7 match the
  `t_small` plans line for line.
- Timings are single-session medians on a laptop (Postgres.app, no tuning), with
  the indexed and unindexed configurations interleaved so that neither group
  runs entirely on a throttled CPU. Ratios reproduce between runs; the third
  significant digit does not (absolute times move by up to 2x between runs on
  this machine).
- q3 keeps `ts_headline` inside the outer `SELECT`, after the `LIMIT`, so the
  measured 28.6 ms includes highlighting of only the 20 returned documents. Run
  as a single expression over the whole table it would dominate the query.
- The 50k and 200k tiers contain only 7 of the 11 tables (no
  `search_document`, `ingredient_master`, `cuisine_category`, `dietary_audit`),
  so q1-q3 cannot run there as delivered. Part B rebuilds the 4 missing tables
  from the 7 shipped ones (`scale/derive_missing_tables.sql`) and verifies the
  rebuild at x1 with `EXCEPT ALL` - see `docs/scale_experiment.md` §1-2.
