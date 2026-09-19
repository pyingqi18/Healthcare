# Tests

## 1. 运行原则

`tests/`中的测试使用小型人工样本，不连接API，也不提交付费任务。
`tests/integration/`读取本地真实数据，使用`real_data`标记。
所有命令在项目根目录和已激活的`.venv`中运行。

```bash
python -m pytest -q
python -m pytest -m "not real_data" -q
```

测试失败时应区分代码回归、输入版本变化和历史错误证据变化。
不得为了通过测试删除断言或修改legacy原始文件。

## 2. 单元测试文件说明

* `test_business_info_backfill.py`：验证Business Info补抓清单只选择未解决候选，并正确计算批次数、成本和CID约束。
* `test_business_info_parsing.py`：验证Business Info响应解析会保留商家字段、资料身份和抓取来源信息。
* `test_business_listings_pilot.py`：验证13个官方牙科类别、四项两市场试验、参考地点半径覆盖和三档召回率决定规则。
* `test_business_listings_live.py`：验证四请求付费门、ZIP过滤参数、Live完成状态与结果数量一致性、身份字段、CID/place_id去重、大市场分页参数、跨页连续覆盖审计及rollout缺页拦截。
* `test_business_listings_comparison.py`：验证pilot及单市场rollout的美国ZIP、加拿大邮编和缺失邮编分类、类别资格、competition unit参考折叠、旧参考地点地理口径、需要身份佐证的10米匹配规则、全部完成页费用和召回率决定。
* `test_business_listings_manual_audit.py`：验证当前竞争地点、评分profile和历史面板三种资格分别处理，并用人工证据调整旧参考召回率分母。
* `test_business_listings_location_audit.py`：验证Business Listings竞争候选只生成profile-to-location审核pair和临时block，排除候选不参与且不会自动合并。
* `test_business_listings_location_triage.py`：验证多profile block按共享身份证据和链式连接风险分档，单profile block不进入人工队列且所有分档仍保持零自动合并。
* `test_business_listings_location_resolution.py`：验证竞争地点归并与评分profile身份分离、复杂区块决定完整性、canonical profile组内约束以及零rating合并。
* `test_business_listings_competition_universe.py`：验证新发现地点与legacy carry-forward的完整合并、重复地点拦截、canonical唯一性及carry-forward不新增outcome profile。
* `test_business_listings_rollout.py`：验证剩余13个市场的分阶段首轮计划、ZIP有效参考地点半径、Atlanta证据门、10个普通市场批量执行门、纽约洛杉矶第一页探测、目标ZIP效率审计与过滤计数计划、共享日志中的合法续页、已完整类别组排除及有界offset续页。
* `test_major_metro_filtered_pagination.py`：验证纽约洛杉矶ZIP过滤总数生成29页token计划、续页token链完整性、断点状态和验证模式零凭据零请求。
* `test_major_metro_filtered_parse.py`：验证四条ZIP过滤token链完整后才能离线解析，逐条结果符合目标ZIP，并只按Google稳定身份在市场内去重而不合并物理地点。
* `test_business_listings_stage_parse.py`：验证普通市场批量解析只选择standard rollout的10个市场，并拦截分页不完整或日志页数与审计不一致的输入。
* `test_business_listings_stage_comparison.py`：验证批量资格与召回率审计要求10个市场完整对应，并按legacy参考地点数量计算整体召回率而不是简单平均市场比例。
* `test_rollout_maps_supplement_plan.py`：验证召回缺口分档不自动匹配、真正缺ZIP审计、所有阶段市场统一核心关键词计划、旧地点核验与主发现任务隔离，以及主任务按100项分批。
* `test_rollout_maps_standard_execution.py`：验证统一Maps Standard执行入口只接受冻结的15市场30项核心发现任务，并拒绝遗漏市场或legacy定向核验混入付费主manifest。
* `test_maps_supplement.py`：验证Maps核心结果排除付费广告、在市场内按稳定ID去重、统计两个关键词边际覆盖，并分别保留主类别分组、多标签类别证据和旧优先级结果。
* `test_maps_supplement_audit.py`：验证Maps候选按实际ZIP审核、Business Listings显式纳入状态、市场内Google稳定ID精确重合及零自动地点合并。
* `test_maps_only_review.py`：验证真正Maps独有profile、未覆盖市场、类别冲突队列和跨来源身份候选pair相互分开，并保持零自动类别决定与零自动地点合并。
* `test_candidate_audit.py`：验证搜索候选审计能汇总关键词产出、候选重叠和覆盖情况。
* `test_candidate_eligibility.py`：验证候选资格规则保留全部记录、分配互斥状态并拒绝重复规则类别。
* `test_candidate_enrichment.py`：验证候选地理补全、美国ZIP解析、加拿大记录排除和资料覆盖要求。
* `test_clinic_candidates.py`：验证诊所候选构建优先使用Maps资料、映射ZIP市场并拒绝冲突ZIP。
* `test_competition_unit_spatial_audit.py`：验证竞争单位内profile不会互相计作邻居，半径结果完整映射回所有profile且单位不能跨市场。
* `test_competition_units.py`：验证同市场完整地址和坐标一致时才共用竞争单位，缺失地址与坐标冲突保持独立。
* `test_coordinate_cluster_audit.py`：验证完全同坐标和50米内候选仅在市场内生成，排除无效坐标且不执行自动合并。
* `test_dataforseo_business_info.py`：验证Business Info批量提交保留逐任务状态，并执行100项上限和CID一致性检查。
* `test_dataforseo_reviews.py`：验证评论任务支持place_id或CID、保留请求参数和状态，并执行标识符与批量上限约束。
* `test_dataforseo_search.py`：验证认证、Business Listings过滤目录GET与地点搜索都经过共享客户端，并在任务提交时保留可追踪标签。
* `test_distance_ring_variants.py`：验证圆环比较模型加入年份或市场年份固定效应、保留预期变量和样本，并拒绝重复clinic-year。
* `test_download_business_info_results.py`：验证Business Info下载计划支持续传、核对任务与CID并原子写入JSON。
* `test_download_location_results.py`：验证地点结果下载会过滤失败任务、支持续传、核对清单字段并原子写入JSON。
* `test_download_review_results.py`：验证评论下载计划、商家身份、抓取深度状态和JSON原子写入。
* `test_duplicate_candidate_audit.py`：验证重复候选只根据充分身份信号配对，并排除跨市场、已排除记录和弱联系证据。
* `test_final_location_resolution.py`：验证人工决策覆盖完整后生成稳定地点、profile交叉表和唯一canonical记录。
* `test_final_analysis_config.py`：验证完整重抓前冻结的主模型年份、2-mile exposure、t-2 density、固定效应、共同样本和敏感性分析角色不会漂移。
* `test_geography.py`：验证地区代码标准化、区域代码唯一性、地点状态和最终分析资格标记。
* `test_identifiers.py`：验证ZIP和名称标准化，以及Google标识优先和fallback clinic_key稳定性。
* `test_legacy.py`：验证旧诊所与时间线使用安全匹配，并拒绝重复时间线键。
* `test_legacy_distance_rings.py`：验证legacy固定距离圆环的边界、自身排除、全样本邻居、2025年缺失和重复身份拒绝。
* `test_legacy_two_mile.py`：验证已冻结的2-mile legacy复现保留跨市场邻居、自身entry shock和density减一逻辑。
* `test_legacy_reviews.py`：验证旧评论的各类连接路径和诊所名称ZIP键唯一性约束。
* `test_location_resolution_audit.py`：验证地点审计识别非牙科资料、冲突证据和跨组近邻异常。
* `test_major_metro_source_audit.py`：验证LA和NYC使用同一融合历史参考分别计算Business Listings与Maps Standard召回率，并单独计算两种新来源的精确profile重合。
* `test_all_market_source_audit.py`：验证15市场四批Business Listings来源不重叠、统一融合历史分母加权汇总、Maps精确profile重合和pilot人工当前有效性分母隔离。
* `test_source_union_audit.py`：验证Business Listings与Maps在同一历史地点键上的共同发现、Maps增量、联合召回、剩余缺口及市场门槛分档，防止直接相加两种来源召回率。
* `test_unmatched_reference_audit.py`：验证两种来源均未发现地点能连接历史身份与最近候选证据、按距离和信息完整性分档，并保持当前状态、付费补抓和地点合并均为人工决定。
* `test_identity_rule_validation.py`：验证放宽身份规则只生成精确名称、门牌号、地址相似度和距离支持的人工候选，并拒绝重复历史键且不自动确认身份。
* `test_identity_rule_adjudication.py`：验证身份人工决定必须完整覆盖候选、保持历史标题身份不变，并正确区分确认匹配、分母排除和规则样本内精度。
* `test_adjudicated_source_union.py`：验证已审核的身份匹配和分母排除只作用于指定reference key，并正确重算15市场联合召回率且不触发API或地点合并。
* `test_manual_candidate_review.py`：验证人工候选决策保留记录、覆盖全部待决候选并阻止身份漂移。
* `test_panel.py`：验证年度面板构建、历史评论累计、进入年份缺失处理和混合日期格式保留。
* `test_parse_business_info_results.py`：验证已下载Business Info文件的任务标签、身份和解析结果。
* `test_parse_location_results.py`：验证地点搜索解析保留全部观测和来源信息，并拒绝任务标签错配。
* `test_parsing.py`：验证Maps、Local Finder和评论响应解析保留业务字段、稳定ID与provenance，并接受空结果。
* `test_pipeline.py`：验证pipeline配置解析、阶段范围、缺失输入诊断、付费确认门、manifest校验值、断点续跑和blocked profile。
* `test_physical_location_groups.py`：验证物理地点分组证据、canonical资料选择、弱边不串联合并和最终资格过滤。
* `test_region_location_codes.py`：验证纽约地区使用正确DataForSEO地点代码，并排除同名错误代码。
* `test_regression_readiness.py`：验证回归字段缺失、完整估计样本、组内变异和重复clinic-year诊断。
* `test_replacement_audit.py`：验证错误批次替换的行数守恒、评论覆盖、地点碰撞和冻结计数。
* `test_replacement_build.py`：验证纠正批次按物理地点替换旧数据，评论连接改用最终地点ID。
* `test_rescrape.py`：验证地点重抓清单生成、目标地区映射和未知地区拒绝规则。
* `test_result_audit.py`：验证地点搜索结果的任务覆盖、结果数量和空结果处理。
* `test_review_collection.py`：验证每个canonical地点只提交一次评论任务，并计算自适应深度、上限、批次和成本。
* `test_review_result_audit.py`：验证评论原始结果的商家身份、抓取深度、缺失ID和跨文件重复评论。
* `test_review_result_parsing.py`：验证评论解析计划完整性、零评论地点保留、重复review_id拒绝和结果汇总。
* `test_scrape_safety.py`：验证抓取任务数量由实际task tag推导，且付费确认文本使用尚未提交的任务数动态生成。
* `test_scrape_run_context.py`：验证run name不能逃逸目录、raw与interim路径统一生成，并确认已登记的有效抓取脚本全部使用共享run context。
* `test_scrape_plan.py`：验证原15市场规划完整、旧1590项对照可复算、新关键词不组合以及所有新阶段保持不可付费执行。
* `test_scrape_checks.py`：验证认证检查经过共享客户端且不泄露凭据，并验证任务状态选择和已就绪结果摘要。
* `test_settings.py`：验证Google评论抓取配置能够从项目设置中正确加载。
* `test_spatial.py`：验证进入冲击仅在市场内部计算，并正确添加空间分析资格。
* `test_spatial_scale_audit.py`：验证固定半径邻居只在市场内统计，并排除无资格或无效坐标记录。
* `test_strict_legacy_sample_audit.py`：验证严格009a与04兼容版本的邻居池、ZIP与类别排除、缺失面板原因和回归clinic-year交集能够被准确区分。
* `test_strict_legacy_two_mile.py`：验证严格009a 2-mile基线恢复ZIP、类别、评分、年份、全局邻居和自身计数规则，同时保留已审核的corrected replacement类别。
* `test_strict_spatial_suite.py`：验证strict 009a剩余空间方法共用邻居池、自身排除、2024截止年份和三种固定效应注册表。
* `test_strict_two_mile_variants.py`：验证严格009a自身entry shock修正保留冻结样本，并在同样本上正确加入共同年份和严格ZIP市场年份固定效应。
* `test_two_mile_variants.py`：验证2-mile新规格排除自身entry shock、保持样本结构，并正确加入年份或市场年份固定效应。
* `test_submit_business_info_backfill.py`：验证Business Info提交清单接受不同任务规模，并检查批量大小和成功任务续跑状态。
* `test_submit_review_collection.py`：验证评论提交清单接受不同任务规模，并检查批量大小、成功任务重试和标识符一致性。
* `test_validation.py`：验证评分对账会保留来源评分不一致证据。

