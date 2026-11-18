# Data Engineering for Set-Oriented Recipe Retrieval: Profiling, Cleaning, and Reproducible Dataset Construction

Person A — Data Engineering

DSC5003 Storing and Retrieving Data, Group Project

Smart Recipe and Nutrition Retrieval System

## Abstract

This report presents the data engineering component of a group project that reproduces the set-similarity join method of Sarawagi and Kirpal (SIGMOD 2004) on a recipe retrieval system. Five course-provided CSV files containing 208,523 rows and 9,997 recipes were profiled, cleaned and expanded into three scale tiers. Although the input is structurally flawless, it is semantically unreliable: 12,190 dietary label values conflict with the corresponding ingredient lists, quantities are free text in six units, and 7,996 ingredient rows are duplicates. We describe an eight-step, read-only extract-transform-load pipeline that recomputes verifiable labels, converts quantities into three canonical dimensions, consolidates duplicate ingredients by estimated mass, winsorises 143 outlying recipes, derives allergen and inverse-document-frequency tables, and produces eleven cleaned tables. Unverifiable values are retained and explicitly flagged rather than overwritten. Correctness is enforced by 50 executable assertions and 25 unit tests, all passing, and two independent rebuilds are byte-identical. The resulting artefacts provide the schema, index and query experiments of subsequent project stages with a documented and reproducible foundation.

Keywords: data quality; extract-transform-load; set-valued attributes; inverse document frequency; reproducibility.

## 1. Introduction

The project builds a recipe retrieval system in which a recipe is represented primarily by its ingredient set. A user supplies available ingredients; the system ranks dishes by set overlap and reports missing ingredients. Secondary functions combine cuisine, duration, nutrition, dietary preference, allergen exclusion and cost filters with full-text search. The database-systems interest lies in similarity retrieval over set-valued attributes, indexing for multi-predicate queries, and the change in index benefit as data volume increases.

This report covers the data engineering stage only. Its contribution is fourfold: (i) a field-level and cross-table quality profile of the raw dataset; (ii) a documented cleaning methodology in which every rule produces both audit columns and an executable assertion; (iii) a set of derived tables that fix the downstream contract, including canonical ingredient identifiers and inverse-document-frequency weights; and (iv) a one-command rebuild whose output is deterministic and verifiable. Schema design, index structures, query implementation and performance measurement belong to subsequent stages and are described elsewhere.

The remainder of the report is organised as follows. Section 2 reviews the reproduced paper. Section 3 describes the data source and its preliminary assessment. Section 4 formalises the cleaning rules. Section 5 reports results and verification. Section 6 discusses challenges, Section 7 states limitations, and Section 8 concludes.

## 2. Related Work and Reproduced Paper

The reproduced paper is S. Sarawagi and A. Kirpal, "Efficient Set Joins on Similarity Predicates," Proceedings of the 2004 ACM SIGMOD International Conference on Management of Data, Paris, France, pp. 743–754, 2004 (DOI 10.1145/1007568.1007652). It addresses the weak support for set-similarity joins in object-relational databases and formalises four predicates: T-overlap, Jaccard, weighted match and cosine similarity. Its Probe_Cluster algorithm starts from inverted-index probing, then applies threshold-based pruning, size and prefix partitioning, and memory-resident compressed index partitions to obtain exact results one to two orders of magnitude faster than earlier methods.

Two elements of the paper are directly relevant to data preparation. First, every recipe must be representable as a clean set of canonical elements; duplicate and synonymous ingredient names would corrupt both intersection cardinality and posting lists. Second, elements may be weighted by the inverse of their database frequency. We therefore export a document-frequency table and the smoothed inverse-document-frequency weight

$$ \mathrm{idf}(t) = \ln\frac{N+1}{\mathrm{df}(t)+1} + 1 \tag{1} $$

where N is the number of recipes and df(t) is the number of recipes containing ingredient t. The additive smoothing keeps ubiquitous ingredients at a small positive weight.

For a query set q and a recipe set d, the three set predicates used in the downstream experiments are the T-overlap condition, the Jaccard coefficient and the rarity-weighted overlap score:

