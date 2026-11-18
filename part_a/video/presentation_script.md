# Presentation Script — Person A (Data Engineering)

Verbatim English script for the 87-second segment. Read at a steady
160 words per minute. The timeline, on-screen evidence and subtitle text are
aligned with `demo_walkthrough.md`; every spoken number is traceable to
`docs/profile_metrics.md`.

| Item | Value |
|---|---|
| Designed duration | 87 s (2 s title + 83 s speech and pauses + 2 s handoff) |
| Net speech | 81.3 s at 2.6 words/s |
| Words | 206 spoken words, plus numeric tokens |
| Language | English throughout |
| Companion runbook | `video/demo_walkthrough.md` |
| Group video | 5–8 min; this is Person A's 60–90 s segment |

---

## 1. Segment map

| Division-of-labour item | Part | Time | Words | Primary evidence |
|---|---|---|---:|---|
| Data source and overall quality conclusion | 1 | 0:02–0:20 | 43 | `docs/profile_metrics.md` sections 1 and 2 |
| Before/after: label conflicts | 2A | 0:20–0:38 | 42 | section 2.1, `recipe_dietary_audit.csv` |
| Before/after: unit parsing | 2B | 0:38–0:48 | 26 | `unit_conversion.csv`, `ingredients.csv` |
| Before/after: deduplication and clipping | 2C | 0:48–1:02 | 32 | `quality_summary.csv`, `clipped_recipes.csv` |
| One-command ETL rebuild | 3 | 1:02–1:25 | 63 | Live `python make.py seed`, `50/50 PASS` |

---

## 2. Timeline, screen action and subtitles

| Time | Screen action | Verbatim speech | Subtitle / overlay |
|---|---|---|---|
| **0:00–0:02** | Title card: "Person A \| Data Engineering / DSC5003 Group Project" | *(silence)* | Person A \| Data Engineering |
| **0:02–0:20** | File manager shows five CSVs; `python make.py demo`; then `docs/profile_metrics.md` section 2 | Hello, I am Person A, responsible for data engineering. The input is five course CSVs: 208,523 rows and 9,997 recipes. Structurally it is clean: zero nulls, zero duplicates, zero orphan keys. Semantically it is not; labels, quantities and ingredient sets must be rebuilt. | `5 CSV · 208,523 rows · 9,997 recipes` / `Structure: PASS · Semantics: FAIL` |
| **0:20–0:38** | Section 2.1 conflict table; `dietary_rules.csv`; first rows of `recipe_dietary_audit.csv` | First, dietary labels. Comparing four flags with the ingredient lists found 12,190 conflicts in 7,952 recipes. We recomputed the three verifiable flags, correcting 10,862 values. The halal flag lacks certification data, so we kept the source value and marked it as unverifiable. | Bar chart: `5,863 / 3,259 / 1,740 / 1,328` / `Corrected 10,862` / `is_halal_verifiable = false` |
| **0:38–0:48** | Split screen: raw `quantity` column vs `qty_*` columns; `unit_conversion.csv` below | Second, quantities. 1,517 free-text strings across six units were parsed into value and unit, normalised to grams, millilitres and pieces, with placeholders coded as TO_TASTE. | `1,517 strings -> g / ml / piece + TO_TASTE` |
| **0:48–1:02** | `data/profile/quality_summary.csv`; `RCP00004` merge example; `clipped_recipes.csv` row for `RCP00043` | Third, consolidation. 7,996 surplus duplicate ingredient rows are gone, and detail falls from 103,908 to 95,912 rows. 143 recipes above 1,200 grams per serving were scaled proportionally, with a full audit record. | `103,908 -> 95,912` / `7,996 -> 0` / `143 -> 0` / `cap: 1,200 g/serving` |
| **1:02–1:25** | Full-screen terminal running `python make.py seed`; STEP 1–7 accelerated, STEP 8 and the PASS line at normal speed; then the three directory listings | All of this comes from one command. I will run make seed now. Eight steps produce eleven clean tables, four lookup tables and three scale tiers. The final step runs fifty correctness assertions; all fifty pass. With a fixed seed, two independent rebuilds are byte-identical. The clean data and IDF weights now go to Person B for the index experiments. Over to him. | `python make.py seed` -> `8 STEP` -> `50/50 PASS` -> `idempotent` / `ingredient_stats.idf` |
| **1:25–1:27** | "NEXT -> Person B \| Database Design and Core Queries" | *(silence)* | NEXT -> Person B |

---

## 3. Number-to-evidence verification

Every spoken number must match the screen and the data source. Do not
change a subtitle without changing the source metric.

