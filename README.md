# Medical Institution Ratings Research

This repository contains the reproducible research pipeline for a study of local dental-market competition and Google ratings. It reorganizes the full 2025 to 2026 code history and separates historical reproduction, corrected-data auditing, new data acquisition, physical-location resolution, panel construction, spatial exposure measurement, and fixed-effects estimation.

## Research objective

The central question is whether entry by nearby dental providers is associated with subsequent changes in incumbent clinics' Google ratings.

The planned main analysis measures the number of new competing physical locations entering within two miles in the previous year. It relates that exposure to the current cumulative rating of an incumbent Google profile while controlling for two-year-lagged incumbent density, clinic fixed effects, and market-by-year fixed effects.

The design estimates conditional associations. It does not support a causal interpretation without an additional source of exogenous variation.

## Working hypotheses

1. Recent nearby entry may be associated with incumbent rating changes because clinics can respond to competition through service quality, pricing, capacity, or patient selection. The coefficient direction is not imposed in advance.
2. The stock of nearby incumbent competitors may be related to both entry and ratings, so the main model controls for competition density measured at the end of year `t-2`.
3. Competitive relationships should weaken with distance. The fixed two-mile specification is primary, while a 0.5-mile radius, distance rings, gravity weights, and nearest-competitor measures are sensitivity analyses.
4. Associations may differ across small towns, mid-size cities, large cities, states, and dental-provider categories. These comparisons are reported as heterogeneity analyses and do not determine the primary specification.

## Units of observation

The pipeline deliberately separates rating outcomes from competition exposure.

| Unit | Definition | Analytical role |
|---|---|---|
| Outcome entity | One Google profile, identified by `clinic_key` and later by `outcome_entity_id` | Retains its own rating and review history. Ratings from separate profiles are not averaged or concatenated. |
| Competition location | One physical operating location, identified by `competition_location_id` | Used to count entry and incumbent density without double-counting multiple profiles at one address. |
| Clinic-year observation | One outcome entity in one year | Forms the longitudinal rating panel. |
| Market | One `search_location` and its predefined ZIP scope | Restricts eligibility and spatial neighbors to a comparable geographic market. |

## Data sources

The study combines the following inputs:

1. Historical clinic and review data in which the legacy collection and external additions were already merged.
2. DataForSEO Business Listings results for broad business-profile discovery.
3. Google Maps Standard results from uniform core and specialist dental keywords.
4. Google Reviews results for review histories and annual cumulative ratings.
5. Business Info, website dates, and earliest-review dates for provider attributes and entry-date evidence.
6. Manual category, geography, historical-identity, and physical-location adjudication.

Some early merged files no longer preserve a reliable source label for every row. The current crosswalk therefore cannot truthfully split every historical record back into a legacy-only or external-only source.

## Current corrected-data audit

The `corrected_v1` dataset is used for historical reproduction and design auditing. It is not the final rebuilt analysis dataset.

```text
Geographically eligible clinics:                         5,663
Spatially eligible clinics:                              5,605
Clinics entering the clinic-year panel:                  4,183
Clinic-year rows:                                       37,474
Rows in the 2015 to 2025 analysis period:               34,353
Rows meeting both analysis-period and spatial criteria: 34,030
```

The active acquisition audit currently has the following checkpoint:

```text
Current historical reference locations:                 3,525
Reference locations discovered by the source union:     3,398
Historical-reference recall:                            96.40%
Current historical references still unmatched:            127
Unique unresolved manual decisions:                          0
```

These figures measure coverage of a historical reference set. They are not final clinic totals. Newly discovered profiles still require eligibility review and physical-location resolution.

## Study markets

The project covers fifteen markets in New York, California, and Georgia. Final counts will be populated only after cross-source profile identity, physical competition locations, and outcome profiles are frozen. Historical-reference counts and raw profile counts are not substitutes for final market totals.

