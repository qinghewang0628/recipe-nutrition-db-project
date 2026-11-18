# Video Demonstration: Complete Walkthrough

Person A, Data Engineering. This document defines the full demonstration
process for the data engineering part of the group video. It states, for
every function and every piece of content, the exact demonstration steps,
the required on-screen evidence and the point the viewer should take away.

Companion file: `presentation_script.md` (the verbatim English script).

---

## 1. Scope and deliverable

The group video is 5–8 minutes. Person A's segment is a 60–90 second
section, designed here at 87 seconds, covering three items required by the
division of labour:

1. the data source and the overall quality conclusion;
2. the before/after comparison — label conflicts, unit parsing, duplicate
   removal and clipping;
3. the one-command ETL rebuild.

Performance charts, query plans and the reproduced paper are presented by
other members. Person D assembles the final video and publishes the link.

---

## 2. Recording environment

| Item | Setting |
|---|---|
| Recorder | OBS Studio, Zoom or Loom screen recording |
| Resolution | 1920 x 1080, terminal font at least 20 pt |
| Terminal | UTF-8; no notifications; no animated cursor trail |
| Working directory | Repository root |
| Python | 3.9+ standard library only |

The canonical command is `python make.py seed`. On Windows CMD or PowerShell,
`make seed` also works through the supplied `make.bat`; on a machine with
GNU make, the `Makefile` is used. All three routes call the same driver.

**Pre-recording check** — run once and confirm no errors:

```bash
python make.py help     # prints the target list
python make.py seed     # confirm the final line: 50/50 PASS, 0 FAIL
python make.py test     # 25 unit tests + 50 assertions
python make.py demo      # print the before/after table
```

Never record before this check succeeds. The rebuild takes about 90–130
seconds on the development machine; the 20x tier dominates. Record the
entire run as one raw take and compress time in editing.

---

## 3. Function-to-demonstration map

This is the master table. Each row names a function or content item, the
demonstration steps, the display focus and the evidence file.

| # | Function / content | Demonstration steps | Display focus | Evidence |
|---:|---|---|---|---|
| 1 | Data source | Open `../archive-datasets/`; show five CSVs and their sizes; run `python make.py demo` | Five files, 208,523 rows, 9,997 recipes; raw files are read-only | `docs/profile_metrics.md` section 1 |
| 2 | Overall quality conclusion | Open `docs/profile_metrics.md` section 2; highlight the consistency table | Structurally perfect, semantically unreliable — zero nulls / zero duplicates / zero orphan keys, but 12,190 conflicts | `docs/profile_metrics.md`, `data/profile/profile_raw.json` |
| 3 | Dietary label conflicts | Open section 2.1; show the four-row conflict table; open `data/mappings/dietary_rules.csv` | 12,190 total / 7,952 recipes / 10,862 corrected / 1,328 retained as unverifiable | `recipe_dietary_audit.csv`, `dietary_rules.csv` |
| 4 | Unverifiable field policy | Show `is_halal_verifiable=false` in `data/clean/recipes.csv` and `halal_proxy` in the audit table | The project does not convert an unverifiable inference into a fact | `docs/cleaning_rules.md` R1 |
| 5 | Quantity parsing | Split screen: raw `quantity` column on the left, `qty_*` columns on the right; show `unit_conversion.csv` | 1,517 strings -> value + unit -> g / ml / piece + placeholder codes | `data/mappings/unit_conversion.csv`, `data/clean/ingredients.csv` |
| 6 | Duplicate consolidation | Open `data/profile/quality_summary.csv`; show `RCP00004` before and after | 103,908 -> 95,912 rows; 7,996 surplus rows removed; audit columns retained | `quality_summary.csv`, `ingredients.csv` |
| 7 | Outlier treatment | Open `data/profile/clipped_recipes.csv`; show `RCP00043` | 143 recipes; 1,200 g/serving cap; proportional scaling with an audit record | `clipped_recipes.csv` |
| 8 | Lookup tables and column dictionary | List `data/mappings/`, open `docs/data_dictionary.md` | Four lookup tables and a fixed column contract for downstream work | `data/mappings/`, `docs/data_dictionary.md` |
| 9 | Cleaned output | List `data/clean/` (11 CSVs) | Eleven tables ready for schema, index and query work | `docs/profile_metrics.md` section 4 |
| 10 | Scale tiers | List `data/scales/`; show `docs/scale_datasets.md` | 9,997 / 49,985 / 199,940 recipes; synthetic, for scalability only | `data/scales/scales_manifest.json` |
| 11 | SQL loaders and manifest | Open `sql/load_clean.sql`; open `data/manifest.json` | `psql \copy` loaders, per-file SHA-256 and row counts | `sql/`, `data/manifest.json` |
| 12 | One-command rebuild | Type and execute `python make.py seed` in a full-screen terminal | Eight STEP lines, real terminal output, `50/50 PASS` at normal speed | `etl/pipeline.py`, `Makefile` |
| 13 | Correctness verification | Hold the STEP 8 output; optionally show `docs/verification_report.md` | 50 executable assertions, 25 unit tests, zero failures | `docs/verification_report.md` |
| 14 | Reproducibility | Show the idempotency assertion from `python make.py test` | Two independent rebuilds are byte-identical; fixed seed 20261116 | `tests/test_pipeline.py`, `verification_report.md` |
| 15 | Handoff | Open `docs/handoff.md`; end on the `NEXT -> Person B` card | Clean data and IDF weights pass to the index and query stage | `docs/handoff.md` |

