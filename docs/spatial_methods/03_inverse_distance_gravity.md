# 5-mile 反距离 Gravity Exposure 规格

## 登记状态

| 项目 | 登记值 |
| --- | --- |
| 规格 ID | `distance_gravity_inverse_5mi_v1` |
| 当前状态 | 已文档化并冻结，尚未选定 |
| 建议角色 | 探索性或稳健性规格，不建议直接作为主规格 |
| 历史来源 | `009a`、`009b`、`009c`、`009d`（2026-03-10）notebook |
| 最大距离 | 包含边界的 5 mile |
| legacy 权重 | \(w(d)=1/(1+d)\)，\(d\) 的单位为 mile |
| outcome 实体 | 原始 `clinic_key` |
| 邻居计数单位 | 原始 `clinic_key` |
| 市场字段 | `search_location` |
| 构造 exposure 时使用 outcome | 否 |
| 正式代码实现 | 在全部距离方法登记完成前暂停 |

该方法让近距离竞争者获得更大权重，避免 5 mile 内所有邻居权重完全相同。但 legacy 的函数形式、参数 1 和 5-mile 截断均未使用患者流、出行或竞争反应数据校准，因此目前只能作为候选稳健性规格。

## Legacy 定义和需要修正的实现

历史 notebook 对所有 profile 建立一棵 Haversine BallTree，查询 5 mile 内邻居，以行索引排除自身，并计算：

\[
\sum_j\frac{1}{1+d_{ij}}
\]

其中 active density 使用 \(a_j\le t\) 的邻居，entry shock 使用 \(a_j=t-1\) 的邻居。随后对两个加权和使用 `log1p`，分别保存为 `log_gravity_density` 和 `log_gravity_shock`。

正式实现必须修正：

1. 全样本邻居查询改为只允许相同 `search_location`。
2. 用稳定 `clinic_key` 排除自身，不能依赖 DataFrame 行号。
3. `range(entry_y, 2025)` 遗漏的 2025 年必须按 corrected panel 补齐。
4. raw weighted sum 和 `log1p` 结果必须同时保存，不能只保留变换值。

## 邻居集合和距离

令 \(d_{ij}\) 为 profile \(i\) 与 \(j\) 的 Haversine 大圆距离，单位为 mile。定义 5-mile 邻居集合：

\[
\mathcal{N}_{i,5}=\{j:j\ne i,\ m_j=m_i,\ 0\le d_{ij}\le5\},
\]

其中 \(m_i\) 是 `search_location`。边界 5 mile 被计入。不同 `clinic_key` 即使坐标相同，也作为不同邻居；地址竞争单位仍只属于冻结敏感性分支。

邻居池包含所有市场、坐标、进入年份有效的空间合格 profile，不要求其 rating 可观测。坐标在面板年份内视为不变。

## 权重函数

legacy 权重登记为：

\[
w(d)=\frac{1}{1+d},\qquad 0\le d\le5.
\]

代表性权重为：

| 距离 | 权重 |
| --- | ---: |
| 0 mile | 1.000 |
| 0.5 mile | 0.667 |
| 1 mile | 0.500 |
| 2 mile | 0.333 |
| 5 mile | 0.167 |
| 超过 5 mile | 0 |

加 1 可以避免同坐标时除以零，但带来三个需要明确的限制。第一，常数 1 与距离单位绑定，若改用 kilometer，权重会改变。第二，衰减速度没有经验校准。第三，权重在 5 mile 处从约 0.167 突然降为零，并非真正连续的无限距离 gravity model。

## Exposure 定义

令 \(a_j\) 为邻居进入年份，\(t\) 为 clinic-year。加权上年进入冲击为：

\[
G^{E}_{it}=\sum_{j\in\mathcal{N}_{i,5}}w(d_{ij})\mathbf{1}(a_j=t-1).
\]

加权活跃竞争密度为：

\[
G^{D}_{it}=\sum_{j\in\mathcal{N}_{i,5}}w(d_{ij})\mathbf{1}(a_j\le t).
\]

正式字段为：

| 字段 | 定义 |
| --- | --- |
| `gravity_entry_shock_5mi` | \(G^{E}_{it}\) |
| `log_gravity_entry_shock_5mi` | \(\log(1+G^{E}_{it})\) |
| `gravity_density_5mi` | \(G^{D}_{it}\) |
| `log_gravity_density_5mi` | \(\log(1+G^{D}_{it})\) |

legacy 的 `log_gravity_shock` 和 `log_gravity_density` 只能作为显式 alias 读取。正式变量名必须写明 5-mile 截断，避免将其误认为没有最大距离的 gravity exposure。

## 回归解释

legacy 模型同时放入 `log_gravity_entry_shock_5mi` 和 `log_gravity_density_5mi`。entry-shock 系数表示在加权 active density 给定时，加权上年进入强度与 rating 的条件关联。

