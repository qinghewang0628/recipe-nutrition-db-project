# Handoff Contracts

Person A to Persons B, C and D. This document fixes the interfaces so that
downstream work does not depend on assumptions about the cleaned data.

---

## 0. Data flow at a glance

```
archive-datasets/*.csv  (5 files, read-only)
   -> etl/clean.py -> data/clean/*.csv (11 tables)
   -> etl/scale.py -> data/scales/{small,medium,large}/
   -> etl/seed.py  -> sql/load_*.sql, data/manifest.json
   -> etl/verify.py -> docs/verification_report.md
```

---

## 1. To Person B (database design and core queries)

### Immediately usable

- `data/clean/` — eleven CSV tables with a header row, UTF-8 encoding,
  lowercase booleans and no embedded newlines.
- `docs/data_dictionary.md` — logical types, key roles, nullability, domains
  and source transforms for every column.
- `data/mappings/` — four lookup tables plus the machine-readable column
  dictionary.
- `sql/load_clean.sql` and `sql/load_<tier>.sql` — `psql \copy` loaders.
- `data/scales/` — three tiers for indexed vs unindexed experiments.
- `data/clean/ingredient_stats.csv` — `doc_freq` and `idf` weights.

### Six rules B must observe

1. Reference ingredients only by `canonical_id`. `ingredient_name_raw` is
   audit-only; 58 raw names collapse to 57 canonical ids.
2. Use `ingredient_stats.idf` for rarity-weighted overlap scoring. Common
   ingredients (Salt, Onion, Garlic) have `idf = 1`; Tomato has
   `idf = 3.737794` with `doc_freq = 646`.
3. Use `recipe_allergens.has_*` for allergen exclusion. 9,132 recipes carry
   at least one of the ten classes.
4. Use `recipe_search_document.search_document` for full-text indexing;
   `doc_length` supports BM25 length-normalisation experiments.
5. Do not use `recipe_steps.estimated_time_minutes` as a duration metric.
   Use `prep_time_minutes + cook_time_minutes = total_time_minutes`.
6. Do not treat `is_halal` as corrected. It is retained from the source with
   `is_halal_verifiable = false`; only the proxy is in the audit table.

If `schema.sql` uses different table names, edit `TABLE_MAP` in
`etl/seed.py` and rerun `make seed` to regenerate the loaders.

### Limits on scale tiers

Synthetic expansion supports index-scalability and execution-plan comparison
only. It must not be used for accuracy, nutrition, or absolute comparison
with the paper's results. State results as relative speed-up on this
project's synthetic expansion.

---

## 2. To Person C (backend and business logic)

- Use `qty_canonical_value` together with `qty_canonical_unit` for any
  display of quantity. `qty_approx_g` is an approximate cross-dimension
  value for shopping lists, cost roll-ups and outlier detection only.
- Never compute nutrition from quantities. Take all nutrition values from
  `recipe_nutrition.csv`; `calories_per_serving` and `nutrition.calories`
  are consistent for all 9,997 recipes.
- Placeholder quantities (`qty_is_placeholder = true`) have empty numeric
  fields and a code in `qty_placeholder_code`. Render the code, not a zero.
- Dietary flags are computed under explicit conventions documented in
  `docs/cleaning_rules.md` R1. Do not describe them as authoritative
  dietary advice.
- `merged_row_count`, `merged_units`, `quantity_raw` and `is_*_raw` are audit
  columns; expose them only in an audit or detail view.
- `recipe_dietary_audit.csv` is the source for any conflict visualisation.

---

## 3. To Person D (integration and submission)

### Report

- The English final report for Part A is `report/PartA_Final_Report.docx`
  with a Markdown source at `report/PartA_Final_Report.md`.
- Figures and tables should follow the list in `docs/data_profile.md`
  section 7, with consistent captions and a stated data source.
- Every numeric claim must trace to `docs/profile_metrics.md`.

### Video

- `video/demo_walkthrough.md` is the full demonstration runbook.
- `video/presentation_script.md` is the 87-second verbatim English script.
- Person A's segment covers data source and quality conclusions, the
  before/after comparison, and the one-command rebuild. Performance charts
  belong to Person B's segment.
- Upload the final video to a publicly accessible drive and place the link
  in the group report's deliverables section.

### GitHub

- Raw course CSVs are excluded by `.gitignore` (licence unconfirmed). Only
  `data/raw/MANIFEST.sha256` and `NOTICE.md` are committed.
- Three scale CSVs above 50 MB are committed as `.csv.gz`. Run
  `make unpack` after cloning, or `make scale` to rebuild.
- Confirm the dataset licence with the instructor before making the
  repository public.

---

## 4. Reproduction for any reviewer

```bash
# 1. Place the five course CSVs in ../archive-datasets/ or data/raw/
# 2. From the repository root:
python make.py seed
python make.py test
# 3. Optional: after schema.sql has been applied,
python make.py load DATABASE_URL=postgres://user:pwd@localhost:5432/recipes
```

`data/manifest.json` lists row counts, byte counts and SHA-256 values for
every output, so a reviewer can confirm an exact reconstruction.

---

## 5. Explicitly out of scope for Person A

`schema.sql`, index definitions, the three core SQL queries, execution plans,
the API layer, the front end, the merged group report and the final video
assembly belong to Persons B, C and D. This package supplies their inputs
and the contracts above, not those artefacts.
