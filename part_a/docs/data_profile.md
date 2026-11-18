# Data Profile

Person A, Data Engineering. This document summarises the raw dataset, the
quality problems found before cleaning, the state after cleaning, and the
fitness of the data for downstream use.

All figures come from `docs/profile_metrics.md` and
`data/profile/*.json`, both produced by `make seed`.

---

## 1. Summary

The raw input is structurally sound but semantically unreliable. It contains
no empty cells, no duplicate rows and no orphan foreign keys, and every
cross-table count is consistent. However, 12,190 dietary label values
conflict with the ingredient lists, quantities are free text in six units,
and 7,996 ingredient rows are duplicates. Without cleaning, allergen
exclusion, dietary filtering and shopping-list aggregation would return
systematically wrong results.

After cleaning, the eleven output tables have zero residual conflicts, zero
duplicate ingredient groups, zero unparseable quantities and no recipe above
the 1,200 g/serving cap.

---

## 2. Files and scale

| File | Rows | Columns | Role |
|---|---:|---:|---|
| `cuisine_metadata.csv` | 5 | 3 | Cuisine dimension |
| `recipes_master.csv` | 9,997 | 23 | Recipe master |
| `recipe_ingredients.csv` | 103,908 | 5 | Ingredient detail (set-valued attribute) |
| `recipe_nutrition.csv` | 9,997 | 13 | Nutrition detail |
| `recipe_steps.csv` | 84,616 | 4 | Preparation steps |

Total: 208,523 rows, 10,253,005 bytes (about 9.8 MB). SHA-256 values are in
`data/raw/MANIFEST.sha256` and are checked at the start of every rebuild.

### Structural checks

| Check | Result |
|---|---|
| Empty cells | 0 |
| Fully duplicated rows | 0 |
| Orphan `recipe_id` in the three detail tables | 0 / 0 / 0 |
| `cuisine_metadata.recipe_count` vs master table | 5 / 5 match, total 9,997 |
| `calories_per_serving` vs `nutrition.calories` | 9,997 / 9,997 match |
| `prep + cook = total_time` | 9,997 / 9,997 |
| Dates | 2023-02-16 to 2026-02-13, no future values or format errors |
| Rows with quote or newline hazards | 0 |

---

## 3. Field-level observations

The master table has 3,085 distinct recipe names across 9,997 recipes, five
cuisines, eleven categories and eight cooking methods. Numeric columns are
bounded and approximately uniform: rating 3.5–5.0, calories 150–799,
sodium 200–1499 mg, review count 10–4999, cost 2.0–25.0 USD.

The ingredient table contains 58 distinct names and 1,517 distinct quantity
strings. The step table contains only 20 distinct description templates of
at most 59 characters. These regularities, together with strictly sequential
identifiers and zero structural defects, indicate a programmatically
generated teaching dataset rather than a real-world corpus.

---

## 4. Six quality problems before cleaning

### 4.1 Dietary labels contradict the ingredient lists

Comparing the four `is_*` flags with the ingredient sets produced 12,190
conflicting label values across 7,952 recipes (79.5%).

| Flag | Conflicting recipes | Share | Source `True` | Derived `True` |
|---|---:|---:|---:|---:|
| `is_gluten_free` | 5,863 | 58.6% | 1,527 | 6,302 |
| `is_vegetarian` | 3,259 | 32.6% | 3,734 | 2,669 |
| `is_vegan` | 1,740 | 17.4% | 964 | 984 |
| `is_halal` | 1,328 | 13.3% | 8,669 | 9,997 |
| **Total** | **12,190** | — | — | — |

The first three flags are verifiable from the ingredient names and were
recomputed, correcting 10,862 label values. `is_halal` is not verifiable:
slaughter method and certification are absent from the data. Its source
values were retained and marked `is_halal_verifiable = false`.

### 4.2 Quantities are free text

