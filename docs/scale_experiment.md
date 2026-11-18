# Scale Experiment (Part B)

Do the four indexes still earn their place when the data grows? The 10k tier
answers q1-q3 in 17 ms, 0.6 ms and 29 ms, which is too fast to separate signal
from laptop noise. This document records the same three queries, unchanged, on
Part A's x1, x5 and x20 tiers (9,997 / 49,985 / 199,940 recipes), with and
without `sql/index.sql`.

Raw numbers: `docs/evidence/scale_build.csv`, `scale_timings.csv`,
`scale_plans.txt`, `derivation_equivalence.txt`.

---

## 1. The tiers only ship 7 of the 11 tables

Part A publishes, per tier: `recipes`, `ingredients`, `steps`, `nutrition`,
`cuisines`, `recipe_allergens`, `ingredient_stats`. It does **not** publish
`ingredient_master`, `cuisine_category`, `recipe_dietary_audit` or
`recipe_search_document` - all four exist only in the x1 delivery.

That blocks the experiment: q2 filters on `is_vegetarian AND is_gluten_free`
(columns of `recipes`, fine) but q3 needs `recipe_search_document.search_document`
and q1 the 57-row `ingredient_master` dimension. The two ways out were:

1. rewrite q1-q3 for the tiers - rejected: the experiment must time the SQL that
   ships, not a variant of it;
2. rebuild the four missing tables from the seven that do ship - chosen.

`scale/derive_missing_tables.sql` does the rebuild with Part A's own rules
(`etl/clean.py` lines 180-330), not with rules invented here: the same ten-name
ingredient dictionary, the same dietary re-computation, the same
document-ordering (`COLLATE "C"`, because Python's `sorted()` compares code
points while the database default collation ignores spaces), and
`doc_freq`/`idf` recomputed from each tier's own numbers so rarity weights stay
correct at scale.

**The rebuild is exact.** At x1 both versions exist, so
`scale/check_equivalence.sql` diffs them with `EXCEPT ALL` in both directions:

```
       table_name       | rows_part_a | rows_derived | only_part_a | only_derived
------------------------+-------------+--------------+-------------+--------------
 cuisine_category       |          25 |           25 |           0 |            0
 ingredient_stats       |          57 |           57 |           0 |            0
 recipe_dietary_audit   |        9997 |         9997 |           0 |            0
 recipe_search_document |        9997 |         9997 |           0 |            0
```

So `sql/schema.sql`, `sql/index.sql` and `sql/queries.sql` run on the tiers
byte-for-byte as delivered, with the same parameter literals.

## 2. Building a tier

```bash
createdb -h 127.0.0.1 recipe_scale
python3 scale/run_experiment.py                    # all three tiers
python3 scale/run_experiment.py --tiers large --blocks 2   # one tier
```

Per tier the script creates `t_<tier>` (schema -> `load_ingredient_master.sql` ->
`part_a/sql/load_<tier>.sql` -> `derive_missing_tables.sql` -> `index.sql`) and
`t_<tier>_noidx` (the same, minus the index file, with the same `ANALYZE` calls
so the two plans come from identical statistics).

| Tier | recipes | ingredients | steps | search docs | `t_*` size | `t_*_noidx` size | load | derive | index |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| x1 | 9,997 | 95,912 | 84,616 | 9,997 | 57.7 MB | 46.4 MB | 1.6 s | 0.4 s | 1.2 s |
| x5 | 49,985 | 472,756 | 423,080 | 49,985 | 292.6 MB | 238.5 MB | 13.1 s | 3.6 s | 6.0 s |
| x20 | 199,940 | 1,890,743 | 1,692,320 | 199,940 | 1,137 MB | 929 MB | 44.5 s | 12.4 s | 10.4 s |

Both phases are linear in the input (x20 is 27x the x1 load time for 20x the
rows; the derivation 30x) and cheap enough that rebuilding the four tables costs
a fraction of the load. The index build is the cheapest part: 10.4 s for four
indexes over 1.9 M ingredient rows.

The post-derivation checks print `unmapped_ingredient_rows=0` on every tier (no
`canonical_id` outside the 57-row master) and `flag_mismatches` of 0 / 720 /
2,849 - see finding 5 in section 6 for why the last two are non-zero.

## 3. Measurement protocol

Two traps to avoid, both of which produce a flattering and wrong answer:

- **Don't drop the indexes between the two runs.** On a laptop the first group
  of runs is measured while the CPU is cold and the second group after it has
  throttled, so "no index" always looks slower. An early version of this
  experiment did exactly that and reported q1 as 3.3x faster with indexes
  (`docs/load_verification.md` records the correction). Instead the script
  builds two schemas per tier and alternates between them.
- **Don't trust single runs.** Warm-up runs, then 4 measured runs per block, 3
  blocks, alternating `indexed` -> `noindex` inside every block: 12 runs per
  query per configuration. Median and minimum are both reported; the minimum is
  the more stable statistic here because the frequency scaling only ever makes a
  run slower.

