# 最近 Entrant 距离规格

## 登记状态

| 项目 | 登记值 |
| --- | --- |
| 规格 ID | `distance_nearest_prior_year_entrant_5mi_v1` |
| 当前状态 | 已文档化并冻结，尚未选定 |
| 建议角色 | two-part 探索性稳健性规格 |
| 历史来源 | `009a` 至 `009d`（2026-03-10）notebook |
| 搜索范围 | 相同市场内不超过 5 mile |
| treatment timing | 上一个日历年进入 |
| outcome 与邻居单位 | 原始 `clinic_key` |

## Legacy 方法与问题

legacy 在 5 mile 邻居中选取上年 entrant 的最小距离，并保存 `log_dist_nearest_shock = log1p(distance)`。如果没有上年 entrant，则直接赋值 5 mile。

这种编码把两个不同状态混在一起：5 mile 内没有 entrant，以及最近 entrant 恰好位于 5 mile。距离本身也只在存在 entrant 时才有定义。正式实现不得把无 entrant 当作一个真实距离观测。

## 正式定义

令 \(\mathcal{S}_{it}=\{j:j\ne i,\ m_j=m_i,\ d_{ij}\le5,\ a_j=t-1\}\)。定义：

\[
A_{it}=\mathbf{1}(|\mathcal{S}_{it}|>0),
\]

\[
R_{it}=\min_{j\in\mathcal{S}_{it}}d_{ij}\quad\text{仅在 }A_{it}=1\text{ 时定义。}
\]

正式字段为：

| 字段 | 定义 |
| --- | --- |
| `has_prior_year_entrant_5mi` | \(A_{it}\) |
| `nearest_prior_year_entrant_distance_5mi` | \(R_{it}\)，无 entrant 时为缺失 |
| `log_nearest_prior_year_entrant_distance_5mi` | \(\log(1+R_{it})\)，只在有 entrant 时计算 |
| `prior_year_entrant_5mi_count` | 5 mile 内上年 entrant 数，用于区分最近距离与冲击强度 |

回归必须使用 two-part 设计：先用 `has_prior_year_entrant_5mi` 表达 extensive margin，再在有 entrant 的 clinic-year 中描述条件距离，或预先登记两者的交互。不能只把缺失距离填成 5 后运行单一连续变量回归。

## 实现规则

1. 邻居必须与 focal clinic 具有相同 `search_location`。
2. 使用稳定 `clinic_key` 排除自身，不能使用行号。
3. 距离采用 Haversine mile，5 mile 边界包含在内。
4. 共址但不同 `clinic_key` 的 entrant 距离可以为零；地址分组只用于冻结敏感性分析。
5. 邻居不要求 rating 可观测，rating 也不能参与 exposure 构造。
6. entry year 来自冻结日期 hierarchy，冲击时点为 \(t-1\)。
7. exposure 覆盖 corrected panel 全部年份，包括 2025 年；估计再使用 `analysis_period`。

## 文献解释

nearest-provider distance 是常见的空间可及性指标，但它只利用一个 provider。Guagliardo（2004）指出，在拥挤城市中，最近 provider 的 travel impedance 和行政边界内供给计数可能缺乏有效性。McKernan 等（2016）研究实际牙科利用时专门比较最近牙医与实际就诊牙医，说明患者可能绕过最近 provider。因此，最近 entrant 是局部竞争接近程度的代理，不能被解释为患者实际选择的竞争者。

该方法也不同于一般 nearest-provider access：这里的对象仅是上年新进入者，clinic-year 没有 entrant 时距离不存在。two-part 处理是由变量定义决定的，不是可选的数据清洗技巧。

## 主要风险与必需诊断

1. 最近距离忽略同年其他 entrant 的数量和距离。
2. 只搜索 5 mile 会使更远 entrant 与完全没有 entrant 都落在 `has=0`。
3. 共址 profile 会产生零距离并高度影响分布。
4. 大圆距离可能偏离道路出行距离。
5. 必须报告 `has=0` 比例、条件距离分布、同年 entrant 数量、clinic 内变化、共址贡献和按市场分布。
6. 必须测试无 entrant 时距离为缺失、恰好 5 mile 时距离为 5，两个状态不能相同。
7. 必须检查同市场、自身排除、2025 年保留和 panel 行数守恒。

## 文献

1. Guagliardo, M. F.（2004）. Spatial accessibility of primary care: concepts, methods and challenges. https://doi.org/10.1186/1476-072X-3-3
2. McKernan, S. C., et al.（2016）. Travel burden and dentist bypass among dentally insured children. https://pubmed.ncbi.nlm.nih.gov/26797766/
3. Shin, H., and Ahn, E.（2018）. Does the regional deprivation impact the spatial accessibility to dental care services? https://doi.org/10.1371/journal.pone.0203640
