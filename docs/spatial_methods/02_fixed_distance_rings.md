# 固定距离圆环 Competition Exposure 规格

## 登记状态

| 项目 | 登记值 |
| --- | --- |
| 规格 ID | `distance_rings_0_0p5_0p5_2_2_5_v1` |
| 当前状态 | legacy-compatible复现已运行；正式修正版尚未运行 |
| 建议角色 | 距离梯度稳健性规格，不自动作为主规格 |
| 历史来源 | `009a`（2026-03-10）notebook |
| 圆环 | 0 至 0.5、0.5 至 2、2 至 5 mile |
| outcome 实体 | 原始 `clinic_key` |
| 邻居计数单位 | 原始 `clinic_key` |
| 市场字段 | `search_location` |
| 构造 exposure 时使用 outcome | 否 |
| 正式代码实现 | `legacy_distance_rings.py`冻结legacy复现；`distance_ring_variants.py`比较年份和市场年份固定效应；正式修正版仍暂停 |

该方法把 5 mile 内的竞争者分到三个互不重叠的距离带，以检验进入冲击和活跃密度是否随距离减弱。它扩展固定 2-mile 规格，但三个圆环的系数含义不同，不能把任意一项单独解释为总竞争效应。

## Legacy 定义和需要修正的实现

`009a` 先用全样本 BallTree 查询 5 mile 内 profile，再显式排除当前行索引，随后按距离分为：

1. \(d\le0.5\) mile；
2. \(0.5<d\le2\) mile；
3. \(2<d\le5\) mile。

它分别计算三个圆环中的上年 entrant 数和当年 active profile 数，并在同一个 PanelOLS 公式中同时放入六个 `log1p` 变量。notebook 还单独估计过 0.5-mile 模型。

正式实现必须修正三点：

1. legacy BallTree 是全样本查询，正式实现必须限制为相同 `search_location`。
2. legacy 通过行索引排除自身，正式实现必须使用稳定的 `clinic_key`。
3. legacy 使用 `range(entry_y, 2025)`，实际只生成到 2024 年；正式实现必须服从 corrected panel 的完整年份并保留 2025 年。

当前运行入口`08_run_legacy_distance_rings.py`属于legacy-compatible复现，因此保留全样本邻居查询和2025年缺失，只把旧行序号身份适配为稳定`clinic_key`。这些兼容性变化和保留行为会写入metadata。该脚本的输出不能标记为正式修正结果。

## Legacy-compatible运行结果

本次运行使用`corrected_v1`数据复现`009a`的固定距离圆环算法，因此是**旧方法在修正后数据上的兼容复现**，不是新增的正式模型。与notebook相比，仅作三项数据兼容处理：用稳定`clinic_key`替代行序号身份、邻居池使用corrected panel中空间合格且有进入年份的诊所、进入年份从`entry_year`或`entry_date_proxy`读取。全样本5-mile查询、自身排除、三个旧圆环、只生成至2024年、诊所固定效应和无年份固定效应均按legacy保留。

Exposure输入为37474个panel行和5674家诊所。4060家诊所进入邻居池，32353行获得圆环exposure，5121行没有exposure；其中4183行是因为legacy年份循环明确不生成2025年。5 mile内实际跨市场有向邻居链接为0，因此这批数据中“全样本查询”没有造成跨市场计数，但算法本身仍未加入同市场约束。

联合圆环模型使用2015至2024年的27990行、3861家诊所，标准误按`clinic_key`聚类。结果如下：

| 变量 | 系数 | 标准误 | p值 |
| --- | ---: | ---: | ---: |
| `log_shock_0_05` | 0.013582 | 0.005846 | 0.0202 |
| `log_shock_05_2` | 0.017581 | 0.005684 | 0.0020 |
| `log_shock_2_5` | 0.029185 | 0.005858 | 6.32e-07 |
| `log_density_0_05` | -0.040658 | 0.028403 | 0.1523 |
| `log_density_05_2` | -0.093963 | 0.037051 | 0.0112 |
| `log_density_2_5` | -0.093331 | 0.038709 | 0.0159 |
| `log_votes_dynamic` | 0.104130 | 0.007529 | <0.0001 |

单独0.5-mile legacy模型使用同一批27990行和3861家诊所：

| 变量 | 系数 | 标准误 | p值 |
| --- | ---: | ---: | ---: |
| `log_shock_0_05` | 0.032335 | 0.005894 | 4.15e-08 |
| `log_density_0_05` | -0.142985 | 0.023999 | 2.59e-09 |
| `log_votes_dynamic` | 0.078532 | 0.006411 | <0.0001 |