$$ |q \cap d| \ge T \tag{2} $$

$$ J(q,d) = \frac{|q \cap d|}{|q \cup d|} \tag{3} $$

$$ \mathrm{score}_w(q,d) = \frac{\sum_{t \in q \cap d} \mathrm{idf}(t)}{\sum_{t \in q} \mathrm{idf}(t)} \tag{4} $$

The denominator normalises by the total weight of the query, so adding common ingredients to a query cannot inflate its score.

The reproduction is implemented at the SQL level on PostgreSQL rather than by modifying the database kernel. Accordingly, absolute running times are not compared with the paper; the experiment measures the relative benefit of indexes across three dataset scales.

## 3. Data Source and Preliminary Assessment

### 3.1 Source and provenance

The input consists of five course-provided CSV files: a cuisine dimension, a recipe master table, an ingredient detail table, a nutrition detail table and a preparation-step table. Together they contain 208,523 rows and approximately 9.8 MB. SHA-256 fingerprints are recorded in data/raw/MANIFEST.sha256 and checked at the start of every rebuild.

The bundle contains no licence, author, version or source URL, and no exact public match was found for the five-file combination. Structural fingerprints — strictly sequential identifiers, cuisine counts summing exactly to 9,997, only twenty step templates, zero structural defects across all 208,523 rows, uniform numeric ranges and a 32.6–58.6% label-conflict rate — indicate programmatically generated teaching data. We therefore describe it as a course-provided synthetic dataset, exclude the raw files from the public repository, and commit only their checksums and the rebuild script. Confirmation of attribution and redistribution rights remains an open item.

*Table 1. Raw input files.*

| File | Rows | Columns | Role |
|---|---|---|---|
| cuisine_metadata.csv | 5 | 3 | Cuisine dimension |
| recipes_master.csv | 9,997 | 23 | Recipe master |
| recipe_ingredients.csv | 103,908 | 5 | Ingredient detail (set-valued) |
| recipe_nutrition.csv | 9,997 | 13 | Nutrition detail |
| recipe_steps.csv | 84,616 | 4 | Preparation steps |

### 3.2 Structural quality

Structural checks pass without exception: zero empty cells, zero duplicate rows, zero orphan foreign keys in the three detail tables, five out of five cuisine counts matching the master table, 9,997 out of 9,997 calorie values consistent between the master and nutrition tables, and 9,997 out of 9,997 recipes satisfying prep + cook = total time. Dates lie between 2023-02-16 and 2026-02-13 with no future values or format errors, and no row contains a quote or newline hazard.

### 3.3 Semantic quality

Semantic checks reveal six defects. Dietary labels contradict ingredient lists in 12,190 label values across 7,952 recipes (79.5%). Quantities comprise 1,517 distinct strings in six units across three dimensions, plus 9,997 placeholders. There are 7,523 duplicate ingredient groups contributing 7,996 surplus rows. Estimated ingredient mass reaches 1,937.5 g per serving, with 143 recipes above 1,200 g. Paneer appears under two categories, and two flour names are synonyms. Finally, the sum of step durations equals total time for only 51 of 9,997 recipes, so that column cannot serve as a business time metric.

The conclusion is that the raw files are a sound structural carrier but cannot directly support allergen exclusion, dietary filtering or shopping-list aggregation. Cleaning is a prerequisite, not an optimisation.

## 4. Cleaning Methodology

The pipeline comprises eight steps: lookup-table construction, column dictionary generation, raw profiling, cleaning, cleaned profiling and comparison, scale-tier generation, loader and manifest generation, and correctness verification. It uses only the Python standard library, treats the raw CSV files as read-only, and keeps audit columns at every step. Rules R1–R8 are recorded in docs/cleaning_rules.md.

### 4.1 Dietary label reconstruction

Three flags are recomputed as set-disjointness tests over the canonical ingredient set. Let A(r) be the canonical ingredient set of recipe r and let V, M and G denote the sets of non-vegetarian, animal-derived and gluten-containing ingredients respectively. Then

