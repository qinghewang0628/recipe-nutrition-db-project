-- ===========================================================================
-- The three core retrieval queries (Part B, q1 / q2 / q3)
--
-- Every query is self-contained and runnable as-is with psql:
--     psql -h 127.0.0.1 -d recipe_db -f sql/queries.sql
--     psql -h 127.0.0.1 -d recipe_db -c "$(sed -n '/-- q1/,/-- q2/p' sql/queries.sql | head -n -1)"
--
-- Parameters live in a one-row literal block inside the statement (a `WITH input`
-- CTE for q1/q3, a FROM subquery for q2 - see point 4 in the q2 header for why),
-- so the query text stays pure SQL: no psql \set, no client quoting. For the API
-- layer, Person C replaces those literals with driver parameters, e.g. $1::text[]
-- for the ingredient array, and binds LIMIT as $n. The parameter interface is:
--
--   q1  wanted text[], min_match int, row_limit int
--   q2  cuisine text, category text, max_total_minutes int, max_cost_usd numeric,
--       min_calories int, max_calories int, spice_level text, difficulty text,
--       min_rating numeric, want_vegetarian bool, want_vegan bool,
--       want_gluten_free bool, exclude_allergens text[], row_limit int
--   q3  user_query text, row_limit int
--
-- NULL always means "no constraint" in q2, so a filter is only applied when the
-- caller actually supplies a value.
-- ===========================================================================

-- ===========================================================================
-- q1 - reverse ingredient search ("what can I cook with these?")
--
-- Ranking problem. Salt, onion and garlic appear in 100% of the 9,997 recipes,
-- so counting shared ingredients - or a plain Jaccard ratio - produces thousands
-- of ties and a result list dominated by generic dishes. The fix is to weight
-- every match by its rarity (ingredient_stats.idf, computed by the ETL as
-- ln((N+1)/(df+1))+1) and to require a minimum number of matches. Because the
-- weight is 1.0 for the ubiquitous ingredients and up to 3.74 for rare ones,
-- matching "Tomato" is worth more than matching "Salt" three times over.
--
-- Access path: index scan on ingredients(canonical_id) for the handful of
-- wanted ingredients (idx_ingredients_canonical), hash aggregate by recipe_id,
-- primary-key lookups into recipes for the returned rows only (LIMIT 10).
--
-- Tie-break. Because salt/onion/garlic occur in every recipe, a request that
-- contains only such ingredients produces thousands of identical weighted
-- scores (try ARRAY['Tomato','Onion','Garlic'] to see the pathological case).
-- Equal scores are therefore broken by "how much of the recipe can I already
-- supply" (matched_ingredients / ingredient_count): with the same score, the
-- dish that needs fewer extra ingredients wins, which is also what a cook
-- expects from a search box.
-- ===========================================================================
WITH input AS (
    SELECT ARRAY['Tomato', 'Paneer', 'Cardamom']::text[] AS wanted,
           2::int                                       AS min_match,  -- of 3 wanted
           10::int                                      AS row_limit
),
wanted AS (
    SELECT m.canonical_id,
           m.canonical_name,
           s.idf
    FROM ingredient_master m
    JOIN ingredient_stats  s USING (canonical_id)
    CROSS JOIN input       p
    WHERE m.canonical_name = ANY (p.wanted)
),
matched AS (
    -- one row per (recipe, wanted ingredient); the source can repeat an
    -- ingredient inside a recipe, hence the GROUP BY
    SELECT i.recipe_id, w.canonical_id, w.idf
    FROM ingredients i
    JOIN wanted w USING (canonical_id)
    GROUP BY i.recipe_id, w.canonical_id, w.idf
),
scored AS (
    SELECT m.recipe_id,
           count(*)                                   AS matched_ingredients,
           sum(m.idf)                                 AS weighted_score,
           sum(m.idf) / NULLIF((SELECT sum(idf) FROM wanted), 0) AS coverage
    FROM matched m
    GROUP BY m.recipe_id
    HAVING count(*) >= (SELECT min_match FROM input)
)
SELECT r.recipe_id,
       r.recipe_name,
       r.cuisine,
       r.category,
       r.total_time_minutes,
       r.calories_per_serving,
       s.matched_ingredients,
       r.ingredient_count,
       round(s.matched_ingredients::numeric / r.ingredient_count, 3) AS matched_share,
       round(s.weighted_score, 3) AS weighted_score,
       round(s.coverage, 3)       AS coverage
