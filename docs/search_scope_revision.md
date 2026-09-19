# 全局重抓前的搜索范围修订

## 状态

这是后续全市场重抓前必须完成的设计修改。当前 Malone 和 Syracuse 修复批次继续沿用已经验证的解析、CID补查、ZIP筛选和类别审核流程，不在中途改变样本发现方法。

## 2026-09-08 实证证据

本次纠正地区代码后，共得到 13,213 条搜索观测和 1,120 个唯一 CID。补充 Business Info 并重新判定地理位置后：

1. 231 个 CID 位于目标 ZIP，占全部候选的 20.62%。
2. 887 个 CID 明确位于目标 ZIP 之外。
3. 2 个 CID 仍缺少足够 ZIP 证据。
4. 严格类别规则下，187 个 CID 可明确归为牙医或牙科诊所，占全部候选的 16.70%。
5. 769 个原先缺少地理信息的候选中，仅 15 个位于目标 ZIP，占 1.95%。
6. 769 个补查对象中，490 个位于美国，277 个位于加拿大，2 个缺少国家代码。

这些数字说明当前搜索策略适合作为高召回率候选发现，但不适合直接定义市场样本。

## 根因

1. DataForSEO 的 `location_code` 控制搜索发起位置，不构成商家地址必须位于该地区的约束。
2. 查询中的 `+` 会被解码为空格，不代表布尔交集。
3. 现有代码对每个关键词组生成所有非空组合，每个市场和接口合计 53 个查询，制造大量重复和宽泛匹配。
4. Local Finder 在本批数据中提供 CID，但没有地址、ZIP和坐标。请求地区不能替代商家实际地区。
5. 当前流程在地理筛选之前抓取大量候选，导致后续 CID 资料补查和评论任务存在不必要成本。

## 后续全局重抓的推荐结构

### 第一层：结构化地区发现

优先评估 DataForSEO Business Listings Search。按 Google 商家类别和 `location_coordinate` 搜索，每个请求最多设置 10 个类别并返回结构化地址、ZIP、坐标和 CID。

每个市场在 `config/regions.yaml` 中增加明确的发现半径。发现半径只负责候选召回，最终市场资格仍由配置中的 ZIP 规则决定。

### 第二层：分级关键词补充

如 Business Listings 对部分牙科类别覆盖不足，仅提交单个关键词查询，例如 `dentist`、`dental clinic`、`orthodontist`。禁止默认生成全部关键词组合。

补充查询应分层执行：先运行核心词，去重并检查新增 CID；只有新增覆盖仍明显时才运行专科词。每一层必须记录新增 CID 数量。

### 第三层：立即去重和地理确认

搜索结果返回后立即按 CID 去重。任何缺少结构化地址的候选都必须通过 Maps 或 Business Info 补齐。没有地理证据的候选不得进入市场样本，也不得开始评论抓取。

### 第四层：ZIP和类别筛选前置

评论任务只能针对同时满足以下条件的 CID 创建：

1. ZIP 属于预先配置的研究市场。
2. Google主类别或人工审核结果符合牙医诊所定义。
3. CID和 clinic_key 唯一。

## 需要修改的代码位置

1. `src/medical_ratings/rescrape.py`
   删除默认的全组合关键词生成，改为单关键词和分级扩展策略。
2. `scripts/scrape/00_plan_location_rescrape.py`
   在任务清单中加入 `discovery_method`、`discovery_tier` 和任务数量上限。
3. `src/medical_ratings/dataforseo.py`
   增加 Business Listings Search 客户端方法和逐请求成本记录。
4. `src/medical_ratings/parsing.py`
   增加 Business Listings 结构化结果解析器。
5. `config/regions.yaml`
   为每个市场增加候选发现半径，同时继续保留最终 ZIP 资格规则。
6. 新增全局抓取保护测试
   禁止将请求地区直接写入 `mapped_location`；禁止在ZIP和类别资格确认前生成评论任务；禁止默认关键词组合爆炸。

## 实施顺序

1. 使用 Malone 和 Syracuse 做 Business Listings 小规模试验。
2. 将试验结果与当前 231 个目标ZIP候选按 CID 比较。
3. 审核只被某一种发现方法找到的差异记录。
4. 确认统一发现方法后，再用于所有市场。
5. 全市场必须使用同一版发现逻辑和明确的方法版本号，避免不同市场由不同抓取方法定义。

