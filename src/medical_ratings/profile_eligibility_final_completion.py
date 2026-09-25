"""Apply the frozen final 114 exact-profile eligibility decisions."""

from __future__ import annotations

from typing import Any

import pandas as pd

from medical_ratings.profile_eligibility_completion import (
    FINAL_REVIEW_COLUMNS,
    _clean,
    _validate_decision_states,
)


EXPECTED_TOTAL_PROFILES = 199
EXPECTED_DECIDED_BEFORE = 85
REVIEWED_BY = "Codex-assisted exact-profile audit"
REVIEWED_ON = "2026-09-25"

# The sequence-to-profile mapping freezes the identity of every row reviewed here.
# It prevents the decisions from being applied to a regenerated or reordered queue.
EXPECTED_PROFILE_KEYS = {
    77: "google:cid:3440383556425355901",
    78: "google:cid:16921693145374816641",
    79: "google:cid:16710840398733596569",
    80: "google:cid:5424899260031512217",
    82: "google:cid:685936001646178210",
    83: "google:cid:17148503378792403798",
    84: "google:cid:1041337711816604659",
    87: "google:cid:8733211690348049313",
    88: "google:cid:11349040228690126297",
    90: "google:cid:11311635005790691978",
    91: "google:cid:6614151412022945732",
    92: "google:cid:16938644178152517497",
    93: "google:cid:13084037250118456891",
    94: "google:cid:7614563752735245075",
    95: "google:cid:16643914325503616698",
    96: "google:cid:16173013667061739290",
    98: "google:cid:12486001094639181232",
    102: "google:cid:6196496635137087288",
    103: "google:cid:8154161051919693340",
    104: "google:cid:2840277457789965236",
    108: "google:cid:3096215368823140089",
    110: "google:cid:6179340572617374652",
    111: "google:cid:1439068570786713565",
    112: "google:cid:2329387890553899643",
    113: "google:cid:17870772743849719591",
    114: "google:cid:920815215444172769",
    116: "google:cid:13284838367573234959",
    117: "google:cid:2683486518035905913",
    119: "google:cid:4599951736689123327",
    120: "google:cid:135096128598810680",
    121: "google:cid:7177437249452483103",
    122: "google:cid:16296289560891316346",
    123: "google:cid:18214434003362221946",
    124: "google:cid:5978500574907670907",
    125: "google:cid:7258043979584977031",
    126: "google:cid:10654524086348142840",
    128: "google:cid:14013165419560239248",
    130: "google:cid:5575282571407485970",
    131: "google:cid:9768454306702895582",
    132: "google:cid:18267820865628352209",
    135: "google:cid:9629879480313591668",
    136: "google:cid:5699955828418129941",
    137: "google:cid:3395348879050996542",
    138: "google:cid:14221168649792805791",
    139: "google:cid:5427215135935540092",
    142: "google:cid:18239375735290298326",
    144: "google:cid:7626899602233517191",
    145: "google:cid:3257959083374607564",
    146: "google:cid:15971631033806517776",
    147: "google:cid:1233923132299180747",
    148: "google:cid:12316060239770702726",
    149: "google:cid:18302922146132025269",
    150: "google:cid:6815302961615898188",
    151: "google:cid:13390369086248022341",
    152: "google:cid:18397791011711702157",
    155: "google:cid:18166011723617241542",
    156: "google:cid:8780094804165839386",
    157: "google:cid:8290167571579195981",
    158: "google:cid:10928271238652832087",
    159: "google:cid:3260818236341142390",
    160: "google:cid:14237711967666725015",
    162: "google:cid:10983116578148769284",
    163: "google:cid:7955568972727550025",
    164: "google:cid:12517242987390427288",
    165: "google:cid:12201026490335252961",
    166: "google:cid:14242845636480544373",
    167: "google:cid:10103828371342018102",
    168: "google:cid:1725797652379241771",
    170: "google:cid:2428785299818441667",
    171: "google:cid:17876037465300181764",
    172: "google:cid:16042696556243485449",
    173: "google:cid:16190680881071780487",
    174: "google:cid:11366070002874749651",
    176: "google:cid:4884419086949519441",
    180: "google:cid:3746368657671100983",
    182: "google:cid:2810400098018904937",
    183: "google:cid:17695359038008349542",
    184: "google:cid:16992949408117753400",
    185: "google:cid:8725559073317735762",
    186: "google:cid:5006005254849634573",
    189: "google:cid:7491525317975939457",
    190: "google:cid:706109540966761708",
    191: "google:cid:11349239648908701467",
    193: "google:cid:11990484528381377309",
    194: "google:cid:8019442712982059650",
    195: "google:cid:15466958758423106428",
    198: "google:cid:15840384001208137121",
    199: "google:cid:8776957313786257906",
    200: "google:cid:4534990736566493603",
    203: "google:cid:4691704608957327781",
    205: "google:cid:15322627160932991390",
    209: "google:cid:6263446382272302887",
    210: "google:cid:3053711292195176961",
    211: "google:cid:8516860510085333250",
    213: "google:cid:12624793362500748108",
    214: "google:cid:15164199505872784181",
    215: "google:cid:15310307393337248434",
    216: "google:cid:6451845079583961423",
    217: "google:cid:6164055533882993300",
    218: "google:cid:6881627921830420633",
    219: "google:cid:12260773327504859179",
    220: "google:cid:5725267993414120448",
    221: "google:cid:10257469848042679318",
    223: "google:cid:10487271695260862641",
    224: "google:cid:2981445453940694204",
    228: "google:cid:10842945812211081545",
    229: "google:cid:6790315200658554690",
    230: "google:cid:1252474763438112699",
    231: "google:cid:8951881897675096385",
    232: "google:cid:11047455065508509761",
    234: "google:cid:10636425930933224952",
    235: "google:cid:10967843234449240540",
    237: "google:cid:10667488645197953416",
    238: "google:cid:5141540515377181725",
}

