"""Generate the column dictionary for raw and cleaned tables."""
from __future__ import annotations

from pathlib import Path

from . import config as C
from . import io_utils as U

COLUMNS = ["table", "column", "ordinal", "logical_type", "key_role", "nullable",
           "domain_or_range", "description", "source_or_transform"]

T = "text"; I = "integer"; D = "decimal"; B = "boolean"; DT = "date"


def _f(col, typ, role, nullable, domain, desc, src):
    return (col, typ, role, nullable, domain, desc, src)


RAW_SPEC: dict[str, list[tuple]] = {
    "cuisine_metadata.csv": [
        _f("cuisine", T, "PK", "no", "Pakistani / Indian / Bangladeshi / Afghan / Fusion", "Cuisine code", "Raw"),
        _f("categories", T, "", "no", "Comma-separated category list", "Categories in this cuisine (denormalised; split before use)", "Raw"),
        _f("recipe_count", I, "", "no", "999 ~ 3498", "Recipe count for this cuisine (matches the master table)", "Raw"),
    ],
    "recipes_master.csv": [
        _f("recipe_id", T, "PK", "no", "RCP00001 ~ RCP09997", "Recipe primary key", "Raw"),
        _f("recipe_name", T, "", "no", "1 ~ 35 characters", "Recipe name (not unique, 3085 distinct values)", "Raw"),
        _f("cuisine", T, "FK->cuisine_metadata.cuisine", "no", "5 values", "Cuisine", "Raw"),
        _f("category", T, "", "no", "11 values", "Category (Main Course / Desserts / ...)", "Raw"),
        _f("cooking_method", T, "", "no", "8 values", "Cooking method", "Raw"),
        _f("difficulty", T, "", "no", "Easy / Medium / Hard", "Difficulty", "Raw"),
        _f("prep_time_minutes", I, "", "no", "10 ~ 59", "Preparation time (minutes)", "Raw"),
        _f("cook_time_minutes", I, "", "no", "15 ~ 179", "Cooking time (minutes)", "Raw"),
        _f("total_time_minutes", I, "", "no", "26 ~ 237; = prep + cook", "Total time (minutes)", "Raw; consistency check 9997/9997 PASS"),
        _f("servings", I, "", "no", "2 ~ 7", "Servings", "Raw"),
        _f("spice_level", T, "", "no", "Mild / Medium / Hot / Very Hot", "Spice level", "Raw"),
        _f("meal_type", T, "", "no", "6 values", "Meal type (unconstrained by category; noise column)", "Raw"),
        _f("is_vegetarian", B, "", "no", "True / False", "Source vegetarian flag (3259 conflicts with ingredients)", "Raw; kept in *_raw after cleaning"),
        _f("is_vegan", B, "", "no", "True / False", "Source vegan flag (1740 conflicts)", "Raw; kept in *_raw after cleaning"),
        _f("is_gluten_free", B, "", "no", "True / False", "Source gluten-free flag (5863 conflicts)", "Raw; kept in *_raw after cleaning"),
        _f("is_halal", B, "", "no", "True / False", "Source halal flag (cannot be verified from ingredient names)", "Raw; retained after cleaning and marked is_halal_verifiable=false"),
        _f("rating", D, "", "no", "3.5 ~ 5.0", "Rating", "Raw"),
        _f("review_count", I, "", "no", "10 ~ 4999", "Review count", "Raw"),
        _f("calories_per_serving", I, "", "no", "150 ~ 799", "Calories per serving (kcal)", "Raw; fully consistent with nutrition.calories"),
        _f("estimated_cost_usd", D, "", "no", "2.0 ~ 25.0", "Estimated cost (USD)", "Raw"),
        _f("date_added", DT, "", "no", "2023-02-16 ~ 2026-02-13", "Date added, ISO-8601", "Raw"),
        _f("is_traditional", B, "", "no", "True / False", "Traditional dish flag", "Raw"),
        _f("is_festival_special", B, "", "no", "True / False", "Festival special flag", "Raw"),
    ],
    "recipe_ingredients.csv": [
        _f("recipe_id", T, "PK(part),FK->recipes_master", "no", "RCP*", "Recipe primary key", "Raw"),
        _f("ingredient_number", I, "PK(part)", "no", "1 ~ 19; contiguous per recipe", "Ingredient ordinal", "Raw; renumbered after cleaning"),
        _f("ingredient_name", T, "", "no", "58 values", "Ingredient name (contains synonyms and duplicates)", "Raw; becomes canonical_name after cleaning"),
        _f("quantity", T, "", "no", "1517 distinct strings", "Raw quantity text (e.g. '1 medium', '933g', 'to taste')", "Raw; becomes structured qty_* columns after cleaning"),
        _f("category", T, "", "no", "8 values", "Ingredient category (Paneer appears as both Dairy and Proteins)", "Raw; unified via the lookup table after cleaning"),
    ],
    "recipe_nutrition.csv": [
        _f("recipe_id", T, "PK,FK->recipes_master", "no", "RCP*", "Recipe primary key", "Raw"),
        _f("calories", I, "", "no", "150 ~ 799", "Energy (kcal)", "Raw"),
        _f("protein_g", I, "", "no", "5 ~ 49", "Protein (g)", "Raw"),
        _f("carbohydrates_g", I, "", "no", "30 ~ 79", "Carbohydrate (g)", "Raw"),
        _f("fat_g", I, "", "no", "10 ~ 39", "Fat (g)", "Raw"),
        _f("fiber_g", I, "", "no", "2 ~ 14", "Fibre (g)", "Raw"),
        _f("sugar_g", I, "", "no", "2 ~ 19", "Sugar (g)", "Raw"),
        _f("sodium_mg", I, "", "no", "200 ~ 1499", "Sodium (mg)", "Raw"),
        _f("cholesterol_mg", I, "", "no", "0 ~ 99", "Cholesterol (mg)", "Raw"),
        _f("vitamin_a_percent", I, "", "no", "5 ~ 39", "Vitamin A (% daily value)", "Raw"),
        _f("vitamin_c_percent", I, "", "no", "5 ~ 59", "Vitamin C (% daily value)", "Raw"),
        _f("calcium_percent", I, "", "no", "5 ~ 29", "Calcium (% daily value)", "Raw"),
        _f("iron_percent", I, "", "no", "10 ~ 39", "Iron (% daily value)", "Raw"),
    ],
    "recipe_steps.csv": [
        _f("recipe_id", T, "PK(part),FK->recipes_master", "no", "RCP*", "Recipe primary key", "Raw"),
        _f("step_number", I, "PK(part)", "no", "1 ~ 11", "Step ordinal", "Raw"),
        _f("step_description", T, "", "no", "20 template strings, at most 59 characters", "Step description (template text; synthetic-data signature)", "Raw; used to assemble the full-text document"),
        _f("estimated_time_minutes", I, "", "no", "2 ~ 14", "Step duration (sum does not equal total_time; not a business metric)", "Raw"),
    ],
}

