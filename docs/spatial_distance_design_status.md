# 空间距离设计状态

## 当前状态

空间身份分支已在构建 exposure 之前冻结。目前尚未选定任何主回归半径或距离权重规则，也不得使用地址归组后的竞争单位估计主回归系数。

当前有效的回归前诊断为：

1. 回归输入就绪审计。
2. 使用原始 `clinic_key` 的 outcome-blind 固定半径分布审计。
3. 完全同坐标和 50 米内共址候选审计。

地址竞争单位审计及其半径审计只作为冻结的敏感性诊断保留。它们不能证明同地址 profile 属于同一诊所。

## 冻结依据

地址规则将 5,605 个空间合格 profile 暂时映射为 4,746 个竞争单位，使潜在邻居池减少 859 个 profile，但现有字段不能验证这 859 个 profile 是重复诊所。

在 597 个共享地址组中：

1. 339 组同时包含机构和个人执业者名称。
2. 62 组只包含个人执业者名称。
3. 52 组只包含机构名称。
4. 144 组的名称组合无法可靠分类。
5. 现有 legacy 表中没有可用于组内确认的重复非缺失电话或域名证据。
6. 没有任何组包含完全相同的标准化名称。

因此，结果证明的是 profile 共址，而不是已经验证的诊所身份交叉表。原始 `clinic_key` 继续作为 legacy 分析单位。

## 历史距离方法登记表

近期 notebook 包含以下方法。每种方法必须先单独形成文档，再进入正式回归代码。

1. 固定 2-mile 邻居计数：已在 `docs/spatial_methods/01_fixed_2mile.md` 中登记并冻结为未选定候选规格。
2. 固定 0 至 0.5、0.5 至 2、2 至 5 mile 分层圆环：已在 `docs/spatial_methods/02_fixed_distance_rings.md` 中登记并冻结为未选定的距离梯度稳健性候选。
3. 5-mile 反距离 gravity exposure：已在 `docs/spatial_methods/03_inverse_distance_gravity.md` 中登记并冻结为探索性稳健性候选。
4. 到最近新进入者的距离：已在 `docs/spatial_methods/04_nearest_entrant_distance.md` 中登记，必须使用 two-part 表达，不能把无 entrant 编码为 5 mile。
5. 到第 5 个活跃竞争者的距离：已在 `docs/spatial_methods/05_fifth_active_competitor_distance.md` 中登记，必须显式记录不足五家的右删失状态。
6. 各市场内部两两距离的 P25 和 P50 半径：已在 `docs/spatial_methods/06_market_percentile_radii.md` 中登记为样本标准化稳健性候选。
7. 各市场 P25 至 P50 外环：与 P25/P50 一并登记在 `docs/spatial_methods/06_market_percentile_radii.md`。
8. 描述性 P75 市场距离：已在 `docs/spatial_methods/07_descriptive_p75_distance.md` 中登记，不能误称为 legacy 回归规格。

此前 1、3、5、10、25 mile 的固定半径审计只用于观察分布，不能单独决定回归规格。

## 每种方法必须记录的内容

1. 距离所代表的竞争或可及性机制。
2. 精确的数学 exposure 定义。
3. 邻居池和市场边界规则。
4. treatment timing 和进入年份规则。
5. 自身、共址 profile 和缺失坐标的处理。
6. 主规格、稳健性或探索性角色。
7. 支持文献，以及把文献移植到牙科评分竞争问题时的限制。
8. 后续实现必须具备的单元测试和真实数据诊断。

文献审计还会评估距离衰减、可变 catchment、patient-flow market 和正式 exposure mapping。这些只是候选方法，尚未批准。

## 初始文献

1. Luo and Qi (2009)，带距离分区的 enhanced two-step floating catchment area：https://doi.org/10.1016/j.healthplace.2009.06.002
2. McGrail (2012)，距离衰减和可变 catchment 的空间可及性比较：https://pubmed.ncbi.nlm.nih.gov/23153335/
3. Bauer and Groneberg (2016)，floating catchment 中的可变距离衰减：https://doi.org/10.1371/journal.pone.0159148
4. Aronow and Samii (2017)，干扰条件下的因果 exposure mapping：https://doi.org/10.1214/16-AOAS1005
5. Li and Dor (2025)，用 patient-flow 数据定义重叠医疗市场：https://doi.org/10.1111/1475-6773.14396

## 下一道门

全部 legacy 距离方法和文献建议的新增方法已经完成文档登记，比较表见 `docs/spatial_method_registry.md`。下一步必须由用户确认主规格、稳健性规格和探索性规格，并解决 2014/2015 分析起始年份冲突。完成这两个决定前不得构建正式空间 exposure。