$$ \mathrm{is\_vegetarian}(r) = \mathbf{1}[A(r) \cap V = \varnothing] \tag{5} $$

with analogous expressions for is_vegan using M and is_gluten_free using G. This corrected 3,259, 1,740 and 5,863 values respectively, a total of 10,862. Original values are retained in is_*_raw columns and in recipe_dietary_audit.csv, making the transformation reversible.

The fourth flag, is_halal, is not recomputed. Slaughter method and certification information are absent; a conservative pork-and-alcohol proxy would classify all 9,997 recipes as halal and would therefore fabricate a fact. Its 1,328 conflicts are retained with is_halal_verifiable = false, and the proxy is written only to an audit column.

### 4.2 Quantity normalisation

Each quantity string is parsed into a numeric value v and a unit u. Conversion to the canonical unit uses a factor k(u), while a separate approximate gram factor gamma(u) supports cross-dimension aggregation:

$$ v_c = v\,k(u), \qquad g_a = v\,\gamma(u) \tag{6} $$

Dimensions are not forcibly cross-converted: mass maps to grams, volume to millilitres and count to pieces. Only the approximate gram value is comparable across dimensions, and it is used for aggregation, ranking and outlier detection, never as a nutrition input.

The six raw units are g, ml, tbsp, tsp, cloves and medium; conversion factors include 15 ml per tablespoon, 5 ml per teaspoon, 3 g per garlic clove and 100 g per medium vegetable. These are conventional cooking approximations, not per-ingredient densities, and their basis is recorded in unit_conversion.csv. Placeholder strings are coded as TO_TASTE, AS_NEEDED, PINCH, UNSPECIFIED or OPTIONAL with empty numeric fields. After cleaning, 8,940 placeholder rows remain; the 1,057 removed rows merged into quantified rows of the same ingredient.

### 4.3 Duplicate consolidation

Rows are grouped by (recipe_id, canonical_id). Within a group, approximate gram values of non-placeholder rows are summed; the row with the largest gram value determines the canonical dimension and unit; and the summed mass is converted back to a canonical value. All-placeholder groups retain placeholder semantics. Ingredient ordinals are renumbered to a contiguous sequence. The 57 canonical identifiers come from a manually reviewed synonym table: All-Purpose Flour merges into Wheat Flour, whereas Coriander seed and Fresh Coriander leaf are deliberately kept distinct. Ingredient detail falls from 103,908 to 95,912 rows.

### 4.4 Outlier treatment

Estimated ingredient mass per serving has P50 = 323.0 g, P95 = 910.3 g, P99 = 1,285.5 g and a maximum of 1,937.5 g. A round domain threshold C = 1,200 g/serving near P99 was adopted. For a recipe r with servings s(r) and total estimated mass G(r), each ingredient quantity is scaled by

$$ v'_i = v_i \cdot \min\!\left(1,\ \frac{C\,s(r)}{G(r)}\right) \tag{7} $$

so internal recipe proportions are preserved. 143 recipes (1.4%) are affected. Deletion was rejected because the performance experiment requires an exact 9,997-recipe baseline and strict 1x/5x/20x multiples. Before and after values and the scale factor are recorded per recipe in data/profile/clipped_recipes.csv.

### 4.5 Derived tables and downstream contracts

Six derived tables complete the cleaned dataset: a 25-row cuisine–category link table for third normal form modelling; a per-recipe allergen table with ten indexable has_* columns (9,132 recipes carry at least one allergen); a dietary audit table; a 57-row ingredient dimension; an ingredient statistics table carrying doc_freq and idf as defined in Equation (1); and 9,997 full-text documents with a doc_length column for BM25 experiments. In total, eleven tables are written to data/clean/.

Three scale tiers are produced by deterministic replication with a fixed seed. Independent numeric fields are perturbed by small percentages, and one non-core ingredient is dropped in 15% of copies so that posting lists differ. Canonical identifiers, allergen flags, dietary flags and step text are not perturbed, so performance differences reflect scale rather than distribution drift. The tiers contain 9,997, 49,985 and 199,940 recipes respectively.