1,517 distinct strings span six units (`g`, `ml`, `tbsp`, `tsp`, `cloves`,
`medium`) across three dimensions, plus 9,997 `to taste` placeholders.
Formatting is inconsistent (`933g` versus `299 g`).

### 4.3 Duplicate ingredients within a recipe

7,523 duplicate groups contribute 7,996 surplus rows. Some groups mix
units or mix a placeholder with a quantified row, so simple deletion or
numeric addition is not valid.

### 4.4 Extreme quantities

Estimated ingredient mass per serving reaches 1,937.5 g (P99 = 1,285.5 g).
143 recipes (1.4%) exceed the 1,200 g/serving cap.

### 4.5 Inconsistent names and categories

`Paneer` appears under both `Dairy` and `Proteins`. `All-Purpose Flour` and
`Wheat Flour` are synonyms. `Coriander` (seed) and `Fresh Coriander` (leaf)
are different ingredients and must not be merged.

### 4.6 Step durations are not a business metric

The sum of `estimated_time_minutes` equals `total_time_minutes` for only
51 of 9,997 recipes (mean absolute difference 68.4 minutes). Business
duration uses the verified identity `prep + cook = total`.

---

## 5. State after cleaning

| Metric | Before | After |
|---|---:|---:|
| Ingredient rows | 103,908 | 95,912 |
| Recipes | 9,997 | 9,997 |
| Empty cells | 0 | 0 |
| Dietary label conflicts | 12,190 | 0 |
| Recipes with a conflict | 7,952 | 0 |
| Duplicate ingredient groups | 7,523 | 0 |
| Surplus duplicate rows | 7,996 | 0 |
| `to taste` rows | 9,997 | 8,940 |
| Unparseable quantities | 0 | 0 |
| Recipes above 1,200 g/serving | 143 | 0 |
| Distinct ingredient names | 58 | 57 |
| Ingredients with category conflicts | 1 | 0 |
| Recipes with an allergen | — | 9,132 |

Eleven cleaned tables are written to `data/clean/`. The largest is
`ingredients.csv` with 95,912 rows and 22 columns.

---

## 6. Fitness for downstream use

| Capability | Status | Condition |
|---|---|---|
| Ingredient-set retrieval and overlap ranking | Ready | Use `canonical_id` and `ingredient_stats.idf` |
| Multi-predicate filtering | Ready | Use the cleaned `recipes` columns |
| Nutrition range filtering | Ready | Use `recipe_nutrition`; never derive nutrition from `qty_approx_g` |
| Allergen exclusion | Ready | Use `recipe_allergens.has_*` |
| Shopping-list and cost aggregation | Ready with caveat | `qty_approx_g` uses approximate densities |
| Full-text search | Ready | Use `recipe_search_document` |
| Dietary filtering | Ready with caveat | Rules are an explicit project convention, not a domain standard |
| Halal certification claims | Not supported | Field is unverifiable and retained as source data |

Synthetic scale tiers must be used only for index-scalability experiments,
never for accuracy, nutrition or comparison with published absolute results.

---

## 7. Suggested figures for the group report

| Reference | Content | Data source |
|---|---|---|
| Figure 3-1 | Pipeline and table flow | `docs/cleaning_rules.md` |
| Table 3-1 | Raw files and sizes | `docs/profile_metrics.md` section 1 |
| Figure 3-2 | Conflicts per dietary flag | `docs/profile_metrics.md` section 2.1 |
| Table 3-2 | Column dictionary excerpt | `docs/data_dictionary.md` |
| Table 3-3 | Before/after comparison | `data/profile/quality_summary.csv` |
| Figure 3-3 | Unit distribution | `docs/profile_metrics.md` section 2.2 |
| Figure 3-4 | Grams per serving and the 1,200 g cap | `data/profile/clipped_recipes.csv` |
| Table 3-4 | Three scale tiers | `docs/scale_datasets.md` |
| Table 3-5 | Verification results | `docs/verification_report.md` |

All figure and table captions should state the data source and the command
that reproduces it (`make seed`).
