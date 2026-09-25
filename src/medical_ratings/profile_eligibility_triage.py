"""Prepare auditable review batches for unresolved cross-source profiles."""

from __future__ import annotations

from collections import Counter
import hashlib
import re
from typing import Any

import pandas as pd


ALLOWED_FINAL_DECISIONS = {
    "include_dental_provider",
    "exclude_non_dentist_category",
}
ALLOWED_RULE_DECISIONS = {"include", "exclude", "manual_review"}

DENTAL_TITLE_PATTERNS = {
    "dental": r"\bdental\b",
    "dentist": r"\bdentist(?:s)?\b",
    "dentistry": r"\bdentistry\b",
    "orthodontic": r"\borthodont",
    "endodontic": r"\bendodont",
    "periodontic": r"\bperiodont",
    "prosthodontic": r"\bprosthodont",
    "maxillofacial": r"\bmaxillofacial\b",
    "oral_surgery": r"\boral\s+(?:and\s+maxillofacial\s+)?surg",
    "dds": r"\bdds\b",
    "dmd": r"\bdmd\b",
}

NONDENTAL_TITLE_PATTERNS = {
    "veterinary": r"\bvet(?:erinary|erinarian)?\b",
    "animal": r"\banimal\b",
    "medical": r"\bmedical\b",
    "hospital": r"\bhospital\b",
    "pharmacy": r"\bpharmacy\b",
    "pediatrics": r"\bpediatric(?:ian|s)?\b",
    "laboratory": r"\blaborator(?:y|ies)\b|\bdental\s+lab\b",
    "insurance": r"\binsurance\b",
    "attorney": r"\battorney\b",
    "software": r"\bsoftware\b",
    "marketing": r"\bmarketing\b",
    "pet_or_companion_animal": r"\b(?:dog|cat|pet)s?\b",
    "staffing": r"\bstaffing\b|\btemp\s+agency\b",
    "equipment_sales": r"\bequipment\s+sales\b|\bsupply\s+store\b",
    "school_or_training": r"\b(?:school|college|academy|training|assistant\s+program)\b",
}

NONPROVIDER_CATEGORY_PATTERNS = {
    "veterinary": r"\bveterinar|\bveterinary\s+care\b",
    "animal_provider": r"\banimal\s+hospital\b",
    "dental_supply": r"\bdental\s+supply\s+store\b",
    "education": r"\bdental\s+school\b|\beducational\s+institution\b",
    "staffing": r"\btemp\s+agency\b|\bemployment\s+agency\b",
    "software_or_marketing": r"\bsoftware\s+company\b|\bmarketing\s+agency\b",
    "research_or_sales": r"\bmarket\s+researcher\b|\bresearch\s+foundation\b",
    "insurance": r"\binsurance\s+agency\b|\bhealth\s+insurance\s+agency\b",
    "manufacturer": r"\bmanufacturer\b",
    "design_engineer": r"\bdesign\s+engineer\b",
}


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _split_pipe(value: Any) -> list[str]:
    return sorted({_text(item) for item in _text(value).split("|") if _text(item)})


def _signals(title: Any, patterns: dict[str, str]) -> list[str]:
    text = _text(title).casefold()
    return [name for name, pattern in patterns.items() if re.search(pattern, text)]