---

## 4. Shot-by-shot runbook for the 87-second segment

### Shot 0 — 0:00–0:02 — Title card

Static card: "Person A | Data Engineering / DSC5003 Group Project". No speech.
**Focus:** identify the speaker and the segment boundary.

### Shot 1 — 0:02–0:20 — Data source and quality conclusion

| Time | Action | Required on-screen evidence |
|---|---|---|
| 0:02–0:08 | Open the file manager on `../archive-datasets/` | Five CSVs, about 9.8 MB in total |
| 0:08–0:14 | Run `python make.py demo` | "Raw rows 208,523 / 5 CSV", "Empty cells 0" |
| 0:14–0:20 | Open `docs/profile_metrics.md` section 2 | Orphan ids 0/0/0; cuisine counts 5/5; prep + cook = total 9,997/9,997 |

**Focus:** the contrast between structural integrity and semantic defects.
On-screen caption: "Structure: PASS / Semantics: FAIL".

### Shot 2 — 0:20–0:38 — Dietary label conflicts

| Action | Required on-screen evidence |
|---|---|
| Open `docs/profile_metrics.md` section 2.1 | Four rows 5,863 / 3,259 / 1,740 / 1,328; total 12,190; 7,952 recipes (79.5%) |
| Open `data/mappings/dietary_rules.csv` | The `is_halal` row with `verifiable=false` and its conflict policy |
| Open the first rows of `data/clean/recipe_dietary_audit.csv` | `is_halal_raw`, `halal_proxy`, `conflict_count`, `conflict_flags` |

**Focus:** distinguish 12,190 (all four flags) from 10,862 (the three
corrected flags). The 1,328 difference is `is_halal` and was **not**
corrected. Caption: "Corrected 10,862 / is_halal unverifiable".

### Shot 3 — 0:38–0:48 — Quantity parsing

Split screen. Left: the raw `quantity` column (`933g`, `299 g`, `4 tbsp`,
`3 cloves`, `to taste`). Right: `qty_value`, `qty_unit_norm`,
`qty_dimension`, `qty_canonical_value`, `qty_canonical_unit`,
`qty_approx_g`, `qty_placeholder_code`. Overlay `unit_conversion.csv`.

**Focus:** 1,517 distinct strings collapse to three dimensions plus
placeholder codes. Caption: "1,517 -> g / ml / piece + TO_TASTE".

### Shot 4 — 0:48–1:02 — Consolidation and clipping

| Action | Required on-screen evidence |
|---|---|
| Open `data/profile/quality_summary.csv` | 103,908 -> 95,912; 7,996 -> 0; 143 -> 0 |
| Show the `RCP00004` example | Two `All-Purpose Flour` rows (`293 g`, `474 g`) merge to `Wheat Flour`, `767 g`, `merged_row_count = 2` |
| Open `data/profile/clipped_recipes.csv` | `RCP00043: 1363.50 -> 1200`, factor 0.880088 |

**Focus:** merging preserves mass and an audit trail; clipping preserves
recipe proportions and the exact scale-tier multiples. Caption:
"1,200 g/serving cap".

### Shot 5 — 1:02–1:25 — One-command rebuild

1. Within the first two seconds, type `python make.py seed` and press Enter.
   The command itself must be legible for at least one second.
