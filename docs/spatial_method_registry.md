# 空间方法总登记表

## 当前决定状态

全部历史方法和文献候选已经完成书面登记，但尚未批准主回归规格。以下角色是基于研究设计和当前数据的建议，用户确认前不授权 exposure 构建。

| ID | 方法 | 当前数据可实现 | 建议角色 | 主要优点 | 主要限制 |
| --- | --- | --- | --- | --- | --- |
| `distance_fixed_2mi_v1` | 固定 2 mile | 是 | provisional main candidate | 物理尺度固定、透明、早期 legacy 设计 | 2 mile 未经患者行为验证 |
| `distance_rings_0_0p5_0p5_2_2_5_v1` | 三层固定圆环 | 是 | 稳健性 | 可观察距离梯度 | 多重系数、共线性、硬边界 |
| `distance_gravity_inverse_5mi_v1` | 5-mile `1/(1+d)` | 是 | 探索性 | 连续降低近远权重 | 函数和截断未校准、单位依赖 |
| `distance_nearest_prior_year_entrant_5mi_v1` | 最近上年 entrant | 是 | two-part 探索性 | 直接描述最近冲击 | 无 entrant 时距离未定义、忽略其他 entrant |
| `distance_fifth_active_competitor_5mi_v1` | 第五 active competitor | 是 | 探索性 | 描述局部紧密度 | 不足五家时右删失、k=5 任意 |
| `distance_market_pairwise_p25_p50_v1` | 市场 P25/P50 与外环 | 是 | 稳健性 | 允许市场尺度差异 | 半径由样本决定、物理尺度不可比 |
| `distance_market_pairwise_p75_descriptive_v1` | 市场 P75 | 是 | 描述性 | 描述市场空间跨度 | 从未形成 legacy exposure |
| `road_network_impedance_candidate` | 道路时间或距离 | 当前否 | 未来高优先级稳健性 | 更接近真实空间摩擦 | 需要冻结道路网络和 routing 参数 |
| `patient_flow_market_candidate` | patient-flow overlapping market | 当前否 | 有数据时优先 | 最接近竞争与质量机制 | 需要患者流，且必须避免 post-treatment weights |
| `calibrated_decay_candidate` | 经验校准 distance decay | 部分 | 未来稳健性 | 避免任意 legacy 权重 | 需要外部或独立 calibration data |
| `e2sfca_access_candidate` | E2SFCA | 当前否 | access context 或异质性 | 同时考虑供给、需求和阻抗 | 不是直接的 clinic competition treatment |

## 建议的当前模型族

如果用户批准现有数据路线，建议预先登记以下有限模型族：

| 层级 | 方法 | 数量控制 |
| --- | --- | --- |
| 主候选 | 固定 2-mile prior-year entrant 与 active density | 1 个核心距离规格 |
| 稳健性 1 | 0 至 0.5、0.5 至 2、2 至 5 mile 联合圆环 | 1 个联合规格 |
| 稳健性 2 | outcome-blind 冻结的市场 P25/P50 | P25、P50、外环按预登记顺序报告 |
| 探索性 | legacy gravity、nearest entrant、fifth competitor | 全部标记 exploratory，不决定主结论 |
| 身份敏感性 | 暂定地址 competition unit | 不改变 outcome entity，不称为去重主样本 |

## 仍需用户决定的两项

### 1. 分析起始年份

`scripts/01_build_legacy_panel.py` 默认 `analysis_start_year=2015`，而 `config/settings.yaml` 写有 `minimum_treatment_year: 2014`。正式 exposure 和回归必须只使用一个来源。建议以 corrected panel 已冻结的 `analysis_period` 为当前版本依据，同时把配置统一为 2015；若研究理论要求 2014，则应先重建和重新审计面板。

### 2. 是否接受当前模型族

用户需要确认：

1. 固定 2 mile 是否作为 provisional main specification；
2. 圆环和 P25/P50 是否作为预定稳健性规格；
3. gravity、nearest 和 fifth distance 是否只标为 exploratory；
4. patient-flow 与 road-network 方法是否延后到完整重抓或获得新数据之后。

## 批准后的实现顺序

1. 统一分析起始年份配置。
2. 新增一个通用、同市场、稳定 ID、自身排除的 neighbor engine。
3. 首先实现固定 2-mile exposure 及单元测试。
4. 对真实 corrected panel 运行 outcome-blind exposure audit。
5. 只有审计通过后才实现预定稳健性 exposure。
6. 更新 `tests/README.md`，为每个新增 test file 添加一句说明。
7. 更新 `src/README.md` 仅限新增了实际源码入口或直接操作时。
8. exposure 冻结并记录 hash 后，才进入 regression readiness 和模型实现。

## 禁止事项

在用户批准前，不得修改 `config/settings.yaml`、实现 exposure、运行回归、选择系数或把文献候选写成已经完成的数据功能。
