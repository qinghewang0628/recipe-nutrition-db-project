# Project Context and Reproduced Paper

This document records the assignment context used by the final report and
flags one unresolved interpretation issue for the group lead.

---

## 1. Project

Title: **Smart Recipe and Nutrition Retrieval System**.

The system treats a recipe's ingredient set as the primary retrieval object.
A user submits available ingredients and receives the dishes that can be
prepared and the ingredients still missing. It also supports combined
filtering by cuisine, duration, nutrition range, dietary preference, allergen
exclusion and cost, as well as full-text search over names, cuisines, methods
and ingredients. Ancillary functions cover nutrition analysis, shopping-list
aggregation, cost estimation and basic meal planning.

From a database-systems perspective, the technical focus is threefold:
similarity retrieval over set-valued attributes, indexing strategies for
multi-predicate filtering, and quantifying the benefit of indexes as data
volume grows.

---

## 2. Reproduced paper

> S. Sarawagi and A. Kirpal, "Efficient Set Joins on Similarity Predicates,"
> in *Proceedings of the 2004 ACM SIGMOD International Conference on
> Management of Data (SIGMOD '04)*, Paris, France, 13–18 June 2004,
> pp. 743–754. DOI: 10.1145/1007568.1007652.
> Authors: Sunita Sarawagi (IIT Bombay), Alok Kirpal (IIT Bombay; at Yahoo!
> Inc., Bangalore at the time of publication).

SIGMOD satisfies the rubric requirement that the reproduced paper appear at
SIGMOD, VLDB, ICDE or an equivalent database conference.

**Problem.** Set-valued attributes and text columns are common in
object-relational databases, but support for similarity joins between sets
is weak. The paper formalises four predicates: T-overlap join (intersection
size above T), Jaccard coefficient above f, weighted match above T, and
cosine similarity above f. It notes that elements may carry arbitrary
weights, for example the inverse of their database frequency — the
information-retrieval notion of IDF.

**Method.** Starting from inverted-index probing, the authors develop the
`Probe_Cluster` algorithm. It exploits the high-similarity thresholds typical
of real queries for pruning, partitions data by set size and prefix, and
fits compressed index partitions into available memory. It returns exact
answers and improves running time by one to two orders of magnitude over
earlier approaches across several weighted and unweighted overlap measures.

---

## 3. Motivation for selecting this paper

| Paper element | Implementation in this project | Owner |
|---|---|---|
| Set-valued record | Each recipe's ingredient set (`recipe_id` -> `canonical_id`, mean 9.6 ingredients) | A supplies clean data, B models it |
| T-overlap join | "What can I cook with these ingredients" = overlap ranking | B, core query 1 |
| Weighted match (inverse frequency) | Rarity weighting: Salt/Onion/Garlic carry low weight; Tofu/Almonds high weight. A produces `ingredient_stats.idf` | A supplies weights, B writes scoring SQL |
| Inverted index and probe pruning | Ingredient reverse index plus composite indexes; indexed vs unindexed plans | B, core queries and performance |
| Partitioning / memory-resident index | Index benefit across 1x / 5x / 20x tiers | A supplies tiers, B runs `EXPLAIN ANALYZE` |
| Multi-predicate combination (engineering extension) | Cuisine, time, nutrition, allergen and cost filters | B, query 2; C, API |

Reasons for the choice:

1. It is a full SIGMOD paper, so the venue requirement is unambiguous.
2. It addresses set-similarity joins inside a database system, matching the
   project's "retrieval with a database" positioning; a recommendation or
   machine-learning paper would not lead naturally to the
   schema–index–execution-plan experimental chain.
3. Its weighted-match element is directly and measurably reproducible: A
   computed `doc_freq` and `idf` for 57 ingredients, so B can compare
   weighted and unweighted scoring on the same query set.
4. Its reported one-to-two-orders-of-magnitude speed-up provides a clear
   experimental anchor. The tier x index experiment answers a relative
   question — how much speed-up do indexes bring on this dataset — even
   though absolute numbers are not comparable.

---

## 4. Scope of reproduction and declared deviations

| Paper | This project | Reason |
|---|---|---|
| General set-similarity join operator (`Probe_Cluster`, partition pruning) | Normalised tables, inverted and composite indexes, and SQL on PostgreSQL; the DBMS kernel is not modified | Coursework is database application development; the method is reproduced at the SQL level |
| The paper's text and web datasets | 9,997 synthetic course recipes plus seeded expansion to three tiers | Dataset licence unconfirmed; expansion serves scalability only |
| Absolute one-to-two-orders-of-magnitude speed-up | Relative speed-up of indexed vs unindexed plans, with `EXPLAIN (ANALYZE)` output | Dataset, hardware and DBMS differ; absolute values are not comparable |

---

## 5. Unresolved interpretation issue

Two course materials describe the task differently.

| Source | Statement |
|---|---|
| `TeamForming.docx` | Track 1: Database Application Development; describes system functions without specifying a reproduced paper |
| Assignment rubric | Requires the reproduced paper's title, authors and venue; a summary of its technical method and the project's implementation strategy; and a statement of deviations |

The report follows the rubric: Sarawagi and Kirpal (SIGMOD 2004) is treated
as the reproduced paper, and the system is presented as an application of
its method to recipe retrieval.

If the instructor confirms Track 1 with no reproduction requirement, three
changes are needed in the report:

1. Recast section 2 as "Related Work and Reference Paper" rather than
   "Reproduced Paper".
2. Recast the motivation section as "System Motivation and Functional Value",
   removing claims of reproducing a method.
3. Replace the deviation discussion with "Design Trade-offs Relative to the
   Reference Approach".

The paper should remain in the References under either interpretation,
because it genuinely informs the weighted-overlap design. This issue does
not affect any data engineering artefact, verification result or video
content in this package.

---

## 6. Open items owned by the group

| Item | Owner |
|---|---|
| Confirm the track interpretation | Group lead / instructor |
| Confirm dataset source, attribution and public-release permission | Group lead / instructor |
| Supply member names, undergraduate majors and Team No. | Group lead |
| Supply the GitHub URL, video URL and final PDF filename | Person D |
| Merge the four report parts and export the PDF | Person D |
| Align sections 4–6 with the final paper choice | Persons B and C |