FROM scored s
JOIN recipes r USING (recipe_id)
ORDER BY s.weighted_score DESC,
         s.matched_ingredients::numeric / r.ingredient_count DESC,
         r.ingredient_count,
         r.recipe_id
LIMIT (SELECT row_limit FROM input);

-- ===========================================================================
-- q2 - multi-condition filtering (the search page's filter panel)
--
-- Three design points that are easy to get wrong:
--
-- 1. Three-valued logic. A naive `AND (NOT p.want_vegetarian OR r.is_vegetarian)`
--    drops every row when the caller leaves the flag NULL, because NOT NULL is
--    NULL and NULL makes the whole conjunction unknown. Every optional flag is
--    therefore tested with `IS NOT TRUE`, which is true for NULL and false: an
--    absent filter never removes a recipe. The same reasoning applies to the
--    array: an empty or NULL array must disable exclusion instead of matching
--    nothing.
--
-- 2. NULL data vs "does not satisfy". Rows whose quantity could not be parsed
--    (8,940 placeholder lines) have no gram estimate, but that is a fact about
--    the data, not about the recipe's cost or calories: recipes.estimated_*
--    fields are always populated, so the range filters never silently drop a
--    recipe that merely has an incomplete ingredient line.
--
-- 3. Index-usable predicates. Comparisons are written as
--    `column <op> parameter` on bare columns (no function wrapping, no casts on
--    the indexed side) so that idx_recipes_cuisine_category_time can be used.
--    calories_per_serving is filtered on `recipes` (Part A guarantees it equals
--    nutrition.calories for all 9,997 recipes), which keeps the filter on the
--    indexed table; `nutrition` is only joined when its columns are displayed.
--
-- 4. Why the parameters sit in a FROM subquery and not in a WITH clause. A
--    `(p.x IS NULL OR col = p.x)` predicate can only become an index condition
--    if the planner can fold it to a constant. With a CTE that is referenced
--    more than once this never happens (PostgreSQL does not inline it), and the
--    result is a sequential scan with a join filter - visible in the 10k-row
--    EXPLAIN captured in docs/load_verification.md. A subquery in FROM is pulled
--    up instead, so `(NULL IS NULL OR col = 'x')` folds to `col = 'x'` and the
--    index is used. The API layer achieves the same effect by appending only the
--    predicates the caller actually supplied (the usual pattern for filter
--    panels); bound parameters ($1, $2 ...) cannot be folded, so a driver that
--    passes NULL for "unset" would de-index the query.
--
-- Access path: BitmapIndexScan on idx_recipes_veg_gf_time (vegetarian and
-- gluten free supplied) or on idx_recipes_cuisine_category_time (cuisine and
-- category supplied, no dietary flag), then primary-key joins, then sort by
-- rating. With no selective filter at all the plan falls back to a sequential
-- scan, which is the correct plan for a filter that matches most of the table.
-- ===========================================================================
SELECT r.recipe_id,
       r.recipe_name,
       r.cuisine,
       r.category,
       r.difficulty,
       r.spice_level,
       r.total_time_minutes,
       r.estimated_cost_usd,
       r.calories_per_serving,
       r.rating,
       r.review_count,
       a.allergens
FROM recipes r
JOIN recipe_allergens a USING (recipe_id)
-- parameter row: one row, literals only, so every predicate folds at plan time
CROSS JOIN (
    SELECT 'Indian'::text        AS cuisine,          -- NULL = any
           NULL::text            AS category,         -- NULL = any
           90::int               AS max_total_minutes,
           10.00::numeric        AS max_cost_usd,
           200::int              AS min_calories,
           600::int              AS max_calories,
           'Medium'::text        AS spice_level,
           NULL::text            AS difficulty,
           4.0::numeric          AS min_rating,
           true::boolean         AS want_vegetarian,  -- NULL = no constraint
           NULL::boolean         AS want_vegan,
           true::boolean         AS want_gluten_free,
           ARRAY['peanut', 'shellfish']::text[] AS exclude_allergens
) p
WHERE (p.cuisine           IS NULL OR r.cuisine       =  p.cuisine)
  AND (p.category          IS NULL OR r.category      =  p.category)
  AND (p.spice_level       IS NULL OR r.spice_level   =  p.spice_level)
  AND (p.difficulty        IS NULL OR r.difficulty    =  p.difficulty)
  AND (p.max_total_minutes IS NULL OR r.total_time_minutes <= p.max_total_minutes)
  AND (p.max_cost_usd      IS NULL OR r.estimated_cost_usd <= p.max_cost_usd)
  AND (p.min_calories      IS NULL OR r.calories_per_serving >= p.min_calories)
  AND (p.max_calories      IS NULL OR r.calories_per_serving <= p.max_calories)
  AND (p.min_rating        IS NULL OR r.rating               >= p.min_rating)
  AND (p.want_vegetarian   IS NOT TRUE OR r.is_vegetarian)
  AND (p.want_vegan        IS NOT TRUE OR r.is_vegan)
  AND (p.want_gluten_free  IS NOT TRUE OR r.is_gluten_free)
  AND NOT EXISTS (
        SELECT 1
        FROM unnest(COALESCE(p.exclude_allergens, ARRAY[]::text[])) AS x (tag)
        WHERE CASE x.tag
                  WHEN 'gluten'    THEN a.has_gluten
                  WHEN 'milk'      THEN a.has_milk
                  WHEN 'egg'       THEN a.has_egg
                  WHEN 'fish'      THEN a.has_fish
                  WHEN 'shellfish' THEN a.has_shellfish
                  WHEN 'tree_nuts' THEN a.has_tree_nuts
                  WHEN 'sesame'    THEN a.has_sesame
                  WHEN 'soy'       THEN a.has_soy
                  WHEN 'mustard'   THEN a.has_mustard
                  WHEN 'peanut'    THEN a.has_peanut
                  ELSE false
              END
      )
ORDER BY r.rating DESC, r.review_count DESC, r.recipe_id
LIMIT 20;  -- page size (the API binds this as $n)

-- ===========================================================================
-- q3 - full-text search over the composite document
--
-- Why not search the recipe name (or the steps) alone: the 84,616 step texts are
-- only 20 template sentences, so they carry almost no signal, and the names use
-- vocabulary users do not type ("Biryani", "Karahi"). The searched text is
-- therefore the concatenated document built by the ETL (name + cuisine +
-- category + cooking method + ingredient names + steps), which makes both
-- "chicken curry" and "Pakistani" productive queries.
--
-- The index (idx_search_document_fts) is on the expression
-- to_tsvector('english', search_document). The WHERE clause must repeat that
-- expression verbatim - same function, same configuration name - or the planner
-- cannot match it and silently falls back to a sequential scan.
--
-- Ranking: ts_rank with normalisation flag 32 (rank / (rank + 1)) keeps long
-- documents from winning on length alone. doc_length is stored so that a BM25-like
-- variant can be plugged in later
-- (rank * (k+1) / (rank + k * (1 - b + b * doc_length / avgdl))) without a schema change.
--
-- ts_headline is deliberately computed only for the top N rows (inside the final
-- SELECT, after the LIMIT): it re-parses the document and is by far the most
-- expensive part of the query, so it must never run over the whole table.
--
-- Access path: Bitmap Index Scan on idx_search_document_fts => sort by rank =>
-- LIMIT 20 => primary-key joins to recipes => ts_headline on 20 documents.
-- ===========================================================================
WITH input AS (
    SELECT 'chicken curry'::text AS user_query,
           20::int               AS row_limit
),
query AS (
    SELECT plainto_tsquery('english', user_query) AS tsq   -- user text cannot break the syntax
    FROM input
),
hits AS (
    SELECT d.recipe_id,
           ts_rank(to_tsvector('english', d.search_document), q.tsq, 32) AS rank
    FROM recipe_search_document d
    CROSS JOIN query q
    WHERE to_tsvector('english', d.search_document) @@ q.tsq
    ORDER BY rank DESC, d.recipe_id
    LIMIT (SELECT row_limit FROM input)
)
SELECT r.recipe_id,
       r.recipe_name,
       r.cuisine,
       r.category,
       r.total_time_minutes,
       round(h.rank::numeric, 5) AS rank,
       ts_headline('english', d.search_document, q.tsq,
                   'StartSel=<b>, StopSel=</b>, MaxWords=25, MinWords=8') AS headline
FROM hits h
JOIN recipes r                ON r.recipe_id = h.recipe_id
JOIN recipe_search_document d ON d.recipe_id = h.recipe_id
CROSS JOIN query q
ORDER BY h.rank DESC, r.recipe_id;
