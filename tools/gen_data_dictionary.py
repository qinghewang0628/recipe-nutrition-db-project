#!/usr/bin/env python3
"""Generate docs/data_dictionary.md from the built database.

Part A ships a *logical* dictionary (part_a/docs/data_dictionary.md): one row per
CSV column, with meaning, domain and provenance.  This script produces the
*physical* companion: what PostgreSQL actually enforces and how it is accessed -
key, nullability, CHECK constraints, index membership, foreign-key target - read
from pg_catalog rather than retyped, so it cannot drift from sql/schema.sql.

    python3 tools/gen_data_dictionary.py            # writes docs/data_dictionary.md
    python3 tools/gen_data_dictionary.py --check    # only verify the curated text

Exit status is non-zero when a column has no curated description (or a
description refers to a column that no longer exists), which is the intended way
to notice that the schema changed.
"""
import re
import subprocess
import sys

DB = "recipe_db"
PSQL = ["psql", "-h", "127.0.0.1", "-d", DB, "-At", "-F", "\x1f", "-q", "-c"]
OUT = "docs/data_dictionary.md"

TABLES = [
    ("cuisines", "cuisine"),
    ("cuisine_category", "cuisine x category"),
    ("recipes", "recipe"),
    ("ingredient_master", "canonical ingredient"),
    ("ingredients", "recipe x ingredient line"),
    ("steps", "recipe x step"),
    ("nutrition", "recipe (1:1)"),
    ("recipe_allergens", "recipe (1:1)"),
    ("recipe_dietary_audit", "recipe (1:1)"),
    ("ingredient_stats", "canonical ingredient"),
    ("recipe_search_document", "recipe (1:1)"),
]

# Columns deliberately not indexed, with the reason (mirrors sql/index.sql).
NOT_INDEXED = {
    ("ingredients", "recipe_id"): "leading column of the primary key",
    ("recipe_allergens", "recipe_id"): "reached by 1:1 primary-key join",
    ("recipes", "cuisine"): "leading column of idx_recipes_cuisine_category_time",
    ("recipes", "calories_per_serving"): "INCLUDE column of the composite index",
    ("nutrition", "calories"): "reached by 1:1 primary-key join",
}


def q(sql):
    out = subprocess.run(PSQL + [sql], capture_output=True, text=True, check=True).stdout
    return [r.split("\x1f") for r in out.splitlines() if r]


def collect():
    cols = q("SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), "
             "a.attnotnull, coalesce(pg_get_expr(d.adbin, d.adrelid), '-') "
             "FROM pg_attribute a "
             "JOIN pg_class c ON c.oid = a.attrelid "
             "JOIN pg_namespace n ON n.oid = c.relnamespace "
             "LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum "
             "WHERE n.nspname = 'public' AND c.relkind = 'r' "
             "AND a.attnum > 0 AND NOT a.attisdropped "
             "ORDER BY c.relname, a.attnum")
    cons = q("SELECT t.relname, c.conname, c.contype, "
             "pg_get_constraintdef(c.oid) FROM pg_constraint c "
             "JOIN pg_class t ON t.oid = c.conrelid "
             "JOIN pg_namespace n ON n.oid = t.relnamespace "
             "WHERE n.nspname = 'public' ORDER BY t.relname, c.contype, c.conname")
    idx = q("SELECT t.relname, i.relname, a.attname, "
             "CASE WHEN k.ord > x.indnkeyatts THEN 'include' ELSE 'key' END, "
             "pg_get_indexdef(x.indexrelid) "
             "FROM pg_index x "
             "JOIN pg_class i ON i.oid = x.indexrelid "
             "JOIN pg_class t ON t.oid = x.indrelid "
             "CROSS JOIN LATERAL unnest(x.indkey) WITH ORDINALITY AS k(attnum, ord) "
             "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum "
             "WHERE t.relnamespace = 'public'::regnamespace AND t.relkind = 'r' "
             "ORDER BY t.relname, i.relname, k.ord")
    rows = {t: q(f"SELECT count(*) FROM {t}")[0][0] for t, _ in TABLES}
    return cols, cons, idx, rows


