# 固定 2-mile 竞争 Exposure 规格

## 登记状态

| 项目 | 登记值 |
| --- | --- |
| 规格 ID | `distance_fixed_2mi_v1` |
| 当前状态 | 已文档化并冻结，尚未选为主规格 |
| 历史来源 | `008`（2026-02-25）与 `009a`（2026-03-10）notebook |
| 距离规则 | 包含边界的 2-mile 大圆距离 |
| outcome 实体 | 原始 `clinic_key` |
| 邻居计数单位 | 原始 `clinic_key` |
| 市场字段 | `search_location` |
| 进入冲击时点 | 上一个日历年 |
| 构造 exposure 时使用 outcome | 否 |
| 正式代码实现 | legacy复现已冻结；修正规格位于独立variants模块；最终主规格仍未确定 |

本文档在查看系数前冻结候选设计，但不表示固定 2-mile 已被选为最终主规格。

## 已运行版本和结果区别

以下三项使用同一 corrected_v1 数据。后两项属于新修改，不能标记为 legacy 结果。

| 版本 | 相对前一版本的修改 | 样本 | entry shock系数 | 标准误 | p值 | 结果变化 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Legacy-compatible baseline | 将legacy算法适配稳定`clinic_key`和corrected panel；保留自身计数及仅诊所固定效应 | 31,984 | 0.036456 | 0.005123 | 1.14e-12 | legacy基线 |
| Self-excluded variant | 只排除诊所自身的上一年进入计数 | 31,984 | 0.034569 | 0.005241 | 4.30e-11 | 系数下降5.18%，显著性结论不变 |
| Entity and year FE variant | 在self-excluded版本上加入年份固定效应 | 31,984 | 0.005794 | 0.005872 | 0.3238 | 系数下降83.24%，不再显著 |
| Entity and market-year FE variant | 用`search_location`乘年份固定效应替代共同年份固定效应 | 31,984 | 0.001804 | 0.006230 | 0.7721 | 较年份固定效应再下降68.86%，较legacy基线累计下降95.05% |

`legacy_two_mile.py`只保留第一行的算法和模型。其余三行位于`two_mile_variants.py`。本表记录已观察到的结果，不用于选择距离半径。

年份固定效应使系数接近零并失去统计显著性，市场年份固定效应又将系数降至0.001804。原先正相关主要由共同年份和市场年份变化解释。当前证据不支持把2-mile进入冲击解释为稳定的评分影响。

## 研究含义

该方法衡量诊所附近高度局部的竞争压力。它考察某诊所 2 mile 直线距离内出现一个或多个新进入 profile 后，诊所评分是否变化，同时控制该半径内已经活跃的 sampled profile 数量。

这是一种 provider-location 竞争 exposure，不是患者可及性指标，也不是经过验证的牙科服务区。它不能证明所有患者都会把 2 mile 内的诊所视为可替代选择。

## outcome 样本与邻居池

outcome 面板继续以 `clinic_key` 和 `year` 唯一确定一行。只有已被现有面板标记为 `analysis_period` 和 `spatial_analysis_eligible`，且后续登记模型所需变量完整的 clinic-year 才能进入估计。

邻居池不得限制为 outcome 完整样本。它应包含所有具有有效 `clinic_key`、`search_location`、经纬度和整数进入年份的空间合格 profile。邻居即使没有可观测评分，也仍然构成竞争 exposure；否则会让 exposure 取决于 rating 是否可得。

当前 corrected panel 默认构建 2008 至 2025 年历史，并将 2015 至 2025 年标记为分析期。exposure 应先覆盖完整面板历史，估计时再使用 `analysis_period`。`config/settings.yaml` 中仍有 `minimum_treatment_year: 2014`，与面板默认的 2015 不一致。正式回归前必须解决该冲突，本规格不会静默选择其中一个年份。

## 距离和边界

令 \(d_{ij}\) 为 outcome 诊所 \(i\) 与潜在邻居 \(j\) 之间的 Haversine 大圆距离，单位为 mile，地球半径使用 3,958.8 mile。定义：

\[
\mathcal{N}_{i,2}=\{j: j\ne i,\ m_j=m_i,\ d_{ij}\le 2\},
\]

其中 \(m_i\) 是 `search_location`。边界采用 \(\le 2\)，因此恰好 2 mile 的邻居会被计入。坐标在面板期内视为不随时间变化。

同市场限制是强制规则。历史 notebook 使用一棵全样本 BallTree，地理位置接近但被划入不同研究市场的 profile 可能相互计数。正式实现必须在 `search_location` 内查询或过滤邻居。

## Exposure 的精确定义

令 \(a_j\) 为邻居 \(j\) 的整数进入年份，\(t\) 为 clinic-year。上年进入冲击为：

\[
E_{it}^{2mi}=\sum_{j\in\mathcal{N}_{i,2}}\mathbf{1}(a_j=t-1).
\]

活跃竞争密度为：

\[
D_{it}^{2mi}=\sum_{j\in\mathcal{N}_{i,2}}\mathbf{1}(a_j\le t).
\]

正式字段登记为：

| 字段 | 定义 |
| --- | --- |
| `entry_shock_2mi_count` | \(E_{it}^{2mi}\) |
| `entry_shock_2mi_dummy` | \(E_{it}^{2mi}>0\) 时为 1，否则为 0 |
| `log_entry_shock_2mi_count` | \(\log(1+E_{it}^{2mi})\) |
| `density_2mi_count` | \(D_{it}^{2mi}\) |
| `log_density_2mi_count` | \(\log(1+D_{it}^{2mi})\) |

