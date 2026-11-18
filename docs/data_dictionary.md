# Data Dictionary - physical schema

> Generated from the live catalogue by `tools/gen_data_dictionary.py` - do not edit by hand.
> Regenerate with `python3 tools/gen_data_dictionary.py`; it fails if a column has no
> curated description, so the text below cannot silently drift from `sql/schema.sql`.
>
> This is the *physical* companion to `part_a/docs/data_dictionary.md`, which documents the
> *logical* side of each source column (domain, provenance, transform). Here the question is
> what PostgreSQL enforces (keys, nullability, CHECK) and how each column is reached (index).
> Cardinality and relationships: `docs/figures/er-diagram.png`. Design rationale:
> `docs/schema-design.md`.

Totals: **11 tables, 125 columns, 56 CHECK constraints, 10 foreign keys, 5 secondary indexes.**

## 1. Tables

| Table | Grain (one row per) | Rows at x1 | Cols | Primary key | Indexes |
|---|---|---:|---:|---|---|
| `cuisines` | cuisine | 5 | 4 | `cuisine` | - |
| `cuisine_category` | cuisine x category | 25 | 2 | `cuisine`, `category` | - |
| `recipes` | recipe | 9997 | 35 | `recipe_id` | `idx_recipes_cuisine_category_time`, `idx_recipes_veg_gf_time` |
| `ingredient_master` | canonical ingredient | 57 | 8 | `canonical_id` | `ingredient_master_canonical_name_key` |
| `ingredients` | recipe x ingredient line | 95912 | 22 | `recipe_id`, `ingredient_number` | `idx_ingredients_canonical` |
| `steps` | recipe x step | 84616 | 4 | `recipe_id`, `step_number` | - |
| `nutrition` | recipe (1:1) | 9997 | 13 | `recipe_id` | - |
| `recipe_allergens` | recipe (1:1) | 9997 | 13 | `recipe_id` | - |
| `recipe_dietary_audit` | recipe (1:1) | 9997 | 12 | `recipe_id` | - |
| `ingredient_stats` | canonical ingredient | 57 | 9 | `canonical_id` | - |
| `recipe_search_document` | recipe (1:1) | 9997 | 3 | `recipe_id` | `idx_search_document_fts` |

## 2. Columns

### 2.1 `cuisines` - one row per cuisine (5 rows)

| # | Column | Type | Null | Key | CHECK | Index | Description |
|---:|---|---|---|---|---|---|---|
| 1 | `cuisine` | text | **no** | PK |  |  | Cuisine code (5 values); primary key |
| 2 | `categories` | text | **no** |  |  |  | Display cache of `cuisine_category`; never filtered on (1NF fix below) |
| 3 | `recipe_count` | integer | **no** |  | `cuisines_recipe_count_check` |  | Recipes in this cuisine (derived count, not FK-enforced) |
| 4 | `category_count` | integer | **no** |  | `cuisines_category_count_check` |  | Distinct categories this cuisine has |

### 2.2 `cuisine_category` - one row per cuisine x category (25 rows)

| # | Column | Type | Null | Key | CHECK | Index | Description |
|---:|---|---|---|---|---|---|---|
| 1 | `cuisine` | text | **no** | PK, FK -> `cuisines` |  |  | FK -> `cuisines`; part of the composite key |
| 2 | `category` | text | **no** | PK |  |  | Category name; one row per (cuisine, category) pair |

### 2.3 `recipes` - one row per recipe (9997 rows)

