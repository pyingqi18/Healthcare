# 第五个活跃竞争者距离规格

## 登记状态

| 项目 | 登记值 |
| --- | --- |
| 规格 ID | `distance_fifth_active_competitor_5mi_v1` |
| 当前状态 | 已文档化并冻结，尚未选定 |
| 建议角色 | 局部市场紧密度的探索性稳健性规格 |
| 历史来源 | `009a` 至 `009d`（2026-03-10）notebook |
| 搜索范围 | 相同市场内不超过 5 mile |
| outcome 与邻居单位 | 原始 `clinic_key` |

## Legacy 方法与问题

legacy 对当年 active 邻居距离排序。如果至少有五家，取第五小距离；否则赋值 5 mile，再计算 `log1p`。因此，“不足五家竞争者”与“第五家恰好在 5 mile”无法区分。该变量存在 5-mile 右删失，不能把删失值当作完整观测。

## 正式定义

令 \(\mathcal{A}_{it}=\{j:j\ne i,\ m_j=m_i,\ d_{ij}\le5,\ a_j\le t\}\)，并令 \(n_{it}=|\mathcal{A}_{it}|\)。定义：

\[
H_{it}=\mathbf{1}(n_{it}\ge5),
\]

\[
Q_{it}^{(5)}=\text{第五小的 }d_{ij}\quad\text{仅在 }H_{it}=1\text{ 时定义。}
\]

正式字段为：

| 字段 | 定义 |
| --- | --- |
| `active_competitor_count_5mi` | \(n_{it}\) |
| `has_five_active_competitors_5mi` | \(H_{it}\) |
| `fifth_active_competitor_distance_5mi` | \(Q_{it}^{(5)}\)，不足五家时为缺失 |
| `log_fifth_active_competitor_distance_5mi` | \(\log(1+Q_{it}^{(5)})\)，只在可观测时计算 |

如果未来需要保留 5-mile censored value，必须另设明确带 `_censored` 的字段并同时保留 `H_it`。普通回归不得把不足五家直接填成 5。

## 解释与回归角色

较小的第五邻居距离表示至少五个 active profile 更紧密地集中在 focal clinic 周围。它更接近局部空间密度或 compactness，而不是 entrant shock。系数方向与计数 exposure 相反：距离越大通常意味着竞争者越稀疏。

在当前永久活跃假设下，该距离随新进入只能保持不变或下降。它没有利用第五家以外的竞争者，也没有说明为什么 \(k=5\) 是牙科竞争的经济阈值。因此建议只作为固定半径 density 的稳健性或描述性补充。

## 实现规则

1. 邻居必须同属 `search_location`，使用 `clinic_key` 排除自身。
2. active 定义为进入年份不晚于 \(t\)，暂不使用未经验证的退出年份。
3. 距离采用 Haversine mile，5 mile 边界包含在内。
4. 共址但不同 ID 的 profile 可占据最前若干顺位，必须单独报告。
5. 邻居池不以 rating 是否可得为条件。
6. corrected panel 的 2025 年必须保留。

## 文献解释

nearest 或 order-statistic distance 可以避免行政边界，并描述局部 provider 可得性，但只总结一个顺位，忽略其余供给。Guagliardo（2004）强调空间可及性指标的有效性取决于城市环境和研究情境。牙科可及性研究更常结合道路时间、provider supply 和 population demand，而不是把第五个 provider 的直线距离直接当作竞争市场。

因此，文献支持使用邻居距离描述空间结构，却不能验证第五个邻居、5-mile 搜索上限或 profile-level 计数。本项目必须把它标为数据驱动的局部紧密度候选。

## 必需诊断与测试

1. 按市场和年份报告不足五家的比例、条件距离分布及 clinic 内变化。
2. 报告前五个顺位中完全同坐标和 50 米内 profile 的比例。
3. 比较第五距离与 2-mile/5-mile density count 的相关性。
4. 检查不足五家时为缺失，恰好第五家位于 5 mile 时为真实 5。
5. 测试距离排序、并列距离、同市场、自身排除、active timing 和 2025 年。
6. 验证 exposure 合并后 panel 行数及 clinic-year 唯一性守恒。

## 文献

1. Guagliardo, M. F.（2004）. Spatial accessibility of primary care: concepts, methods and challenges. https://doi.org/10.1186/1476-072X-3-3
2. Rahman, M. S., et al.（2024）. Dental Clinic Deserts in the US: Spatial Accessibility Analysis. https://pubmed.ncbi.nlm.nih.gov/39714842/
3. Nasseh, K., Eisenberg, Y., and Vujicic, M.（2017）. Geographic access to dental care varies in Missouri and Wisconsin. https://pubmed.ncbi.nlm.nih.gov/28075494/