## 3. 真实数据测试文件说明

* `integration/test_legacy_inputs.py`：验证旧诊所、评论、合并前诊所和时间线文件存在，字段有效且身份键符合已知结构。
* `integration/test_legacy_panel.py`：验证真实年度面板的文件、唯一性、年份范围、累计结果和摘要守恒。
* `integration/test_prepared_legacy_output.py`：验证准备后的诊所表字段、唯一身份、时间线安全匹配、进入日期和非美国邮编处理。
* `integration/test_prepared_legacy_reviews.py`：验证准备后的评论行数守恒、clinic_key覆盖、连接路径、日期评分和非美国评论识别。

只运行真实数据测试：

```bash
python -m pytest tests/integration -m real_data -q
```

## 4. 当前回归前诊断测试
下面五类测试检查回归字段、固定半径、坐标共址和暂定竞争单位。它们只验证函数行为，不代表竞争单位已经被批准为主样本。
分别运行：

```bash
python -m pytest tests/test_regression_readiness.py -q
python -m pytest tests/test_spatial_scale_audit.py -q
python -m pytest tests/test_coordinate_cluster_audit.py -q
python -m pytest tests/test_competition_units.py -q
python -m pytest tests/test_competition_unit_spatial_audit.py -q
```

一次运行：

```bash
python -m pytest \
  tests/test_regression_readiness.py \
  tests/test_spatial_scale_audit.py \
  tests/test_coordinate_cluster_audit.py \
  tests/test_competition_units.py \
  tests/test_competition_unit_spatial_audit.py -q
```