INCLUDE_SEQUENCES = {
    77, 78, 80, 82, 83, 87, 88, 95, 96, 98, 102, 103, 104, 108, 110,
    111, 112, 113, 119, 121, 122, 123, 126, 128, 130, 131, 132, 135,
    137, 138, 139, 142, 145, 147, 151, 155, 156, 157, 160, 163, 165,
    166, 168, 172, 173, 174, 184, 186, 191, 200, 203, 211, 213, 214,
    215, 216, 218, 219, 220, 228, 229, 235, 237,
}

SPECIAL_EVIDENCE = {
    116: (
        "Walmart announced that all Walmart Health centers would close, so this "
        "profile is not a current patient-facing dental provider.",
        "https://corporate.walmart.com/news/2024/04/30/walmart-health-is-closing",
    ),
    146: (
        "The current official orthodontic practice location is 66 Lincoln Court, "
        "not the exact 364 Merrick Road profile address.",
        "https://www.halberstadtortho.com/contact",
    ),
}


def _require_columns(frame: pd.DataFrame) -> None:
    required = {"profile_key", "completion_sequence", "exact_google_profile_url"}
    required.update(FINAL_REVIEW_COLUMNS)
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Checkpoint is missing columns: {missing}")


def _sequence(frame: pd.DataFrame) -> pd.Series:
    numeric = pd.to_numeric(frame["completion_sequence"], errors="coerce")
    if numeric.isna().any() or (numeric % 1 != 0).any():
        raise ValueError("Checkpoint contains invalid completion_sequence values")
    return numeric.astype(int)


def _decision_evidence(row: pd.Series, sequence: int, include: bool) -> tuple[str, str]:
    if sequence in SPECIAL_EVIDENCE:
        return SPECIAL_EVIDENCE[sequence]
    url = row["exact_google_profile_url"]
    if include:
        return (
            "Exact-profile review verified a patient-facing dental, orthodontic, "
            "oral-surgery, denture, or dental-sleep service at this location.",
            url,
        )
    category = row.get("observed_categories", "") or "profile identity"
    return (
        f"Exact-profile review did not verify a current patient-facing dental "
        f"provider; observed category or identity: {category}.",
        url,
    )