| # | Column | Type | Null | Key | CHECK | Index | Description |
|---:|---|---|---|---|---|---|---|
| 1 | `recipe_id` | text | **no** | PK |  |  | Recipe identifier `RCPnnnnn`; stable business key |
| 2 | `recipe_name` | text | **no** |  |  |  | Display name; not unique (3,085 distinct values on 9,997 rows) |
| 3 | `cuisine` | text | **no** | FK -> `cuisines` |  | `idx_recipes_cuisine_category_time` | FK -> `cuisines`; leading column of the q2 composite index |
| 4 | `category` | text | **no** |  |  | `idx_recipes_cuisine_category_time` | Course / category of the dish (11 values) |
| 5 | `cooking_method` | text | **no** |  |  |  | Method (8 values); displayed, never filtered |
| 6 | `difficulty` | text | **no** |  | `recipes_difficulty_check` |  | `Easy` / `Medium` / `Hard` (CHECK) |
| 7 | `prep_time_minutes` | smallint | **no** |  | `recipes_prep_time_minutes_check`, `total_time_is_prep_plus_cook` |  | Preparation time in minutes |
| 8 | `cook_time_minutes` | smallint | **no** |  | `recipes_cook_time_minutes_check`, `total_time_is_prep_plus_cook` |  | Cooking time in minutes |
| 9 | `total_time_minutes` | smallint | **no** |  | `recipes_total_time_minutes_check`, `total_time_is_prep_plus_cook` | `idx_recipes_cuisine_category_time`, `idx_recipes_veg_gf_time` | `prep + cook` (CHECK-enforced); the range filter in q2 |
| 10 | `servings` | smallint | **no** |  | `recipes_servings_check` |  | Servings the recipe yields |
| 11 | `spice_level` | text | **no** |  | `recipes_spice_level_check` |  | `Mild` / `Medium` / `Hot` / `Very Hot` (CHECK) |
| 12 | `meal_type` | text | **no** |  |  |  | Source column with no constraint to category (noise; not used by the API) |
| 13 | `is_vegetarian` | boolean | **no** |  |  | `idx_recipes_veg_gf_time (predicate)` | **Recomputed** from the ingredient list; the flag q2 filters on |
| 14 | `is_vegan` | boolean | **no** |  |  |  | **Recomputed** from the ingredient list |
| 15 | `is_gluten_free` | boolean | **no** |  |  | `idx_recipes_veg_gf_time (predicate)` | **Recomputed**; half of the partial-index predicate |
| 16 | `is_halal` | boolean | **no** |  |  |  | Source flag kept as-is: halal cannot be derived from ingredient names |
| 17 | `is_vegetarian_raw` | boolean | **no** |  |  |  | Source-declared flag, kept for the audit (3,259 disagreements) |
| 18 | `is_vegan_raw` | boolean | **no** |  |  |  | Source-declared vegan flag (1,740 disagreements) |
| 19 | `is_gluten_free_raw` | boolean | **no** |  |  |  | Source-declared gluten-free flag (5,863 disagreements) |
| 20 | `is_halal_raw` | boolean | **no** |  |  |  | Source-declared halal flag |
| 21 | `is_halal_verifiable` | boolean | **no** |  |  |  | Always false - documents that `is_halal` is unverified |
| 22 | `dietary_conflict_count` | smallint | **no** |  | `recipes_dietary_conflict_count_check` |  | How many of the 3 dietary flags disagree with the raw value (0-3) |
| 23 | `rating` | numeric(2,1) | **no** |  | `recipes_rating_check` |  | 0.0-5.0 with one decimal (CHECK); primary sort key of q2 |
| 24 | `review_count` | integer | **no** |  | `recipes_review_count_check` |  | Popularity; second sort key of q2 |
| 25 | `calories_per_serving` | smallint | **no** |  | `recipes_calories_per_serving_check` | none - INCLUDE column of the composite index | kcal per serving; an INCLUDE column of the q2 index |
| 26 | `estimated_cost_usd` | numeric(6,2) | **no** |  | `recipes_estimated_cost_usd_check` |  | Estimated cost in USD; an INCLUDE column of the q2 index |
| 27 | `date_added` | date | **no** |  |  |  | Date the recipe entered the corpus (ISO-8601) |
| 28 | `is_traditional` | boolean | **no** |  |  |  | Traditional-dish flag |
| 29 | `is_festival_special` | boolean | **no** |  |  |  | Festival-special flag |
| 30 | `ingredient_count` | smallint | **no** |  | `recipes_ingredient_count_check` |  | denormalised: COUNT over `ingredients`; denominator of q1's tie-break |
| 31 | `step_count` | smallint | **no** |  | `recipes_step_count_check` |  | denormalised: COUNT over `steps` |
| 32 | `allergen_count` | smallint | **no** |  | `recipes_allergen_count_check` |  | denormalised: number of true `has_*` flags in `recipe_allergens` |
| 33 | `estimated_total_g` | numeric(10,2) | yes |  | `recipes_estimated_total_g_check` |  | denormalised: estimated total weight in grams |
| 34 | `estimated_g_per_serving` | numeric(10,2) | yes |  | `recipes_estimated_g_per_serving_check` |  | denormalised: estimated weight per serving |
| 35 | `qty_clipped_recipe` | boolean | **no** |  |  |  | True when any quantity in the recipe was clipped while parsing |

### 2.4 `ingredient_master` - one row per canonical ingredient (57 rows)

