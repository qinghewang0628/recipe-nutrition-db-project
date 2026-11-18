-- ===========================================================================
-- ingredient_master for a scale tier.
--
-- The canonical vocabulary is tier independent: Part A resolves ingredient
-- names to the same 57 canonical ids for every scale factor, so the 10k-tier
-- master is the correct dimension for the medium (x5) and large (x20) tiers
-- too. It has to be loaded *before* the fact tables, because the foreign keys
-- in ingredients / ingredient_stats are checked at COMMIT of the load
-- transaction, which is earlier than the derivation step.
--
-- Run from part_a/ (the \copy path is relative):
--   PGOPTIONS='--search_path=t_large' psql -d recipe_scale -f ../scale/load_ingredient_master.sql
-- ===========================================================================
\set ON_ERROR_STOP on
\copy ingredient_master FROM 'data/clean/ingredient_master.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

\echo 'loaded ingredient_master rows:'
SELECT count(*) AS ingredient_master_rows FROM ingredient_master;