## 当前流程的处理结论

本批严重多抓没有直接进入最终样本，因为所有候选均经过CID补查、ZIP筛选、类别审核和实体地点归并。它造成的主要损失是多余任务、时间和费用。

19家类别候选和2家缺ZIP候选已经完成审核。最终保留187个合格Google资料，排除10个异常资料后将177个资料归并为109个实体牙科地点。Malone保留8个地点，Syracuse保留101个地点。

当前修复批次已经完成诊所和评论替换。搜索策略修改保留到全市场统一重抓前执行，不能在不同市场之间混用不同发现口径。

## 15市场只规划profile

`config/scrape_plans.yaml`中的`existing_15_markets_planning_v1`只覆盖现有15个研究市场，不增加新州或新地点，也不允许API执行。

旧方案作为费用和任务量对照保留。每个市场为53组关键词组合乘两个接口，共106项；15个市场共1590项。按2026-09-18公开标准队列价格及depth 100估算，Maps每项读取100条，Local Finder每项读取100条即5页，合计约2.862美元。该数字不包括后续Business Info和评论抓取。

新方案分四阶段：

1. 先用Malone和Syracuse验证Business Listings。研究纳入13个官方类别，接口每次最多10个类别，因此每个市场拆成2次，两市场共4次。最低请求费用0.048美元；若4次都返回上限1000 items，费用上限为1.488美元。
2. 只有两市场CID召回达到预先确定的标准后，才允许15市场rollout。当前该阶段未批准。
3. 只有Business Listings存在记录明确的召回缺口时，才考虑`dentist`和`dental clinic`两个Maps单关键词补充。
4. 专科仍缺失时，才考虑五个专科单关键词。新计划禁止自动生成关键词组合。

官方类别名、试验半径和召回率门槛已经在离线计划中冻结。付费试验前仍需实现Business Listings客户端、结构化结果解析器和独立付费确认门，并用reference coverage输出确认109个既有地点全部落入试验圆。

2026-09-18进一步核对官方类别目录后，13个研究纳入类别全部获得精确接口名称。Malone使用5 km试验圆，Syracuse使用15 km试验圆，目的仅是覆盖corrected reference。召回率规则预先设为：总体不低于95%且各市场不低于90%时可作为主发现方法；总体达到90%但未通过主门槛时增加Maps单关键词补充；总体低于90%或任一市场低于80%时拒绝或重新设计。旧参考集不是完整真值，新发现且符合ZIP与类别资格的地点另行审核。

## 官方接口依据

DataForSEO Business Listings Search 支持按类别和坐标半径检索，可在单次请求中设置最多 10 个类别，并返回地址、联系方式、评分等结构化资料：

https://docs.dataforseo.com/v3/business_data-business_listings-search-live/

## 两市场付费试验结论

四项Live请求实际费用为0.2406美元，返回534条类别观测和493个唯一profile。按实际ZIP判断，271个profile属于Malone或Syracuse目标市场，占54.97%。固定匹配规则找回109个corrected reference中的104个，总体召回率为95.41%，两个市场分别达到预设门槛，因此Business Listings获批作为主发现入口，暂不追加Maps关键词付费搜索。

这个批准不等于直接接受全部profile。类别异常的6个目标ZIP profile另有带证据的决定文件。当前竞争地点、可用于评分结果的profile和历史面板保留资格分别判断。例如St. Marianne Cope确认提供牙科服务，可以保留为竞争地点候选，但混合医疗和牙科profile的评分不进入牙科outcome；已关闭的旧Aspen地点不进入当前接口召回率分母，但不会仅因当前关闭而删除历史面板记录。

人工证据调整后，当前有效参考地点为105个，Business Listings发现其中104个，竞争地点召回率为99.05%。唯一仍有效但未被发现的地点是Hybridge Dental Implants。后续全市场重抓应以Business Listings为主，同时显式携带已经验证但未重新发现的旧地点，随后再进行profile到物理地点的审核。

DataForSEO Business Info 的关键词参数会对加号进行解码，并支持通过 `cid:` 获取单一商家资料：

https://docs.dataforseo.com/v3/business_data-google-my_business_info-task_post/