比较历史输出时，可以把 `lag_entry_shock_2mi_count`、`lag_entry_shock_2mi_dummy`、`log_lag_entry_shock_2mi` 和 `log_density_2mi_total` 显式映射到上述字段，但正式代码不能继续保留两套命名来源。

## 自身、共址和活跃状态

必须在计数前根据 `clinic_key` 显式排除自身。历史 panel 循环在 entrant 名称列表中排除了自身，但 numeric `lag_count` 没有排除，导致诊所在自身进入后的下一年可能把自己计为 entrant。上述正式定义修复该错误。先聚合再减一不能代替显式排除自身。

共用坐标但 `clinic_key` 不同的 profile 在本候选规格中仍作为不同邻居，因为共址审计没有证明它们属于同一诊所。暂定地址竞争单位只能保留为冻结的敏感性分支，不能替换主候选的计数单位。

诊所从进入年份起一直视为活跃至 2025 年。当前不采用退出日期，因为 review inactivity 不能验证真实停业。由此产生的 density 不会下降，解释结果时必须说明这一限制。

## 日期与缺失值规则

1. 进入年份必须来自已经冻结且可追踪来源的 entry-date hierarchy，空间方法不得另设日期 fallback。
2. 缺失或无效进入年份的 profile 不进入邻居池，并按日期来源和市场计入 metadata。
3. 缺失、非有限或越界坐标的 profile 不进入邻居池和空间估计，但不能从源数据删除。
4. `search_location` 缺失或为空时，该 profile 不进入本 exposure。
5. 面板按年构建，因此进入冲击只使用年份，不使用月份或日期。
6. rating、votes、未来表现和 NLP outcome 不得影响进入状态或邻居池成员资格。

本基础规格不包含 strong entrant。legacy 版本使用了可能来自进入后的 rating 和 review 信息，存在 look-ahead bias。如需保留，必须另建只使用进入时可得信息的规格。

## 文献能够支持的范围

固定半径计数具有清楚、可复现的 exposure mapping：研究者预先说明哪些单位可能影响 focal unit，再根据该映射计算 treatment。Aronow and Samii（2017）提供了干扰条件下 exposure mapping 的因果框架，但该框架不能证明 2 mile 是本研究正确的经济边界。

牙科出行文献不支持把单一固定距离当作通用牙科 catchment。Shin and Ahn（2018）使用 road-network travel distance，发现牙科出行距离随城乡、地区条件和治疗类型变化，其样本中农村患者出行明显更远。McGrail（2012）也发现，在农村和都市地区衡量医疗可及性时，需要同时考虑距离衰减和可变 catchment。这些研究关注医疗可及性，并非 Google rating 竞争，因此只能支持开展敏感性分析，不能识别本项目的竞争半径。

因此，2 mile 被保留是因为它属于较早、容易解释的 legacy 选择，也是合理的局部竞争候选。它不能被表述为文献确认的牙科市场。road travel time、距离衰减、市场自适应半径、圆环和 patient-flow 方法将在后续分别登记。

## 主要解释风险

1. 大圆距离可能与公路距离和实际出行时间差异明显。
2. 同一 2-mile 边界在高密度城市、郊区和农村市场中的行为含义不同。
3. profile 可能代表个人执业者、机构或同地址多个 listing，因此 profile 数不等于物理诊所数。
4. entry-year proxy 可能反映 NPI 登记、网站建立或首条可观测 review，而非真实开业。
5. 当前样本依赖后期平台可见性，可能遗漏已经关闭或没有被抓到的诊所。
6. 同市场限制能防止跨市场污染，但相邻诊所若市场标签不同，会产生人为边界。
7. 永久活跃假设会在真实停业后高估 density。
8. 硬阈值把 0.1 与 1.9 mile 赋予相同权重，却让 2.01 mile 的权重直接变为零。

## 回归前必须输出的诊断

后续实现必须生成不使用 outcome 的 metadata 和表格，至少包括：

1. outcome profile 与邻居 profile 的纳入、排除数量及原因。
2. overall、market-year 层面的 exposure 分布。
3. entry shock 为零和 active competitor 为零的 clinic-year 比例。
4. 每个 entry-shock 变量具有 clinic 内时间变化的诊所数。
5. entry-shock 强度与 active density 的相关性。
6. 极端计数及其对应 clinic-year。
7. 证明所有计数 pair 具有相同 `search_location` 的检查。
8. 证明任何距离和年份下都不会计入自身的检查。
9. 完全同坐标和近距离邻居数量。
10. 使用冻结暂定竞争单位的敏感性结果，并明确标记为未验证的 profile grouping。

不得根据系数选择该方法是否成为主规格。只有全部历史距离方法和文献补充方法完成登记后，才允许选择主规格。

## 后续实现所需测试

本步不新增 exposure 代码。获准实现时，单元测试必须覆盖：恰好 2 mile、刚超过 2 mile、同市场限制、显式自身排除、共址但不同 `clinic_key`、上年进入时点、density 时点、无效坐标、缺失进入年份、在 focal year 之后进入的诊所，以及稳定字段命名。真实数据审计还必须验证 exposure 合并后 panel 行数守恒。

## 文献

1. Aronow, P. M., and Samii, C. (2017). Estimating average causal effects under general interference, with application to a social network experiment. *Annals of Applied Statistics*, 11(4), 1912-1947. https://doi.org/10.1214/16-AOAS1005
2. McGrail, M. R. (2012). Spatial accessibility of primary health care utilising the two step floating catchment area method: an assessment of recent improvements. *International Journal of Health Geographics*, 11, 50. https://doi.org/10.1186/1476-072X-11-50
3. Shin, H., and Ahn, E. (2018). Does the regional deprivation impact the spatial accessibility to dental care services? *PLOS ONE*, 13(9), e0203640. https://doi.org/10.1371/journal.pone.0203640
