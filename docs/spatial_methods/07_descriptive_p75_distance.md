# 市场 Pairwise Distance P75 描述性规格

## 登记状态

| 项目 | 登记值 |
| --- | --- |
| 规格 ID | `distance_market_pairwise_p75_descriptive_v1` |
| 当前状态 | 已文档化并冻结 |
| 角色 | 只用于描述市场空间范围 |
| 历史来源 | `013`（2026-04-11）notebook |
| legacy 回归 exposure | 没有 |

## 定义

对每个 `search_location` 的冻结空间合格 profile，计算所有无序、不含自身的 pairwise Haversine mile 距离集合 \(\mathcal{D}_m\)，并定义：

\[
r_{m,75}=Q_{0.75}(\mathcal{D}_m).
\]

正式描述字段为 `market_pairwise_distance_p75_miles`。同时必须输出市场 profile 数、有效 pair 数、P25、P50、P75 和 quantile algorithm。只有一个有效 profile 的市场应标为不可计算，不能把 P75 设为真实 0 mile。

## Legacy 范围

`013` 使用 P25、P50、P75 制作市场距离汇总表，之后的 panel exposure 仍只使用 P25 和 P50。没有证据显示 P75 曾作为 regression radius。因此，为满足“记录全部历史方法”的要求，本文件保留它，但不得把它列成已有回归模型。

如果未来希望把 P75 转成 exposure，必须另建新的预登记规格，说明研究机制、字段、模型角色和多重规格问题，不能通过本描述文件直接授权。

## 解释限制与诊断

P75 描述的是 sampled profile 两两距离分布的上部位置，主要反映市场地理跨度、形状和样本布局。它不是患者 travel distance、局部竞争半径或 75% 患者来源区域。

必须检查无效坐标、共址 pair、市场边界、极端长距离 pair、样本版本和重抓前后变化。输出不得只保留四舍五入后的数值；计算精度值用于审计，展示表可以另行保留两位小数。

## 文献定位

牙科可及性研究通常使用道路时间、患者与 provider 的空间关系、人口供需或可变 catchment。市场内 provider-provider pairwise P75 没有直接的患者行为含义。因此，本统计量只适合描述市场空间尺度，并可帮助判断固定半径是否相对于某些市场过大或过小。

## 文献

1. Rahman, M. S., et al.（2024）. Dental Clinic Deserts in the US: Spatial Accessibility Analysis. https://pubmed.ncbi.nlm.nih.gov/39714842/
2. Nasseh, K., Eisenberg, Y., and Vujicic, M.（2017）. Geographic access to dental care varies in Missouri and Wisconsin. https://pubmed.ncbi.nlm.nih.gov/28075494/
3. Shin, H., and Ahn, E.（2018）. Does the regional deprivation impact the spatial accessibility to dental care services? https://doi.org/10.1371/journal.pone.0203640