def build(cols, cons, idx):
    pk = {t: set() for t, _ in TABLES}
    fk = {}
    uk = {t: set() for t, _ in TABLES}
    chk = {t: [] for t, _ in TABLES}
    for t, name, typ, definition in cons:
        cols_in = set()
        if typ in ("p", "u", "f"):
            cols_in = set(definition.split("(")[1].split(")")[0].split(", "))
        if typ == "p":
            pk[t] |= cols_in
        elif typ == "u":
            uk[t] |= cols_in
        elif typ == "f":
            ref = definition.split("REFERENCES ")[1].split("(")[0].strip()
            for c in cols_in:
                fk[(t, c)] = ref
        elif typ == "c":
            chk[t].append((name, definition))
    col_index = {}
    for t, iname, cname, role, _def in idx:
        if iname.endswith("_pkey") or role != "key":
            continue  # INCLUDE payloads are noted in section 5 only
        col_index.setdefault((t, cname), []).append(iname)
    checks_of = {}
    for t, _ in TABLES:
        colnames = [c[1] for c in cols if c[0] == t]
        for name, definition in chk[t]:
            body = definition.split("CHECK", 1)[-1]
            for col in colnames:
                if re.search(r"\b%s\b" % re.escape(col), body):
                    checks_of.setdefault((t, col), []).append(name)
    return pk, fk, uk, chk, col_index, checks_of