| # | Column | Type | Null | Key | CHECK | Index | Description |
|---:|---|---|---|---|---|---|---|
| 1 | `canonical_id` | text | **no** | PK |  |  | Canonical key (57 values); the **only** join key for ingredients |
| 2 | `canonical_name` | text | **no** | UNIQUE |  | `ingredient_master_canonical_name_key` | Display name, UNIQUE; never used as a join key |
| 3 | `category` | text | **no** |  |  |  | Ingredient category (8 values; `Paneer` unified across two source spellings) |
| 4 | `allergens` | text | **no** |  |  |  | `\|`-separated allergen classes, or `none` |
| 5 | `is_animal` | boolean | **no** |  |  |  | Animal-derived? Used to recompute `is_vegan` |
| 6 | `is_meat_fish` | boolean | **no** |  |  |  | Meat or fish? Used to recompute `is_vegetarian` |
| 7 | `is_gluten_source` | boolean | **no** |  |  |  | Wheat / barley / ... ? Used to recompute `is_gluten_free` |
| 8 | `note` | text | yes |  |  |  | Free-text mapping note (nullable) |

### 2.5 `ingredients` - one row per recipe x ingredient line (95912 rows)

| # | Column | Type | Null | Key | CHECK | Index | Description |
|---:|---|---|---|---|---|---|---|
| 1 | `recipe_id` | text | **no** | PK, FK -> `recipes` |  | none - leading column of the primary key | FK -> `recipes`; leading column of the composite primary key |
| 2 | `ingredient_number` | smallint | **no** | PK | `ingredients_ingredient_number_check` |  | Ordinal within the recipe; contiguous from 1 |
| 3 | `canonical_id` | text | **no** | FK -> `ingredient_master` |  | `idx_ingredients_canonical` | FK -> `ingredient_master`; **the q1 filter column** (indexed) |
| 4 | `canonical_name` | text | **no** |  |  |  | denormalised: display only, never joined on |
| 5 | `ingredient_name_raw` | text | **no** |  |  |  | Line as written in the source (audit only) |
| 6 | `category` | text | **no** |  |  |  | Ingredient category at line level |
| 7 | `quantity_raw` | text | **no** |  |  |  | Quantity as written (`1 medium`, `to taste`) |
| 8 | `qty_value` | numeric(12,4) | yes |  | `ingredients_qty_value_check`, `placeholder_has_no_value` |  | Parsed numeric value; NULL exactly when `qty_is_placeholder` |
| 9 | `qty_unit_raw` | text | yes |  |  |  | Unit as written |
| 10 | `qty_unit_norm` | text | yes |  |  |  | Unit after normalisation |
| 11 | `qty_dimension` | text | **no** |  | `ingredients_qty_dimension_check`, `placeholder_dimension_is_na` |  | `mass` / `volume` / `count` / `na` - `na` exactly for placeholders (CHECK) |
| 12 | `qty_canonical_value` | numeric(12,4) | yes |  | `ingredients_qty_canonical_value_check` |  | Value converted to the canonical unit of its dimension |
| 13 | `qty_canonical_unit` | text | yes |  |  |  | Canonical unit for that dimension |
| 14 | `qty_approx_g` | numeric(12,4) | yes |  | `ingredients_qty_approx_g_check` |  | Estimated weight in grams; the basis of the nutrition estimate |
| 15 | `qty_is_placeholder` | boolean | **no** |  | `placeholder_dimension_is_na`, `placeholder_has_code`, `placeholder_has_no_value` |  | True for `to taste` / `a pinch` (8,940 lines); **never render as 0** |
| 16 | `qty_placeholder_code` | text | yes |  | `placeholder_has_code` |  | Placeholder code, present iff `qty_is_placeholder` (CHECK) |
| 17 | `qty_parse_status` | text | **no** |  | `ingredients_qty_parse_status_check` |  | `OK` / `PLACEHOLDER` (CHECK) |
| 18 | `merged_row_count` | smallint | **no** |  | `ingredients_merged_row_count_check` |  | Source rows merged into this line; `SUM` = 103,908 raw rows |
| 19 | `merged_units` | text | yes |  |  |  | Units merged when the source repeated the ingredient |
| 20 | `qty_clipped` | boolean | **no** |  |  |  | True when the value was clipped to a sane range |
| 21 | `allergen_flags` | text | yes |  |  |  | `\|`-separated allergen classes implied by this line |
| 22 | `match_status` | text | yes |  | `ingredients_match_status_check` |  | `exact` / `merge` / `exact\|merge` - how the name was mapped |

### 2.6 `steps` - one row per recipe x step (84616 rows)

