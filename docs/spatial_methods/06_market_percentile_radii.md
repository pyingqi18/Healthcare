# 市场 P25/P50 距离半径及外环规格

## 登记状态

| 项目 | 登记值 |
| --- | --- |
| 规格 ID | `distance_market_pairwise_p25_p50_v1` |
| 当前状态 | 已文档化并冻结，尚未选定 |
| 建议角色 | 样本标准化或市场异质性稳健性规格 |
| 历史来源 | `010`（2026-03-25）、`012`（2026-04-04）、`013`（2026-04-11）notebook |
| 半径 | 每个市场全部两两距离的 P25 与 P50 |
| outcome 与邻居单位 | 原始 `clinic_key` |

## 半径定义

对市场 \(m\) 的冻结空间合格 profile 集合 \(C_m\)，计算所有无序且不含自身的 pairwise Haversine 距离：

\[
\mathcal{D}_m=\{d_{ij}:i,j\in C_m,\ i<j\}.
\]

定义 \(r_{m,25}=Q_{0.25}(\mathcal{D}_m)\)，\(r_{m,50}=Q_{0.50}(\mathcal{D}_m)\)。正式实现必须登记 quantile algorithm、输入行数、坐标版本和结果 hash。半径一旦冻结，不得因回归样本或 outcome 缺失而重新计算。

legacy 使用 `df_reg` 计算半径，而 `df_reg` 已经按 rating、坐标、日期等条件筛选。正式实现必须改为 outcome-blind 的空间合格诊所表，否则 treatment definition 会随 outcome 可得性变化。

## Exposure 定义

对 clinic \(i\) 定义 inner 集合 \(0\le d_{ij}\le r_{m,25}\)，outer cumulative 集合 \(0\le d_{ij}\le r_{m,50}\)，以及不重叠 outer ring：

\[
r_{m,25}<d_{ij}\le r_{m,50}.
\]

每个集合分别生成上年 entry count、dummy、`log1p` count 以及当年 active density count 和 `log1p` density。建议正式字段前缀为：

| 区域 | 字段前缀 |
| --- | --- |
| 0 至 P25 | `market_p25_` |
| 0 至 P50 | `market_p50_` |
| P25 至 P50 | `market_p25_p50_ring_` |

所有 neighbor 必须同属 `search_location` 并按 `clinic_key` 显式排除自身。legacy 的全样本 BallTree 和 numeric lag count 自身污染必须修正。strong entrant 不进入基础登记。

## 解释限制

P25/P50 半径在每个市场代表相同的 pairwise-distance 排名，却不代表相同 physical distance。它会随市场边界、样本覆盖、共址 profile 和重新抓取结果变化。全体 pairwise 距离的分位数也不是 focal clinic 的局部 nearest-neighbor 分位数，不能解释为典型患者出行范围。

外环必须直接由边界条件计算，不应只用 cumulative count 相减后假定两个邻居集合完全一致。直接计算便于检测市场污染、边界并列和 ID 问题；同时应验证 `P50 = P25 + ring` 的计数守恒。

## 文献解释

McGrail（2012）和后续可变 catchment 文献说明，城乡差异可能需要不同 catchment 大小。Clark 等（2024）在 NHS dentistry 可及性研究中同时考虑 varying catchments、distance decay 和 supply competition。这些研究支持检查空间尺度异质性。

它们没有使用“本样本所有诊所两两距离的 P25/P50”来定义牙科竞争市场。因此，本方法是内部样本标准化，不是经文献验证的市场边界。它也可能把抓取覆盖差异转化为半径差异，不能作为首选主规格。

## 必需诊断与测试

1. 输出每个市场的 profile 数、pair 数、P25/P50 mile 和坐标版本。
2. 报告重新抓取或排除共址 profile 后半径变化。
3. 报告每个市场半径内 neighbor count、shock 零值比例及 clinic 内变化。
4. 验证 P25 不大于 P50，单 profile 市场不能静默设为有效零半径。
5. 验证同市场、自身排除和所有边界的 inclusive/exclusive 规则。
6. 验证 P50 count 等于 P25 count 加 P25-P50 ring count。
7. 确认半径输入不使用 rating、votes 或回归 complete-case mask。
8. 保存冻结半径表，回归阶段只读取，不能重新估计。

## 文献

1. McGrail, M. R.（2012）. Spatial accessibility of primary health care utilising the two step floating catchment area method. https://pubmed.ncbi.nlm.nih.gov/23153335/
2. Clark, S. D., et al.（2024）. Spatial disparities in access to NHS dentistry. https://pubmed.ncbi.nlm.nih.gov/38908020/
3. Shin, H., and Ahn, E.（2018）. Does the regional deprivation impact the spatial accessibility to dental care services? https://doi.org/10.1371/journal.pone.0203640
