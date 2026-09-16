# 文献建议的新增空间方法

## 目的

本文件评估 legacy 代码之外可能更合理的空间方法。这里的“更好”取决于 estimand 和可用数据，不存在对所有研究问题都占优的距离定义。

本项目的问题是新竞争者进入与既有诊所 online rating 的关系。它不同于“居民能否获得牙科服务”的空间可及性问题。因此，患者可及性文献可以改善距离测量，但不能自动定义竞争 treatment。

## 候选 A：道路网络时间或距离

### 方法

用道路网络最短时间或最短距离替代 Haversine distance，形成固定 travel-time bands、连续 travel-time decay 或最近 entrant travel time。

### 文献依据

Shin and Ahn（2018）直接使用道路网络计算患者到牙科机构的实际 travel distance。Nasseh 等（2017）使用 street-network travel time 和 catchment 研究牙科可及性。Rahman 等（2024）在美国牙科诊所研究中使用 30-minute drive-time impedance 的 E2SFCA。Clark（2024）也使用 car journey time、varying catchments 和 distance decay。

### 对本项目的适用性

道路时间比直线距离更接近真实空间摩擦，尤其适用于河流、桥梁、高速公路和城乡差异明显的市场。它需要冻结 routing engine、道路网络版本、交通模式、是否考虑时段及不可达路线规则。

文献中的 30 分钟是 access catchment，不等于 rating competition 的正确半径。本项目不能直接复制 30 分钟作为主竞争 exposure。若采用，应先用 outcome-blind 分布比较其与固定 mile exposure 的差异。

### 当前可行性

当前没有冻结的道路网络矩阵。可列为完整重抓后的高优先级稳健性方法，不能在现阶段无记录地调用在线 routing API。

## 候选 B：patient-flow-defined overlapping markets

### 方法

使用患者来源和就诊目的地构造 clinic-specific market overlap。两个 provider 共享越多患者来源区域，竞争权重越高。可以进一步构造 clinic-specific HHI、竞争者质量或 entrant exposure。

### 文献依据

Li and Dor（2025）研究 community health center 的 quality competition，使用 patient-flow data 构建 CHC-specific HHI 和竞争者质量指标。这与本项目“竞争是否影响质量”的问题最接近。

### 对本项目的适用性

如果获得 dental claims、appointment origin、可信 patient ZIP flow 或其他稳定利用数据，patient flow 比任意圆形边界更能反映重叠市场。市场权重必须使用 treatment 前数据或固定基期计算。若用 entrant 进入后的患者流定义竞争者，会把 treatment 的结果写进 treatment definition，产生 post-treatment bias。

### 当前可行性

当前 Google profile、review 和 NPPES 数据不包含患者流，不能实现。不得用 reviewer location 猜测患者来源，除非其覆盖、隐私和代表性得到单独验证。

## 候选 C：经验校准的连续距离衰减

### 方法

以外部或预处理阶段的利用数据估计 \(w(d)\)，例如 exponential、Gaussian 或 power decay，再构造：

\[
G_{it}=\sum_j w(d_{ij})\mathbf{1}(a_j=t-1).
\]

权重可以使用 road travel time，并允许 urban/rural 或 market type 不同的衰减参数。

### 文献依据

McGrail（2012）表明，跨农村和都市区域的可及性测量需要同时考虑 distance decay 和 variable catchment。Bauer and Groneberg（2016）使用可变 logistic distance decay 与有效 catchment。Clark（2024）在 NHS dentistry 中同时考虑 varying catchments 和 distance decay。

### 对本项目的适用性

这比未经校准的 `1/(1+d)` 更有行为依据，但衰减参数不能用 rating 回归结果挑选。优先使用外部 patient-flow 数据；其次使用预先冻结的独立 calibration sample。若两者都没有，只能预登记少量理论函数作为稳健性分析，并进行多规格调整。

### 当前可行性

可实现预登记函数比较，但无法声称经验校准。现阶段不应新增大量 kernel 与 bandwidth 搜索。

## 候选 D：E2SFCA 或其他供需可及性指标

### 方法

将 provider supply、周边人口 demand、travel impedance 和 distance decay 结合，计算居民或区域层面的 dental accessibility。

### 文献依据

Luo and Qi（2009）提出带距离分区的 E2SFCA。Rahman 等（2024）将 30-minute drive-time E2SFCA 用于美国 dental clinic access。Nasseh 等（2017）使用 street-network 2SFCA 研究牙科 shortage areas。Clark（2024）加入 supply competition、varying catchments 和 distance decay。