| Market | State | Size | Study ZIP scope | Final competition locations | Final outcome profiles |
|---|---|---|---|---:|---:|
| Malone | NY | Small | 12953 | Pending final freeze | Pending final freeze |
| Saranac Lake | NY | Small | 12983 | Pending final freeze | Pending final freeze |
| Syracuse | NY | Mid-size | 13200 to 13299 | Pending final freeze | Pending final freeze |
| Buffalo | NY | Large | 14200 to 14299 | Pending final freeze | Pending final freeze |
| New York City | NY | Large | 10000 to 10499 and 11000 to 11699 | Pending final freeze | Pending final freeze |
| Eureka | CA | Small | 95501, 95502, 95503, and 95534 | Pending final freeze | Pending final freeze |
| Fort Bragg | CA | Small | 95437 | Pending final freeze | Pending final freeze |
| Modesto | CA | Mid-size | 95350 to 95358 | Pending final freeze | Pending final freeze |
| San Francisco | CA | Large | 94100 to 94188 | Pending final freeze | Pending final freeze |
| Los Angeles | CA | Large | 90000 to 91699 | Pending final freeze | Pending final freeze |
| Vidalia | GA | Small | 30474 and 30475 | Pending final freeze | Pending final freeze |
| Toccoa | GA | Small | 30577 | Pending final freeze | Pending final freeze |
| Macon | GA | Mid-size | 31200 to 31299 | Pending final freeze | Pending final freeze |
| Augusta | GA | Large | 30900 to 30999 | Pending final freeze | Pending final freeze |
| Atlanta | GA | Large | 30300 to 30399 and 31100 to 31199 | Pending final freeze | Pending final freeze |

## Frozen main specification

```text
Outcome:                    dynamic_rating
Primary exposure:           log1p of same-market entries within 2 miles at t-1
Density control:            log1p of same-market incumbent stock within 2 miles at t-2
Self handling:              focal location excluded from entry and density
Fixed effects:              clinic_key and search_location by year
Covariance:                 standard errors clustered by clinic_key
Analysis years:             2015 to 2025
Interpretation:             conditional association
```

The registered main and sensitivity specifications are stored in `config/final_analysis.yaml`. Spatial methods must be compared on a frozen common sample. Statistical significance is not used to redefine the main specification.

## Current project status

Planning stage `41a` produced the 177-reference gap inventory, a targeted status-audit manifest for five below-gate markets, and a conditional uniform residual-keyword manifest. Stages `42a` and `43a` then submitted and downloaded all 50 targeted status tasks. All 50 tasks were ready, all 50 responses were saved, and no premature result GET was attempted.

Stage `44a` parses those responses and creates one manual decision row per historical reference. The evidence is used to distinguish an active unchanged location, an active renamed or relocated location, an active reference not rediscovered, a closed location, an out-of-scope historical reference, or an unresolved case. Targeted results are excluded from the main discovery numerator. Only a reviewed closure or scope decision may change the current reference denominator.

The 50 reviewed records are all outside the frozen patient-facing dental-provider taxonomy. The returned identities include non-dental medical facilities, pharmacies, veterinary businesses, retail and civic organizations. The only dental-labelled record is a dental laboratory, which the frozen category rules explicitly exclude. Stage `44a` applied all 50 decisions without increasing the main discovery numerator. The current reference denominator is 3,525, the source union covers 3,398 locations, and all 15 markets meet the frozen 90% recall gate.

Stage `45a` freezes this historical-reference coverage benchmark and marks the separate 75-task residual-keyword manifest as `cancelled_not_needed_after_gate`. This is not a final clinic count. Cross-source profiles still require provider review, identity reconciliation, and physical competition-location resolution before `full_rebuild_v1` can begin.

Stage `46a` combined 33,238 source rows into 29,984 exact Google profiles, removing 3,254 repeated source observations without merging physical locations. The canonical manual-review cohort contains 450 profiles and 410 review blocks. Its untouched all-blank baseline remains under `archive/profile_eligibility_review/original_manual_review_20260924`. Stages `46f` through `46i` increased the verified set to 251 profiles, comprising 141 inclusions and 110 exclusions. Stage `46l` completed the frozen 199-profile remainder without changing any identity field. The user-generated verified-additions file contains 76 inclusions and 123 exclusions, with zero unresolved rows. Stage `46m` strictly rebuilds the final 450-profile freeze from the versioned 251 decisions plus those 199 additions, expects 217 inclusions and 233 exclusions, injects them into the untouched `46a` template, and prepares review-only physical-location blocks. It makes no API request or automatic profile or location merge and does not change the regression BallTree or exposure code.

The user-generated stage `46m` output contains 29,550 included Google profiles, 434 excluded profiles, 127 legacy anchors, 19,560 provisional location blocks, and 5,679 multi-profile blocks. Stage `46n` converts that large provisional set into one frozen policy-review table. It proposes the current block for 4,031 routine same-base-address blocks, proposes a normalized-base-address split for 1,072 complex multi-address blocks, and concentrates manual review on the remaining 576 blocks. Suggestions are not applied decisions, and stage `46n` assigns no final location ID.

Stage `46o` closes the physical-location gate without another manual pass. The main specification accepts the 4,031 routine blocks, splits the 1,072 multi-address blocks by normalized base address, and conservatively keeps each exact Google profile separate inside the remaining 576 ambiguous same-address blocks. A frozen sensitivity mapping groups each of those ambiguous blocks. Expected counts are 22,299 main competition locations and 20,762 address-merge sensitivity locations, while all 29,550 Google outcome profiles remain separate.

