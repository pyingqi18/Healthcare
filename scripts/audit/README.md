# Legacy data audit commands

只读取`final_merged_time.csv`并生成诊断结果的脚本。不修改 legacy 原始数据，不生成回归输入。
所有命令在项目根目录运行。

## 1. 激活虚拟环境：

```bash
source .venv/Scripts/activate
```

创建诊断输出目录：

```bash
mkdir -p outputs/diagnostics
```

检查语法：

```bash
python -m py_compile scripts/audit/*.py
```

## 2. 诊断

### 2.1 检查诊所和评论的行数、日期、评分、匹配字段和匹配状态。

```bash
python scripts/audit/00_audit_legacy_data.py \
  --legacy-dir "data/legacy/dentist_LMS_keywords/output/final" \
  --output "outputs/diagnostics/legacy_audit_summary.json"
```

输出：

```text
outputs/diagnostics/legacy_audit_summary.json
```

### 2.2 未匹配评论检查具有完整名称和 ZIP、但无法通过名称和 ZIP 找到诊所的评论。

```bash
python scripts/audit/00b_audit_unmatched_reviews.py \
  --legacy-dir "data/legacy/dentist_LMS_keywords/output/final" \
  --output-directory "outputs/diagnostics"
```

输出：

```text
outputs/diagnostics/unmatched_review_summary.json
outputs/diagnostics/unmatched_review_keys.csv
```

### 2.3 把全部评论划分为完整名称和 ZIP 唯一匹配、歧义匹配、缺少 ZIP 后按名称匹配，以及完全无法匹配等互斥类别。

```bash
python scripts/audit/00c_audit_linkage_paths.py \
  --legacy-dir "data/legacy/dentist_LMS_keywords/output/final" \
  --output-directory "outputs/diagnostics"
```

输出：

```text
outputs/diagnostics/linkage_path_summary.json
outputs/diagnostics/missing_zip_review_titles.csv
```

### 2.4 检查旧最终诊所表中重复的 `clinic_key`，并比较重复组内哪些字段不同。

```bash
python scripts/audit/00d_audit_duplicate_clinics.py \
  --clinics "data/legacy/dentist_LMS_keywords/output/final/final_merged_time.csv" \
  --output-directory "outputs/diagnostics"
```

输出：

```text
outputs/diagnostics/duplicate_clinic_summary.json
outputs/diagnostics/duplicate_clinic_rows.csv
outputs/diagnostics/duplicate_clinic_groups.csv
```

### 2.5 使用重复诊所记录追查 `timeline_data_final.csv` 中同名不同地点和年份冲突的问题。

运行前，必须先运行 `00d_audit_duplicate_clinics.py`。

```bash
python scripts/audit/00e_audit_timeline_duplicates.py \
  --timeline "data/legacy/dentist_LMS_keywords/output/final/timeline_data_final.csv" \
  --duplicate-clinics "outputs/diagnostics/duplicate_clinic_rows.csv" \
  --output-directory "outputs/diagnostics"
```

输出：

```text
outputs/diagnostics/duplicate_timeline_summary.json
outputs/diagnostics/duplicate_timeline_candidates.csv
```

## 3. 合并前数据`final_processed_with_earliest_review.csv`与安全时间线审计

### 3.1 检查标准化名称和 ZIP 能否形成唯一的时间线匹配。

```bash
python scripts/audit/00f_audit_timeline_linkage.py \
  --clinics "data/legacy/dentist_LMS_keywords/output/final/final_processed_with_earliest_review.csv" \
  --timeline "data/legacy/dentist_LMS_keywords/output/final/timeline_data_final.csv" \
  --output "outputs/diagnostics/timeline_linkage_summary.json"
```

输出：

```text
outputs/diagnostics/timeline_linkage_summary.json
```

### 3.2 使用地址和坐标检查缺失名称或 ZIP 的时间线记录能否找到地点候选。

```bash
python scripts/audit/00g_audit_incomplete_timeline.py \
  --clinics "data/legacy/dentist_LMS_keywords/output/final/final_processed_with_earliest_review.csv" \
  --timeline "data/legacy/dentist_LMS_keywords/output/final/timeline_data_final.csv" \
  --output-directory "outputs/diagnostics"
```

输出：

```text
outputs/diagnostics/incomplete_timeline_summary.json
outputs/diagnostics/incomplete_timeline_audit.csv
```

### 3.3 判断多个地点候选行是同一个 `clinic_key`，还是多个不同诊所。

```bash
python scripts/audit/00h_audit_timeline_candidates.py \
  --clinics "data/legacy/dentist_LMS_keywords/output/final/final_processed_with_earliest_review.csv" \
  --timeline "data/legacy/dentist_LMS_keywords/output/final/timeline_data_final.csv" \
  --output-directory "outputs/diagnostics"
```

输出：

```text
outputs/diagnostics/incomplete_timeline_candidate_summary.json
outputs/diagnostics/incomplete_timeline_candidate_summary.csv
outputs/diagnostics/incomplete_timeline_candidate_rows.csv
```

### 3.4 检查合并前诊所表中 `earliest_review_date` 的有效数量和覆盖率。

```bash
python scripts/audit/00i_audit_earliest_review_coverage.py \
  --clinics "data/legacy/dentist_LMS_keywords/output/final/final_processed_with_earliest_review.csv" \
  --output "outputs/diagnostics/earliest_review_coverage.json"
```

输出：

```text
outputs/diagnostics/earliest_review_coverage.json
```

### 3.5 使用完整名称和 ZIP 匹配，把有效网站年份和最早评论日期组合为进入日期覆盖统计。

```bash
python scripts/audit/00j_audit_entry_date_coverage.py \
  --clinics "data/legacy/dentist_LMS_keywords/output/final/final_processed_with_earliest_review.csv" \
  --timeline "data/legacy/dentist_LMS_keywords/output/final/timeline_data_final.csv" \
  --output "outputs/diagnostics/entry_date_coverage.json"
```

输出：

```text
outputs/diagnostics/entry_date_coverage.json
```

## 4. 执行顺序

```text
00 → 00b → 00c → 00d → 00e → 00f → 00g → 00h → 00i → 00j
```
脚本应在原始数据、匹配规则或日期规则发生变化时重新运行。

## 5. 退出虚拟环境

```bash
deactivate
```