## 5. Results and Verification

### 5.1 Before and after cleaning

*Table 2. Comparison of the raw and cleaned datasets.*

| Metric | Before | After |
|---|---|---|
| Ingredient detail rows | 103,908 | 95,912 |
| Recipes | 9,997 | 9,997 |
| Dietary label conflicts | 12,190 | 0 |
| Recipes with a conflict | 7,952 | 0 |
| Duplicate ingredient groups | 7,523 | 0 |
| Surplus duplicate rows | 7,996 | 0 |
| to taste placeholder rows | 9,997 | 8,940 |
| Unparseable quantities | 0 | 0 |
| Recipes above 1,200 g/serving | 143 | 0 |
| Distinct ingredient names | 58 | 57 |
| Recipes with an allergen | not available | 9,132 |

The 10,862 corrections to verifiable labels account for most of the 12,190 raw conflicts; the remaining 1,328 is_halal conflicts are deliberately retained and marked unverifiable. The two numbers must not be conflated.

### 5.2 Correctness verification

Verification is code, not a manual checklist. etl/verify.py implements 50 executable assertions in six groups: input integrity (raw checksums, file presence, lookup tables); keys and referential integrity (nine primary-key checks, six orphan checks, per-recipe coverage); cleaning rules (contiguous ordinals, no duplicate canonical pairs, zero unparseable quantities, consistent placeholder encoding, category conflicts resolved); semantic consistency (recomputed labels, retained is_halal, reproducible audit counts, allergen unions, calorie agreement, time identity, cap compliance, full-text coverage, recomputable IDF); scale tiers (row counts, keys, duplicates and caps at each tier); and reproducibility (byte-identical rebuilds and matching manifest checksums). All 50 assertions pass, as do the 25 unit tests in tests/. Results are written to docs/verification_report.md.

### 5.3 Reproducibility

A single command, make seed (equivalently python make.py seed), rebuilds the entire package in eight steps. Randomness is fixed at RANDOM_SEED = 20261116, iteration order is fixed, all writes are atomic (.tmp followed by os.replace), and data/manifest.json records row counts, byte counts, SHA-256 values and all configuration parameters. An explicit test asserts that two independent rebuilds are byte-identical. On the development machine the full rebuild completes in approximately 90–130 seconds, with the 20x tier dominating the cost.

Three scale CSVs exceed GitHub's 50 MB warning threshold. They are committed as .csv.gz archives at 8–14% of the original size and restored with make unpack, so the repository remains within hosting limits without sacrificing reproducibility.

## 6. Challenges and Lessons Learned

First, label errors were not a simple repair problem. Whether eggs count as vegetarian, whether cross-contamination affects gluten-free status, and whether chickpea flour is gluten-free all change the answer. The rules were therefore externalised into dietary_rules.csv with their expression, source, verifiability, conflict policy and stated convention. Changing a convention requires editing one set and rerunning the pipeline, not editing code.

Second, the most serious cleaning error would have been over-confidence. The is_halal conflicts look like ordinary dirty data but cannot be resolved from ingredient names. Verifiability was made a first-class column (is_halal_verifiable) rather than a comment, and the field is labelled as unverifiable in the dictionary, the cleaning rules, this report and the video subtitles.

Third, three physical dimensions cannot be converted losslessly. Shopping lists require an additive quantity, but the density of a tablespoon of oil differs from that of flour. The design keeps a lossless layer (dimension, canonical value, canonical unit) for business queries and a separate, explicitly approximate gram layer for aggregation only. Nutrition is never derived from quantities.

Fourth, deciding which names denote the same ingredient is a business decision, not a string-similarity problem. A manually reviewed synonym table was preferred to automatic fuzzy clustering; merging coriander seed with coriander leaf would have corrupted allergen and retrieval semantics.

Fifth, the source is structurally perfect but semantically empty: 9,997 recipes have only 3,085 names, 20 step templates and 58 ingredients. This produced three constraints: no claim that the corpus is real, no business use of step durations, and no accuracy or nutrition claims from synthetic scale tiers. The same structural evidence underlies the unresolved provenance question.