该变量没有“新增一家诊所”的统一边际含义。一家距离 0.5 mile 的 entrant 对 raw exposure 增加约 0.667，一家距离 5 mile 的 entrant 只增加约 0.167；经过 `log1p` 后，边际变化还依赖原有 exposure 水平。因此报告结果时必须给出具有实际距离和基准 exposure 的示例变化，不能只解释一个抽象的 log coefficient。

## 日期、活跃和缺失规则

1. entry shock 使用进入年份 \(t-1\)，density 使用进入年份不晚于 \(t\)。
2. entry year 只能来自已冻结且带来源的日期 hierarchy。
3. 市场、坐标或进入年份无效的 profile 不进入邻居池，并按原因进入 metadata。
4. rating、votes、未来 rating 类别和 NLP outcome 不参与权重或邻居资格。
5. 在可靠关闭日期缺失时，profile 从进入年持续视为活跃至面板结束。
6. 估计使用 panel 的 `analysis_period`；2014 与 2015 的配置冲突仍需另行解决。
7. 本规格不加入 strong-entrant 分类。

## 文献能够支持的范围

空间可及性文献长期使用 gravity 思路表达距离增加时服务互动或可及性下降。Guagliardo（2004）总结了 provider-to-population、nearest-provider、average-distance 和 gravity-based 方法，并指出边界区域内简单供给计数在拥挤城市中可能失去有效性。Luo and Qi（2009）与 McGrail（2012）进一步使用分区或连续距离衰减改善固定 catchment 方法。

这些文献支持“较近 provider 应获得较高空间权重”的一般原则，但不能验证本研究的 \(1/(1+d)\) 形式、参数 1 或 5-mile 截断。它们多数衡量患者对医疗供给的可及性，通常还包含人口需求或 provider capacity；本项目的 legacy exposure 只对 provider profile 求和，衡量的是潜在竞争压力，不能称为完整的医疗可及性 gravity model。

Shin and Ahn（2018）的牙科研究使用 road-network 距离，并发现实际牙科出行随地区和治疗类型变化。因此，若未来获得患者流或可信的出行代理，更好的方法是用观察到的选择或流量校准距离衰减，而不是把 legacy 权重视为已知行为参数。

## 主要风险

1. 权重函数和最大距离未经本研究数据校准。
2. 权重依赖 mile 单位，改用其他单位会改变结果。
3. 5-mile 处存在人为不连续截断。
4. 大圆距离没有反映道路网络和实际出行时间。
5. 同一衰减函数在高密度城市与农村市场中可能含义不同。
6. 同坐标 profile 获得最大权重，共址身份不确定性可能放大其影响。
7. profile 数不等于 physical practice 数。
8. entry-year measurement error 会错误改变 shock 的年份。
9. 永久活跃假设会在真实关闭后高估加权 density。
10. 同市场过滤防止跨市场污染，但可能遗漏市场边界另一侧的真实近邻。

## 实现前必须输出的诊断

1. raw 和 `log1p` gravity exposure 按市场和年份的分布。
2. entry shock 为零的 clinic-year 比例及具有 clinic 内变化的诊所数。
3. 不同距离带对加权和的贡献比例。
4. 完全同坐标及 50 米内 profile 对总权重的贡献比例。
5. weighted exposure 与未加权 5-mile count、2-mile count 和圆环变量的相关性。
6. 最大 exposure clinic-year 及其邻居明细。
7. 所有 neighbor pair 同市场且排除自身的断言。
8. 5-mile 边界内外的数值测试。
9. exposure 合并前后 panel 行数与 clinic-year 唯一性守恒。
10. 对替代衰减参数、无硬截断权重或 road travel time 的预先登记敏感性比较；不得查看系数后再选择函数。

## 后续实现测试

本步不新增代码。获准实现时，单元测试必须覆盖 0、0.5、1、2、5 mile 的精确权重，刚超过 5 mile 的零权重，同市场限制，稳定 ID 自身排除，共址但不同 ID，上年进入和 active timing，无效坐标及进入年份，raw/log 字段一致性，以及 2025 年保留。

## 文献

1. Guagliardo, M. F.（2004）. Spatial accessibility of primary care: concepts, methods and challenges. *International Journal of Health Geographics*, 3, 3. https://doi.org/10.1186/1476-072X-3-3
2. Luo, W., and Qi, Y.（2009）. An enhanced two-step floating catchment area method for measuring spatial accessibility to primary care physicians. *Health & Place*, 15(4), 1100-1107. https://doi.org/10.1016/j.healthplace.2009.06.002
3. McGrail, M. R.（2012）. Spatial accessibility of primary health care utilising the two step floating catchment area method: an assessment of recent improvements. *International Journal of Health Geographics*, 11, 50. https://doi.org/10.1186/1476-072X-11-50
4. Shin, H., and Ahn, E.（2018）. Does the regional deprivation impact the spatial accessibility to dental care services? *PLOS ONE*, 13(9), e0203640. https://doi.org/10.1371/journal.pone.0203640