CLEAN_RECIPES_EXTRA = [
    _f("is_vegetarian/is_vegan/is_gluten_free", B, "", "no", "true / false", "Verifiable dietary flags recomputed from the ingredient set", "clean.py step 4; see dietary_rules.csv"),
    _f("is_halal", B, "", "no", "true / false", "Source label retained (cannot be verified from ingredient names)", "Passed through unchanged + is_halal_verifiable=false"),
    _f("is_*_raw", B, "", "no", "true / false", "Four raw source flags kept for audit and rollback", "Kept verbatim"),
    _f("is_halal_verifiable", B, "", "no", "false", "Explicitly marks this flag as unverifiable", "Constant"),
    _f("dietary_conflict_count", I, "", "no", "0 ~ 3", "Number of conflicts among the three verifiable flags", "recipe_dietary_audit.conflict_count"),
    _f("ingredient_count / step_count / allergen_count", I, "", "no", ">= 0", "Derived counts; avoids runtime JOIN aggregation", "Derived in clean.py"),
    _f("estimated_total_g / estimated_g_per_serving", D, "", "no", "<= 1200 g/serving", "Estimated total ingredient mass after clipping", "units.py + clipping policy"),
    _f("qty_clipped_recipe", B, "", "no", "true / false", "Whether this recipe was clipped", "clean.py step 3"),
]