| # | Column | Type | Null | Key | CHECK | Index | Description |
|---:|---|---|---|---|---|---|---|
| 1 | `recipe_id` | text | **no** | PK, FK -> `recipes` |  |  | FK -> `recipes`; part of the composite key |
| 2 | `step_number` | smallint | **no** | PK | `steps_step_number_check` |  | Ordinal within the recipe; contiguous from 1 |
| 3 | `step_description` | text | **no** |  |  |  | One of 20 template sentences (low signal; part of the q3 document) |
| 4 | `estimated_time_minutes` | smallint | yes |  | `steps_estimated_time_minutes_check` |  | **Not a duration metric** (template-derived); use `recipes.total_time_minutes` |

### 2.7 `nutrition` - one row per recipe (1:1) (9997 rows)

| # | Column | Type | Null | Key | CHECK | Index | Description |
|---:|---|---|---|---|---|---|---|
| 1 | `recipe_id` | text | **no** | PK, FK -> `recipes` |  |  | PK **and** FK -> `recipes` (1:1) |
| 2 | `calories` | integer | **no** |  | `nutrition_calories_check` | none - reached by 1:1 primary-key join | Energy in kcal; consistent with `recipes.calories_per_serving` |
| 3 | `protein_g` | numeric(8,2) | **no** |  | `nutrition_protein_g_check` |  | Protein, grams |
| 4 | `carbohydrates_g` | numeric(8,2) | **no** |  | `nutrition_carbohydrates_g_check` |  | Carbohydrates, grams |
| 5 | `fat_g` | numeric(8,2) | **no** |  | `nutrition_fat_g_check` |  | Fat, grams |
| 6 | `fiber_g` | numeric(8,2) | **no** |  | `nutrition_fiber_g_check` |  | Fibre, grams |
| 7 | `sugar_g` | numeric(8,2) | **no** |  | `nutrition_sugar_g_check` |  | Sugar, grams |
| 8 | `sodium_mg` | numeric(8,2) | **no** |  | `nutrition_sodium_mg_check` |  | Sodium, milligrams |
| 9 | `cholesterol_mg` | numeric(8,2) | **no** |  | `nutrition_cholesterol_mg_check` |  | Cholesterol, milligrams |
| 10 | `vitamin_a_percent` | numeric(6,2) | **no** |  | `nutrition_vitamin_a_percent_check` |  | % of daily value |
| 11 | `vitamin_c_percent` | numeric(6,2) | **no** |  | `nutrition_vitamin_c_percent_check` |  | % of daily value |
| 12 | `calcium_percent` | numeric(6,2) | **no** |  | `nutrition_calcium_percent_check` |  | % of daily value |
| 13 | `iron_percent` | numeric(6,2) | **no** |  | `nutrition_iron_percent_check` |  | % of daily value |

### 2.8 `recipe_allergens` - one row per recipe (1:1) (9997 rows)

| # | Column | Type | Null | Key | CHECK | Index | Description |
|---:|---|---|---|---|---|---|---|
| 1 | `recipe_id` | text | **no** | PK, FK -> `recipes` |  | none - reached by 1:1 primary-key join | PK **and** FK -> `recipes` (1:1) |
| 2 | `allergens` | text | **no** |  |  |  | denormalised: `\|`-separated display list |
| 3 | `allergen_count` | smallint | **no** |  | `allergen_count_matches_flags`, `recipe_allergens_allergen_count_check` |  | Must equal the sum of the ten flags (CHECK) |
| 4 | `has_gluten` | boolean | **no** |  | `allergen_count_matches_flags` |  | Per-class flag; q2 excludes via `NOT EXISTS` over these |
| 5 | `has_milk` | boolean | **no** |  | `allergen_count_matches_flags` |  | Per-class flag (see `has_gluten`) |
| 6 | `has_egg` | boolean | **no** |  | `allergen_count_matches_flags` |  | Per-class flag (see `has_gluten`) |
| 7 | `has_fish` | boolean | **no** |  | `allergen_count_matches_flags` |  | Per-class flag (see `has_gluten`) |
| 8 | `has_shellfish` | boolean | **no** |  | `allergen_count_matches_flags` |  | Per-class flag (see `has_gluten`) |
| 9 | `has_tree_nuts` | boolean | **no** |  | `allergen_count_matches_flags` |  | Per-class flag (see `has_gluten`) |
| 10 | `has_sesame` | boolean | **no** |  | `allergen_count_matches_flags` |  | Per-class flag (see `has_gluten`) |
| 11 | `has_soy` | boolean | **no** |  | `allergen_count_matches_flags` |  | Per-class flag (see `has_gluten`) |
| 12 | `has_mustard` | boolean | **no** |  | `allergen_count_matches_flags` |  | Per-class flag (see `has_gluten`) |
| 13 | `has_peanut` | boolean | **no** |  | `allergen_count_matches_flags` |  | Per-class flag (see `has_gluten`) |