这些结果只能读作legacy条件关联。联合模型的三个shock系数从近到远反而增大，不支持简单的“距离越近效应越强”；单独0.5-mile的shock系数又明显大于联合模型中的内环系数，说明加入外环shock和三个density后，内环系数的条件含义发生了较大变化。不能从两张表中挑选显著性更强的模型作为主结果。

共同年份固定效应比较继续使用相同的27990行和3861家诊所。联合模型三个shock系数依次降为0.006256、0.005409和0.011238，p值依次为0.3353、0.3862和0.1064。三个density系数依次为-0.030638、-0.072124和-0.038248，p值依次为0.3289、0.0962和0.5295。六个圆环exposure均未达到5%显著性水平。

单独0.5-mile模型加入年份固定效应后，shock系数从0.032335降至0.008801，下降72.78%，p值从4.15e-08变为0.1824；density系数从-0.142985变为-0.043278，绝对值下降69.73%，p值变为0.1711。结果与固定2-mile诊断一致，legacy显著性对共同年份控制不稳健。

共同年份固定效应仍不能控制各市场独有的年度冲击。下一项诊断保持圆环exposure和样本不变，用`search_location × year`固定效应替代共同年份固定效应。在完成该比较、联合显著性检验、系数相等检验和共线性诊断前，不解释为因果效应或可靠的距离梯度。

## 邻居集合与圆环边界

令 \(d_{ij}\) 为 `clinic_key` 不同且属于同一 `search_location` 的两个 profile 之间的 Haversine 大圆距离。定义：

\[
\mathcal{B}_{i1}=\{j:j\ne i,\ m_j=m_i,\ 0\le d_{ij}\le0.5\},
\]

\[
\mathcal{B}_{i2}=\{j:j\ne i,\ m_j=m_i,\ 0.5<d_{ij}\le2\},
\]

\[
\mathcal{B}_{i3}=\{j:j\ne i,\ m_j=m_i,\ 2<d_{ij}\le5\}.
\]

三组边界没有重叠和空缺：0.5 mile 归入第一环，2 mile 归入第二环，5 mile 归入第三环。不同 `clinic_key` 即使距离为零，也进入第一环。暂定地址竞争单位只可用于冻结的敏感性分析。

邻居池沿用固定 2-mile 规格：所有具有有效市场、坐标和进入年份的空间合格 profile 都可作为邻居，不要求具有 rating。坐标在面板期内视为不变。

## Exposure 定义

令 \(a_j\) 为邻居 \(j\) 的进入年份，\(t\) 为 panel year，\(k\in\{1,2,3\}\) 表示圆环。定义：

\[
E_{itk}=\sum_{j\in\mathcal{B}_{ik}}\mathbf{1}(a_j=t-1),
\qquad
D_{itk}=\sum_{j\in\mathcal{B}_{ik}}\mathbf{1}(a_j\le t).
\]

每个圆环均生成 raw count 和 `log1p` 版本：

| 圆环 | 进入冲击字段 | 密度字段 |
| --- | --- | --- |
| 0 至 0.5 mile | `entry_shock_0_0p5mi_count`、`log_entry_shock_0_0p5mi_count` | `density_0_0p5mi_count`、`log_density_0_0p5mi_count` |
| 0.5 至 2 mile | `entry_shock_0p5_2mi_count`、`log_entry_shock_0p5_2mi_count` | `density_0p5_2mi_count`、`log_density_0p5_2mi_count` |
| 2 至 5 mile | `entry_shock_2_5mi_count`、`log_entry_shock_2_5mi_count` | `density_2_5mi_count`、`log_density_2_5mi_count` |

历史字段 `log_shock_0_05`、`log_shock_05_2`、`log_shock_2_5`、`log_density_0_05`、`log_density_05_2` 和 `log_density_2_5` 只能通过明确的 legacy alias 映射读取，不能成为第二套正式命名。

## 回归登记方式

距离梯度规格应在同一个模型中同时放入三个圆环的 entry-shock 变量和三个相应 density 变量。每个 entry-shock 系数表示在另外两个距离带的进入冲击及三个密度计数给定时，该距离带增加 entrant 的条件关联。

必须同时报告：

1. 三个 entry-shock 系数的联合显著性检验；
2. 三个系数相等的检验；
3. 从近到远是否单调衰减的描述，但不能只凭显著性星号判断；
4. 六个 exposure 变量的相关矩阵和 variance inflation 诊断；
5. 每个圆环中具有 clinic 内时间变化的诊所数。