def complete_final_checkpoint(
    checkpoint_decisions: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fill exactly the frozen 114 rows while preserving all prior decisions."""

    _require_columns(checkpoint_decisions)
    checkpoint = _clean(checkpoint_decisions)
    if len(checkpoint) != EXPECTED_TOTAL_PROFILES:
        raise ValueError(
            f"Expected {EXPECTED_TOTAL_PROFILES} checkpoint rows, got {len(checkpoint)}"
        )
    if checkpoint["profile_key"].duplicated().any():
        raise ValueError("Checkpoint contains duplicate profile keys")
    decided = _validate_decision_states(checkpoint, "checkpoint decisions")
    if int(decided.sum()) != EXPECTED_DECIDED_BEFORE:
        raise ValueError(
            f"Expected {EXPECTED_DECIDED_BEFORE} existing decisions, "
            f"got {int(decided.sum())}; install the prior 85-decision checkpoint first"
        )

    sequence = _sequence(checkpoint)
    unresolved = checkpoint.loc[~decided].copy()
    unresolved_sequence = sequence.loc[~decided]
    actual_sequences = set(unresolved_sequence.tolist())
    expected_sequences = set(EXPECTED_PROFILE_KEYS)
    if actual_sequences != expected_sequences:
        raise ValueError(
            "Unresolved completion sequences do not match the frozen final audit; "
            f"missing={sorted(expected_sequences - actual_sequences)[:10]}, "
            f"extra={sorted(actual_sequences - expected_sequences)[:10]}"
        )

    mismatches: list[str] = []
    for index, seq in unresolved_sequence.items():
        expected_key = EXPECTED_PROFILE_KEYS[seq]
        actual_key = checkpoint.at[index, "profile_key"]
        if actual_key != expected_key:
            mismatches.append(f"{seq}:{actual_key}")
    if mismatches:
        raise ValueError(
            "Unresolved profile identities differ from the frozen audit: "
            + ", ".join(mismatches[:10])
        )

    result = checkpoint.copy()
    for index, seq in unresolved_sequence.items():
        include = seq in INCLUDE_SEQUENCES
        evidence, evidence_url = _decision_evidence(result.loc[index], seq, include)
        result.at[index, "manual_decision"] = (
            "include_dental_provider" if include else "exclude_non_dentist_category"
        )
        result.at[index, "decision_evidence"] = evidence
        result.at[index, "evidence_url"] = evidence_url
        result.at[index, "reviewed_by"] = REVIEWED_BY
        result.at[index, "reviewed_on"] = REVIEWED_ON

    decided_after = _validate_decision_states(result, "completed decisions")
    if not decided_after.all():
        raise AssertionError("Final completion left unresolved decision rows")
    if not result.loc[decided, FINAL_REVIEW_COLUMNS].equals(
        checkpoint.loc[decided, FINAL_REVIEW_COLUMNS]
    ):
        raise AssertionError("Final completion changed an existing decision")

    summary = {
        "analysis_status": "remaining_profile_eligibility_audit_complete",
        "api_requests_submitted": 0,
        "checkpoint_profiles": int(len(result)),
        "decided_before": int(decided.sum()),
        "new_decisions_added": int((~decided).sum()),
        "decided_after": int(decided_after.sum()),
        "remaining_unresolved": int((~decided_after).sum()),
        "include_dental_provider": int(
            result["manual_decision"].eq("include_dental_provider").sum()
        ),
        "exclude_non_dentist_category": int(
            result["manual_decision"].eq("exclude_non_dentist_category").sum()
        ),
        "automatic_final_decisions_applied": 0,
    }
    return result[checkpoint_decisions.columns], summary