### 2.9 `recipe_dietary_audit` - one row per recipe (1:1) (9997 rows)

| # | Column | Type | Null | Key | CHECK | Index | Description |
|---:|---|---|---|---|---|---|---|
| 1 | `recipe_id` | text | **no** | PK, FK -> `recipes` |  |  | PK **and** FK -> `recipes` (1:1) |
| 2 | `is_vegetarian_raw` | boolean | **no** |  |  |  | Source-declared vegetarian flag |
| 3 | `is_vegetarian_calc` | boolean | **no** |  |  |  | Recomputed from the ingredient list |
| 4 | `is_vegan_raw` | boolean | **no** |  |  |  | Source-declared vegan flag |
| 5 | `is_vegan_calc` | boolean | **no** |  |  |  | Recomputed from the ingredient list |
| 6 | `is_gluten_free_raw` | boolean | **no** |  |  |  | Source-declared gluten-free flag |
| 7 | `is_gluten_free_calc` | boolean | **no** |  |  |  | Recomputed from the ingredient list |
| 8 | `is_halal_raw` | boolean | **no** |  |  |  | Source-declared halal flag |
| 9 | `halal_proxy` | boolean | **no** |  |  |  | Conservative heuristic (no pork / alcohol); a hint, not a fact |
| 10 | `halal_proxy_conflict` | boolean | **no** |  |  |  | True when the proxy disagrees with the source flag |
| 11 | `conflict_count` | smallint | **no** |  | `recipe_dietary_audit_conflict_count_check` |  | How many of the three dietary flags disagree (0-3, CHECK) |
| 12 | `conflict_flags` | text | yes |  |  |  | Name of each conflicting flag; **NULL** when there is none |

### 2.10 `ingredient_stats` - one row per canonical ingredient (57 rows)

| # | Column | Type | Null | Key | CHECK | Index | Description |
|---:|---|---|---|---|---|---|---|
| 1 | `canonical_id` | text | **no** | PK, FK -> `ingredient_master` |  |  | PK **and** FK -> `ingredient_master` |
| 2 | `canonical_name` | text | **no** |  |  |  | Display copy |
| 3 | `doc_freq` | integer | **no** |  | `doc_freq_within_total`, `ingredient_stats_doc_freq_check` |  | Recipes containing this ingredient (`<= total_recipes`, CHECK) |
| 4 | `total_recipes` | integer | **no** |  | `doc_freq_within_total`, `ingredient_stats_total_recipes_check` |  | Recipes in the tier these statistics were computed on |
| 5 | `idf` | numeric(10,6) | **no** |  | `ingredient_stats_idf_check` |  | `ln((N+1)/(df+1))+1`, `>= 1`; **the weight q1 ranks by** |
| 6 | `idf_norm` | numeric(10,6) | yes |  | `ingredient_stats_idf_norm_check` |  | `idf` rescaled to [0, 1] for display |
| 7 | `rarity_rank` | integer | yes |  | `ingredient_stats_rarity_rank_check` |  | 1 = rarest ingredient |
| 8 | `avg_approx_g` | numeric(10,2) | yes |  | `ingredient_stats_avg_approx_g_check` |  | Mean grams per use (only over lines with a real quantity) |
| 9 | `share_pct` | numeric(6,3) | yes |  | `ingredient_stats_share_pct_check` |  | Percentage of recipes containing it |

### 2.11 `recipe_search_document` - one row per recipe (1:1) (9997 rows)

| # | Column | Type | Null | Key | CHECK | Index | Description |
|---:|---|---|---|---|---|---|---|
| 1 | `recipe_id` | text | **no** | PK, FK -> `recipes` |  |  | PK **and** FK -> `recipes` (1:1) |
| 2 | `search_document` | text | **no** |  |  | `idx_search_document_fts (expr)` | name + cuisine + category + method + ingredients + steps; GIN-indexed |
| 3 | `doc_length` | integer | **no** |  | `recipe_search_document_doc_length_check` |  | Token count, kept for a future BM25-style normalisation |

## 3. Foreign keys

All 10 are declared `DEFERRABLE INITIALLY DEFERRED`, so the bulk loader may insert
parent and child rows in one transaction and has them validated at `COMMIT`.