def _group_id(*values: Any) -> str:
    payload = "\x1f".join(_text(value) for value in values)
    return "eligibility_group:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def prepare_profile_eligibility_triage(
    decisions: pd.DataFrame,
    inventory: pd.DataFrame,
    category_rules: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Return row-level suggestions, category groups, unknown-category queue, and summary."""

    required_decisions = {
        "decision_id",
        "market",
        "profile_key",
        "title",
        "observed_sources",
        "observed_categories",
        "observed_source_decisions",
        "allowed_manual_decisions",
        "manual_decision",
        "decision_evidence",
        "evidence_url",
        "reviewed_by",
        "reviewed_on",
    }
    missing = required_decisions - set(decisions.columns)
    if missing:
        raise ValueError(f"Profile decisions are missing: {sorted(missing)}")
    required_inventory = {
        "profile_key",
        "requested_location",
        "preliminary_profile_status",
    }
    missing = required_inventory - set(inventory.columns)
    if missing:
        raise ValueError(f"Profile inventory is missing: {sorted(missing)}")
    required_rules = {"category", "category_decision", "reason"}
    missing = required_rules - set(category_rules.columns)
    if missing:
        raise ValueError(f"Category rules are missing: {sorted(missing)}")
    if decisions["decision_id"].duplicated().any() or decisions["profile_key"].duplicated().any():
        raise ValueError("Profile decision identifiers must be unique")
    if decisions["manual_decision"].astype(str).str.strip().ne("").any():
        raise ValueError("Triage input must be the unmodified blank decision template")

    pending = inventory.loc[
        inventory["preliminary_profile_status"].eq("pending_manual_review"),
        ["requested_location", "profile_key"],
    ].copy()
    expected = set(zip(pending["requested_location"], pending["profile_key"]))
    actual = set(zip(decisions["market"], decisions["profile_key"]))
    if expected != actual:
        raise ValueError("Decision template does not exactly cover pending inventory profiles")

    rules = category_rules.copy()
    rules["category_key"] = rules["category"].astype("string").str.strip().str.casefold()
    if rules["category_key"].duplicated().any():
        raise ValueError("Category rules contain duplicate normalized categories")
    invalid = set(rules["category_decision"]) - ALLOWED_RULE_DECISIONS
    if invalid:
        raise ValueError(f"Invalid category rule decisions: {sorted(invalid)}")
    rule_lookup = {
        str(row.category_key): (str(row.category_decision), str(row.reason))
        for row in rules.itertuples(index=False)
    }

    records: list[dict[str, Any]] = []
    unknown_counter: Counter[str] = Counter()
    unknown_rows: dict[str, list[dict[str, Any]]] = {}
    for row in decisions.itertuples(index=False):
        categories = _split_pipe(row.observed_categories)
        category_decisions: list[str] = []
        unknown_categories: list[str] = []
        category_reasons: list[str] = []
        for category in categories:
            rule = rule_lookup.get(category.casefold())
            if rule is None:
                category_decisions.append("unknown")
                unknown_categories.append(category)
                unknown_counter[category] += 1
            else:
                category_decisions.append(rule[0])
                category_reasons.append(f"{category}: {rule[1]}")
        if not categories:
            category_decisions = ["unknown"]
            unknown_categories = ["<blank category>"]
            unknown_counter["<blank category>"] += 1

        decision_set = set(category_decisions)
        dental_signals = _signals(row.title, DENTAL_TITLE_PATTERNS)
        nondental_signals = _signals(row.title, NONDENTAL_TITLE_PATTERNS)
        category_nonprovider_signals = _signals(
            row.observed_categories, NONPROVIDER_CATEGORY_PATTERNS
        )
        if decision_set == {"exclude"}:
            suggestion = "exclude_non_dentist_category"
            tier = "routine_frozen_rule"
            basis = "all observed categories have frozen exclude rules"
        elif category_nonprovider_signals and "include" not in decision_set:
            suggestion = "exclude_non_dentist_category"
            tier = "focused_category_evidence"
            basis = "unconfigured category identifies an auxiliary or non-provider business"
        elif "include" in decision_set:
            suggestion = "include_dental_provider"
            tier = "focused_category_conflict"
            basis = "at least one observed category has a frozen include rule"
        elif dental_signals and not nondental_signals:
            suggestion = "include_dental_provider"
            tier = "focused_title_evidence"
            basis = "dental title signal with no configured include category"
        elif nondental_signals and not dental_signals:
            suggestion = "exclude_non_dentist_category"
            tier = "focused_title_evidence"
            basis = "non-dental title signal with no configured final category rule"
        else:
            suggestion = ""
            tier = "external_evidence_required"
            basis = "category and title evidence do not support a safe batch suggestion"

        rule_pattern = "|".join(sorted(decision_set))
        group_id = _group_id(
            row.observed_categories,
            row.observed_source_decisions,
            rule_pattern,
            tier,
            suggestion,
        )
        record = row._asdict()
        record.update(
            {
                "category_group_id": group_id,
                "category_rule_pattern": rule_pattern,
                "category_rule_reasons": " || ".join(category_reasons),
                "unknown_categories": "|".join(unknown_categories),
                "dental_title_signals": "|".join(dental_signals),
                "nondental_title_signals": "|".join(nondental_signals),
                "category_nonprovider_signals": "|".join(category_nonprovider_signals),
                "suggested_manual_decision": suggestion,
                "review_tier": tier,
                "suggestion_basis": basis,
                "automatic_final_decision_applied": False,
            }
        )
        records.append(record)
        for category in unknown_categories:
            unknown_rows.setdefault(category, []).append(record)

    triage = pd.DataFrame.from_records(records).sort_values(
        ["review_tier", "category_group_id", "market", "title", "profile_key"],
        ignore_index=True,
    )
    group_records: list[dict[str, Any]] = []
    for group_id, group in triage.groupby("category_group_id", sort=True):
        group_records.append(
            {
                "category_group_id": group_id,
                "observed_categories": group["observed_categories"].iloc[0],
                "observed_source_decisions": group["observed_source_decisions"].iloc[0],
                "category_rule_pattern": group["category_rule_pattern"].iloc[0],
                "review_tier": group["review_tier"].iloc[0],
                "suggested_manual_decision": group["suggested_manual_decision"].iloc[0],
                "suggestion_basis": group["suggestion_basis"].iloc[0],
                "profile_count": len(group),
                "markets": "|".join(sorted(set(group["market"]))),
                "sample_titles": " || ".join(group["title"].head(5)),
                "group_manual_decision": "",
                "group_decision_evidence": "",
                "reviewed_by": "",
                "reviewed_on": "",
            }
        )
    groups = pd.DataFrame.from_records(group_records).sort_values(
        ["review_tier", "profile_count", "observed_categories"],
        ascending=[True, False, True],
        ignore_index=True,
    )

    unknown_records: list[dict[str, Any]] = []
    for category, rows in sorted(unknown_rows.items()):
        frame = pd.DataFrame.from_records(rows)
        unknown_records.append(
            {
                "category": category,
                "profile_count": unknown_counter[category],
                "markets": "|".join(sorted(set(frame["market"]))),
                "profiles_with_dental_title_signal": int(frame["dental_title_signals"].ne("").sum()),
                "profiles_with_nondental_title_signal": int(frame["nondental_title_signals"].ne("").sum()),
                "sample_titles": " || ".join(frame["title"].head(8)),
                "proposed_category_decision": "",
                "decision_reason": "",
                "reviewed_by": "",
                "reviewed_on": "",
            }
        )
    unknown = pd.DataFrame.from_records(unknown_records).sort_values(
        ["profile_count", "category"], ascending=[False, True], ignore_index=True
    )

    tier_counts = triage["review_tier"].value_counts()
    suggestion_counts = triage["suggested_manual_decision"].replace(
        {"": "no_safe_suggestion"}
    ).value_counts()
    if "routine_frozen_rule" in tier_counts:
        next_action = (
            "Review routine frozen-rule suggestions first, then category conflicts "
            "and title evidence; obtain external evidence for rows without a safe suggestion."
        )
    else:
        next_action = (
            "Review category conflicts and title-based suggestions, then obtain external "
            "evidence for rows without a safe suggestion."
        )
    summary = {
        "analysis_status": "profile_eligibility_triage_prepared_not_final",
        "api_requests_submitted": 0,
        "input_pending_profiles": len(triage),
        "category_review_groups": len(groups),
        "unknown_category_values": len(unknown),
        "profiles_by_review_tier": {
            str(key): int(value) for key, value in tier_counts.items()
        },
        "profiles_by_suggested_decision": {
            str(key): int(value) for key, value in suggestion_counts.items()
        },
        "automatic_final_decisions_applied": 0,
        "regression_balltree_modified": False,
        "next_required_action": next_action,
    }
    return triage, groups, unknown, summary
