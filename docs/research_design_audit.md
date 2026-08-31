# Research Design Audit

## Bottom line

The project contains a substantial data-engineering and exploratory modeling history, but the latest coefficients should not yet be interpreted as causal effects of competition on clinic ratings. The main threats arise before estimation: provider identity, sample selection, historical entry and exit measurement, exposure construction, and post-treatment controls.

## Critical issues

### 1. Provider identity is unstable

Historical merges often use `title` or `title + ZIP`. Clinic IDs are later assigned from row order using values such as `C_0`, `C_1`, and so on. Row-order IDs are not stable across deduplication, sorting, or new data pulls.

Required fix:

1. Prefer a stable Google place identifier such as `place_id` or `cid`.
2. Retain NPI as a separate provider identifier and allow a practice location to map to multiple NPIs.
3. Use a documented probabilistic or reviewed linkage table when stable identifiers are unavailable.
4. Freeze a clinic-location crosswalk before panel construction.

### 2. The sample is conditioned on current observability

Historical panels are reconstructed from clinics found in later search results. Clinics that closed, changed names, lost their listing, or were never captured can be missing. This creates survivorship and search-selection bias in entry, density, and exit measures.

Required fix:

1. Define the sampling frame independently of current Google visibility.
2. Preserve all attempted searches and missing results.
3. Compare included and excluded clinics using NPPES and acquisition metadata.
4. Treat conclusions as selected-sample associations unless historical coverage can be demonstrated.

### 3. Entry dates are measured with multiple noisy proxies

Website creation dates, NPI enumeration dates, and first observed review dates measure different events. They cannot be combined silently into one opening date.

Required fix:

1. Preserve each date source separately.
2. Define an explicit date hierarchy.
3. Report source coverage and disagreement.
4. Run sensitivity analyses by date source.

### 4. Strong-competitor status uses future information

Later notebooks classify a competitor as strong using its current rating and current vote count, then apply that status to historical entry years. This introduces look-ahead bias because later success is used to classify an entrant at the time of entry.

Required fix:

Define strength using information available at or before the entry year, such as first-year rating and first-year review volume. If contemporaneous data are unavailable, label this branch exploratory and do not interpret it as an entry-time treatment.

### 5. Exit is inferred from review inactivity

The 2026-04-11 notebook treats two years without reviews as clinic exit. Low-volume clinics can remain open without receiving reviews, and review data may be incomplete.

Required fix:

Use verified closure signals, NPPES deactivation, website status, phone status, or archived business listings. Until then, call the variable `review_inactivity`, not `exit`.

## Estimation issues

### 6. Vote counts may be post-treatment

Competition can affect review volume, platform visibility, and rating composition. Controlling for cumulative vote counts can block part of the treatment pathway or create collider bias.

Required fix:

Exclude `log_votes_dynamic` from the main specification unless the estimand explicitly conditions on review volume. Report models with and without vote controls.

### 7. Market-scaled radii are sample-dependent

The latest code defines local radii from the 25th and 50th percentiles of pairwise clinic distances within each city. These thresholds change when the sampled clinics change and do not represent common physical distances across markets.

Required fix:

Use a prespecified physical radius as the main exposure. Treat percentile radii as a heterogeneity or normalization robustness check. Restrict every neighbor query to the same intended market.

### 8. Baseline fixed effects vary across specifications

Some models use entity effects only, some use entity and year effects, and later models use entity plus city-year, ZIP3-year, or ZIP5-year effects. These specifications estimate different comparisons.

Required fix:

Select one main fixed-effects structure before reviewing final results. A defensible candidate is clinic effects plus market-by-year effects, with clinic-clustered standard errors. More granular ZIP5-by-year effects may absorb most identifying variation and should be justified.

The active model wrapper supports entity plus one market-year effect, consistent with the documented two-effect limit in `linearmodels.PanelOLS`.

### 9. Event-study treatment is recurrent

Competitor entry can occur multiple times, but the event study uses the first observed shock as a one-time absorbing treatment. Later shocks and changing intensity remain in the post period.

Required fix:

Decide whether the estimand concerns first exposure, any exposure, or cumulative exposure. For first exposure, censor or model later shocks explicitly and check pre-trends. For recurrent treatment, use a design that accommodates repeated events.

### 10. Low-rating threshold crossing is not absorbing

Ratings can recover after falling below 3.5. Treating the first threshold crossing as permanent survival failure imposes an artificial absorbing state.

Required fix:

Use a repeated binary panel outcome or define a persistent failure rule. Do not label threshold Logit output as survival analysis without a valid risk-set interpretation.

### 11. FE and RE selection tests are unreliable

Historical code compares dummy-variable OLS fixed effects with `statsmodels.MixedLM` using a manually assembled Hausman statistic. Negative statistics and non-positive covariance differences appear in the notebook history.

Required fix:

Do not use the current Hausman output to choose the main specification. Fixed effects should follow the research design and the plausibility of correlation between unobserved clinic traits and competition exposure.

### 12. Specification search is extensive

The notebook history tries many thresholds, radii, outcomes, category splits, market sizes, density measures, strong-entry definitions, fixed effects, NLP ratios, and event windows.

Required fix:

1. Declare one main outcome, exposure, radius, sample, fixed-effects structure, and standard-error rule.
2. Label all alternatives as robustness or exploratory analysis.
3. Address multiple testing for large outcome families, especially NLP ratios.
4. Preserve a specification registry in the output tables.

## Data quality issues

1. API task-level errors were not consistently validated.
2. Existing JSON files could cause failed results to be skipped permanently.
3. Query, task, rank, requested location, retrieval time, and stable place identifiers were not always retained.
4. Title-only deduplication can collapse branches or same-name providers.
5. Rating totals and rating-distribution totals can disagree, but records should not be dropped until field semantics and refresh timing are understood.
6. Earlier taxonomy labels were incorrect and included non-dentist dental occupations.
7. Region labels and ZIP rules were duplicated and inconsistent across notebooks.

## Priority order

1. Rotate credentials and freeze raw data.
2. Build and review a stable clinic-location identity crosswalk.
3. Audit sample coverage and missing clinics.
4. Separate date sources and define opening-date rules.
5. Rebuild exposures without future information.
6. Choose a single main specification and estimand.
7. Rebuild tables from the frozen analysis dataset.
8. Run robustness, NLP, category, and exit branches only after the main pipeline is locked.