| # | Child | Parent | Constraint |
|---:|---|---|---|
| 1 | `cuisine_category` | `cuisines` | `FOREIGN KEY (cuisine) REFERENCES cuisines(cuisine) DEFERRABLE INITIALLY DEFERRED` |
| 2 | `ingredient_stats` | `ingredient_master` | `FOREIGN KEY (canonical_id) REFERENCES ingredient_master(canonical_id) DEFERRABLE INITIALLY DEFERRED` |
| 3 | `ingredients` | `ingredient_master` | `FOREIGN KEY (canonical_id) REFERENCES ingredient_master(canonical_id) DEFERRABLE INITIALLY DEFERRED` |
| 4 | `ingredients` | `recipes` | `FOREIGN KEY (recipe_id) REFERENCES recipes(recipe_id) DEFERRABLE INITIALLY DEFERRED` |
| 5 | `nutrition` | `recipes` | `FOREIGN KEY (recipe_id) REFERENCES recipes(recipe_id) DEFERRABLE INITIALLY DEFERRED` |
| 6 | `recipe_allergens` | `recipes` | `FOREIGN KEY (recipe_id) REFERENCES recipes(recipe_id) DEFERRABLE INITIALLY DEFERRED` |
| 7 | `recipe_dietary_audit` | `recipes` | `FOREIGN KEY (recipe_id) REFERENCES recipes(recipe_id) DEFERRABLE INITIALLY DEFERRED` |
| 8 | `recipe_search_document` | `recipes` | `FOREIGN KEY (recipe_id) REFERENCES recipes(recipe_id) DEFERRABLE INITIALLY DEFERRED` |
| 9 | `recipes` | `cuisines` | `FOREIGN KEY (cuisine) REFERENCES cuisines(cuisine) DEFERRABLE INITIALLY DEFERRED` |
| 10 | `steps` | `recipes` | `FOREIGN KEY (recipe_id) REFERENCES recipes(recipe_id) DEFERRABLE INITIALLY DEFERRED` |

## 4. CHECK constraints

Constraint names are stable and are quoted verbatim from `pg_constraint`, so a reader
can grep the error message they saw in PostgreSQL back to this table.

**`cuisines`** (2)

| Constraint | Definition |
|---|---|
| `cuisines_category_count_check` | `CHECK ((category_count >= 0))` |
| `cuisines_recipe_count_check` | `CHECK ((recipe_count >= 0))` |

**`recipes`** (17)

| Constraint | Definition |
|---|---|
| `recipes_allergen_count_check` | `CHECK ((allergen_count >= 0))` |
| `recipes_calories_per_serving_check` | `CHECK ((calories_per_serving >= 0))` |
| `recipes_cook_time_minutes_check` | `CHECK ((cook_time_minutes >= 0))` |
| `recipes_dietary_conflict_count_check` | `CHECK (((dietary_conflict_count >= 0) AND (dietary_conflict_count <= 3)))` |
| `recipes_difficulty_check` | `CHECK ((difficulty = ANY (ARRAY['Easy'::text, 'Medium'::text, 'Hard'::text])))` |
| `recipes_estimated_cost_usd_check` | `CHECK ((estimated_cost_usd >= (0)::numeric))` |
| `recipes_estimated_g_per_serving_check` | `CHECK ((estimated_g_per_serving >= (0)::numeric))` |
| `recipes_estimated_total_g_check` | `CHECK ((estimated_total_g >= (0)::numeric))` |
| `recipes_ingredient_count_check` | `CHECK ((ingredient_count > 0))` |
| `recipes_prep_time_minutes_check` | `CHECK ((prep_time_minutes >= 0))` |
| `recipes_rating_check` | `CHECK (((rating >= (0)::numeric) AND (rating <= (5)::numeric)))` |
| `recipes_review_count_check` | `CHECK ((review_count >= 0))` |
| `recipes_servings_check` | `CHECK ((servings > 0))` |
| `recipes_spice_level_check` | `CHECK ((spice_level = ANY (ARRAY['Mild'::text, 'Medium'::text, 'Hot'::text, 'Very Hot'::text])))` |
| `recipes_step_count_check` | `CHECK ((step_count > 0))` |
| `recipes_total_time_minutes_check` | `CHECK ((total_time_minutes > 0))` |
| `total_time_is_prep_plus_cook` | `CHECK ((total_time_minutes = (prep_time_minutes + cook_time_minutes)))` |

**`ingredients`** (11)