### 对本项目的适用性

E2SFCA 非常适合研究患者可及性和 provider shortage，却不直接等于 clinic-to-clinic competition。若未来加入 Census population、provider capacity 和道路时间，它可作为市场环境控制、异质性分组或独立研究 outcome。除非明确建立从 access change 到 clinic rating 的理论机制，否则不建议替代 entrant exposure。

### 当前可行性

当前缺少冻结的需求人口、provider capacity 和 travel-time matrix，暂不能实现完整 E2SFCA。

## 候选 E：正式 exposure mapping

### 方法

在干扰条件下，先明确其他诊所的进入状态如何映射为 focal clinic 的 exposure category 或 intensity，再定义 estimand。固定半径、圆环、gravity 和 patient-flow weights 都可嵌入该框架。

### 文献依据

Aronow and Samii（2017）提供 general interference 下 exposure mapping 和平均因果效应的框架。

### 对本项目的适用性

这是设计约束，不是新的距离数据。它要求在回归前固定 neighbor graph、timing、intensity、重复 treatment 和 estimand。当前项目应采用该原则管理所有空间规格，避免看过系数后改变邻居定义。

## 候选 F：空间相关推断

空间 exposure 和空间误差相关是两个问题。即使使用 clinic-clustered standard errors，相邻诊所的未观测冲击仍可能相关。正式模型阶段应评估空间 HAC 或市场层面的替代推断，但这不会改变 treatment exposure，也不能修复错误的市场定义。

此项需要单独的 inference 文档和文献审计，不在当前距离登记中直接实现。

## 当前建议顺序

### 使用现有 corrected legacy 数据

1. 把固定 2-mile exposure 保留为 provisional main candidate，因为它物理尺度固定、容易审计，也最接近早期 legacy 设计。
2. 用固定圆环检验距离梯度。
3. 用 P25/P50 检验市场尺度异质性，但明确其 sample dependence。
4. 把 legacy gravity、最近 entrant 和第五竞争者距离标为探索性。
5. 地址竞争单位只做身份敏感性，不称为已去重数据。

以上仍是建议登记，不是已经批准的主规格。

### 完整重抓或获得新数据后

1. 优先加入冻结版本的 road-network travel time。
2. 若能获得合法、可靠且代表性的患者流，优先构建 pre-treatment patient-flow market。
3. 使用患者流或独立 calibration sample 估计 distance decay。
4. 如研究问题扩展为患者可及性，再加入 population-demand 和 provider-capacity 的 E2SFCA。

## 不应采用的做法

1. 根据 rating coefficient 最大、最显著或符号最理想来选择半径。
2. 使用 outcome complete-case 样本重新计算半径或 decay parameter。
3. 把 access 文献中的 30-minute threshold 直接称为竞争市场。
4. 用进入后的 patient flow 定义 entrant 是否为竞争者。
5. 同时尝试大量半径、kernel 和 cutoff 却只报告显著结果。
6. 把 clinic-clustered error 当作已经处理空间相关。

## 文献

1. Aronow, P. M., and Samii, C.（2017）. Estimating average causal effects under general interference. https://doi.org/10.1214/16-AOAS1005
2. Bauer, J., and Groneberg, D. A.（2016）. Measuring spatial accessibility of health care providers. https://doi.org/10.1371/journal.pone.0159148
3. Clark, S. D.（2024）. Spatial disparities in access to NHS dentistry. https://pubmed.ncbi.nlm.nih.gov/38908020/
4. Li, K., and Dor, A.（2025）. Overlapping markets and quality competition among community health centers. https://pubmed.ncbi.nlm.nih.gov/39468411/
5. Luo, W., and Qi, Y.（2009）. An enhanced two-step floating catchment area method. https://doi.org/10.1016/j.healthplace.2009.06.002
6. McGrail, M. R.（2012）. Spatial accessibility of primary health care utilising the two step floating catchment area method. https://pubmed.ncbi.nlm.nih.gov/23153335/
7. Nasseh, K., Eisenberg, Y., and Vujicic, M.（2017）. Geographic access to dental care varies in Missouri and Wisconsin. https://pubmed.ncbi.nlm.nih.gov/28075494/
8. Rahman, M. S., et al.（2024）. Dental Clinic Deserts in the US: Spatial Accessibility Analysis. https://pubmed.ncbi.nlm.nih.gov/39714842/
9. Shin, H., and Ahn, E.（2018）. Does the regional deprivation impact the spatial accessibility to dental care services? https://doi.org/10.1371/journal.pone.0203640
