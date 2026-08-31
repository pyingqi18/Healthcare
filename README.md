# Medical Institution Ratings Research

This project reorganizes the full 2025 to 2026 code history for the medical institution ratings study.

## What is included

1. A sanitized chronological archive of every received source file.
2. A stage-based map covering collection, preprocessing, exploratory analysis, panel construction, NLP, and regression.
3. Shared configuration files for paths, study parameters, regions, and provider taxonomy.
4. Reusable Python modules for identifiers, validation, API collection, parsing, panel construction, spatial exposure construction, and fixed-effects estimation.
5. A research-design audit identifying issues that must be resolved before interpreting coefficients causally.

## Recommended execution order

```text
01 Raw acquisition
02 Parsing and provenance retention
03 Provider identity resolution
04 Data validation
05 Review-year panel construction
06 Spatial exposure construction
07 Preliminary analysis
08 Main fixed-effects regression
09 Robustness and heterogeneity analysis
10 NLP outcomes and event studies
```

The active code is under `src/medical_ratings/` and `scripts/`. Historical notebooks are under `archive/` and should not be executed as a pipeline.

## Configuration policy

Dependencies, research parameters, and secrets are intentionally separate:

```text
pyproject.toml                  Package dependencies
.env                            Local credentials, never versioned
.env.example                    Required credential names
config/settings.yaml           Paths and study parameters
config/regions.yaml            Geographic definitions
config/provider_taxonomy.csv   Provider inclusion definitions
src/medical_ratings/config.py  Validated loading interface
```

No notebook needs to be run first to establish global state.

## Security

The historical source files contained plaintext DataForSEO credentials. Sanitized archive copies load credentials from environment variables. The original credential should be rotated before any future API use.

## Research status

The code is organized and the reusable modules are syntax-tested with synthetic unit tests. End-to-end reproduction requires the original DataForSEO, NPPES, review, website, and NLP data files, which were not part of the upload set.

Read `docs/research_design_audit.md` before treating any regression as a main specification.