| Constraint | Definition |
|---|---|
| `ingredients_ingredient_number_check` | `CHECK ((ingredient_number > 0))` |
| `ingredients_match_status_check` | `CHECK ((match_status = ANY (ARRAY['exact'::text, 'merge'::text, 'exact\|merge'::text])))` |
| `ingredients_merged_row_count_check` | `CHECK ((merged_row_count >= 1))` |
| `ingredients_qty_approx_g_check` | `CHECK ((qty_approx_g >= (0)::numeric))` |
| `ingredients_qty_canonical_value_check` | `CHECK ((qty_canonical_value >= (0)::numeric))` |
| `ingredients_qty_dimension_check` | `CHECK ((qty_dimension = ANY (ARRAY['mass'::text, 'volume'::text, 'count'::text, 'na'::text])))` |
| `ingredients_qty_parse_status_check` | `CHECK ((qty_parse_status = ANY (ARRAY['OK'::text, 'PLACEHOLDER'::text])))` |
| `ingredients_qty_value_check` | `CHECK ((qty_value >= (0)::numeric))` |
| `placeholder_dimension_is_na` | `CHECK (((qty_dimension = 'na'::text) = qty_is_placeholder))` |
| `placeholder_has_code` | `CHECK (((NOT qty_is_placeholder) OR (qty_placeholder_code IS NOT NULL)))` |
| `placeholder_has_no_value` | `CHECK ((qty_is_placeholder = (qty_value IS NULL)))` |

**`steps`** (2)

| Constraint | Definition |
|---|---|
| `steps_estimated_time_minutes_check` | `CHECK ((estimated_time_minutes >= 0))` |
| `steps_step_number_check` | `CHECK ((step_number > 0))` |

**`nutrition`** (12)

| Constraint | Definition |
|---|---|
| `nutrition_calcium_percent_check` | `CHECK ((calcium_percent >= (0)::numeric))` |
| `nutrition_calories_check` | `CHECK ((calories >= 0))` |
| `nutrition_carbohydrates_g_check` | `CHECK ((carbohydrates_g >= (0)::numeric))` |
| `nutrition_cholesterol_mg_check` | `CHECK ((cholesterol_mg >= (0)::numeric))` |
| `nutrition_fat_g_check` | `CHECK ((fat_g >= (0)::numeric))` |
| `nutrition_fiber_g_check` | `CHECK ((fiber_g >= (0)::numeric))` |
| `nutrition_iron_percent_check` | `CHECK ((iron_percent >= (0)::numeric))` |
| `nutrition_protein_g_check` | `CHECK ((protein_g >= (0)::numeric))` |
| `nutrition_sodium_mg_check` | `CHECK ((sodium_mg >= (0)::numeric))` |
| `nutrition_sugar_g_check` | `CHECK ((sugar_g >= (0)::numeric))` |
| `nutrition_vitamin_a_percent_check` | `CHECK ((vitamin_a_percent >= (0)::numeric))` |
| `nutrition_vitamin_c_percent_check` | `CHECK ((vitamin_c_percent >= (0)::numeric))` |

**`recipe_allergens`** (2)

| Constraint | Definition |
|---|---|
| `allergen_count_matches_flags` | `CHECK ((allergen_count = ((((((((((has_gluten)::integer + (has_milk)::integer) + (has_egg)::integer) + (has_fish)::integer) + (has_shellfish)::integer) + (has_tree_nuts)::integer) + (has_sesame)::integer) + (has_soy)::integer) + (has_mustard)::integer) + (has_peanut)::integer)))` |
| `recipe_allergens_allergen_count_check` | `CHECK (((allergen_count >= 0) AND (allergen_count <= 10)))` |

**`recipe_dietary_audit`** (1)

| Constraint | Definition |
|---|---|
| `recipe_dietary_audit_conflict_count_check` | `CHECK (((conflict_count >= 0) AND (conflict_count <= 3)))` |

**`ingredient_stats`** (8)

| Constraint | Definition |
|---|---|
| `doc_freq_within_total` | `CHECK ((doc_freq <= total_recipes))` |
| `ingredient_stats_avg_approx_g_check` | `CHECK ((avg_approx_g >= (0)::numeric))` |
| `ingredient_stats_doc_freq_check` | `CHECK ((doc_freq >= 1))` |
| `ingredient_stats_idf_check` | `CHECK ((idf >= (1)::numeric))` |
| `ingredient_stats_idf_norm_check` | `CHECK (((idf_norm >= (0)::numeric) AND (idf_norm <= (1)::numeric)))` |
| `ingredient_stats_rarity_rank_check` | `CHECK ((rarity_rank >= 1))` |
| `ingredient_stats_share_pct_check` | `CHECK (((share_pct >= (0)::numeric) AND (share_pct <= (100)::numeric)))` |
| `ingredient_stats_total_recipes_check` | `CHECK ((total_recipes >= 1))` |