CLEAN_INGREDIENT_EXTRA = [
    _f("canonical_id", T, "FK->ingredient_master", "no", "ING_*", "Canonical ingredient id (the only downstream key)", "ingredient_synonyms.csv"),
    _f("canonical_name", T, "", "no", "Canonical ingredient name", "Ingredient name after synonym merging", "ingredient_synonyms.csv"),
    _f("ingredient_name_raw", T, "", "no", "Raw names (joined with | when merged)", "Raw name kept for audit", "Kept verbatim"),
    _f("quantity_raw", T, "", "no", "Raw quantity strings (joined with | when merged)", "Raw quantity kept for audit", "Kept verbatim"),
    _f("qty_value", D, "", "yes", ">= 0; empty for placeholders", "Parsed numeric value", "units.parse_quantity"),
    _f("qty_unit_raw / qty_unit_norm", T, "", "no", "g/ml/tbsp/tsp/cloves/medium or a placeholder code", "Raw unit token / normalised unit", "unit_conversion.csv"),
    _f("qty_dimension", T, "", "no", "mass / volume / count / na", "Dimension", "unit_conversion.csv"),
    _f("qty_canonical_value", D, "", "yes", ">= 0", "Value after canonical conversion", "mass->g, volume->ml, count->piece"),
    _f("qty_canonical_unit", T, "", "yes", "g / ml / piece / placeholder code", "Unit after canonical conversion", "unit_conversion.csv"),
    _f("qty_approx_g", D, "", "yes", ">= 0", "Estimated grams for shopping lists and cost roll-ups (approximate density)", "gram_equivalent_per_unit"),
    _f("qty_is_placeholder / qty_placeholder_code", B, "", "no", "TO_TASTE / AS_NEEDED / ...", "Placeholder flag and canonical code", "PLACEHOLDER_CODES"),
    _f("qty_parse_status", T, "", "no", "OK / OK_UNITLESS / PLACEHOLDER / UNPARSEABLE / UNKNOWN_UNIT", "Parse status (verification requires the last two to be 0)", "units.parse_quantity"),
    _f("merged_row_count / merged_units", I, "", "no", ">= 1", "Row count and units before merging; deduplication audit", "clean.py step 2"),
    _f("qty_clipped", B, "", "no", "true / false", "Whether this row was scaled by clipping", "clean.py step 3"),
    _f("allergen_flags / match_status", T, "", "no", "Allergen list / match type", "Derived allergens and synonym match type", "allergen_map.csv"),
]

DERIVED_SPEC: dict[str, list[tuple]] = {
    "cuisine_category.csv": [
        _f("cuisine", T, "PK(part),FK->cuisines", "no", "5 values", "Cuisine", "Split from the comma-separated categories into a 3NF link table"),
        _f("category", T, "PK(part)", "no", "11 values", "Category", "As above"),
    ],
    "recipe_allergens.csv": [
        _f("recipe_id", T, "PK,FK->recipes", "no", "RCP*", "Recipe primary key", "Derived from the union of ingredient allergens"),
        _f("allergens", T, "", "no", "10 allergen classes, separated by | or none", "All allergens for this recipe", "allergen_map.csv"),
        _f("allergen_count", I, "", "no", "0 ~ n", "Number of allergen classes", "Derived"),
        _f("has_<allergen>", B, "", "no", "true/false x 10", "Ten indexable boolean columns for allergen exclusion queries", "Derived"),
    ],
    "recipe_dietary_audit.csv": [
        _f("recipe_id", T, "PK,FK->recipes", "no", "RCP*", "Recipe primary key", "-"),
        _f("<flag>_raw / <flag>_calc", B, "", "no", "true/false x 3", "Raw and recomputed flags compared field by field", "clean.py step 4"),
        _f("is_halal_raw / halal_proxy", B, "", "no", "true/false", "Raw halal flag and conservative proxy (does not overwrite the business column)", "dietary_rules.csv"),
        _f("conflict_count / conflict_flags", I, "", "no", "0 ~ 3", "Conflict count and field list; source for report and video figures", "Derived"),
    ],
    "ingredient_master.csv": [
        _f("canonical_id", T, "PK", "no", "ING_*", "Canonical ingredient id", "allergen_map.csv"),
        _f("canonical_name / category / allergens", T, "", "no", "-", "Name, unified category and allergens", "allergen_map.csv"),
        _f("is_animal / is_meat_fish / is_gluten_source", B, "", "no", "true/false", "Predicates used to recompute dietary flags", "dietary_rules.csv"),
    ],
    "ingredient_stats.csv": [
        _f("canonical_id", T, "PK,FK->ingredient_master", "no", "ING_*", "Canonical ingredient id", "-"),
        _f("doc_freq / total_recipes", I, "", "no", "1 ~ 9997", "Recipes containing this ingredient / total recipes", "Computed from the cleaned ingredient table"),
        _f("idf", D, "", "no", "ln((N+1)/(df+1))+1", "Rarity weight supporting weighted-overlap ranking", "Derived"),
        _f("idf_norm / rarity_rank", D, "", "no", "0 ~ 1 / 1 ~ n", "Normalised weight and rarity rank", "Derived"),
        _f("avg_approx_g / share_pct", D, "", "no", ">= 0", "Mean estimated grams and coverage", "Derived"),
    ],
    "recipe_search_document.csv": [
        _f("recipe_id", T, "PK,FK->recipes", "no", "RCP*", "Recipe primary key", "-"),
        _f("search_document", T, "", "no", "Concatenated text", "Name + cuisine + category + method + ingredients + steps, for full-text indexing", "Derived"),
        _f("doc_length", I, "", "no", ">= 0", "Document length for BM25 / length-normalisation experiments", "Derived"),
    ],
}


