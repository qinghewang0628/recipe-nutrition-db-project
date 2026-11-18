# Cleaning Rules and Design Decisions

Person A, Data Engineering. This document is the normative record of rules
R1–R8. Constants live in `etl/config.py`; implementations are in
`etl/units.py`, `etl/mappings.py` and `etl/clean.py`; `make test` checks
each invariant.

**Governing principles.** Raw files are read-only. Every step retains audit
columns. Only inferences that can be verified from the data are allowed to
overwrite source values; unverifiable inferences are retained and labelled.
Every threshold records its justification and its deviation from the source.

---

## R1 Recompute dietary flags

Three flags are recomputed from the canonical ingredient set and overwrite
the master-table values. The originals are preserved in `*_raw` columns and
in `recipe_dietary_audit.csv`, so the change is fully reversible.

| Flag | Rule (canonical set disjoint from) | Corrections |
|---|---|---:|
| `is_vegetarian` | `NON_VEG = {Beef, Chicken, Fish, Mutton, Shrimp, Eggs}` | 3,259 |
| `is_vegan` | `ANIMAL = NON_VEG + {Milk, Butter, Ghee, Cream, Yogurt, Paneer}` | 1,740 |
| `is_gluten_free` | `GLUTEN = {Wheat Flour, All-Purpose Flour, Semolina}` | 5,863 |
| **Total** | — | **10,862** |

Conventions: eggs count as non-vegetarian; `Chickpea Flour`, `Basmati Rice`
and `Lentils (Dal)` are gluten-free; cross-contamination is not modelled.
These are explicit project conventions, not domain standards. To adopt a
different convention, move `Eggs` out of `NON_VEG` and rerun `make seed`.

`is_halal` is **not** recomputed. A conservative "no pork, no alcohol"
proxy would imply that all 9,997 recipes are halal, because neither category
appears in the data; that would be a fabricated fact. The 1,328 conflicts are
instead retained with `is_halal_verifiable = false`, and the proxy is written
only to `recipe_dietary_audit.halal_proxy`.

---

## R2 Parse quantities into value and unit

`etl/units.py:parse_quantity` maps 1,517 free-text strings to ten structured
columns (`qty_value`, `qty_unit_norm`, `qty_dimension`,
`qty_canonical_value`, `qty_canonical_unit`, `qty_approx_g`,
`qty_is_placeholder`, `qty_placeholder_code`, `qty_parse_status`, and
related audit fields).

| Raw unit | Rows | Dimension | Canonical unit | Factor | Gram equivalent |
|---|---:|---|---|---:|---:|
| `tbsp` | 32,016 | volume | ml | 15 | 15 g |
| `medium` | 17,948 | count | piece | 1 | 100 g |
| `g` | 17,897 | mass | g | 1 | 1 g |
| `cloves` | 9,997 | count | piece | 1 | 3 g |
| `ml` | 8,067 | volume | ml | 1 | 1 g |
| `tsp` | 7,986 | volume | ml | 5 | 5 g |
| `to taste` | 9,997 | — | `TO_TASTE` | — | excluded from sums |

The parser tolerates spacing and case differences (`933g` versus `299 g`),
unit aliases, decimals and bare numbers. The three dimensions are not
forcibly cross-converted: business queries use
`qty_dimension + qty_canonical_value + qty_canonical_unit`. Only
`qty_approx_g` is comparable across dimensions; it is an approximation used
for aggregation, ranking and outlier detection, never as an input to
nutrition calculations.

**Deviation.** `1 tbsp = 15 g`, `1 ml = 1 g`, `1 medium = 100 g` and
`1 clove = 3 g` are conventional cooking approximations. Per-ingredient
densities (oil about 0.92 g/ml, honey about 1.4 g/ml) are not modelled, so
`qty_approx_g` carries systematic error. All factors and their basis are
recorded in `unit_conversion.csv`.

Parse status is one of `OK`, `OK_UNITLESS`, `PLACEHOLDER`, `UNPARSEABLE`,
`UNKNOWN_UNIT`; verification requires the last two to be zero.

---

## R3 Normalise placeholder names

`to taste`, `as needed`, `a pinch`, `N/A`, `-` and empty strings map to
uppercase codes (`TO_TASTE`, `AS_NEEDED`, `PINCH`, `UNSPECIFIED`,
`OPTIONAL`). Numeric columns stay empty and `qty_is_placeholder = true`.
8,940 placeholder rows remain after cleaning; the 1,057 removed rows merged
into quantified rows of the same ingredient under R4.

---

## R4 Merge duplicate ingredients

Grouping on `(recipe_id, canonical_id)` reduces 103,908 rows to 95,912.

1. Sum `qty_approx_g` over all non-placeholder rows in the group.
2. Take the row with the largest estimated grams as the dominant row; it
   determines `qty_dimension` and `qty_canonical_unit`.