| # | Spoken | On screen | Evidence / command | Data source |
|---:|---|---|---|---|
| 1 | five course CSVs | 5 CSV | File manager | `../archive-datasets/` |
| 2 | 208,523 rows | 208,523 | `python make.py demo` | `profile_raw.json: cross_checks.total_rows` |
| 3 | 9,997 recipes | 9,997 | `python make.py demo` | `recipes_master.csv` row count |
| 4 | zero nulls / duplicates / orphan keys | 0 / 0 / 0 | `docs/profile_metrics.md` section 2 | `empty_cells_total`, `referential_integrity` |
| 5 | 12,190 conflicts | 12,190 | section 2.1 total row | 5,863 + 3,259 + 1,740 + 1,328 |
| 6 | 7,952 recipes | 7,952 (79.5%) | section 2.1 total row | `dietary_conflict_recipes` |
| 7 | four flags | 5,863 / 3,259 / 1,740 / 1,328 | Bar chart (Figure 3-2) | `dietary_conflicts` |
| 8 | correcting 10,862 values | 10,862 | `recipe_dietary_audit.csv` conflict sum | `dietary_conflict_verifiable_labels` |
| 9 | halal unverifiable | `is_halal_verifiable=false` | `dietary_rules.csv`, `recipes.csv` | `docs/cleaning_rules.md` R1 |
| 10 | 1,517 free-text strings | 1,517 | Raw `quantity` column | `distinct_quantity_strings` |
| 11 | six units | `g / ml / tbsp / tsp / cloves / medium` | `unit_conversion.csv` | `quantity_unit_distribution` |
| 12 | grams / millilitres / pieces | `g / ml / piece` | `qty_canonical_unit` | `docs/data_dictionary.md` |
| 13 | TO_TASTE | `TO_TASTE` (8,940 rows) | `qty_placeholder_code` | `quality_summary.csv` |
| 14 | 7,996 surplus rows | 7,996 -> 0 | `quality_summary.csv` | `duplicate_ingredient_extra_rows` |
| 15 | 103,908 to 95,912 | 103,908 -> 95,912 | `quality_summary.csv` | `profile_raw / profile_clean.row_counts.ingredients` |
| 16 | 143 recipes | 143 | `clipped_recipes.csv` row count | `approx_g_per_serving.recipes_over_cap` |
| 17 | 1,200 grams per serving | `1,200 g/serving` | `RCP00043: 1363.50 -> 1200` | `config.CAP_G_PER_SERVING` |
| 18 | one command / eight steps | `python make.py seed` / `STEP 1..8` | Live terminal | `Makefile`, `etl/pipeline.py` |
| 19 | eleven / four / three | 11 / 4 / 3 | Three directory listings | `data/manifest.json` |
| 20 | fifty assertions, all pass | **50/50 PASS** | STEP 8 held for 2 s | `docs/verification_report.md` |
| 21 | byte-identical rebuilds | `idempotent` | `python make.py test` | `tests/test_pipeline.py` |
| 22 | IDF weights to Person B | `ingredient_stats.idf` | Handoff card | `data/clean/ingredient_stats.csv` |

---

## 4. Teleprompter text

Read continuously at an even pace. The `|` marks a shot change or a breath;
do not read it aloud.

```
[0:02] Hello, I am Person A, responsible for data engineering. The input
is five course CSVs: 208,523 rows and 9,997 recipes. Structurally it is
clean: zero nulls, zero duplicates, zero orphan keys. Semantically it is
not; labels, quantities and ingredient sets must be rebuilt. |

[0:20] First, dietary labels. Comparing four flags with the ingredient
lists found 12,190 conflicts in 7,952 recipes. We recomputed the three
verifiable flags, correcting 10,862 values. The halal flag lacks
certification data, so we kept the source value and marked it as
unverifiable. |

[0:38] Second, quantities. 1,517 free-text strings across six units were
parsed into value and unit, normalised to grams, millilitres and pieces,
with placeholders coded as TO_TASTE. |

[0:48] Third, consolidation. 7,996 surplus duplicate ingredient rows are
gone, and detail falls from 103,908 to 95,912 rows. 143 recipes above 1,200
grams per serving were scaled proportionally, with a full audit record. |

[1:02] All of this comes from one command. I will run make seed now. Eight
steps produce eleven clean tables, four lookup tables and three scale
tiers. The final step runs fifty correctness assertions; all fifty pass.
With a fixed seed, two independent rebuilds are byte-identical. The clean
data and IDF weights now go to Person B for the index experiments. Over
to him.
```

---

## 5. Delivery notes

1. Run `python make.py seed` successfully before recording. Keep one complete
   raw take; compress STEP 1–7 by acceleration and cuts only. STEP 8 and the
   `50/50 PASS` line must remain at normal speed and be genuine output.
2. Reading time varies with the machine. Do not state a runtime in the
   subtitles; `make seed` took 88–130 s in earlier runs and 377.6 s on the
   final English rebuild because of disk load.
3. Pronounce numbers clearly; subtitles always use Arabic numerals.
4. Keep the distinction between 12,190 and 10,862 explicit: the 1,328
   difference is `is_halal`, which was retained as unverifiable.
5. Never describe the dataset as real recipes, and never say the halal flag
   was corrected.
6. Do not read whole documents on screen. Highlight the single row or column
   that supports the sentence being spoken.
7. Hand the raw recording, this script, the runbook and the chart images to
   Person D, who assembles the group video and records its public URL in the
   final report.