MEANINGS = {
    # cuisines / cuisine_category
    ("cuisines", "cuisine"): "Cuisine code (5 values); primary key",
    ("cuisines", "categories"): "Display cache of `cuisine_category`; never filtered on (1NF fix below)",
    ("cuisines", "recipe_count"): "Recipes in this cuisine (derived count, not FK-enforced)",
    ("cuisines", "category_count"): "Distinct categories this cuisine has",
    ("cuisine_category", "cuisine"): "FK -> `cuisines`; part of the composite key",
    ("cuisine_category", "category"): "Category name; one row per (cuisine, category) pair",
    # recipes
    ("recipes", "recipe_id"): "Recipe identifier `RCPnnnnn`; stable business key",
    ("recipes", "recipe_name"): "Display name; not unique (3,085 distinct values on 9,997 rows)",
    ("recipes", "cuisine"): "FK -> `cuisines`; leading column of the q2 composite index",
    ("recipes", "category"): "Course / category of the dish (11 values)",
    ("recipes", "cooking_method"): "Method (8 values); displayed, never filtered",
    ("recipes", "difficulty"): "`Easy` / `Medium` / `Hard` (CHECK)",
    ("recipes", "prep_time_minutes"): "Preparation time in minutes",
    ("recipes", "cook_time_minutes"): "Cooking time in minutes",
    ("recipes", "total_time_minutes"): "`prep + cook` (CHECK-enforced); the range filter in q2",
    ("recipes", "servings"): "Servings the recipe yields",
    ("recipes", "spice_level"): "`Mild` / `Medium` / `Hot` / `Very Hot` (CHECK)",
    ("recipes", "meal_type"): "Source column with no constraint to category (noise; not used by the API)",
    ("recipes", "is_vegetarian"): "**Recomputed** from the ingredient list; the flag q2 filters on",
    ("recipes", "is_vegan"): "**Recomputed** from the ingredient list",
    ("recipes", "is_gluten_free"): "**Recomputed**; half of the partial-index predicate",
    ("recipes", "is_halal"): "Source flag kept as-is: halal cannot be derived from ingredient names",
    ("recipes", "is_vegetarian_raw"): "Source-declared flag, kept for the audit (3,259 disagreements)",
    ("recipes", "is_vegan_raw"): "Source-declared vegan flag (1,740 disagreements)",
    ("recipes", "is_gluten_free_raw"): "Source-declared gluten-free flag (5,863 disagreements)",
    ("recipes", "is_halal_raw"): "Source-declared halal flag",
    ("recipes", "is_halal_verifiable"): "Always false - documents that `is_halal` is unverified",
    ("recipes", "dietary_conflict_count"): "How many of the 3 dietary flags disagree with the raw value (0-3)",
    ("recipes", "rating"): "0.0-5.0 with one decimal (CHECK); primary sort key of q2",
    ("recipes", "review_count"): "Popularity; second sort key of q2",
    ("recipes", "calories_per_serving"): "kcal per serving; an INCLUDE column of the q2 index",
    ("recipes", "estimated_cost_usd"): "Estimated cost in USD; an INCLUDE column of the q2 index",
    ("recipes", "date_added"): "Date the recipe entered the corpus (ISO-8601)",
    ("recipes", "is_traditional"): "Traditional-dish flag",
    ("recipes", "is_festival_special"): "Festival-special flag",
    ("recipes", "ingredient_count"): "denormalised: COUNT over `ingredients`; denominator of q1's tie-break",
    ("recipes", "step_count"): "denormalised: COUNT over `steps`",
    ("recipes", "allergen_count"): "denormalised: number of true `has_*` flags in `recipe_allergens`",
    ("recipes", "estimated_total_g"): "denormalised: estimated total weight in grams",
    ("recipes", "estimated_g_per_serving"): "denormalised: estimated weight per serving",
    ("recipes", "qty_clipped_recipe"): "True when any quantity in the recipe was clipped while parsing",
    # ingredient_master
    ("ingredient_master", "canonical_id"): "Canonical key (57 values); the **only** join key for ingredients",
    ("ingredient_master", "canonical_name"): "Display name, UNIQUE; never used as a join key",
    ("ingredient_master", "category"): "Ingredient category (8 values; `Paneer` unified across two source spellings)",
    ("ingredient_master", "allergens"): "`|`-separated allergen classes, or `none`",
    ("ingredient_master", "is_animal"): "Animal-derived? Used to recompute `is_vegan`",
    ("ingredient_master", "is_meat_fish"): "Meat or fish? Used to recompute `is_vegetarian`",
    ("ingredient_master", "is_gluten_source"): "Wheat / barley / ... ? Used to recompute `is_gluten_free`",
    ("ingredient_master", "note"): "Free-text mapping note (nullable)",
    # ingredients
    ("ingredients", "recipe_id"): "FK -> `recipes`; leading column of the composite primary key",
    ("ingredients", "ingredient_number"): "Ordinal within the recipe; contiguous from 1",
    ("ingredients", "canonical_id"): "FK -> `ingredient_master`; **the q1 filter column** (indexed)",
    ("ingredients", "canonical_name"): "denormalised: display only, never joined on",
    ("ingredients", "ingredient_name_raw"): "Line as written in the source (audit only)",
    ("ingredients", "category"): "Ingredient category at line level",
    ("ingredients", "quantity_raw"): "Quantity as written (`1 medium`, `to taste`)",
    ("ingredients", "qty_value"): "Parsed numeric value; NULL exactly when `qty_is_placeholder`",
    ("ingredients", "qty_unit_raw"): "Unit as written",
    ("ingredients", "qty_unit_norm"): "Unit after normalisation",
    ("ingredients", "qty_dimension"): "`mass` / `volume` / `count` / `na` - `na` exactly for placeholders (CHECK)",
    ("ingredients", "qty_canonical_value"): "Value converted to the canonical unit of its dimension",
    ("ingredients", "qty_canonical_unit"): "Canonical unit for that dimension",
    ("ingredients", "qty_approx_g"): "Estimated weight in grams; the basis of the nutrition estimate",
    ("ingredients", "qty_is_placeholder"): "True for `to taste` / `a pinch` (8,940 lines); **never render as 0**",
    ("ingredients", "qty_placeholder_code"): "Placeholder code, present iff `qty_is_placeholder` (CHECK)",
    ("ingredients", "qty_parse_status"): "`OK` / `PLACEHOLDER` (CHECK)",
    ("ingredients", "merged_row_count"): "Source rows merged into this line; `SUM` = 103,908 raw rows",
    ("ingredients", "merged_units"): "Units merged when the source repeated the ingredient",
    ("ingredients", "qty_clipped"): "True when the value was clipped to a sane range",
    ("ingredients", "allergen_flags"): "`|`-separated allergen classes implied by this line",
    ("ingredients", "match_status"): "`exact` / `merge` / `exact|merge` - how the name was mapped",
    # steps
    ("steps", "recipe_id"): "FK -> `recipes`; part of the composite key",
    ("steps", "step_number"): "Ordinal within the recipe; contiguous from 1",
    ("steps", "step_description"): "One of 20 template sentences (low signal; part of the q3 document)",
    ("steps", "estimated_time_minutes"): "**Not a duration metric** (template-derived); use `recipes.total_time_minutes`",
    # nutrition
    ("nutrition", "recipe_id"): "PK **and** FK -> `recipes` (1:1)",
    ("nutrition", "calories"): "Energy in kcal; consistent with `recipes.calories_per_serving`",
    ("nutrition", "protein_g"): "Protein, grams",
    ("nutrition", "carbohydrates_g"): "Carbohydrates, grams",
    ("nutrition", "fat_g"): "Fat, grams",
    ("nutrition", "fiber_g"): "Fibre, grams",
    ("nutrition", "sugar_g"): "Sugar, grams",
    ("nutrition", "sodium_mg"): "Sodium, milligrams",
    ("nutrition", "cholesterol_mg"): "Cholesterol, milligrams",
    ("nutrition", "vitamin_a_percent"): "% of daily value",
    ("nutrition", "vitamin_c_percent"): "% of daily value",
    ("nutrition", "calcium_percent"): "% of daily value",
    ("nutrition", "iron_percent"): "% of daily value",
    # recipe_allergens
    ("recipe_allergens", "recipe_id"): "PK **and** FK -> `recipes` (1:1)",
    ("recipe_allergens", "allergens"): "denormalised: `|`-separated display list",
    ("recipe_allergens", "allergen_count"): "Must equal the sum of the ten flags (CHECK)",
    ("recipe_allergens", "has_gluten"): "Per-class flag; q2 excludes via `NOT EXISTS` over these",
    ("recipe_allergens", "has_milk"): "Per-class flag (see `has_gluten`)",
    ("recipe_allergens", "has_egg"): "Per-class flag (see `has_gluten`)",
    ("recipe_allergens", "has_fish"): "Per-class flag (see `has_gluten`)",
    ("recipe_allergens", "has_shellfish"): "Per-class flag (see `has_gluten`)",
    ("recipe_allergens", "has_tree_nuts"): "Per-class flag (see `has_gluten`)",
    ("recipe_allergens", "has_sesame"): "Per-class flag (see `has_gluten`)",
    ("recipe_allergens", "has_soy"): "Per-class flag (see `has_gluten`)",
    ("recipe_allergens", "has_mustard"): "Per-class flag (see `has_gluten`)",
    ("recipe_allergens", "has_peanut"): "Per-class flag (see `has_gluten`)",
    # recipe_dietary_audit
    ("recipe_dietary_audit", "recipe_id"): "PK **and** FK -> `recipes` (1:1)",
    ("recipe_dietary_audit", "is_vegetarian_raw"): "Source-declared vegetarian flag",
    ("recipe_dietary_audit", "is_vegetarian_calc"): "Recomputed from the ingredient list",
    ("recipe_dietary_audit", "is_vegan_raw"): "Source-declared vegan flag",
    ("recipe_dietary_audit", "is_vegan_calc"): "Recomputed from the ingredient list",
    ("recipe_dietary_audit", "is_gluten_free_raw"): "Source-declared gluten-free flag",
    ("recipe_dietary_audit", "is_gluten_free_calc"): "Recomputed from the ingredient list",
    ("recipe_dietary_audit", "is_halal_raw"): "Source-declared halal flag",
    ("recipe_dietary_audit", "halal_proxy"): "Conservative heuristic (no pork / alcohol); a hint, not a fact",
    ("recipe_dietary_audit", "halal_proxy_conflict"): "True when the proxy disagrees with the source flag",
    ("recipe_dietary_audit", "conflict_count"): "How many of the three dietary flags disagree (0-3, CHECK)",
    ("recipe_dietary_audit", "conflict_flags"): "Name of each conflicting flag; **NULL** when there is none",
    # ingredient_stats
    ("ingredient_stats", "canonical_id"): "PK **and** FK -> `ingredient_master`",
    ("ingredient_stats", "canonical_name"): "Display copy",
    ("ingredient_stats", "doc_freq"): "Recipes containing this ingredient (`<= total_recipes`, CHECK)",
    ("ingredient_stats", "total_recipes"): "Recipes in the tier these statistics were computed on",
    ("ingredient_stats", "idf"): "`ln((N+1)/(df+1))+1`, `>= 1`; **the weight q1 ranks by**",
    ("ingredient_stats", "idf_norm"): "`idf` rescaled to [0, 1] for display",
    ("ingredient_stats", "rarity_rank"): "1 = rarest ingredient",
    ("ingredient_stats", "avg_approx_g"): "Mean grams per use (only over lines with a real quantity)",
    ("ingredient_stats", "share_pct"): "Percentage of recipes containing it",
    # recipe_search_document
    ("recipe_search_document", "recipe_id"): "PK **and** FK -> `recipes` (1:1)",
    ("recipe_search_document", "search_document"): "name + cuisine + category + method + ingredients + steps; GIN-indexed",
    ("recipe_search_document", "doc_length"): "Token count, kept for a future BM25-style normalisation",
}