3. Convert the summed grams back to `qty_canonical_value` using the
   dominant unit's factor.
4. If every row is a placeholder, keep the placeholder semantics and leave
   numeric fields empty.
5. Renumber `ingredient_number` to a contiguous 1..n sequence.
6. Preserve `merged_row_count`, `merged_units`, `quantity_raw` and
   `ingredient_name_raw` for audit.

Example: `RCP00013` lists Garlic as `3 cloves` and `2 medium`. The merged
value is `qty_approx_g = 3 x 3 + 2 x 100 = 209 g`, with the dominant unit
`medium`, giving `qty_canonical_value = 2.09 piece`.

Synonyms: `All-Purpose Flour` maps to `Wheat Flour`; `Coriander` (seed) and
`Fresh Coriander` (leaf) are deliberately not merged. The result is 57
canonical ids and 113 synonym/alias records.

---

## R5 Winsorise extreme quantities

Estimated ingredient mass per serving: min 52.1 g, P50 323.0 g,
P95 910.3 g, P99 1,285.5 g, max 1,937.5 g. The cap
`config.CAP_G_PER_SERVING = 1200` is a round domain value near P99.

143 recipes (1.4%) exceed it. All ingredient quantities in such a recipe are
scaled by the same factor `1200 / (grams per serving)`, preserving the
recipe's internal proportions. Affected rows carry `qty_clipped = true` and
the recipe carries `qty_clipped_recipe = true`. Before/after values and the
scale factor are recorded per recipe in `data/profile/clipped_recipes.csv`.

Deletion was rejected because the performance experiment requires the exact
9,997-recipe baseline and strict 1x/5x/20x multiples. The 1,200 g value is a
domain threshold, not a constant from the reproduced paper.

---

## R6 Unify categories and derive allergens

- `Paneer` is resolved to `Dairy`; the conflict is noted in `allergen_map.csv`.
- Ten allergen classes (gluten, milk, egg, fish, shellfish, tree_nuts,
  sesame, soy, mustard, peanut) produce `allergen_map.csv` and, by union per
  recipe, `recipe_allergens.csv`. 9,132 recipes contain at least one class.
  Ten `has_*` boolean columns are directly indexable.
- `Tofu` maps to soy, `Sesame Seeds` to sesame, `Mustard Seeds` to mustard,
  `Almonds` and `Cashews` to tree_nuts.
- `Coconut Milk` is not classified as a tree nut under Codex practice; an
  FDA-based classification would require an additional flag.
- `ingredient_stats.csv` provides `doc_freq` and
  `idf = ln((N+1)/(df+1)) + 1` as rarity weights, so common ingredients
  such as Salt, Onion and Garlic do not dominate top-k results.

---

## R7 Derived tables and full-text document

| Table | Content |
|---|---|
| `cuisine_category.csv` | 25 `(cuisine, category)` rows split from the comma-separated list, for 3NF modelling |
| `recipe_search_document.csv` | 9,997 concatenated documents (name, cuisine, category, method, ingredients, steps) with `doc_length` |
| `recipe_dietary_audit.csv` | Raw flag, recomputed flag, conflict count and conflict fields |
| `ingredient_master.csv` | 57 canonical ingredients |
| `ingredient_stats.csv` | IDF weight, coverage and mean estimated grams |

`recipe_steps.estimated_time_minutes` is retained but excluded from the
business time metric. Business duration always uses
`prep_time_minutes + cook_time_minutes = total_time_minutes`, verified for
all 9,997 recipes.

---

## R8 Reproducibility and audit

- Fixed `RANDOM_SEED = 20261116`; fixed scale factors 1, 5 and 20.
- All writes use `io_utils.write_csv`, which writes `.tmp` then
  `os.replace`, so an interrupted run leaves no partial file.
- `data/manifest.json` records row counts, byte counts, SHA-256 values and
  all configuration parameters.
- `make test` asserts that two independent rebuilds are byte-identical and
  that every manifest checksum matches.
- Raw SHA-256 values are registered in `etl/config.py` and checked at
  startup; a substituted input fails verification immediately.

---

## Deviations from the source data and the reproduced paper

| # | Deviation | Reason |
|---|---|---|
| 1 | Dietary labels recomputed from canonical ingredient sets instead of trusting source labels | Conflict rate up to 58.6% would invalidate filtering |
| 2 | Cross-dimension conversion uses a single approximate density, not per-ingredient densities | The dataset has no density information; the field supports aggregation, not nutrition |
| 3 | Extreme values winsorised at 1,200 g/serving rather than deleted | Preserves strict scale-tier multiples |
| 4 | `is_halal` retained and marked unverifiable | Slaughter and certification data are absent |
| 5 | Scale tiers built by seeded synthetic expansion rather than a larger external dataset | Licence unconfirmed; the experiment measures index scalability, not distribution fitting |
