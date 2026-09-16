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
* `test_candidate_audit.py`：验证搜索候选审计能汇总关键词产出、候选重叠和覆盖情况。
* `test_candidate_eligibility.py`：验证候选资格规则保留全部记录、分配互斥状态并拒绝重复规则类别。
* `test_candidate_enrichment.py`：验证候选地理补全、美国ZIP解析、加拿大记录排除和资料覆盖要求。
* `test_clinic_candidates.py`：验证诊所候选构建优先使用Maps资料、映射ZIP市场并拒绝冲突ZIP。
* `test_competition_unit_spatial_audit.py`：验证竞争单位内profile不会互相计作邻居，半径结果完整映射回所有profile且单位不能跨市场。
* `test_competition_units.py`：验证同市场完整地址和坐标一致时才共用竞争单位，缺失地址与坐标冲突保持独立。
* `test_coordinate_cluster_audit.py`：验证完全同坐标和50米内候选仅在市场内生成，排除无效坐标且不执行自动合并。
* `test_dataforseo_business_info.py`：验证Business Info批量提交保留逐任务状态，并执行100项上限和CID一致性检查。
* `test_dataforseo_reviews.py`：验证评论任务支持place_id或CID、保留请求参数和状态，并执行标识符与批量上限约束。
* `test_dataforseo_search.py`：验证认证与地点搜索都经过共享客户端，并在任务提交时保留可追踪标签。
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
* `test_scrape_checks.py`：验证认证检查经过共享客户端且不泄露凭据，并验证任务状态选择和已就绪结果摘要。
* `test_settings.py`：验证Google评论抓取配置能够从项目设置中正确加载。
* `test_spatial.py`：验证进入冲击仅在市场内部计算，并正确添加空间分析资格。
* `test_spatial_scale_audit.py`：验证固定半径邻居只在市场内统计，并排除无资格或无效坐标记录。
* `test_strict_legacy_sample_audit.py`：验证严格009a与04兼容版本的邻居池、ZIP与类别排除、缺失面板原因和回归clinic-year交集能够被准确区分。
* `test_strict_legacy_two_mile.py`：验证严格009a 2-mile基线恢复ZIP、类别、评分、年份、全局邻居和自身计数规则，同时保留已审核的corrected replacement类别。
* `test_strict_spatial_suite.py`：验证strict 009a剩余空间方法共用邻居池、自身排除、2024截止年份和三种固定效应注册表。
* `test_strict_two_mile_variants.py`：验证严格009a自身entry shock修正保留冻结样本，并在同样本上正确加入共同年份和严格ZIP市场年份固定效应。
* `test_two_mile_variants.py`：验证2-mile新规格排除自身entry shock、保持样本结构，并正确加入年份或市场年份固定效应。
* `test_submit_business_info_backfill.py`：验证Business Info提交清单、批量大小和成功任务续跑状态。
* `test_submit_review_collection.py`：验证评论提交清单、批量大小、成功任务重试和标识符一致性。
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