def build(out_dir: Path | None = None, doc_out: Path | None = None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    def add(table: str, fields: list[tuple]) -> None:
        for i, (col, typ, role, nullable, domain, desc, src) in enumerate(fields, 1):
            rows.append({"table": table, "column": col, "ordinal": str(i),
                         "logical_type": typ, "key_role": role, "nullable": nullable,
                         "domain_or_range": domain, "description": desc,
                         "source_or_transform": src})

    for table, fields in RAW_SPEC.items():
        add(table, fields)
    add("recipes.csv (23 raw columns + derived columns)", RAW_SPEC["recipes_master.csv"] + CLEAN_RECIPES_EXTRA)
    add("ingredients.csv (structured)", CLEAN_INGREDIENT_EXTRA)
    add("nutrition.csv / steps.csv / cuisines.csv",
        RAW_SPEC["recipe_nutrition.csv"] + RAW_SPEC["recipe_steps.csv"] + RAW_SPEC["cuisine_metadata.csv"])
    for table, fields in DERIVED_SPEC.items():
        add(table, fields)

    out = out_dir or C.MAPPINGS
    out.mkdir(parents=True, exist_ok=True)
    U.write_csv(out / "field_dictionary.csv", rows, COLUMNS)

    d = doc_out or C.DOCS / "data_dictionary.md"
    esc = lambda s: str(s).replace("|", r"\|")   # escape pipes inside Markdown table cells
    L = ["# Data Dictionary - Smart Recipe and Nutrition Retrieval System\n\n",
         "> Generated by `python -m etl.pipeline dictionary`. Machine-readable: `data/mappings/field_dictionary.csv`.\n",
         "> Logical types are the suggested PostgreSQL mapping. Column names are a fixed contract.\n\n"]
    cur = None
    for r in rows:
        if r["table"] != cur:
            cur = r["table"]
            L.append(f"\n## `{cur}`\n\n| # | Column | Type | Key | Null | Domain / range | Description | Source / transform |\n"
                     f"|---:|---|---|---|---|---|---|---|\n")
        L.append(f"| {r['ordinal']} | `{esc(r['column'])}` | {esc(r['logical_type'])} | "
                 f"{esc(r['key_role'])} | {esc(r['nullable'])} | {esc(r['domain_or_range'])} | "
                 f"{esc(r['description'])} | {esc(r['source_or_transform'])} |\n")
    L.append("\n## Conventions\n\n"
             "- Booleans are lowercase `true`/`false` so PostgreSQL `COPY` accepts them.\n"
             "- All tables are UTF-8, comma separated, with a header; no embedded newlines.\n"
             "- Downstream code references `canonical_id`; `ingredient_name_raw` is audit-only.\n"
             "- `qty_*`, `merged_*` and `*_raw` are audit columns; `canonical_id` must be kept.\n")
    U.write_text(d, "".join(L))
    return rows
