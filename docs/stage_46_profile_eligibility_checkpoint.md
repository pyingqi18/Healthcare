# Stage 46 profile eligibility checkpoint

## Checkpoint scope

This checkpoint records the verified state reached after stages 46a through 46j. The repository base before this checkpoint was tag `v0.4.0`, commit `9c6ade4`, which ended at stage 45.

The temporary stage 46 code packages generated in the earlier work session were not committed and are not available in the persistent file set. This checkpoint therefore freezes the verified human decisions and provenance facts that can be reproduced from retained files. It does not claim that the missing temporary ZIP packages have been restored.

## Stage notes

### Note 46a: cross-source profile preparation

The cross-source preparation read 33,238 source records and formed 29,984 Google profiles. Rule-based status carried forward 29,333 included profiles and 201 excluded profiles. Exactly 450 profiles remained for manual eligibility review. No manual row was decided automatically.

### Note 46b: eligibility triage

The 450 unresolved profiles formed 147 category groups and contained 104 previously unknown categories. Triage suggestions were 80 include, 87 exclude, and 283 unsafe for automatic resolution. Suggestions were review priorities only. Automatic final decisions remained zero.

### Note 46c through 46g: review evidence and raw freeze

The authoritative raw review baseline is the first 450-row `profile_eligibility_review_rows.csv`: all 450 `manual_decision` cells are blank and the file has SHA256 `c71f6b1197e80849d40670d607a76b496fe103cb0d7b8a50fd11d4b239e0e35b`. Its companion review structure contains 410 blocks.

The external-evidence pass produced 281 evidence records covering 252 review units. These passes did not make automatic decisions, merge profiles or locations, call an API, or alter the regression BallTree.

### Note 46h: singleton audit

After the earlier verified decisions were applied, 238 singleton profiles remained. Of these, 169 had an official-site route and 69 did not. A 39-profile specific official-page priority batch was selected for direct review.

### Note 46i: specific official-page audit

All 39 priority profiles received manual evidence decisions: 20 were included as dental providers and 19 were excluded as non-dentist categories. The cumulative verified decision file then contained 251 profiles, consisting of 141 includes and 110 exclusions. The retained export SHA256 is `ab76cac9bed1869838320151c8dac08300827ed998495ded248deeb64e539155`. Git normalizes that CSV to LF line endings; the versioned file SHA256 is `96ca651d6b95eb000c5238a738438b028e8395cb800dfb7e8a6600052606e9ee`. The parsed rows and fields are identical.

### Note 46j: remaining-profile checkpoint

The remaining decision table contains 199 unique profiles. A verified partial pass completed 65 rows: 4 includes and 61 exclusions. Exactly 134 rows remain blank. The partial checkpoint SHA256 is `c0f60859f57ed068dbcc24682ed8d74993269f5719eb2f2157f2b8e4fc09b5a7`.

This stage submitted zero API requests, performed zero automatic profile or location merges, and made no change to spatial exposures, the regression BallTree, or regression results.

## Versioned decision files

`config/profile_eligibility_verified_decisions_20260925.csv` is the complete 251-row cumulative decision set through Note 46i.

`config/profile_eligibility_remaining_decisions_20260925_partial.csv` is the 199-row Note 46j work table. Its metadata and profile identity columns are frozen. Only the five decision fields may be completed: `manual_decision`, `decision_evidence`, `evidence_url`, `reviewed_by`, and `reviewed_on`.

The raw 450-row all-blank review table remains the lineage baseline. It must not be replaced by a later partially filled export.

## Exact continuation point

1. Review only the 134 rows with blank `manual_decision` in the partial file.
2. Do not revisit the 251 verified upstream decisions or the 65 completed remaining-profile decisions without recording a correction and evidence.
3. Preserve all 199 profile keys and all non-decision columns.
4. Run `python -m pytest tests/test_profile_eligibility_checkpoint.py -q` after every decision batch.
5. When all 199 rows are complete, restore or reimplement the missing stage 46 completion application before building physical locations or the final panel. Do not treat this checkpoint as a completed 450-profile adjudication.
