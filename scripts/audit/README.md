# Legacy data audit commands

只读取`final_merged_time.csv`并生成诊断结果的脚本。不修改 legacy 原始数据，不生成回归输入。
所有命令在项目根目录运行。

## 1. 运行准备

以下命令默认当前终端已经激活`.venv`。每个终端会话只需激活一次，
后续步骤不再重复执行激活命令。

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

## 5. 回归输入就绪审计

在构建空间暴露或运行回归之前，检查纠正后年度面板的字段、样本、
唯一性以及现有变量的组内变异。该步骤不估计模型，也不修改面板。

```bash
python scripts/audit/01_audit_regression_readiness.py \
  --panel "data/processed/corrected_v1/clinic_year_panel.csv" \
  --output "outputs/diagnostics/corrected_v1/regression_readiness.json"
```

当前年度面板尚未加入空间暴露时，输出中的`regression_ready`应为`false`，
并明确列出缺少的 exposure 字段。这是预期诊断结果。

## 6. 固定半径空间尺度诊断

在查看回归结果前，仅使用诊所地点和市场字段，比较固定半径下的邻居
覆盖率。该步骤不读取 rating outcome，也不生成回归 exposure。

```bash
python scripts/audit/02_audit_spatial_scales.py \
  --clinics "data/processed/corrected_v1/clinics_eligibility_flagged.csv" \
  --output-directory "outputs/diagnostics/corrected_v1/spatial_scales" \
  --radii-miles 1 3 5 10 25
```

输出：

```text
outputs/diagnostics/corrected_v1/spatial_scales/fixed_radius_neighbor_counts.csv
outputs/diagnostics/corrected_v1/spatial_scales/fixed_radius_market_summary.csv
outputs/diagnostics/corrected_v1/spatial_scales/fixed_radius_metadata.json
```

## 7. 共址诊所身份审计

固定半径诊断显示异常短的最近邻距离时，在构建竞争暴露前检查完全相同
坐标和50米内的诊所记录。该步骤只生成候选，不自动合并或删除诊所。

```bash
python scripts/audit/03_audit_coordinate_clusters.py \
  --clinics "data/processed/corrected_v1/clinics_eligibility_flagged.csv" \
  --output-directory "outputs/diagnostics/corrected_v1/coordinate_clusters" \
  --distance-threshold-meters 50
```

输出：

```text
outputs/diagnostics/corrected_v1/coordinate_clusters/exact_coordinate_cluster_rows.csv
outputs/diagnostics/corrected_v1/coordinate_clusters/close_coordinate_pairs.csv
outputs/diagnostics/corrected_v1/coordinate_clusters/coordinate_cluster_market_summary.csv
outputs/diagnostics/corrected_v1/coordinate_clusters/coordinate_cluster_metadata.json
```

## 8. 已冻结的敏感性诊断：地址竞争计数单位

状态：已冻结，不属于active pipeline，不得作为主回归exposure输入。

完全同坐标不能直接视为同一诊所。同一建筑中的不同套间可能共享地理编码。
该步骤只在同一市场内合并标准化完整地址相同且坐标最大偏差不超过50米的
资料，用于后续competition exposure计数。每个`clinic_key`和rating outcome
仍然保留，不执行结果实体合并。

```bash
python scripts/audit/04_audit_competition_units.py \
  --clinics "data/processed/corrected_v1/clinics_eligibility_flagged.csv" \
  --output-directory "outputs/diagnostics/corrected_v1/competition_units" \
  --maximum-address-spread-meters 50
```

输出：

```text
outputs/diagnostics/corrected_v1/competition_units/competition_unit_crosswalk.csv
outputs/diagnostics/corrected_v1/competition_units/competition_unit_market_summary.csv
outputs/diagnostics/corrected_v1/competition_units/competition_unit_address_conflicts.csv
outputs/diagnostics/corrected_v1/competition_units/competition_unit_metadata.json
```

该命令仅用于复现已经生成的诊断结果。输出中的竞争单位是暂定地址组，
不代表已经确认的物理诊所。

## 9. 已冻结的敏感性诊断：竞争单位固定半径

状态：已冻结，不属于active pipeline，不得据此锁定主半径。

使用第8步生成的竞争单位作为邻居池，重新计算固定半径分布。
同一竞争单位内的其他profile不计作邻居。结果同时保留竞争单位层和
原始profile层的邻居数量，仍不读取rating outcome。

```bash
python scripts/audit/05_audit_competition_unit_spatial_scales.py \
  --crosswalk "outputs/diagnostics/corrected_v1/competition_units/competition_unit_crosswalk.csv" \
  --output-directory "outputs/diagnostics/corrected_v1/competition_unit_spatial_scales" \
  --radii-miles 1 3 5 10 25
```

输出：

```text
outputs/diagnostics/corrected_v1/competition_unit_spatial_scales/competition_unit_neighbor_counts.csv
outputs/diagnostics/corrected_v1/competition_unit_spatial_scales/profile_adjusted_neighbor_counts.csv
outputs/diagnostics/corrected_v1/competition_unit_spatial_scales/competition_unit_radius_market_summary.csv
outputs/diagnostics/corrected_v1/competition_unit_spatial_scales/competition_unit_radius_metadata.json
```

当前active回归前顺序为：

```text
01回归输入就绪审计
02原始clinic_key固定半径分布审计
03共址候选审计
下一步为距离方法文献审计与规格登记
```

冻结依据和下一步范围见：

```text
docs/spatial_distance_design_status.md
```

## 10. 严格009a与04兼容样本差异审计

该步骤只比较诊所池和回归clinic-year，不重算exposure，不估计模型，也不
修改11号严格基线或04至10号既有结果。

```bash
python scripts/audit/06_audit_strict_legacy_sample.py \
  --base-panel "data/processed/corrected_v1/clinic_year_panel.csv" \
  --clinics "data/processed/corrected_v1/clinics_eligibility_flagged.csv" \
  --strict-panel "outputs/legacy_reproduction/corrected_v1/strict_009a_2mile/strict_009a_2mile_panel.csv" \
  --compatible-panel "outputs/legacy_reproduction/corrected_v1/legacy_2mile/legacy_2mile_panel.csv" \
  --output-directory "outputs/diagnostics/corrected_v1/strict_009a_sample"
```

输出逐家诊所的池成员关系、严格池中未进入corrected panel的诊所、池关系
汇总和clinic-year回归样本交集。

## 11. 退出虚拟环境

```bash
deactivate
```
