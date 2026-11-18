-- ===========================================================================
-- Derive the four tables that Part A publishes for the 10k tier only.
--
-- Part A's scale tiers (medium = x5, large = x20) ship 7 CSVs:
--   recipes, ingredients, nutrition, steps, cuisines, recipe_allergens,
--   ingredient_stats
-- The other four tables of the schema are pure functions of those 7, so this
-- script regenerates them with exactly the rules Part A used in etl/clean.py
-- (canonical names from etl/config.py, document layout from clean.py lines
-- 288-303). Running it on the 10k tier reproduces Part A's own CSVs
-- byte-for-byte - that equality is the proof that the scale numbers are
-- measured on the same schema and the same text, not on a different design.
--
-- Prerequisite: the 7 published tables are already loaded in this schema.
-- Run with search_path pointing at the tier, e.g.
--   PGOPTIONS='--search_path=t_large' psql -d recipe_scale -f scale/derive_missing_tables.sql
-- ===========================================================================
\set ON_ERROR_STOP on
BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Prerequisite: scale/load_ingredient_master.sql has run, so the 57-row
--    canonical vocabulary is present and the deferred FKs of the fact tables
--    can be satisfied at COMMIT time.
-- ---------------------------------------------------------------------------
\echo 'deriving: cuisine_category, recipe_dietary_audit, recipe_search_document'

-- ---------------------------------------------------------------------------
-- 2. cuisine_category: 1NF fix for cuisines.categories (comma-separated list).
-- ---------------------------------------------------------------------------
INSERT INTO cuisine_category (cuisine, category)
SELECT c.cuisine, btrim(t.category)
FROM cuisines c
CROSS JOIN LATERAL unnest(string_to_array(c.categories, ',')) AS t (category)
WHERE btrim(t.category) <> '';

-- ---------------------------------------------------------------------------
-- 3. recipe_dietary_audit: recompute the three verifiable flags from the
--    ingredient set and keep the source labels next to them.
--
--    The name lists mirror part_a/etl/config.py. They are name based on
--    purpose: Part A counts Eggs as non-vegetarian, while
--    ingredient_master.is_meat_fish is false for Eggs, so the ingredient flags
--    cannot reproduce the rule.
-- ---------------------------------------------------------------------------
WITH ing AS (
    SELECT i.recipe_id, array_agg(DISTINCT i.canonical_name) AS names
    FROM ingredients i
    GROUP BY i.recipe_id
),
calc AS (
    SELECT r.recipe_id,
           NOT EXISTS (SELECT 1 FROM unnest(ing.names) n
                       WHERE n = ANY (ARRAY['Beef', 'Chicken', 'Fish', 'Mutton',
                                            'Shrimp', 'Eggs']))            AS veg_calc,
           NOT EXISTS (SELECT 1 FROM unnest(ing.names) n
                       WHERE n = ANY (ARRAY['Beef', 'Chicken', 'Fish', 'Mutton',
                                            'Shrimp', 'Eggs', 'Milk', 'Butter',
                                            'Ghee', 'Cream', 'Yogurt',
                                            'Paneer']))                   AS vegan_calc,
           NOT EXISTS (SELECT 1 FROM unnest(ing.names) n
                       WHERE n = ANY (ARRAY['Wheat Flour', 'All-Purpose Flour',
                                            'Semolina']))                  AS gf_calc,
           NOT EXISTS (SELECT 1 FROM unnest(ing.names) n
                       WHERE n = ANY (ARRAY[]::text[]))                    AS halal_proxy,
           r.is_vegetarian_raw  AS veg_raw,
           r.is_vegan_raw       AS vegan_raw,
           r.is_gluten_free_raw AS gf_raw,
           r.is_halal_raw       AS halal_raw
    FROM recipes r
    JOIN ing USING (recipe_id)
)
INSERT INTO recipe_dietary_audit (
    recipe_id,
    is_vegetarian_raw,  is_vegetarian_calc,
    is_vegan_raw,       is_vegan_calc,
    is_gluten_free_raw, is_gluten_free_calc,
    is_halal_raw,       halal_proxy, halal_proxy_conflict,
    conflict_count,     conflict_flags)