**`recipe_search_document`** (1)

| Constraint | Definition |
|---|---|
| `recipe_search_document_doc_length_check` | `CHECK ((doc_length > 0))` |

## 5. Secondary indexes

Primary keys already index their key columns; these four (plus one UNIQUE) exist for
the three API queries. Measured effect, and the counterfactual without them:
`docs/scale_experiment.md` and `docs/figures/timings.png`.

| Index | Table | Definition | Serves |
|---|---|---|---|
| `ingredient_master_canonical_name_key` | `ingredient_master` | `CREATE UNIQUE INDEX ingredient_master_canonical_name_key ON public.ingredient_master USING btree (canonical_name)` | UNIQUE guard: proves `canonical_name` is a 1:1 alias of `canonical_id` |
| `idx_ingredients_canonical` | `ingredients` | `CREATE INDEX idx_ingredients_canonical ON public.ingredients USING btree (canonical_id) INCLUDE (recipe_id)` | q1 - the ingredient -> recipe lookup, `INCLUDE (recipe_id)` so the join never touches the heap |
| `idx_search_document_fts` | `recipe_search_document` | `CREATE INDEX idx_search_document_fts ON public.recipe_search_document USING gin (to_tsvector('english'::regconfig, search_document))` | q3 - GIN over `to_tsvector('english', search_document)` |
| `idx_recipes_cuisine_category_time` | `recipes` | `CREATE INDEX idx_recipes_cuisine_category_time ON public.recipes USING btree (cuisine, category, total_time_minutes) INCLUDE (calories_per_serving, estimated_cost_usd, rating)` | q2 - `cuisine = ? AND category = ?` plus the time range and the `ORDER BY` |
| `idx_recipes_veg_gf_time` | `recipes` | `CREATE INDEX idx_recipes_veg_gf_time ON public.recipes USING btree (total_time_minutes) WHERE (is_vegetarian AND is_gluten_free)` | q2 - partial index on the vegetarian + gluten-free subset, smaller and hotter than the full tree |

## 6. Reading rules (consequences of the model)

- **Join ingredients on `canonical_id`**, never on `canonical_name`. The raw names contain
  synonyms and duplicates; `canonical_id` is the key that survives cleaning, and it is the
  only indexed path into `ingredients`.
- **Never filter on `cuisines.categories`.** It is a denormalised display string; the 1NF
  home of that fact is `cuisine_category`, which has one row per (cuisine, category).
- **`steps.estimated_time_minutes` is not a duration.** It comes from one of 20 templates;
  use `recipes.total_time_minutes` for any time filter or ranking.
- **`is_vegetarian` / `is_vegan` / `is_gluten_free` are recomputed; the `*_raw` columns keep
  what the source claimed.** Show the recomputed value, and keep `dietary_conflict_count`
  for the audit rather than overwriting history. `is_halal` stays a source flag because
  halal cannot be decided from an ingredient list - hence `is_halal_verifiable = false`.
- **A `qty_is_placeholder` line has no number**: `qty_value` and `qty_approx_g` are `NULL`
  by CHECK, and the UI must render `to taste`, never `0`. `qty_dimension = 'na'` is the
  machine-readable marker.
- **Display allergens from `recipe_allergens.allergens`, filter on the `has_*` flags.**
  Splitting a `|`-string at query time defeats every index and the CHECK that keeps
  `allergen_count` equal to the sum of the flags.
- **The denormalised counters on `recipes` (`ingredient_count`, `step_count`,
  `allergen_count`, `estimated_*_g`) are refreshed by the ETL, not by the API.** They are
  verified against their base tables in `docs/evidence/derivation_equivalence.txt`.
- **`ingredient_stats` is per tier.** It embeds `total_recipes`, so it has to be rebuilt
  when a tier grows (the x20 rebuild at 1.89M ingredient rows is timed in
  `docs/scale_experiment.md` section 3).

## 7. Regenerating

```bash
python3 tools/gen_data_dictionary.py           # rewrite docs/data_dictionary.md
python3 tools/gen_data_dictionary.py --check   # validate the curated text only
```

Needs `psql` (PostgreSQL 14+) and the database built per `docs/load_verification.md`
section 2. Standard library only; no third-party packages.

