# Scale Datasets

Person A, Data Engineering. This document defines the three scale tiers
supplied to Person B for the indexed-versus-unindexed performance
experiment and records the limits of their use.

---

## 1. Definition and measured sizes

| Tier | Factor | `recipes` | `ingredients` | `nutrition` | `steps` | `recipe_allergens` | Size on disk |
|---|---:|---:|---:|---:|---:|---:|---:|
| `small` | 1x | 9,997 | 95,912 | 9,997 | 84,616 | 9,997 | about 19 MB |
| `medium` | 5x | 49,985 | 472,756 | 49,985 | 423,080 | 49,985 | about 99 MB |
| `large` | 20x | 199,940 | 1,890,743 | 199,940 | 1,692,320 | 199,940 | about 396 MB |

`cuisines.recipe_count` is multiplied by the same factor, and
`ingredient_stats.doc_freq` and `idf` are recomputed independently for each
tier so rarity weights remain correct at that scale.

Full row counts, byte counts and SHA-256 values are in
`data/scales/scales_manifest.json` and `data/manifest.json`. Loaders are
`sql/load_small.sql`, `sql/load_medium.sql` and `sql/load_large.sql`
(`psql \copy`, run from the repository root).

---

## 2. Expansion algorithm

The expansion is deterministic and reproducible:

```
for scale in [small(1), medium(5), large(20)]:
    rng = Random(RANDOM_SEED + copy_index*9973 + len(scale)*131)
    for copy in 0..factor-1:
        for each cleaned recipe:
            new_recipe_id = RCP{orig_seq + copy*100000 :07d}
            copy the detail rows and apply the perturbations below
```

| Field | Perturbation | Purpose |
|---|---|---|
| `rating`, `review_count`, `estimated_cost_usd` | +/-3%, +/-15%, +/-10% | Avoid identical rows; make range filters meaningful |
| `date_added` | +/-180 days | Give the date filter a distribution |
| `servings` | +/-1 with 25% probability, clamped to 2–7 | Keep the serving distribution non-degenerate |
| `calories_per_serving` and `nutrition.calories` | +/-5%, applied synchronously | Preserve the cross-table consistency assertion |
| Eleven other nutrition columns | +/-5% | Give nutrition filters a distribution |
| Ingredient detail | Drop one non-core ingredient in 15% of copies, retaining at least five | Make posting lists differ across copies |
| `qty_approx_g`, `qty_canonical_value` | +/-10% | Keep quantity distributions non-degenerate |
| Grams per serving | Still clipped at 1,200 g under R5 | Match the baseline policy |

`canonical_id`, `canonical_name`, allergen flags, dietary flags and step
text are not perturbed. The semantics of the three core queries therefore
stay identical across tiers, and any performance difference is attributable
to scale rather than distribution drift.

A fixed seed and a fixed traversal order make `make seed` idempotent; the
verification report includes an assertion that two independent rebuilds are
byte-identical.

---

## 3. Limits of use

The synthetic tiers support only index-scalability and execution-plan
comparison. They must not be used for:

- accuracy, recall, or nutritional and dietary conclusions — replicated
  recipes are not new real recipes;
- absolute comparison with the reproduced paper's results, which used a
  different dataset, hardware and DBMS;
- statistical inference about real-world recipe distributions.

Performance results should be reported as relative speed-up on this
project's synthetic expansion, not as a multiple of the paper's figures.

---

## 4. Experimental wiring for Person B

1. Run `sql/schema.sql` to create the tables. If table names differ from
   `etl/seed.py:TABLE_MAP`, change that mapping and rerun `make seed` to
   regenerate the loaders.
2. Execute `psql -f sql/load_<tier>.sql` for each tier.
3. For each tier, run the same three query classes — ingredient reverse
   lookup, multi-predicate filtering and full-text search — with and without
   indexes. Repeat each cell at least five times and take the median.
   Capture `EXPLAIN (ANALYZE, BUFFERS)`.
4. Record Planning Time, Execution Time, Shared Hit/Read Blocks, Rows
   Removed by Filter and returned row counts.
5. Produce a 3 tiers x 2 groups x 3 query classes = 18-cell comparison
   table and a line chart for the group report.

`ingredient_stats.idf` is the weight for rarity-weighted overlap. A score
formed as the sum of `idf` over the query-recipe intersection gives near-unit
weight to ubiquitous ingredients (Salt, Onion, Garlic appear in almost all
9,997 recipes) and higher weight to rare ingredients such as Tofu or
Almonds.

---

## 5. GitHub file-size handling

GitHub warns above 50 MB and rejects files above 100 MB. Three CSVs exceed
50 MB:

| File | Raw | Compressed | Ratio |
|---|---:|---:|---:|
| `data/scales/medium/ingredients.csv` | 60 MB | about 8 MB | about 13% |
| `data/scales/large/ingredients.csv` | 240 MB | about 32 MB | about 13% |
| `data/scales/large/steps.csv` | 91 MB | about 7 MB | about 8% |

These three raw CSVs are excluded by `.gitignore`; their `.csv.gz` archives
are committed. After cloning, run `make unpack` to restore them, or
`make scale` to rebuild from scratch (about 40 seconds). If no archives
should be committed at all, `make scale FACTORS=1,5,8` keeps every file
below 50 MB at the cost of reducing the span from 20x to 8x.

`make pack` also writes `data/scales/pack_manifest.json` with raw size,
compressed size, ratio and SHA-256. `make unpack` uses only the Python
standard library `gzip` module.

---

## 6. Reproduction commands

```bash
python make.py seed         # full rebuild, including all three tiers
python make.py scale        # rebuild the tiers only
make scale FACTORS=1,5,10   # custom factors (GNU make)
python make.py pack         # create the .csv.gz archives
python make.py unpack       # restore from the archives
python make.py test         # check tier row counts, keys, caps and checksums
```