SELECT recipe_id,
       veg_raw,   veg_calc,
       vegan_raw, vegan_calc,
       gf_raw,    gf_calc,
       halal_raw, halal_proxy, halal_raw <> halal_proxy,
       (veg_raw <> veg_calc)::int + (vegan_raw <> vegan_calc)::int
                               + (gf_raw  <> gf_calc)::int,
       -- NULL, not '', when nothing conflicts: that is what Part A writes, and
       -- scale/check_equivalence.sql compares the two versions row by row.
       NULLIF(concat_ws('|',
                 CASE WHEN veg_raw   <> veg_calc   THEN 'is_vegetarian' END,
                 CASE WHEN vegan_raw <> vegan_calc THEN 'is_vegan'      END,
                 CASE WHEN gf_raw    <> gf_calc    THEN 'is_gluten_free' END), '')
FROM calc;

-- ---------------------------------------------------------------------------
-- 4. recipe_search_document: name + cuisine + category + method + the sorted
--    distinct canonical ingredient names + the steps in order, joined by single
--    spaces (etl/clean.py lines 294-303).
--
--    COLLATE "C" on the sort is not cosmetic: the database default collation
--    (en_US) ignores spaces and case while Python's sorted() compares code
--    points, so without it the documents would differ from Part A's in word
--    order for names such as "Bay Leaf" / "Basmati Rice" and the q3 numbers
--    would not be comparable.
-- ---------------------------------------------------------------------------
WITH ing AS (
    SELECT i.recipe_id,
           string_agg(DISTINCT i.canonical_name COLLATE "C", ' '
                      ORDER BY i.canonical_name COLLATE "C") AS names
    FROM ingredients i
    GROUP BY i.recipe_id
),
step_text AS (
    SELECT s.recipe_id,
           string_agg(s.step_description, ' ' ORDER BY s.step_number) AS steps
    FROM steps s
    GROUP BY s.recipe_id
),
doc AS (
    SELECT r.recipe_id,
           r.recipe_name || ' ' || r.cuisine || ' ' || r.category || ' ' ||
           r.cooking_method || ' ' || COALESCE(ing.names, '') || ' ' ||
           COALESCE(st.steps, '') AS text
    FROM recipes r
    LEFT JOIN ing       USING (recipe_id)
    LEFT JOIN step_text st USING (recipe_id)
)
INSERT INTO recipe_search_document (recipe_id, search_document, doc_length)
SELECT recipe_id, text, length(text)
FROM doc;

COMMIT;

-- ---------------------------------------------------------------------------
-- Post-derivation checks.
--
-- The first and third blocks must be 0 on every tier. The second block is 0 on
-- the 10k tier and about 1.4% on x5/x20: Part A's scale expansion drops one
-- non-core ingredient from 15% of the copies but keeps the copied dietary
-- flags, so where the dropped line was the only non-vegetarian or gluten
-- ingredient the copied flag and the ingredient list disagree. The audit table
-- is where that becomes visible, on purpose; see docs/scale_experiment.md.
-- ---------------------------------------------------------------------------
\echo 'derived: ingredient rows whose canonical_id is not in ingredient_master (expect 0)'
SELECT count(*) AS unmapped_ingredient_rows
FROM ingredients i
LEFT JOIN ingredient_master m USING (canonical_id)
WHERE m.canonical_id IS NULL;

\echo 'derived: audit calc flags disagreeing with recipes.* (0 on x1, ~1.4% on x5/x20)'
SELECT count(*) AS flag_mismatches
FROM recipe_dietary_audit a
JOIN recipes r USING (recipe_id)
WHERE a.is_vegetarian_calc  <> r.is_vegetarian
   OR a.is_vegan_calc       <> r.is_vegan
   OR a.is_gluten_free_calc <> r.is_gluten_free;


\echo 'derived: 1:1 coverage vs recipes (expect 0 0 0)'
SELECT (SELECT count(*) FROM recipes) - (SELECT count(*) FROM recipe_dietary_audit)   AS audit_missing,
       (SELECT count(*) FROM recipes) - (SELECT count(*) FROM recipe_search_document) AS doc_missing,
       (SELECT count(*) FROM recipes) - (SELECT count(*) FROM recipe_allergens)       AS allergen_missing;