Detailed chronological decisions are recorded in `reports/整理内容.md`. The earlier acquisition freeze is documented in `reports/scrape_freeze_20260919.md`.

## What is included

1. A sanitized chronological archive of received source files.
2. A stage-based workflow covering acquisition, parsing, provenance, identity resolution, validation, panel construction, spatial exposure construction, regression, and reporting.
3. Shared configuration files for paths, markets, study parameters, search plans, and provider taxonomy.
4. Reusable Python modules for identifiers, API collection, parsing, eligibility, profile-to-location resolution, panel construction, spatial measurement, and fixed-effects estimation.
5. A research-design audit separating legacy reproduction, corrected-data diagnostics, and the future full rebuild.
6. Unit tests using synthetic data, with separate real-data checks where local research inputs are required.

## Recommended execution order

```text
01 Acquisition planning and paid-execution gates
02 Raw-response download and provenance retention
03 Parsing, geography, and provider eligibility
04 Cross-source profile identity review
05 Physical competition-location resolution
06 Business Info, reviews, and entry-date completion
07 Clinic-year panel construction
08 Spatial exposure construction
09 Main fixed-effects regression
10 Sensitivity, heterogeneity, and reporting
```

Active code is under `src/medical_ratings/` and `scripts/`. Historical notebooks are under `archive/` and must not be executed as the current pipeline.

## Repository layout

```text
archive/                     Sanitized historical code for provenance only
config/                      Paths, market definitions, research design, and scrape plans
data/                        Raw, interim, and processed data, usually excluded from Git
docs/                        Methods, audit notes, and handoff documentation
outputs/                     Generated diagnostics, regressions, tables, and figures
reports/                     Chronological research decisions and verified counts
scripts/                     Executable stage entry points
src/medical_ratings/         Reusable research and data-processing modules
tests/                       Synthetic and real-data validation tests
```

## Configuration policy

Dependencies, research parameters, and credentials are separated:

```text
pyproject.toml                  Package dependencies
.env                            Local credentials, never versioned
.env.example                    Required credential names
config/settings.yaml           Paths and API endpoints
config/regions.yaml            Market and ZIP definitions
config/final_analysis.yaml     Frozen final analysis protocol
config/scrape_plans.yaml       Uniform acquisition plans and price assumptions
config/provider_taxonomy.csv   Provider inclusion definitions
src/medical_ratings/config.py  Validated credential-loading interface
```

No notebook needs to run first to establish global state.

## Installation and checks

```bash
python -m pip install -e ".[analysis,scraping,test]"
python -m pytest -q
```

Preview the corrected-data regression audit pipeline without execution:

```bash
python scripts/run_pipeline.py --profile corrected_v1_audit
```

The `full_rebuild_v1` profile remains blocked until acquisition, identity, reviews, and entry dates are frozen.

## Security and reproducibility

Historical source files once contained plaintext DataForSEO credentials. Sanitized archive copies and active scripts read `DATAFORSEO_LOGIN` and `DATAFORSEO_PASSWORD` from environment variables. Credentials must not be stored in source code, configuration, logs, or Git.

Paid scripts default to validation-only mode. Submission requires the exact confirmation text printed for the current remaining task count. Each run preserves manifests, task logs, raw responses, stage summaries, and relevant SHA-256 hashes for reconciliation and resumption.

Read `docs/research_design_audit.md` before interpreting any regression. Results from `corrected_v1` remain audit or legacy-comparison results. Final estimates must come from `full_rebuild_v1`.

Stage `46o` freezes 22,299 main physical competition locations and a 20,762-location address-merge sensitivity while preserving 29,550 eligible Google outcome profiles. Stage `47a` plans one Google Reviews task per outcome profile, keeps shared physical locations as a separate spatial identity, and records profiles that may remain left-censored at the API depth limit of 4,490. Stage `47b` audits corrected-v1 histories before any paid collection and removes only complete histories linked by stable Google identity; title-and-ZIP candidates are never automatically reused. Paid validation and submission must use the reduced manifest produced locally by 47b. Real API data must be generated by the user with the resumable commands in `RUN_FULL_REBUILD_REVIEWS.md`.

The first local stage `47b` result reused 68 profiles and reduced the maximum estimated cost by only $1.0567. Stage `47c` therefore repairs row-wise mixed legacy/replacement field selection and evaluates stronger exact-address identity evidence before any paid collection. After 47c, validation and submission must use its enhanced reduced manifest rather than either earlier manifest.