The general lessons are that structural integrity does not imply fitness for use; that every cleaning rule must emit both an audit column and a recomputable assertion; and that thresholds, conventions and density assumptions belong in configuration and documentation, because they will be cited, challenged and revised.

## 7. Limitations and Open Items

- The dietary rules are project conventions, not domain standards. The cleaned labels must not be presented as authoritative dietary advice.
- qty_approx_g relies on conventional density approximations. A per-ingredient density table would reduce its systematic error.
- The 1,200 g/serving cap is a domain threshold chosen near P99, not a constant from the reproduced paper; it affects 1.4% of recipes.
- Synthetic scale tiers support index-scalability experiments only and must not be compared with the paper's absolute results.
- The dataset licence, attribution and permission for public release are unconfirmed. Raw CSVs remain excluded from the repository.
- The course brief and the assignment rubric describe different tracks. This report follows the rubric's paper-reproduction requirement; the alternative wording is recorded in docs/project_context.md.
- Group member names, undergraduate majors, the repository URL, the video URL and the final PDF filename are supplied by the group lead and Person D before submission.
## 8. Conclusion

This work converted a structurally clean but semantically unreliable course dataset into a documented, reproducible foundation for the database experiments that follow. The pipeline corrects 10,862 verifiable label values, reduces 103,908 ingredient rows to a canonical 95,912, normalises 1,517 free-text quantity strings into three dimensions, winsorises 143 outlying recipes, and derives allergen, IDF and full-text tables. Crucially, it also declines to correct what cannot be verified. Fifty executable assertions, twenty-five unit tests and a byte-identical rebuild demonstrate correctness and determinism. All artefacts are reproduced by one command and are ready for schema design, indexing and query evaluation in the subsequent project stages.

## References

[1] S. Sarawagi and A. Kirpal, "Efficient set joins on similarity predicates," in Proc. ACM SIGMOD International Conference on Management of Data (SIGMOD '04), Paris, France, pp. 743–754, 2004. DOI: 10.1145/1007568.1007652.
[2] DSC5003 Storing and Retrieving Data, "Group Project Assignment — Project Deliverables and Grading Rubric," course material, 2026.
[3] DSC5003 Storing and Retrieving Data, "Team Forming Form," course material, 2026.
[4] DSC5003 Storing and Retrieving Data, "Smart Recipe and Nutrition Retrieval System — Course-provided synthetic recipe dataset (archive-datasets/, five CSV files, 208,523 rows)," course material, 2026. Source and licence pending instructor confirmation; SHA-256 manifest: data/raw/MANIFEST.sha256.
[5] PostgreSQL Global Development Group, PostgreSQL Documentation: CREATE INDEX, Full Text Search, EXPLAIN (ANALYZE, BUFFERS), and psql \copy. https://www.postgresql.org/docs/
[6] Codex Alimentarius Commission, "General Standard for the Labelling of Prepackaged Foods (CXS 1-1985)," for allergen classification conventions. Cited for classification practice only.

## Appendix A. Reproduction Commands

All commands are executed from the repository root.

`python make.py seed          # full eight-step rebuild`  
`python make.py test          # 25 unit tests + 50 correctness assertions`  
`python make.py demo          # before/after figures used in the video`  
`python make.py pack          # compress scale CSVs above 50 MB`  
`python make.py unpack        # restore them after cloning`  
`python make.py load DATABASE_URL=postgres://user:pwd@host:5432/recipes`  
## Appendix B. Deliverable Index

A file-by-file index is provided in DELIVERY_MANIFEST.md at the repository root. The principal artefacts are etl/ (source code), sql/ (loaders), data/clean/ and data/scales/ (datasets), docs/ (technical documentation), report/PartA_Final_Report.docx (this report) and video/ (demonstration material).


---

*Equations (1)–(7) are embedded as native Word equation objects in PartA_Final_Report.docx. This Markdown file is a plain-text mirror for repository browsing.*