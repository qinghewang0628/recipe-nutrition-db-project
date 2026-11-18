-- ===========================================================================
-- Equivalence check (Part B): are the four derived tables the same as Part A's?
--
-- scale/derive_missing_tables.sql rebuilds cuisine_category,
-- recipe_dietary_audit, recipe_search_document and ingredient_stats from the 7
-- tables Part A publishes on the medium and large tiers. The claim that the
-- scale run is still a fair test rests on that rebuild being exact, so prove it
-- on the one tier where both versions exist:
--
--   psql -h 127.0.0.1 -d recipe_scale -c 'DROP SCHEMA IF EXISTS t_base CASCADE; CREATE SCHEMA t_base;'
--   PGOPTIONS=--search_path=t_base psql -h 127.0.0.1 -d recipe_scale -f sql/schema.sql
--   (cd part_a && PGOPTIONS=--search_path=t_base psql -h 127.0.0.1 -d recipe_scale -f sql/load_clean.sql)
--   PGOPTIONS=--search_path=t_small psql -h 127.0.0.1 -d recipe_scale \
--       -f sql/schema.sql -f ../scale/load_ingredient_master.sql \
--       -f ../part_a/sql/load_small.sql -f ../scale/derive_missing_tables.sql
--   psql -h 127.0.0.1 -d recipe_scale -f scale/check_equivalence.sql
--
-- t_base holds Part A's 11 published tables at x1, t_small holds the 7
-- published ones plus the 4 derived ones. Every count must be 0.
-- ---------------------------------------------------------------------------
\set ON_ERROR_STOP on
\pset footer off

\echo 'derived tables vs Part A tables at x1: rows differing in each direction (expect 0)'
SELECT 'cuisine_category' AS table_name,
       (SELECT count(*) FROM t_base.cuisine_category)  AS rows_part_a,
       (SELECT count(*) FROM t_small.cuisine_category) AS rows_derived,
       (SELECT count(*) FROM (TABLE t_base.cuisine_category
                              EXCEPT ALL TABLE t_small.cuisine_category) d) AS only_part_a,
       (SELECT count(*) FROM (TABLE t_small.cuisine_category
                              EXCEPT ALL TABLE t_base.cuisine_category) d) AS only_derived
UNION ALL
SELECT 'ingredient_stats',
       (SELECT count(*) FROM t_base.ingredient_stats),
       (SELECT count(*) FROM t_small.ingredient_stats),
       (SELECT count(*) FROM (TABLE t_base.ingredient_stats
                              EXCEPT ALL TABLE t_small.ingredient_stats) d),
       (SELECT count(*) FROM (TABLE t_small.ingredient_stats
                              EXCEPT ALL TABLE t_base.ingredient_stats) d)
UNION ALL
SELECT 'recipe_dietary_audit',
       (SELECT count(*) FROM t_base.recipe_dietary_audit),
       (SELECT count(*) FROM t_small.recipe_dietary_audit),
       (SELECT count(*) FROM (TABLE t_base.recipe_dietary_audit
                              EXCEPT ALL TABLE t_small.recipe_dietary_audit) d),
       (SELECT count(*) FROM (TABLE t_small.recipe_dietary_audit
                              EXCEPT ALL TABLE t_base.recipe_dietary_audit) d)
UNION ALL
SELECT 'recipe_search_document',
       (SELECT count(*) FROM t_base.recipe_search_document),
       (SELECT count(*) FROM t_small.recipe_search_document),
       (SELECT count(*) FROM (TABLE t_base.recipe_search_document
                              EXCEPT ALL TABLE t_small.recipe_search_document) d),
       (SELECT count(*) FROM (TABLE t_small.recipe_search_document
                              EXCEPT ALL TABLE t_base.recipe_search_document) d);
