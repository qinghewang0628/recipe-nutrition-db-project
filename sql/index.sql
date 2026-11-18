-- ===========================================================================
-- Index strategy (Part B)
--
-- Every index below is derived from one access path in sql/queries.sql; nothing
-- is created "just in case". The comment above each index states which query
-- needs it and why the column order is what it is.
--
-- Run after schema.sql and after the data is loaded (building indexes on an
-- empty table is possible, but the planner then has no statistics):
--     psql -h 127.0.0.1 -d recipe_db -v ON_ERROR_STOP=1 -f sql/index.sql
--
-- Re-runnable: every statement uses IF NOT EXISTS.
-- ===========================================================================
\set ON_ERROR_STOP on

-- ---------------------------------------------------------------------------
-- q1 - reverse ingredient search
--
-- Access path: ingredients => filter by a handful of canonical_id values =>
-- group by recipe_id. The index is on the filtered column, and recipe_id is
-- carried in the leaf pages (INCLUDE) so the scan can be index-only: q1 needs
-- no other column from this table (names and units live in the dimensions).
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_ingredients_canonical
    ON ingredients (canonical_id) INCLUDE (recipe_id);

-- ---------------------------------------------------------------------------
-- q2 - multi-condition filtering
--
-- Access path: equality on cuisine and category, then a range on
-- total_time_minutes, then cheap predicates on calories/cost/rating that the
-- plan would otherwise have to fetch from the heap. Two equality columns must
-- come first: a range column anywhere before them would stop the remaining
-- columns from being used as a search key.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_recipes_cuisine_category_time
    ON recipes (cuisine, category, total_time_minutes)
    INCLUDE (calories_per_serving, estimated_cost_usd, rating);

-- A partial index for the most common filter combination (vegetarian AND
-- gluten free). It stores only the ~2.3k qualifying rows and can be scanned in
-- time order, so the planner can skip sorting entirely for that query shape.
-- Note the predicate must be written exactly as the query writes it.
CREATE INDEX IF NOT EXISTS idx_recipes_veg_gf_time
    ON recipes (total_time_minutes)
    WHERE is_vegetarian AND is_gluten_free;

-- ---------------------------------------------------------------------------
-- q3 - full-text search
--
-- Access path: recipe_search_document => @@ plainto_tsquery => rank. A GIN index
-- on the *expression* is the standard structure for @@ lookups. The expression
-- must match the query text exactly (same configuration, 'english'), otherwise
-- PostgreSQL cannot prove the index applies and falls back to a seq scan -
-- this is the single most common reason a full-text index is silently ignored.
--
-- Alternatives and why they were not chosen:
--   * GiST instead of GIN: smaller and cheaper to update, but slower for the
--     membership (@@) queries we run. We bulk-load once, so GIN wins.
--   * a stored tsvector column: impossible with the generated COPY loader
--     (see the comment on recipe_search_document in schema.sql).
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_search_document_fts
    ON recipe_search_document
    USING gin (to_tsvector('english', search_document));

-- ---------------------------------------------------------------------------
-- Deliberately NOT indexed, with the reason (this list belongs in the report,
-- it is as informative as the indexes that do exist):
--
--   ingredients (recipe_id)
--       The primary key (recipe_id, ingredient_number) already provides a
--       btree with recipe_id as its leading column.
--
--   recipe_allergens (has_* / recipe_id)
--       One row per recipe, reached through a primary-key join, and ten boolean
--       flags of low selectivity. The filter runs after the join; an index would
--       add write cost without changing the plan.
--
--   recipes (cuisine)
--       Covered by the leading column of idx_recipes_cuisine_category_time.
--
--   recipes (calories_per_serving), nutrition (calories)
--       Range predicates on a column that is already carried by the composite
--       index (INCLUDE) or reached through a 1:1 primary-key join.
-- ---------------------------------------------------------------------------

-- The planner only considers an index once the table has statistics; refresh
-- them after a bulk load so that the first EXPLAIN is not misleading.
ANALYZE cuisines;
ANALYZE cuisine_category;
ANALYZE recipes;
ANALYZE ingredient_master;
ANALYZE ingredients;
ANALYZE steps;
ANALYZE nutrition;
ANALYZE recipe_allergens;
ANALYZE recipe_dietary_audit;
ANALYZE ingredient_stats;
ANALYZE recipe_search_document;
