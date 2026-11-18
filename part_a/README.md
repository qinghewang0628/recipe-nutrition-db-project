# Smart Recipe and Nutrition Retrieval System — Part A: Data Engineering

DSC5003 Storing and Retrieving Data, Group Project.
Final English delivery package for Person A (Data Engineering).

This directory is a self-contained GitHub-ready submission. It contains the
source code, SQL loaders, cleaned datasets, technical documentation, the
final report and the video demonstration material for the data engineering
part of the project.

---

## 1. What this package delivers

| Deliverable | Location |
|---|---|
| Field profile and quality metrics | `docs/data_profile.md`, `docs/profile_metrics.md` |
| Column dictionary | `docs/data_dictionary.md`, `data/mappings/field_dictionary.csv` |
| ETL and cleaning code | `etl/` (12 functional modules plus `__init__.py`, Python standard library only) |
| Lookup tables | `data/mappings/` (synonyms, allergens, dietary rules, unit conversion) |
| Cleaned tables | `data/clean/` (11 tables) |
| Scale tiers for performance experiments | `data/scales/` (small 1x, medium 5x, large 20x) |
| One-command rebuild | `make seed` / `python make.py seed` |
| PostgreSQL loaders | `sql/load_clean.sql`, `sql/load_<tier>.sql` |
| Correctness verification | `tests/`, `etl/verify.py`, `docs/verification_report.md` |
| Final report | `report/PartA_Final_Report.docx` (and `.md` source) |
| Video demonstration | `video/demo_walkthrough.md`, `video/presentation_script.md` |

A file-by-file index with the purpose of every item is in
`DELIVERY_MANIFEST.md`.

---

## 2. Repository layout

```
partA-final-english/
├── Makefile                  GNU make targets
├── make.py                   Cross-platform build driver (single implementation)
├── make.bat                  Thin wrapper so `make seed` works in Windows CMD/PowerShell
├── requirements.txt          Dependency statement (stdlib only)
├── .gitignore
├── README.md                 This file
├── DELIVERY_MANIFEST.md      Complete file index
├── etl/                      Source code
│   ├── config.py             Paths, thresholds, seed, scale factors
│   ├── io_utils.py           CSV I/O, SHA-256, logging, atomic writes
│   ├── units.py              Quantity parsing and unit conversion
│   ├── mappings.py           Lookup table construction
│   ├── clean.py              Cleaning pipeline and derived tables
│   ├── profile.py            Field profiling and consistency checks
│   ├── dictionary.py         Column dictionary generation
│   ├── scale.py              Deterministic scale expansion
│   ├── seed.py               psql loaders and output manifest
│   ├── verify.py             Executable correctness assertions
│   ├── pack.py               Compress / restore large CSVs
│   └── pipeline.py           CLI orchestration
├── tests/                    Three unittest modules
├── sql/                      Four psql \copy loaders
├── data/
│   ├── raw/                  Raw checksum manifest and provenance notice
│   ├── mappings/             Four lookup tables + machine-readable dictionary
│   ├── clean/                Eleven cleaned tables
│   ├── profile/              Profile JSON, comparison table, audit and verification data
│   ├── scales/               Three scale tiers, their manifests and .csv.gz archives
│   └── manifest.json         Row counts, byte counts and SHA-256 for every output
├── docs/                     Technical documentation
├── report/                   Final report (docx and markdown)
└── video/                    Demonstration runbook and script
```

---

## 3. Environment

| Item | Requirement |
|---|---|
| Python | 3.9 or newer (tested on 3.13) |
| Third-party packages | None |
| Encoding | UTF-8 throughout |
| Operating system | Windows, macOS, Linux (`pathlib` only, no absolute paths) |
| Optional | `psql` for `make load`; the database schema is supplied by Person B |
| Raw input | The five course CSVs in `../archive-datasets/` or `data/raw/` |

The raw CSVs are not committed because the course bundle contains no licence
or provenance statement. Only their SHA-256 values are committed. See
`data/raw/NOTICE.md` and `docs/data_sources_and_license.md`.

---

## 4. Running the code

```bash
python make.py seed          # full eight-step rebuild, works on every platform
make seed                    # same, via GNU make or make.bat on Windows
make test                    # unit tests + correctness verification
make demo                    # print the before/after numbers used in the video
make pack                    # compress scale CSVs above 50 MB
make unpack                  # restore them after cloning
```

`make seed` is idempotent. With the same inputs and the fixed
`config.RANDOM_SEED = 20261116`, two independent rebuilds produce
byte-identical outputs; `make test` asserts this explicitly.

The eight steps are: (1) lookup tables, (2) column dictionary, (3) raw
profile, (4) cleaning, (5) cleaned profile and comparison, (6) three scale
tiers, (7) psql loaders and manifest, (8) correctness verification.

### Where to look

| Question | File |
|---|---|
| What changed during cleaning? | `docs/profile_metrics.md` section 3, `data/profile/quality_summary.csv` |
| What does a column mean? | `docs/data_dictionary.md` |
| Is the data fit for use? | `docs/data_profile.md` |
| Where did the data come from? | `docs/data_sources_and_license.md` |
| Why was a rule chosen? | `docs/cleaning_rules.md` |
| How were the scale tiers built? | `docs/scale_datasets.md` |
| Did verification pass? | `docs/verification_report.md` |
| What is the checksum of each output? | `data/manifest.json` |

---

## 5. Data flow and downstream contracts

```
archive-datasets/*.csv  (5 files, read-only)
        |  etl/profile.py  -> data/profile/*.json -> docs/profile_metrics.md
        |  etl/mappings.py -> data/mappings/*.csv
        |  etl/dictionary.py -> docs/data_dictionary.md
        v
   etl/clean.py  (relabel / parse / merge / clip / code placeholders)
        v
   data/clean/*.csv (11 tables) -> Person B: schema, indexes, queries
                                -> Person C: API and business logic
                                -> Person D: report figures
        v
   etl/scale.py (1x / 5x / 20x) -> data/scales/*
        v
   etl/seed.py -> sql/load_*.sql + data/manifest.json
        v
   etl/verify.py -> docs/verification_report.md
```

Fixed contracts for downstream work:

- All ingredient references use `canonical_id` (`ING_*`), never the raw name.
- `ingredient_stats.idf` is the rarity weight for weighted-overlap ranking.
- `recipe_allergens.has_*` are the indexable allergen exclusion columns.
- `recipe_search_document.search_document` is the full-text document.
- Synthetic scale tiers are valid only for index-scalability experiments.
- `is_halal` is retained from the source and marked
  `is_halal_verifiable = false`; it must not be described as corrected.

---

## 6. Originality and citation

All code in `etl/` and `tests/` was written for this project. External
references — the reproduced paper, PostgreSQL documentation, unit conversion
conventions and the course dataset — are cited in the report's References
section and in `docs/data_sources_and_license.md`. No third-party code was
copied.

---

## 7. Known open items

These are recorded rather than silently assumed:

1. The course brief (`TeamForming.docx`) describes Track 1 application
   development, while the assignment rubric requires a reproduced paper.
   The report follows the rubric; see `docs/project_context.md`.
2. The dataset has no licence, author or source URL. Confirmation from the
   course instructor is still required before any public redistribution.
3. Group member names, undergraduate majors, the repository URL, the video
   URL and the final PDF filename are supplied by the group lead and Person D.