# Which query each secondary index exists for (see sql/index.sql and
# docs/load_verification.md section 5).
SERVES = {
    "idx_ingredients_canonical": "q1 - the ingredient -> recipe lookup, `INCLUDE (recipe_id)` so the join never touches the heap",
    "idx_recipes_cuisine_category_time": "q2 - `cuisine = ? AND category = ?` plus the time range and the `ORDER BY`",
    "idx_recipes_veg_gf_time": "q2 - partial index on the vegetarian + gluten-free subset, smaller and hotter than the full tree",
    "idx_search_document_fts": "q3 - GIN over `to_tsvector('english', search_document)`",
    "ingredient_master_canonical_name_key": "UNIQUE guard: proves `canonical_name` is a 1:1 alias of `canonical_id`",
}


def esc(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def render(cols, cons, idx, idxdefs, rows):
    pk, fk, uk, chk, col_index, checks_of = build(cols, cons, idx)
    for t, iname, definition in idxdefs:  # expression / partial parts carry no attnum
        bodies = []
        expr = re.search(r"USING (?:gin|gist) \((.*)\)", definition)
        if expr:
            bodies.append((expr.group(1), " (expr)"))
        pred = re.search(r" WHERE \((.*)\)$", definition)
        if pred:
            bodies.append((pred.group(1), " (predicate)"))
        for body, suffix in bodies:
            for c in (c[1] for c in cols if c[0] == t):
                if re.search(r"\b%s\b" % re.escape(c), body):
                    entry = col_index.setdefault((t, c), [])
                    if not any(e.startswith(iname) for e in entry):
                        entry.append(iname + suffix)
    out = [
        "# Data Dictionary - physical schema",
        "",
        "> Generated from the live catalogue by `tools/gen_data_dictionary.py` - do not edit by hand.",
        "> Regenerate with `python3 tools/gen_data_dictionary.py`; it fails if a column has no",
        "> curated description, so the text below cannot silently drift from `sql/schema.sql`.",
        ">",
        "> This is the *physical* companion to `part_a/docs/data_dictionary.md`, which documents the",
        "> *logical* side of each source column (domain, provenance, transform). Here the question is",
        "> what PostgreSQL enforces (keys, nullability, CHECK) and how each column is reached (index).",
        "> Cardinality and relationships: `docs/figures/er-diagram.png`. Design rationale:",
        "> `docs/schema-design.md`.",
        "",
        f"Totals: **{len(TABLES)} tables, {len(cols)} columns, "
        f"{sum(len(v) for v in chk.values())} CHECK constraints, "
        f"{sum(1 for c in cons if c[2] == 'f')} foreign keys, "
        f"{len(idxdefs)} secondary indexes.**",
        "",
        "## 1. Tables",
        "",
        "| Table | Grain (one row per) | Rows at x1 | Cols | Primary key | Indexes |",
        "|---|---|---:|---:|---|---|",
    ]
    attnum = {(c[0], c[1]): c for c in cols}
    for t, grain in TABLES:
        ncols = sum(1 for c in cols if c[0] == t)
        keys = ", ".join("`%s`" % k for k in sorted(pk[t], key=lambda x: cols.index(attnum[(t, x)]))) or "-"
        names = [d[1] for d in idxdefs if d[0] == t]
        idx_cell = ", ".join("`%s`" % n for n in names) if names else "-"
        out.append(f"| `{t}` | {grain} | {rows[t]} | {ncols} | {keys} | {idx_cell} |")
    out += ["", "## 2. Columns", ""]
    for t, grain in TABLES:
        out += [f"### 2.{TABLES.index((t, grain)) + 1} `{t}` - one row per {grain} ({rows[t]} rows)", "",
                "| # | Column | Type | Null | Key | CHECK | Index | Description |",
                "|---:|---|---|---|---|---|---|---|"]
        tcols = [c for c in cols if c[0] == t]
        for i, (_, name, typ, notnull, default) in enumerate(tcols, 1):
            marks = []
            if name in pk[t]:
                marks.append("PK")
            if (t, name) in fk:
                marks.append("FK -> `%s`" % fk[(t, name)])
            if name in uk[t] and name not in pk[t]:
                marks.append("UNIQUE")
            key_cell = ", ".join(marks) or ""
            if default != "-":
                key_cell += ("; " if key_cell else "") + "default `%s`" % esc(default)
            chk_cell = ", ".join("`%s`" % n for n in checks_of.get((t, name), []))
            idx_cell = ", ".join("`%s`" % n for n in col_index.get((t, name), []))
            if not idx_cell and (t, name) in NOT_INDEXED:
                idx_cell = "none - " + NOT_INDEXED[(t, name)]
            out.append("| {} | `{}` | {} | {} | {} | {} | {} | {} |".format(
                i, name, typ, "**no**" if notnull == "t" else "yes",
                key_cell, chk_cell, idx_cell, esc(MEANINGS[(t, name)])))
        out.append("")
    out += ["## 3. Foreign keys", "",
            "All 10 are declared `DEFERRABLE INITIALLY DEFERRED`, so the bulk loader may insert",
            "parent and child rows in one transaction and has them validated at `COMMIT`.",
            "",
            "| # | Child | Parent | Constraint |", "|---:|---|---|---|"]
    for i, (t, name, typ, definition) in enumerate(
            [c for c in cons if c[2] == "f"], 1):
        parent = definition.split("REFERENCES ")[1].split("(")[0].strip()
        out.append(f"| {i} | `{t}` | `{parent}` | `{esc(definition)}` |")
    out += ["", "## 4. CHECK constraints", "",
            "Constraint names are stable and are quoted verbatim from `pg_constraint`, so a reader",
            "can grep the error message they saw in PostgreSQL back to this table.",
            ""]
    for t, _ in TABLES:
        if not chk[t]:
            continue
        out += [f"**`{t}`** ({len(chk[t])})", "", "| Constraint | Definition |", "|---|---|"]
        for name, definition in chk[t]:
            out.append(f"| `{name}` | `{esc(definition)}` |")
        out.append("")
    out += ["## 5. Secondary indexes", "",
            "Primary keys already index their key columns; these four (plus one UNIQUE) exist for",
            "the three API queries. Measured effect, and the counterfactual without them:",
            "`docs/scale_experiment.md` and `docs/figures/timings.png`.",
            "",
            "| Index | Table | Definition | Serves |", "|---|---|---|---|"]
    for t, name, definition in idxdefs:
        serves = SERVES.get(name, "")
        out.append(f"| `{name}` | `{t}` | `{esc(definition)}` | {serves} |")
    out += [
        "",
        "## 6. Reading rules (consequences of the model)",
        "",
        "- **Join ingredients on `canonical_id`**, never on `canonical_name`. The raw names contain",
        "  synonyms and duplicates; `canonical_id` is the key that survives cleaning, and it is the",
        "  only indexed path into `ingredients`.",
        "- **Never filter on `cuisines.categories`.** It is a denormalised display string; the 1NF",
        "  home of that fact is `cuisine_category`, which has one row per (cuisine, category).",
        "- **`steps.estimated_time_minutes` is not a duration.** It comes from one of 20 templates;",
        "  use `recipes.total_time_minutes` for any time filter or ranking.",
        "- **`is_vegetarian` / `is_vegan` / `is_gluten_free` are recomputed; the `*_raw` columns keep",
        "  what the source claimed.** Show the recomputed value, and keep `dietary_conflict_count`",
        "  for the audit rather than overwriting history. `is_halal` stays a source flag because",
        "  halal cannot be decided from an ingredient list - hence `is_halal_verifiable = false`.",
        "- **A `qty_is_placeholder` line has no number**: `qty_value` and `qty_approx_g` are `NULL`",
        "  by CHECK, and the UI must render `to taste`, never `0`. `qty_dimension = 'na'` is the",
        "  machine-readable marker.",
        "- **Display allergens from `recipe_allergens.allergens`, filter on the `has_*` flags.**",
        "  Splitting a `|`-string at query time defeats every index and the CHECK that keeps",
        "  `allergen_count` equal to the sum of the flags.",
        "- **The denormalised counters on `recipes` (`ingredient_count`, `step_count`,",
        "  `allergen_count`, `estimated_*_g`) are refreshed by the ETL, not by the API.** They are",
        "  verified against their base tables in `docs/evidence/derivation_equivalence.txt`.",
        "- **`ingredient_stats` is per tier.** It embeds `total_recipes`, so it has to be rebuilt",
        "  when a tier grows (the x20 rebuild at 1.89M ingredient rows is timed in",
        "  `docs/scale_experiment.md` section 3).",
        "",
        "## 7. Regenerating",
        "",
        "```bash",
        "python3 tools/gen_data_dictionary.py           # rewrite docs/data_dictionary.md",
        "python3 tools/gen_data_dictionary.py --check   # validate the curated text only",
        "```",
        "",
        "Needs `psql` (PostgreSQL 14+) and the database built per `docs/load_verification.md`",
        "section 2. Standard library only; no third-party packages.",
        "",
    ]
    return "\n".join(out) + "\n"


def main():
    check_only = "--check" in sys.argv[1:]
    cols, cons, idx, rows = collect()
    have = {(c[0], c[1]) for c in cols}
    missing = sorted(have - set(MEANINGS))
    extra = sorted(set(MEANINGS) - have)
    if missing or extra:
        for t, c in missing:
            print(f"missing description: {t}.{c}", file=sys.stderr)
        for t, c in extra:
            print(f"stale description: {t}.{c}", file=sys.stderr)
        return 1
    idxdefs = q("SELECT tablename, indexname, indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' AND indexname NOT LIKE '%\\_pkey' "
                "ORDER BY tablename, indexname")
    if check_only:
        print(f"OK: {len(TABLES)} tables, {len(cols)} columns described, no drift")
        return 0
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(render(cols, cons, idx, idxdefs, rows))
    print(f"wrote {OUT}: {len(TABLES)} tables, {len(cols)} columns, "
          f"{sum(1 for c in cons if c[2] == 'f')} FKs, "
          f"{sum(1 for c in cons if c[2] == 'c')} CHECKs, {len(idxdefs)} indexes")
    return 0


if __name__ == "__main__":
    sys.exit(main())