单独的 0.5-mile 模型只能标为探索性或补充结果。它与联合圆环模型回答不同问题，不能在查看系数后替换联合规格。

## 日期、活跃和缺失规则

1. entry shock 使用 \(t-1\)，density 使用 \(a_j\le t\)。
2. 从已冻结的 entry-date hierarchy 读取年份，不在空间模块中另设 fallback。
3. 缺失或无效市场、坐标、进入年份的 profile 不进入邻居池，并进入排除 metadata。
4. rating、votes、未来表现和 NLP outcome 不参与 exposure 构造。
5. 在没有可靠关闭日期前，profile 从进入年持续视为活跃至面板结束。
6. 分析期使用 panel 的 `analysis_period`；2014 与 2015 起始年份冲突仍需在回归前单独解决。
7. 本规格不使用 strong-entrant 分类，以避免未来信息造成 look-ahead bias。

## 文献能够支持的范围

Luo and Qi（2009）的 enhanced two-step floating catchment area 方法把 catchment 划分为多个距离区间，并对较远区域赋予较低的 step weights。McGrail（2012）比较了连续和分区式距离衰减，并指出在城乡混合区域中还需要考虑可变 catchment。它们支持“距离带可能比单一硬半径更能表达空间衰减”的一般思路。

本项目的圆环回归与 E2SFCA 并不相同。E2SFCA 衡量人口相对于医疗供给的可及性，本规格则把 provider entry 和 provider density 作为 clinic-rating 回归变量；本规格也没有人口分母或预先给定的衰减权重。因此，文献不能验证 0.5、2、5 mile 这些具体切点，也不能证明三个圆环的竞争效应应当单调。

Shin and Ahn（2018）的牙科 road-network 研究显示，患者出行距离随城乡和治疗类型变化。这进一步说明固定圆环应作为距离异质性检验，而不应直接宣称为真实患者市场。

## 主要风险

1. 三个相邻圆环的 shocks 和 densities 可能高度相关，使单个系数不稳定。
2. 三个 sharp cutoffs 会使边界两侧距离几乎相同的诊所获得不同 exposure。
3. 5 mile 外的竞争被设为零，尚无本项目数据支持这一终点。
4. profile 数不一定等于物理诊所数，共址 profile 主要影响最内环。
5. 大圆距离没有反映道路、桥梁、公共交通和实际出行时间。
6. 同一组固定切点在 NYC 与农村市场中的经济含义可能不同。
7. 同市场限制会在人为市场边界处遗漏近邻。
8. entry-year measurement error 会把 entrant 分配到错误年份和圆环冲击中。

## 正式修正版运行前必须输出的诊断

1. 每个圆环按市场和年份的 shock、density 分布及零值比例。
2. 每个圆环中 clinic 内有 shock 变化的诊所数。
3. 三个圆环计数之和与独立 5-mile 查询结果完全一致的守恒检查。
4. 边界点 0.5、2、5 mile 的唯一归属检查。
5. 所有 neighbor pair 同市场且不包含自身的检查。
6. 六个回归 exposure 的相关矩阵和共线性诊断。
7. 最内环中完全同坐标及 50 米内 profile 的贡献比例。
8. 使用冻结暂定竞争单位后的敏感性差异，但不得把该分支标为已去重主结果。
9. 极端计数 clinic-year 及其 profile 列表。
10. exposure 合并前后 panel 行数和 clinic-year 唯一性守恒。

## 后续实现测试

本步不新增代码。获准实现时，单元测试必须覆盖三个圆环的上下边界、刚越过边界、同市场过滤、稳定 ID 自身排除、零距离但不同 ID、上年进入时点、未来 entrant 不计入当期 density、缺失坐标和进入年份，以及三个圆环之和等于 5-mile 总计数。

## 文献

1. Luo, W., and Qi, Y.（2009）. An enhanced two-step floating catchment area method for measuring spatial accessibility to primary care physicians. *Health & Place*, 15(4), 1100-1107. https://doi.org/10.1016/j.healthplace.2009.06.002
2. McGrail, M. R.（2012）. Spatial accessibility of primary health care utilising the two step floating catchment area method: an assessment of recent improvements. *International Journal of Health Geographics*, 11, 50. https://doi.org/10.1186/1476-072X-11-50
3. Shin, H., and Ahn, E.（2018）. Does the regional deprivation impact the spatial accessibility to dental care services? *PLOS ONE*, 13(9), e0203640. https://doi.org/10.1371/journal.pone.0203640
