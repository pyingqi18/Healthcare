"""Build a self-contained browser app for manual profile eligibility review."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd


BLOCK_DECISIONS = {
    "",
    "include_dental_provider",
    "exclude_non_dentist_category",
    "individual_review",
}
ROW_DECISIONS = {
    "",
    "include_dental_provider",
    "exclude_non_dentist_category",
}

ROW_REQUIRED_COLUMNS = {
    "decision_id",
    "review_block_id",
    "market",
    "profile_key",
    "title",
    "address",
    "observed_categories",
    "review_tier",
    "suggested_manual_decision",
    "source_phone",
    "source_website_url",
    "direct_profile_evidence_url",
    "manual_decision",
    "decision_evidence",
    "evidence_url",
    "reviewed_by",
    "reviewed_on",
}
BLOCK_REQUIRED_COLUMNS = {
    "review_block_id",
    "review_block_basis",
    "review_domain",
    "profile_count",
    "review_tier",
    "observed_categories",
    "suggested_manual_decision",
    "group_manual_decision",
    "reviewed_member_count",
    "group_decision_evidence",
    "reviewed_by",
    "reviewed_on",
}


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{label} is missing columns: {sorted(missing)}")


def _records(frame: pd.DataFrame) -> list[dict[str, str]]:
    clean = frame.fillna("").astype(str)
    return clean.to_dict(orient="records")


def _payload_hash(rows: pd.DataFrame, blocks: pd.DataFrame) -> str:
    payload = "\n".join(
        list(rows["decision_id"].map(_text))
        + list(blocks["review_block_id"].map(_text))
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_profile_eligibility_review_app_inputs(
    rows: pd.DataFrame,
    blocks: pd.DataFrame,
) -> dict[str, Any]:
    """Validate the frozen row and block files before embedding them in HTML."""

    _require_columns(rows, ROW_REQUIRED_COLUMNS, "Profile review rows")
    _require_columns(blocks, BLOCK_REQUIRED_COLUMNS, "Profile review blocks")
    if rows["decision_id"].duplicated().any():
        raise ValueError("Profile review rows contain duplicate decision_id values")
    if rows["profile_key"].duplicated().any():
        raise ValueError("Profile review rows contain duplicate profile_key values")
    if blocks["review_block_id"].duplicated().any():
        raise ValueError("Profile review blocks contain duplicate review_block_id values")
    if set(rows["review_block_id"].map(_text)) != set(
        blocks["review_block_id"].map(_text)
    ):
        raise ValueError("Row and block review_block_id values do not reconcile")
    actual_counts = rows.groupby("review_block_id").size().sort_index()
    declared_counts = (
        pd.to_numeric(blocks.set_index("review_block_id")["profile_count"])
        .astype(int)
        .sort_index()
    )
    if not actual_counts.equals(declared_counts):
        raise ValueError("Block profile counts do not reconcile with review rows")
    invalid_blocks = sorted(
        set(blocks["group_manual_decision"].map(_text)) - BLOCK_DECISIONS
    )
    if invalid_blocks:
        raise ValueError(f"Invalid existing block decisions: {invalid_blocks}")
    invalid_rows = sorted(set(rows["manual_decision"].map(_text)) - ROW_DECISIONS)
    if invalid_rows:
        raise ValueError(f"Invalid existing row decisions: {invalid_rows}")
    multi = blocks.loc[pd.to_numeric(blocks["profile_count"]).gt(1)]
    if not multi["review_block_basis"].eq(
        "shared_domain_within_category_group"
    ).all():
        raise ValueError("Every multi-profile block must be supported by shared domain evidence")
    if multi["review_domain"].map(_text).eq("").any():
        raise ValueError("Every multi-profile block must record its shared domain")

    return {
        "analysis_status": "profile_eligibility_manual_review_app_built",
        "api_requests_submitted": 0,
        "profile_rows": len(rows),
        "review_blocks": len(blocks),
        "shared_domain_review_blocks": int(
            blocks["review_block_basis"]
            .eq("shared_domain_within_category_group")
            .sum()
        ),
        "singleton_review_blocks": int(
            blocks["review_block_basis"].eq("singleton_profile").sum()
        ),
        "maximum_block_size": int(pd.to_numeric(blocks["profile_count"]).max()),
        "payload_sha256": _payload_hash(rows, blocks),
        "automatic_decisions_applied": 0,
    }


HTML_TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Profile eligibility review</title>
<style>
:root { color-scheme: light; font-family: Arial, sans-serif; }
body { margin: 0; background: #f4f6f8; color: #17202a; }
header { position: sticky; top: 0; z-index: 5; background: #17324d; color: white; padding: 14px 20px; }
header h1 { margin: 0 0 8px; font-size: 20px; }
.stats { display: flex; flex-wrap: wrap; gap: 14px; font-size: 14px; }
.toolbar { display: grid; grid-template-columns: 1fr 180px 180px 160px auto auto; gap: 8px; padding: 12px 20px; background: white; border-bottom: 1px solid #ccd4dc; }
input, select, textarea, button { font: inherit; }
input, select, textarea { border: 1px solid #aeb8c2; border-radius: 4px; padding: 7px; box-sizing: border-box; }
button { border: 1px solid #355b7d; background: #355b7d; color: white; border-radius: 4px; padding: 8px 12px; cursor: pointer; }
button.secondary { background: white; color: #24435f; }
main { max-width: 1500px; margin: 16px auto; padding: 0 18px 40px; }
.block { background: white; border: 1px solid #ccd4dc; border-radius: 6px; padding: 16px; }
.block h2 { margin: 0 0 8px; font-size: 20px; }
.meta { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-bottom: 12px; font-size: 13px; }
.meta div { background: #eef2f5; padding: 8px; border-radius: 4px; overflow-wrap: anywhere; }
.decision { display: grid; grid-template-columns: 260px 1fr 180px 150px; gap: 8px; margin: 12px 0; align-items: start; }
.decision textarea { min-height: 70px; }
.confirm { display: flex; gap: 8px; align-items: center; margin: 8px 0 14px; }
.members { display: grid; gap: 12px; }
.member { border: 1px solid #d7dde3; border-radius: 5px; padding: 12px; }
.member h3 { margin: 0 0 6px; font-size: 16px; }
.member-grid { display: grid; grid-template-columns: 1.2fr 1.2fr 1fr 1fr; gap: 7px; font-size: 13px; }
.member-grid div { overflow-wrap: anywhere; }
.links { margin: 8px 0; display: flex; gap: 14px; }
.links a { color: #075aa6; }
.row-decision { display: grid; grid-template-columns: 250px 1fr 170px 140px; gap: 8px; margin-top: 8px; }
.row-decision textarea { min-height: 55px; }
.nav { display: flex; justify-content: space-between; gap: 8px; margin-top: 12px; }
.warning { color: #9b2c2c; font-weight: 600; }
.complete { color: #17643a; font-weight: 600; }
.muted { color: #5e6a75; }
@media (max-width: 900px) {
  .toolbar, .decision, .row-decision, .meta, .member-grid { grid-template-columns: 1fr; }
}
</style>
</head>
<body>
<header>
  <h1>Profile eligibility review</h1>
  <div class="stats">
    <span id="progress"></span>
    <span id="included"></span>
    <span id="excluded"></span>
    <span id="individual"></span>
    <span id="saved"></span>
  </div>
</header>
<div class="toolbar">
  <input id="search" placeholder="Search title, market, category, domain">
  <select id="statusFilter"><option value="all">All statuses</option><option value="unresolved">Unresolved</option><option value="complete">Complete</option><option value="individual_review">Individual review</option></select>
  <select id="tierFilter"><option value="all">All review tiers</option></select>
  <input id="defaultReviewer" placeholder="Default reviewer">
  <button id="exportGroups">Export reviewed blocks CSV</button>
  <button id="exportRows">Export reviewed rows CSV</button>
</div>
<main>
  <div id="position" class="muted"></div>
  <section id="review" class="block"></section>
  <div class="nav">
    <button id="previous" class="secondary">Previous</button>
    <button id="nextUnresolved">Next unresolved</button>
    <button id="next" class="secondary">Next</button>
  </div>
</main>
<script id="rowsData" type="application/json">__ROWS_JSON__</script>
<script id="blocksData" type="application/json">__BLOCKS_JSON__</script>
<script id="metaData" type="application/json">__META_JSON__</script>
<script>
const rows = JSON.parse(document.getElementById('rowsData').textContent);
const blocks = JSON.parse(document.getElementById('blocksData').textContent);
const meta = JSON.parse(document.getElementById('metaData').textContent);
const storageKey = `profile-eligibility-review-${meta.payload_sha256}`;
const allowedFinal = ['include_dental_provider', 'exclude_non_dentist_category'];
const rowsByBlock = {};
for (const row of rows) {
  if (!rowsByBlock[row.review_block_id]) rowsByBlock[row.review_block_id] = [];
  rowsByBlock[row.review_block_id].push(row);
}
let state = JSON.parse(localStorage.getItem(storageKey) || '{"blocks":{},"rows":{}}');
if (!state.blocks) state.blocks = {};
if (!state.rows) state.rows = {};
if (!state.defaultReviewer) state.defaultReviewer = '';
const tierPriority = {focused_category_conflict: 1, focused_title_evidence: 2, focused_category_evidence: 3, external_evidence_required: 4};
const reviewOrder = [...blocks].sort((a, b) => {
  const sharedA = a.review_block_basis === 'shared_domain_within_category_group' ? 0 : 1;
  const sharedB = b.review_block_basis === 'shared_domain_within_category_group' ? 0 : 1;
  return sharedA - sharedB || (tierPriority[a.review_tier] ?? 9) - (tierPriority[b.review_tier] ?? 9) || a.review_block_id.localeCompare(b.review_block_id);
});
let filtered = [];
let index = 0;

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function today() { return new Date().toISOString().slice(0, 10); }
function blockState(block) {
  if (!state.blocks[block.review_block_id]) {
    state.blocks[block.review_block_id] = {
      decision: block.group_manual_decision || '', evidence: block.group_decision_evidence || '',
      reviewer: block.reviewed_by || '', date: block.reviewed_on || '', reviewedAll: block.reviewed_member_count === block.profile_count
    };
  }
  return state.blocks[block.review_block_id];
}
function rowState(row) {
  if (!state.rows[row.decision_id]) {
    state.rows[row.decision_id] = {
      decision: row.manual_decision || '', evidence: row.decision_evidence || '',
      url: row.evidence_url || '', reviewer: row.reviewed_by || '', date: row.reviewed_on || ''
    };
  }
  return state.rows[row.decision_id];
}
function rowComplete(row) {
  const s = rowState(row);
  return allowedFinal.includes(s.decision) && s.evidence.trim() && s.reviewer.trim() && s.date.trim();
}
function blockComplete(block) {
  const s = blockState(block);
  const members = rowsByBlock[block.review_block_id] || [];
  const overridesValid = members.filter(r => rowState(r).decision).every(rowComplete);
  if (members.length && members.every(rowComplete)) return true;
  if (allowedFinal.includes(s.decision)) return s.reviewedAll && s.evidence.trim() && s.reviewer.trim() && s.date.trim() && overridesValid;
  if (s.decision === 'individual_review') return members.every(rowComplete);
  return false;
}
function save() {
  localStorage.setItem(storageKey, JSON.stringify(state));
  document.getElementById('saved').textContent = `Saved locally ${new Date().toLocaleTimeString()}`;
  updateProgress();
}
function updateProgress() {
  const complete = blocks.filter(blockComplete).length;
  const decisions = blocks.map(b => blockState(b).decision);
  document.getElementById('progress').textContent = `Complete ${complete} of ${blocks.length}`;
  document.getElementById('included').textContent = `Block include ${decisions.filter(x => x === allowedFinal[0]).length}`;
  document.getElementById('excluded').textContent = `Block exclude ${decisions.filter(x => x === allowedFinal[1]).length}`;
  document.getElementById('individual').textContent = `Individual ${decisions.filter(x => x === 'individual_review').length}`;
}
function memberHtml(row) {
  const s = rowState(row);
  const website = row.source_website_url ? `<a target="_blank" href="${esc(row.source_website_url)}">Website</a>` : '<span class="muted">No website</span>';
  const google = `<a target="_blank" href="${esc(row.direct_profile_evidence_url)}">Google profile</a>`;
  return `<article class="member" data-row="${esc(row.decision_id)}">
    <h3>${esc(row.title)}</h3>
    <div class="member-grid">
      <div><b>Market</b><br>${esc(row.market)}</div><div><b>Address</b><br>${esc(row.address)}</div>
      <div><b>Categories</b><br>${esc(row.observed_categories)}</div><div><b>Phone</b><br>${esc(row.source_phone || 'Missing')}</div>
    </div>
    <div class="links">${website}${google}</div>
    <div class="muted">Suggested: ${esc(row.suggested_manual_decision || 'none')} | Existing route: ${esc(row.existing_evidence_route)}</div>
    <div class="row-decision">
      <select class="row-field" data-field="decision"><option value="">No row override</option><option value="include_dental_provider" ${s.decision === 'include_dental_provider' ? 'selected' : ''}>Include dental provider</option><option value="exclude_non_dentist_category" ${s.decision === 'exclude_non_dentist_category' ? 'selected' : ''}>Exclude non-dentist</option></select>
      <textarea class="row-field" data-field="evidence" placeholder="Evidence for row decision">${esc(s.evidence)}</textarea>
      <input class="row-field" data-field="reviewer" value="${esc(s.reviewer)}" placeholder="Reviewer">
      <input class="row-field" data-field="date" type="date" value="${esc(s.date)}">
    </div>
  </article>`;
}
function render() {
  applyFilters(false);
  if (!filtered.length) {
    document.getElementById('review').innerHTML = '<p>No blocks match the current filters.</p>';
    document.getElementById('position').textContent = '';
    return;
  }
  index = Math.max(0, Math.min(index, filtered.length - 1));
  const block = filtered[index];
  const s = blockState(block);
  const members = rowsByBlock[block.review_block_id] || [];
  document.getElementById('position').textContent = `Filtered block ${index + 1} of ${filtered.length}`;
  document.getElementById('review').innerHTML = `
    <h2>${esc(block.review_block_basis)} | ${esc(block.review_domain || 'single profile')}</h2>
    <div class="meta">
      <div><b>Review tier</b><br>${esc(block.review_tier)}</div>
      <div><b>Profiles</b><br>${esc(block.profile_count)}</div>
      <div><b>Categories</b><br>${esc(block.observed_categories)}</div>
      <div><b>Suggested</b><br>${esc(block.suggested_manual_decision || 'none')}</div>
    </div>
    <div class="decision">
      <select id="blockDecision"><option value="">Select block decision</option><option value="include_dental_provider" ${s.decision === 'include_dental_provider' ? 'selected' : ''}>Include dental provider</option><option value="exclude_non_dentist_category" ${s.decision === 'exclude_non_dentist_category' ? 'selected' : ''}>Exclude non-dentist</option><option value="individual_review" ${s.decision === 'individual_review' ? 'selected' : ''}>Individual review</option></select>
      <textarea id="blockEvidence" placeholder="Evidence supporting the block decision">${esc(s.evidence)}</textarea>
      <input id="blockReviewer" value="${esc(s.reviewer)}" placeholder="Reviewer">
      <input id="blockDate" type="date" value="${esc(s.date)}">
    </div>
    <label class="confirm"><input id="reviewedAll" type="checkbox" ${s.reviewedAll ? 'checked' : ''}> I reviewed every member shown below before using one block decision.</label>
    <div id="completion" class="${blockComplete(block) ? 'complete' : 'warning'}">${blockComplete(block) ? 'Block complete' : 'Block incomplete'}</div>
    <div class="members">${members.map(memberHtml).join('')}</div>`;
  bindCurrent(block, members);
}
function bindCurrent(block, members) {
  const s = blockState(block);
  document.getElementById('blockDecision').onchange = e => { s.decision = e.target.value; if (s.decision && !s.date) s.date = today(); if (s.decision && !s.reviewer) s.reviewer = state.defaultReviewer; save(); render(); };
  document.getElementById('blockEvidence').oninput = e => { s.evidence = e.target.value; save(); };
  document.getElementById('blockReviewer').oninput = e => { s.reviewer = e.target.value; save(); };
  document.getElementById('blockDate').onchange = e => { s.date = e.target.value; save(); };
  document.getElementById('reviewedAll').onchange = e => { s.reviewedAll = e.target.checked; save(); render(); };
  document.querySelectorAll('.member').forEach(element => {
    const row = members.find(x => x.decision_id === element.dataset.row);
    const rs = rowState(row);
    element.querySelectorAll('.row-field').forEach(field => {
      const eventName = field.tagName === 'SELECT' || field.type === 'date' ? 'change' : 'input';
      field.addEventListener(eventName, e => { rs[e.target.dataset.field] = e.target.value; if (rs.decision && !rs.date) rs.date = today(); if (rs.decision && !rs.reviewer) rs.reviewer = state.defaultReviewer; save(); });
    });
  });
}
function applyFilters(reset=true) {
  const query = document.getElementById('search').value.trim().toLowerCase();
  const status = document.getElementById('statusFilter').value;
  const tier = document.getElementById('tierFilter').value;
  filtered = reviewOrder.filter(block => {
    const members = rowsByBlock[block.review_block_id] || [];
    const haystack = [block.review_domain, block.observed_categories, ...members.flatMap(r => [r.title, r.market, r.address])].join(' ').toLowerCase();
    const statusOk = status === 'all' || (status === 'complete' && blockComplete(block)) || (status === 'unresolved' && !blockComplete(block)) || (status === 'individual_review' && blockState(block).decision === 'individual_review');
    return (!query || haystack.includes(query)) && (tier === 'all' || block.review_tier === tier) && statusOk;
  });
  if (reset) index = 0;
}
function csvEscape(value) {
  const text = String(value ?? '');
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}
function downloadCsv(filename, records, columns) {
  const lines = [columns.map(csvEscape).join(','), ...records.map(record => columns.map(column => csvEscape(record[column])).join(','))];
  const blob = new Blob(['\ufeff' + lines.join('\r\n')], {type: 'text/csv;charset=utf-8'});
  const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = filename; link.click(); URL.revokeObjectURL(link.href);
}
function exportGroups() {
  const output = blocks.map(block => {
    const result = {...block}; const s = blockState(block);
    result.group_manual_decision = s.decision;
    result.reviewed_member_count = allowedFinal.includes(s.decision) && s.reviewedAll ? block.profile_count : '';
    result.group_decision_evidence = s.evidence; result.reviewed_by = s.reviewer; result.reviewed_on = s.date;
    return result;
  });
  downloadCsv('profile_eligibility_review_groups_reviewed.csv', output, meta.block_columns);
}
function exportRows() {
  const output = rows.map(row => {
    const result = {...row}; const s = rowState(row);
    result.manual_decision = s.decision; result.decision_evidence = s.evidence; result.evidence_url = s.url;
    result.reviewed_by = s.reviewer; result.reviewed_on = s.date; return result;
  });
  downloadCsv('profile_eligibility_review_rows_reviewed.csv', output, meta.row_columns);
}
for (const tier of [...new Set(blocks.map(b => b.review_tier))].sort()) {
  const option = document.createElement('option'); option.value = tier; option.textContent = tier; document.getElementById('tierFilter').append(option);
}
document.getElementById('search').oninput = () => { applyFilters(); render(); };
document.getElementById('statusFilter').onchange = () => { applyFilters(); render(); };
document.getElementById('tierFilter').onchange = () => { applyFilters(); render(); };
document.getElementById('defaultReviewer').value = state.defaultReviewer;
document.getElementById('defaultReviewer').oninput = e => { state.defaultReviewer = e.target.value; save(); };
document.getElementById('previous').onclick = () => { if (index > 0) index--; render(); };
document.getElementById('next').onclick = () => { if (index + 1 < filtered.length) index++; render(); };
document.getElementById('nextUnresolved').onclick = () => {
  for (let offset = 1; offset <= filtered.length; offset++) {
    const candidate = (index + offset) % filtered.length;
    if (!blockComplete(filtered[candidate])) { index = candidate; render(); return; }
  }
};
document.getElementById('exportGroups').onclick = exportGroups;
document.getElementById('exportRows').onclick = exportRows;
applyFilters(); updateProgress(); render();
</script>
</body>
</html>'''


def build_profile_eligibility_review_app(
    rows: pd.DataFrame,
    blocks: pd.DataFrame,
) -> tuple[str, dict[str, Any]]:
    """Return a self-contained HTML review app and a validated build summary."""

    summary = validate_profile_eligibility_review_app_inputs(rows, blocks)
    meta = {
        **summary,
        "row_columns": list(rows.columns),
        "block_columns": list(blocks.columns),
    }
    replacements = {
        "__ROWS_JSON__": json.dumps(
            _records(rows), ensure_ascii=False, separators=(",", ":")
        ).replace("<", "\\u003c"),
        "__BLOCKS_JSON__": json.dumps(
            _records(blocks), ensure_ascii=False, separators=(",", ":")
        ).replace("<", "\\u003c"),
        "__META_JSON__": json.dumps(
            meta, ensure_ascii=False, separators=(",", ":")
        ).replace("<", "\\u003c"),
    }
    html = HTML_TEMPLATE
    for token, value in replacements.items():
        html = html.replace(token, value)
    return html, summary
