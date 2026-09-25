总体文档

1. `research_design_audit.md`详细记录身份、样本、进入时间、空间exposure、fixed effects和因果解释中的风险。
2. `variable_dictionary.md`解释每个主要变量从哪里来、单位是什么、历史名称和正式名称有什么区别。
3. `stage_classification.md`把历史notebook分成抓取、清理、面板、回归和NLP阶段，防止历史notebook被误当作正式入口。
4. `chronology.csv`按日期列出历史代码。
5. `handoff_zh.md`用于交接，现在应该从哪里继续。
6. `search_scope_revision.md`解释Malone和Syracuse多抓问题，以及全市场重抓怎么减少无效候选。
7. `spatial_distance_design_status.md`记录空间身份分支和距离方法目前处于什么状态。
8. `spatial_method_registry.md`把所有距离方法放在同一张登记表里。
9. `stage_46_profile_eligibility_checkpoint.md`冻结阶段46a至46l的资格审核进度、文件哈希、代码恢复边界和下一步。当前199条剩余决定已完成，下一步是运行46j应用门生成450条verified freeze。

`spatial_methods/`文件

1. `01_fixed_2mile.md`固定2-mile方法、legacy实现和正式修正版之间的区别。
2. `02_fixed_distance_rings.md`0至0.5、0.5至2、2至5 mile三个圆环。
3. `03_inverse_distance_gravity.md`5-mile反距离权重。
4. `04_nearest_entrant_distance.md`把“附近有没有新进入者”和“最近新进入者多远”分开处理。
5. `05_fifth_active_competitor_distance.md`记录第五个活跃竞争者距离和不足五家时的处理。
6. `06_market_percentile_radii.md`记录市场P25、P50半径。它能适应市场尺度，但物理距离不再统一。
7. `07_descriptive_p75_distance.md`只做市场空间跨度描述，不进入正式回归。
8. `08_literature_motivated_alternatives.md`比较道路时间、patient-flow market、校准衰减和E2SFCA等未来方法。

当前已经冻结的主候选是固定2-mile。圆环、0.5-mile和市场P25/P50属于预定稳健性分析；gravity、最近entrant和第五竞争者距离属于探索性分析。具体机器可读设置以`config/final_analysis.yaml`为准。