2. Show STEP 1–3 at normal speed for 2–3 seconds; for STEP 4–7 use 2x speed
   with three cuts, retaining a 0.5-second still frame on "STEP 4/8 Clean"
   and "STEP 6/8 Build three scale tiers".
3. Return to normal speed for STEP 8. Hold `50/50 PASS, 0 FAIL` for at least
   two seconds.
4. Finish with a three-panel cut: `data/clean/` (11 CSVs),
   `data/mappings/` (4 CSVs), `data/scales/` (small / medium / large).
5. During the line about determinism, overlay
   `test_two_rebuilds_are_byte_identical ... ok`.
6. During the handoff line, show `data/clean/ingredient_stats.csv`:
   Garlic / Onion / Salt `idf = 1` (`df = 9,997`), Tomato
   `idf = 3.737794` (`df = 646`).

**Focus:** everything shown earlier is reproducible from one real command.
The final PASS line must be genuine terminal output. Acceleration and cuts
are allowed; static screenshots or a fabricated PASS line are not.

### Shot 6 — 1:25–1:27 — Handoff card

"NEXT -> Person B | Database Design and Core Queries". No speech.

---

## 5. Extended demonstration for reviewers

If a reviewer asks to see every function rather than the 87-second cut,
walk through the following in order. Each item lists the command, the evidence
and the point to emphasise.

| Order | Item | Command / action | Emphasis |
|---:|---|---|---|
| 1 | Raw integrity | `python make.py demo` | Input checksums match; raw files are never modified |
| 2 | Raw profile | Open `data/profile/profile_raw.json` | Machine-readable field-level statistics |
| 3 | Column dictionary | `python make.py dictionary` | Generated from code; downstream column contract |
| 4 | Lookup tables | `python make.py mappings` | 113 synonyms, 57 canonical ids, 10 allergen classes, 10 unit factors |
| 5 | Cleaning | `python make.py clean-data` | STEP 4 log: 103,908 -> 95,912; 143 clipped; 10,862 corrected |
| 6 | Before/after metrics | Open `docs/profile_metrics.md` section 3 | Every figure quoted in the report and video |
| 7 | Clipping audit | Open `data/profile/clipped_recipes.csv` | Per-recipe before value, after value and factor |
| 8 | Scale tiers | `python make.py scale` | Deterministic 1x / 5x / 20x expansion |
| 9 | Loaders and manifest | `python make.py seed-sql` | `psql \copy` scripts and per-file SHA-256 |
| 10 | Verification | `python make.py verify` | Six groups, 50 executable assertions |
| 11 | Unit tests | `python make.py test` | 25 tests, including byte-identical rebuilds |
| 12 | Archiving | `python make.py pack` / `unpack` | GitHub 50 MB warning handled by .csv.gz archives |
| 13 | Optional database load | `python make.py load DATABASE_URL=...` | Requires Person B's `schema.sql`; not part of the recorded segment |

---

## 6. Post-recording checklist

- [ ] Total duration is between 60 and 90 seconds (target 87 s), with a 2 s
      title card and a 2 s handoff card.
- [ ] Five CSVs, 208,523 rows and 9,997 recipes appear in Shot 1.
- [ ] 12,190 / 7,952 / 10,862 are legible, and `is_halal` is described as
      retained and unverifiable, never as corrected.
- [ ] 1,517 -> g / ml / piece + TO_TASTE appears in Shot 3.
- [ ] 103,908 -> 95,912, 7,996 -> 0, 143 -> 0 and 1,200 g appear in Shot 4.
- [ ] The rebuild command is visible; STEP 8 and `50/50 PASS` are shown at
      normal speed.
- [ ] The handoff to Person B appears at the end.
- [ ] No claim that the corpus contains real recipes; no claim that
      `is_halal` was corrected.
- [ ] Subtitle numbers match `docs/profile_metrics.md` exactly; 12,190 and
      10,862 are not confused.

---

## 7. Material handed to Person D

| Item | Purpose |
|---|---|
| `personA_raw.mp4` | Unedited recording, kept for re-cutting |
| `presentation_script.md` | Verbatim script and subtitle text |
| `demo_walkthrough.md` | This runbook, for editing and review |
| Figure 3-2, Table 3-3, Figure 3-3, Figure 3-4 | Charts, drawn per `docs/data_profile.md` section 7 |
| Final 87-second cut | To be inserted into the 5–8 minute group video |
| Public video URL | To be written into the group report's deliverables section |

The video must be uploaded to Google Drive, Dropbox or OneDrive with an
accessible link, and that link must appear in the final group report.
