# Stage 46 profile eligibility checkpoint

## Checkpoint scope

This checkpoint records the verified state reached after stages 46a through 46j. The repository base before this checkpoint was tag `v0.4.0`, commit `9c6ade4`, which ended at stage 45.

Tag `v0.4.1` froze the verified human decisions before the temporary stage 46 code packages had been restored. Commit `c375d1c` subsequently added the retained stages `46a` through `46j`, their modules, tests, and frozen audit inputs to `main`. The tag remains a historical checkpoint. The current branch can reproduce the stage 46 preparation and application logic from versioned code.

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

### Note 46l: frozen remaining-profile completion

The user ran stage `46l` against the frozen 199-row checkpoint. The completed output contains 76 `include_dental_provider` decisions and 123 `exclude_non_dentist_category` decisions. All five review fields are complete, profile keys are unique, the profile set matches the prepared 199-row queue, and all non-decision fields remain unchanged. The completion summary reports 85 decisions before the run, 114 new decisions, 199 decisions after the run, and zero unresolved rows.

The completed CSV SHA256 is `30de341904293a81831db70ed6b23db500e276ced416633fc3d99ba0e10a9745`. The final-summary JSON SHA256 is `3d0027401d0bd845923d528cb99ad8d1c475c448e8ece3cb5f889b0c6cfa7e62`. These are user-generated interim outputs and are not committed to Git.

### Note 46m: final eligibility application and location-review preparation

The uploaded `remaining_profile_verified_additions.csv` contains the same 199 profile keys and the exact same nine decision columns as the completed stage 46l file. Its SHA256 is `05a4c90cfa42685de482fe81e7b0a09503eb732a8e4024af87c5a7ea8ade3d8c`. Together with the versioned 251-row verified baseline, it reconstructs an exact 450-profile freeze containing 217 inclusions and 233 exclusions.

Stage `46m` validates that the two inputs are complete and disjoint, requires those fixed totals, verifies identity fields against the original 46a decision template, and then uses the retained 46a application logic to prepare physical-location candidate pairs and review blocks. It performs no automatic merge and submits no API request. The user must run this stage locally to create the output data.

The user-generated output confirms 29,550 included Google profiles, 434 excluded profiles, 127 legacy anchors, 29,677 location candidates, 19,560 provisional blocks, and 5,679 multi-profile blocks. The latter contain 15,796 profiles. Review tiers are 4,031 routine shared-identity blocks, 192 focused blocks, and 1,456 complex blocks.

### Note 46n: physical-location policy review

Stage `46n` does not ask the reviewer to click through all 5,679 blocks without structure. It prepares one complete policy table. The frozen suggestion rule maps 4,031 routine same-base-address blocks to `merge_current_block_as_one_physical_location` and 1,072 complex multi-address blocks to `split_block_by_normalized_base_address`. The remaining 576 blocks retain `manual_review_required` and receive a concentrated profile-detail table.

All final decision, evidence, reviewer, date, and custom-partition fields remain blank. Stage 46o treats the suggestion column as a frozen methodological policy and adds a conservative rule for the 576 unresolved blocks; it does not reinterpret the blank fields as human decisions.

### Note 46o: final physical-location freeze

The 576 remaining blocks cannot be resolved from the retained identity fields without imposing a location rule. Stage `46o` replaces further manual review with two preregistered mappings. The main mapping keeps every exact profile separate within those ambiguous blocks, minimizing false merges. The address-merge sensitivity mapping treats each ambiguous provisional block as one location. Both mappings accept the 4,031 routine blocks and split 1,072 multi-address blocks by normalized base address.

The expected result contains 22,299 main competition locations and 20,762 address-merge sensitivity locations. All 29,550 Google outcome profiles retain their original identities and receive both location IDs in the crosswalk. No manual location reviews remain after this freeze.

## Versioned decision files

`config/profile_eligibility_verified_decisions_20260925.csv` is the complete 251-row cumulative decision set through Note 46i.

`config/profile_eligibility_remaining_decisions_20260925_partial.csv` is the 199-row Note 46j work table. Its metadata and profile identity columns are frozen. Only the five decision fields may be completed: `manual_decision`, `decision_evidence`, `evidence_url`, `reviewed_by`, and `reviewed_on`.

The raw 450-row all-blank review table remains the lineage baseline. It must not be replaced by a later partially filled export.

## Exact continuation point

1. Keep the stage 46m and 46n output directories immutable.
2. Run the stage 46o unit tests.
3. Run `46o_freeze_physical_competition_locations.py` locally.
4. Confirm 22,299 main locations, 20,762 sensitivity locations, 29,550 preserved outcome profiles, and zero remaining manual reviews.
5. Use the main crosswalk for panel construction and the address-merge mapping for the frozen location-definition sensitivity analysis.