Absolute milliseconds on this machine still move by up to 2x between two runs of
the same script (five-minute runs, no CPU pinning, Postgres.app defaults). The
plans and the indexed/no-index ratios reproduce; the third digit of a
millisecond does not. Compare ratios, not absolute times.

## 4. Results

Medians of 12 runs, `EXPLAIN (ANALYZE, BUFFERS)` execution time, warm cache.
"speed-up" is the no-index median divided by the indexed median (minimum-based
speed-up in brackets, where it differs materially).

| Query | Tier | Rows returned | No indexes | All 4 indexes | Speed-up |
|---|---|---:|---:|---:|---:|
| q1 reverse ingredient search | x1 | 10 | 17.30 ms | 17.41 ms | 1.0x (1.05x min) |
| | x5 | 10 | 78.01 ms | 54.72 ms | 1.4x (1.11x min) |
| | x20 | 10 | 361.17 ms | 269.76 ms | **1.3x** |
| q2 multi-condition filter | x1 | 14 | 1.68 ms | 0.60 ms | 2.8x |
| | x5 | 20 | 6.57 ms | 2.58 ms | 2.5x |
| | x20 | 20 | 8.14 ms | 3.67 ms | 2.2x |
| q3 full-text search | x1 | 20 | 429.14 ms | 28.57 ms | **15.0x** |
| | x5 | 20 | 2,005.89 ms | 98.44 ms | **20.4x** |
| | x20 | 20 | 5,497.19 ms | 245.33 ms | **22.4x** |

An earlier run of the same script, on the same machine, gave 12.9/291 ms (x1),
59.7/1421 ms (x5) and 243.9/5458 ms (x20) for q3 and 264.7/364.0 ms at x20 for
q1: absolute times moved, plans and ratios did not.

Plan shapes (`docs/evidence/scale_plans.txt`) do not change between tiers; only
q1 changes between configurations:

| Query | No indexes | All 4 indexes |
|---|---|---|
| q1 | `Seq Scan on ingredients` (95,912 -> 1,890,743 rows) | `Index Only Scan using idx_ingredients_canonical` (4,014 -> 79,063 rows) |
| q2 | `Seq Scan on recipes` + heap filter | `Bitmap Index Scan on idx_recipes_veg_gf_time` |
| q3 | `Seq Scan on recipe_search_document` with one `to_tsvector` per row | `Bitmap Index Scan on idx_search_document_fts` |
| (at x20 only) | | the planner switches to `Gather Merge` over 8 workers for q2 |

## 5. Where the time goes as the data grows

