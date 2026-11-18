-- ===========================================================================
-- Smart Recipe and Nutrition Retrieval System
-- Physical schema v1.0 (Part B)
--
-- Input : the eleven cleaned CSV tables produced by Part A
--         (part_a/data/clean/*.csv, see part_a/docs/data_dictionary.md)
-- Output: empty tables ready for part_a/sql/load_clean.sql
--
-- Run with psql (client-side \copy in the loader needs the same client):
--     psql -h 127.0.0.1 -d recipe_db -v ON_ERROR_STOP=1 -f sql/schema.sql
--     cd part_a && psql -h 127.0.0.1 -d recipe_db -v ON_ERROR_STOP=1 -f sql/load_clean.sql
--
-- Design notes
--   1. Table and column names are the fixed contract published in
--      part_a/docs/handoff.md. Renaming any of them breaks the generated
--      loaders, which address columns positionally through the CSV header.
--   2. Every foreign key is DEFERRABLE INITIALLY DEFERRED. The generated
--      loader copies `recipes` before `cuisines` and `ingredients` before
--      `ingredient_master`; all of its \copy calls run inside one transaction,
--      so the constraints are validated at COMMIT instead of per row.
--   3. Types are narrowed to the domains profiled by Part A (docs/profile_metrics.md)
--      so that CHECK constraints act as a second line of defence behind the ETL.
--   4. Deliberate denormalisation is marked with a `-- denormalised:` comment
--      and justified in docs/schema-design.md.
-- ===========================================================================
\set ON_ERROR_STOP on

-- This script rebuilds the database from scratch. It is a build script, not a
-- migration: running it discards existing data on purpose.
DROP TABLE IF EXISTS
    recipe_search_document,
    recipe_dietary_audit,
    recipe_allergens,
    nutrition,
    steps,
    ingredients,
    ingredient_stats,
    recipes,
    cuisine_category,
    cuisines,
    ingredient_master
    CASCADE;

-- ---------------------------------------------------------------------------
-- 1. Cuisine dimension
-- ---------------------------------------------------------------------------
CREATE TABLE cuisines (
    cuisine        text    PRIMARY KEY,
    categories     text    NOT NULL,   -- denormalised: comma-separated cache of
                                       -- cuisine_category, kept for display only
    recipe_count   integer NOT NULL CHECK (recipe_count >= 0),
    category_count integer NOT NULL CHECK (category_count >= 0)
);

-- 1NF fix for cuisines.categories: one row per (cuisine, category) pair.
CREATE TABLE cuisine_category (
    cuisine  text NOT NULL REFERENCES cuisines (cuisine)
                        DEFERRABLE INITIALLY DEFERRED,
    category text NOT NULL,
    PRIMARY KEY (cuisine, category)
);

-- ---------------------------------------------------------------------------
-- 2. Recipe master (grain: one row per recipe)
-- ---------------------------------------------------------------------------
CREATE TABLE recipes (
    recipe_id              text     PRIMARY KEY,
    recipe_name            text     NOT NULL,
    cuisine                text     NOT NULL REFERENCES cuisines (cuisine)
                                    DEFERRABLE INITIALLY DEFERRED,
    category               text     NOT NULL,
    cooking_method         text     NOT NULL,
    difficulty             text     NOT NULL CHECK (difficulty IN ('Easy', 'Medium', 'Hard')),
    prep_time_minutes      smallint NOT NULL CHECK (prep_time_minutes >= 0),
    cook_time_minutes      smallint NOT NULL CHECK (cook_time_minutes >= 0),
    total_time_minutes     smallint NOT NULL CHECK (total_time_minutes > 0),
    servings               smallint NOT NULL CHECK (servings > 0),
    spice_level            text     NOT NULL CHECK (spice_level IN ('Mild', 'Medium', 'Hot', 'Very Hot')),
    meal_type              text     NOT NULL,

    -- Business dietary flags: recomputed from the ingredient list by Part A.
    is_vegetarian          boolean  NOT NULL,
    is_vegan               boolean  NOT NULL,
    is_gluten_free         boolean  NOT NULL,
    is_halal               boolean  NOT NULL,

    -- Audit trail: the flags as declared in the source data. Kept so that the
    -- 3259 / 1740 / 5863 disagreements can be shown instead of silently fixed.
    is_vegetarian_raw      boolean  NOT NULL,
    is_vegan_raw           boolean  NOT NULL,
    is_gluten_free_raw     boolean  NOT NULL,
    is_halal_raw           boolean  NOT NULL,
    is_halal_verifiable    boolean  NOT NULL,  -- always false: halal cannot be
                                               -- decided from ingredient names
    dietary_conflict_count smallint NOT NULL CHECK (dietary_conflict_count BETWEEN 0 AND 3),

    rating                 numeric(2,1) NOT NULL CHECK (rating BETWEEN 0 AND 5),
    review_count           integer  NOT NULL CHECK (review_count >= 0),
    calories_per_serving   smallint NOT NULL CHECK (calories_per_serving >= 0),
    estimated_cost_usd     numeric(6,2) NOT NULL CHECK (estimated_cost_usd >= 0),
    date_added             date     NOT NULL,
    is_traditional         boolean  NOT NULL,
    is_festival_special    boolean  NOT NULL,

    -- denormalised: counts and totals that a query would otherwise have to
    -- aggregate over ingredients / steps / recipe_allergens on every call.
    -- Part A guarantees them to be consistent with the child tables.
    ingredient_count         smallint  NOT NULL CHECK (ingredient_count > 0),
    step_count               smallint  NOT NULL CHECK (step_count > 0),
    allergen_count           smallint  NOT NULL CHECK (allergen_count >= 0),
    estimated_total_g        numeric(10,2) CHECK (estimated_total_g >= 0),
    estimated_g_per_serving  numeric(10,2) CHECK (estimated_g_per_serving >= 0),
    qty_clipped_recipe       boolean   NOT NULL,

    CONSTRAINT total_time_is_prep_plus_cook
        CHECK (total_time_minutes = prep_time_minutes + cook_time_minutes)
);

-- ---------------------------------------------------------------------------
-- 3. Ingredient dimension (57 canonical ingredients)
-- ---------------------------------------------------------------------------
CREATE TABLE ingredient_master (
    canonical_id     text    PRIMARY KEY,
    canonical_name   text    NOT NULL UNIQUE,
    category         text    NOT NULL,
    allergens        text    NOT NULL,      -- '|'-separated allergen classes, or 'none'
    is_animal        boolean NOT NULL,
    is_meat_fish     boolean NOT NULL,
    is_gluten_source boolean NOT NULL,
    note             text                   -- free-text mapping note, nullable
);

-- ---------------------------------------------------------------------------
-- 4. Recipe-ingredient lines (grain: one row per recipe x canonical ingredient)
--
-- The raw source repeats an ingredient inside one recipe (7,996 duplicate lines
-- over 103,908 raw rows). Part A merged them, so the grain here is
-- (recipe_id, ingredient_number) over 95,912 cleaned lines and
-- sum(merged_row_count) still equals the 103,908 raw rows - the merge is
-- lossless and can be audited.
-- ---------------------------------------------------------------------------
CREATE TABLE ingredients (
    recipe_id           text     NOT NULL REFERENCES recipes (recipe_id)
                                  DEFERRABLE INITIALLY DEFERRED,
    ingredient_number   smallint NOT NULL CHECK (ingredient_number > 0),

    canonical_id        text     NOT NULL REFERENCES ingredient_master (canonical_id)
                                  DEFERRABLE INITIALLY DEFERRED,
    canonical_name      text     NOT NULL,   -- denormalised: display only, never join on it
    ingredient_name_raw text     NOT NULL,   -- audit only
    category            text     NOT NULL,

    -- Quantity as written, then the parsed value split from its unit.
    quantity_raw          text     NOT NULL,
    qty_value             numeric(12,4) CHECK (qty_value >= 0),
    qty_unit_raw          text,
    qty_unit_norm         text,
    qty_dimension         text     NOT NULL CHECK (qty_dimension IN ('mass', 'volume', 'count', 'na')),
    qty_canonical_value   numeric(12,4) CHECK (qty_canonical_value >= 0),
    qty_canonical_unit    text,
    qty_approx_g          numeric(12,4) CHECK (qty_approx_g >= 0),

    -- 8,940 lines carry a placeholder instead of a number ("to taste", "a pinch").
    -- Their numeric fields are empty and must be rendered from the code, never as 0.
    qty_is_placeholder    boolean NOT NULL,
    qty_placeholder_code  text,
    qty_parse_status      text    NOT NULL CHECK (qty_parse_status IN ('OK', 'PLACEHOLDER')),
    merged_row_count      smallint NOT NULL CHECK (merged_row_count >= 1),
    merged_units          text,
    qty_clipped           boolean NOT NULL,
    allergen_flags        text,
    match_status          text    CHECK (match_status IN ('exact', 'merge', 'exact|merge')),

    PRIMARY KEY (recipe_id, ingredient_number),

    -- Placeholder and value are mutually exclusive, and only placeholders carry a code.
    CONSTRAINT placeholder_has_no_value
        CHECK (qty_is_placeholder = (qty_value IS NULL)),
    CONSTRAINT placeholder_has_code
        CHECK (NOT qty_is_placeholder OR qty_placeholder_code IS NOT NULL),
    CONSTRAINT placeholder_dimension_is_na
        CHECK ((qty_dimension = 'na') = qty_is_placeholder)
);

-- ---------------------------------------------------------------------------
-- 5. Recipe steps (grain: one row per recipe x step)
-- ---------------------------------------------------------------------------
CREATE TABLE steps (
    recipe_id              text     NOT NULL REFERENCES recipes (recipe_id)
                                    DEFERRABLE INITIALLY DEFERRED,
    step_number            smallint NOT NULL CHECK (step_number > 0),
    step_description       text     NOT NULL,
    -- Not a duration metric: the source fills it from a template sentence.
    -- Use recipes.prep_time_minutes + cook_time_minutes instead.
    estimated_time_minutes smallint CHECK (estimated_time_minutes >= 0),
    PRIMARY KEY (recipe_id, step_number)
);

-- ---------------------------------------------------------------------------
-- 6. Nutrition (grain: one row per recipe, 1:1 extension of recipes)
-- ---------------------------------------------------------------------------
CREATE TABLE nutrition (
    recipe_id         text PRIMARY KEY REFERENCES recipes (recipe_id)
                            DEFERRABLE INITIALLY DEFERRED,
    calories          integer      NOT NULL CHECK (calories >= 0),
    protein_g         numeric(8,2) NOT NULL CHECK (protein_g >= 0),
    carbohydrates_g   numeric(8,2) NOT NULL CHECK (carbohydrates_g >= 0),
    fat_g             numeric(8,2) NOT NULL CHECK (fat_g >= 0),
    fiber_g           numeric(8,2) NOT NULL CHECK (fiber_g >= 0),
    sugar_g           numeric(8,2) NOT NULL CHECK (sugar_g >= 0),
    sodium_mg         numeric(8,2) NOT NULL CHECK (sodium_mg >= 0),
    cholesterol_mg    numeric(8,2) NOT NULL CHECK (cholesterol_mg >= 0),
    vitamin_a_percent numeric(6,2) NOT NULL CHECK (vitamin_a_percent >= 0),
    vitamin_c_percent numeric(6,2) NOT NULL CHECK (vitamin_c_percent >= 0),
    calcium_percent   numeric(6,2) NOT NULL CHECK (calcium_percent >= 0),
    iron_percent      numeric(6,2) NOT NULL CHECK (iron_percent >= 0)
);

-- ---------------------------------------------------------------------------
-- 7. Allergen profile (grain: one row per recipe, 1:1 extension of recipes)
--
-- Ten boolean columns instead of an (recipe, allergen) link table: the allergen
-- vocabulary is closed (10 classes) and fixed by the source, and an allergy
-- filter is a WHERE predicate, not a projection. A link table would force a
-- group-by or one anti-join per excluded class.
-- ---------------------------------------------------------------------------
CREATE TABLE recipe_allergens (
    recipe_id      text PRIMARY KEY REFERENCES recipes (recipe_id)
                         DEFERRABLE INITIALLY DEFERRED,
    allergens      text     NOT NULL,      -- '|'-separated list, or 'none'
    allergen_count smallint NOT NULL CHECK (allergen_count BETWEEN 0 AND 10),
    has_gluten     boolean  NOT NULL,
    has_milk       boolean  NOT NULL,
    has_egg        boolean  NOT NULL,
    has_fish       boolean  NOT NULL,
    has_shellfish  boolean  NOT NULL,
    has_tree_nuts  boolean  NOT NULL,
    has_sesame     boolean  NOT NULL,
    has_soy        boolean  NOT NULL,
    has_mustard    boolean  NOT NULL,
    has_peanut     boolean  NOT NULL,
    CONSTRAINT allergen_count_matches_flags
        CHECK (allergen_count = has_gluten::int + has_milk::int + has_egg::int
                + has_fish::int + has_shellfish::int + has_tree_nuts::int
                + has_sesame::int + has_soy::int + has_mustard::int + has_peanut::int)
);

-- ---------------------------------------------------------------------------
-- 8. Dietary audit (grain: one row per recipe, 1:1 extension of recipes)
--
-- Separated from recipes so the 3,259 / 1,740 / 5,863 disagreements stay
-- visible without widening the hot-path table. halal_proxy is deliberately not
-- copied into recipes.is_halal: it is a conservative heuristic, not a fact.
-- ---------------------------------------------------------------------------
CREATE TABLE recipe_dietary_audit (
    recipe_id            text PRIMARY KEY REFERENCES recipes (recipe_id)
                               DEFERRABLE INITIALLY DEFERRED,
    is_vegetarian_raw    boolean  NOT NULL,
    is_vegetarian_calc   boolean  NOT NULL,
    is_vegan_raw         boolean  NOT NULL,
    is_vegan_calc        boolean  NOT NULL,
    is_gluten_free_raw   boolean  NOT NULL,
    is_gluten_free_calc  boolean  NOT NULL,
    is_halal_raw         boolean  NOT NULL,
    halal_proxy          boolean  NOT NULL,
    halal_proxy_conflict boolean  NOT NULL,
    conflict_count       smallint NOT NULL CHECK (conflict_count BETWEEN 0 AND 3),
    conflict_flags       text
);

-- ---------------------------------------------------------------------------
-- 9. Ingredient statistics (grain: one row per canonical ingredient)
--
-- Derived aggregate consumed by q1. Part A recomputes doc_freq and idf for
-- every scale tier (large tier: max doc_freq 196,994), so the weights always
-- describe the data set they are used on. Refresh procedure: docs/schema-design.md.
-- ---------------------------------------------------------------------------
CREATE TABLE ingredient_stats (
    canonical_id   text PRIMARY KEY REFERENCES ingredient_master (canonical_id)
                        DEFERRABLE INITIALLY DEFERRED,
    canonical_name text    NOT NULL,
    doc_freq       integer NOT NULL CHECK (doc_freq >= 1),
    total_recipes  integer NOT NULL CHECK (total_recipes >= 1),
    idf            numeric(10,6) NOT NULL CHECK (idf >= 1),
    idf_norm       numeric(10,6) CHECK (idf_norm >= 0 AND idf_norm <= 1),
    rarity_rank    integer CHECK (rarity_rank >= 1),
    avg_approx_g   numeric(10,2) CHECK (avg_approx_g >= 0),
    share_pct      numeric(6,3)  CHECK (share_pct >= 0 AND share_pct <= 100),
    CONSTRAINT doc_freq_within_total CHECK (doc_freq <= total_recipes)
);

-- ---------------------------------------------------------------------------
-- 10. Search document (grain: one row per recipe, 1:1 extension of recipes)
--
-- denormalised: name + cuisine + category + method + ingredient names + steps
-- concatenated into one text column, so q3 needs one GIN index and no runtime
-- join. The price is that the text must be regenerated when an ingredient line
-- changes; it belongs to the ETL and is never written by the API.
--
-- No stored tsvector column, on purpose: the generated loader runs
-- COPY ... FROM without a column list, which fails on a stored generated
-- column. sql/index.sql therefore indexes to_tsvector('english', search_document)
-- as an expression index instead.
-- ---------------------------------------------------------------------------
CREATE TABLE recipe_search_document (
    recipe_id       text PRIMARY KEY REFERENCES recipes (recipe_id)
                         DEFERRABLE INITIALLY DEFERRED,
    search_document text    NOT NULL,
    doc_length      integer NOT NULL CHECK (doc_length > 0)   -- for rank normalisation
);

-- ---------------------------------------------------------------------------
-- Table documentation (psql \dt+ , and the appendix of the report)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE cuisines               IS 'Cuisine dimension (5 rows); categories is a display cache of cuisine_category';
COMMENT ON TABLE cuisine_category       IS '1NF link table, one row per (cuisine, category) pair (25 rows)';
COMMENT ON TABLE recipes                IS 'Recipe master, one row per recipe (9,997 rows); recomputed and raw dietary flags';
COMMENT ON TABLE ingredient_master      IS 'Canonical ingredient dimension (57 rows); the only ingredient join key';
COMMENT ON TABLE ingredients            IS 'Recipe-ingredient lines (95,912 rows); sum(merged_row_count) = 103,908 raw rows';
COMMENT ON TABLE steps                  IS 'Recipe steps (84,616 rows); estimated_time_minutes is not a duration metric';
COMMENT ON TABLE nutrition              IS 'Per-recipe nutrition, 1:1 with recipes; the only source of nutrition values';
COMMENT ON TABLE recipe_allergens       IS 'Per-recipe allergen flags, 1:1 with recipes; 9,132 recipes carry at least one class';
COMMENT ON TABLE recipe_dietary_audit   IS 'Raw vs recomputed dietary flags, 1:1 with recipes; source of the conflict figures';
COMMENT ON TABLE ingredient_stats       IS 'Derived IDF weights per canonical ingredient; recomputed per scale tier';
COMMENT ON TABLE recipe_search_document IS 'Denormalised concatenated text for full-text search, 1:1 with recipes';

