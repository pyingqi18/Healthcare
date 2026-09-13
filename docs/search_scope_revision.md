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

## 官方接口依据

DataForSEO Business Listings Search 支持按类别和坐标半径检索，可在单次请求中设置最多 10 个类别，并返回地址、联系方式、评分等结构化资料：

https://docs.dataforseo.com/v3/business_data-business_listings-search-live/

DataForSEO Business Info 的关键词参数会对加号进行解码，并支持通过 `cid:` 获取单一商家资料：

https://docs.dataforseo.com/v3/business_data-google-my_business_info-task_post/
