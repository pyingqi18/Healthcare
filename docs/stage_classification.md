# Stage Classification

## 01 Data collection

Primary historical references:

1. `001` through `005` for keyword-based DataForSEO Local Finder and Maps collection.
2. `005` for the latest complete collection-era notebook and expanded regional sampling.
3. `007` for website metadata and review-history acquisition.

Active modules:

1. `src/medical_ratings/dataforseo.py`
2. `src/medical_ratings/parsing.py`

## 02 Preprocessing and provider identity

Primary historical references:

1. `001` through `005` for API parsing, deduplication, NPPES filtering, and API-source merging.
2. `003` and `005` for rating-count discrepancy diagnostics and NPI-derived searches.

Active modules:

1. `src/medical_ratings/identifiers.py`
2. `src/medical_ratings/validation.py`

## 03 Preliminary analysis

Primary historical references:

1. `003` through `006` for rating distributions by region, category, and market size.
2. `008` and `009a` for spatial clusters and descriptive competition analysis.

These files contain exploratory specifications. They should not determine the final main model after outcomes have been inspected.

## 04 Cross-sectional regression

Primary historical reference:

1. `006`, the first OLS and Logit implementation.

This stage is useful for descriptive associations only. The current rating, current votes, current searchable sample, and historically inferred entry dates do not establish temporal identification.

## 05 Review-year panel construction

Primary historical references:

1. `007` for the first review-year panel.
2. `010` and `013` for the latest cumulative-rating, low-review-share, spatial-density, and shock construction.

Active modules:

1. `src/medical_ratings/panel.py`
2. `src/medical_ratings/spatial.py`

## 06 Formal panel regression

Primary historical references:

1. `008` for the first entity fixed-effects model.
2. `009a` for gravity, nearest-neighbor, concentric-distance, and category robustness specifications.
3. `010` through `013` for market-scaled radii, market-by-year effects, NLP outcomes, event studies, and exit shocks.

Active module:

1. `src/medical_ratings/models.py`

## 07 NLP outcomes

Primary historical references:

1. `010` for the first NLP branch.
2. `011` through `013` for cleaned review-level outputs and clinic-year aggregation.

NLP results must preserve model name, model version, prompt or label definitions, review sampling rules, and raw-to-clean transformations.

## 08 Latest working version

`013_2026-04-11_0411_sanitized.ipynb` is the latest integrated working notebook. It remains a research-development notebook. It is not designated as a final confirmatory analysis.

The three category-specific notebooks from 2026-03-10 are exact code duplicates after replacing the category label and input filename. The maintained pipeline should parameterize category instead of preserving three active copies.