| Tier | `ingredients` heap | postings for the 3 wanted ingredients | recipes with >=2 matches (q1's `HAVING`) | q1 indexed | us per posting |
|---|---:|---:|---:|---:|---:|
| x1 | 15 MB | 4,014 | 426 | 17.4 ms | 4.3 |
| x5 | 73 MB | 19,812 | 2,079 | 54.7 ms | 2.8 |
| x20 | 293 MB | 79,063 | 8,305 | 269.8 ms | 3.4 |

The postings and the timing grow together (19.7x and 15.5x for 20x the recipes,
3-4 us per posting throughout). That is the whole story of q1: its cost is set
by how many ingredient rows the wanted names match, and `LIMIT 10` cannot prune
anything because the weighted score of every candidate has to be computed before
the top ten are known.

The other two queries are bounded by the `LIMIT`, not by the table:

| Tier | q2 indexed | q3 indexed | q3 no index |
|---|---:|---:|---:|
| x1 | 0.60 ms | 28.6 ms | 429 ms |
| x5 | 2.58 ms | 98.4 ms | 2,006 ms |
| x20 | 3.67 ms | 245.3 ms | 5,497 ms |

q2 grows 6.1x while the table grows 20x (it reads 20 rows through the index and
stops), q3 grows 8.6x while the table grows 20x (the GIN bitmap keeps the scan
proportional to the matching documents rather than to the table), and the
unindexed q3 grows 12.8x because it pays one `to_tsvector` per row.

## 6. Findings

1. **q3's GIN index is the only one that changes the asymptotics**, and it is
   the only one that would be unacceptable to ship without: 5.5 s per search at
   x20 versus 245 ms. It also gets *relatively* better with scale (15x -> 22x),
   because the cost it removes is per-row work.
2. **q2's two b-tree indexes hold a stable 2.2-2.8x.** The ratio shrinks with
   scale while the absolute saving grows (1.1 ms -> 4.5 ms). The partial index
   holds 153 / 765 / 3,060 rows on the three tiers, so at x20 the planner
   bitmap-scans 1.5% of `recipes` instead of all 200k rows, applies the
   remaining predicates and sorts 20. Both indexes stay, and the x20 plan
   (`Gather Merge` over 8 workers) shows the planner using them in parallel.
3. **q1's index buys little in ratio but a lot in absolute terms, and the ratio
   is the noisy one:** 0.99x at x1 (a tie; 1.05x by minimum), 1.4x at x5, 1.3x
   at x20. What it buys is a full scan of the `ingredients` heap (1.9 M rows,
   293 MB at x20) removed from the plan, so the absolute saving grows with the
   data: 0 ms -> 23 ms -> 91 ms. It is still the right index - it is the only
   way to answer q1 without scanning `ingredients` - but it is not what makes
   q1 slow, and it never will be, because q1 also has to aggregate the postings
   it finds. If q1 has to get faster, the fix is upstream of the index:
   - anchor the search on the rarest wanted ingredient (`ingredient_stats` has
     `doc_freq` for exactly this decision): at x20 Cardamom matches 14,088 rows
     against the triple's 79,063, so 5.6x fewer postings are visited and the
     other two names become verification probes; only 4,963 of the 8,305
     qualifying recipes (60%) contain Cardamom, so this also drops 40% of the
     current matches;
   - this changes semantics (results would require the anchor), so it is a
     product decision for Part C's API, not a change we can make unilaterally;
   - the alternative, a precomputed pair-co-occurrence table, trades a 5x
     reduction in scanned rows for several GB of storage at x20 - not worth it
     for a 270 ms query.
4. **The derivation step is cheap enough to keep.** 12.4 s to rebuild all four
   tables at x20, against 44.5 s to load the tier. If the project ever needed
   the tiers in production, the four tables would be materialised once and
   refreshed with the load, not derived per query.
5. **Part A's scale tiers have a small internal inconsistency, and the audit
   table catches it.** The x5/x20 expansion drops one non-core ingredient in 15%
   of the copies but copies the dietary flags unchanged
   (`part_a/docs/scale_datasets.md`, section 2). Where that dropped line was the
   only non-vegetarian or gluten ingredient, the copied flag no longer matches
   the ingredient list: 720 rows at x5 (1.44%), 2,849 at x20 (1.42%), 0 at x1.
   The derived `recipe_dietary_audit` recomputes the flags from the ingredients,
   so the disagreement shows up as `flag_mismatches` rather than silently. q2
   filters on `recipes.is_vegetarian` as delivered, so on those tiers up to 1.4%
   of the candidate set can be filtered on a stale flag; on the x1 build, which
   is the graded one, the count is 0 and q2's results are exact.

## 7. Reproducing this

```bash
# 1. scratch database (never reuse recipe_db: the script drops t_* schemas)
createdb -h 127.0.0.1 recipe_scale

# 2. build both configurations of all three tiers and measure
python3 scale/run_experiment.py                 # ~8 min on a laptop
#    -> docs/evidence/scale_build.csv, scale_timings.csv, scale_plans.txt
#    a partial run (--tiers large) replaces only the tiers it measures

# 3. prove the derived tables match Part A's on the tier where both exist
psql -h 127.0.0.1 -d recipe_scale -c 'DROP SCHEMA IF EXISTS t_base CASCADE; CREATE SCHEMA t_base;'
PGOPTIONS=--search_path=t_base psql -h 127.0.0.1 -d recipe_scale -f sql/schema.sql
(cd part_a && PGOPTIONS=--search_path=t_base psql -h 127.0.0.1 -d recipe_scale -f sql/load_clean.sql)
psql -h 127.0.0.1 -d recipe_scale -f scale/check_equivalence.sql
#    -> 0 rows differing in either direction for all four tables

# 4. free the space again: x5/x20 are 2.6 GB of the 2.7 GB, x1 is 150 MB and is
#    what step 3 needs, so it is the part worth keeping
psql -h 127.0.0.1 -d recipe_scale -c 'DROP SCHEMA t_medium, t_medium_noidx,
    t_large, t_large_noidx CASCADE;'
```

Every schema is recreated from scratch by the step that needs it, so nothing has
to be kept for a re-run. `dropdb -h 127.0.0.1 recipe_scale` is the shorter
version once the CSVs are in `docs/evidence/`. The tiers themselves stay out of
git: `part_a` commits the large CSVs as `.csv.gz` and the loader reads them
through `part_a/data/scales/`.

## 8. Caveats

- The **x1 tier is the graded build**; every integrity statement in
  `docs/load_verification.md` is about `recipe_db`. The tiers exist to measure
  indexes, and the four derived tables on x5/x20 are Part B's reconstruction of
  Part A's rules, verified to be exact only at x1 (section 1).
- x5/x20 are synthetic copies with perturbed quantities (Part A's expansion,
  `part_a/docs/scale_datasets.md` §2), so they test volume, not new
  distributions. Two of the perturbations are visible here: the ingredient drop
  of finding 5, and the fact that ingredient lines differ between copies of the
  same recipe, which shifts `doc_freq` slightly on every tier.
- Single-user measurements: one psql session, no concurrency, no
  `shared_buffers` tuning, no `pg_prewarm`. An API serving several users would
  need the same numbers under load, which this experiment does not establish.
- The derivations in `scale/derive_missing_tables.sql` were written from Part A's
  `etl/clean.py`; they are a dependency on Part A's internals, and the
  `EXCEPT ALL` check is what keeps that dependency honest. Re-run it if Part A
  ever changes its cleaning rules.
