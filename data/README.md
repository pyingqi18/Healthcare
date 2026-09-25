1. 文件夹用途
data保存研究输入、中间结果和正式冻结数据。实际数据不提交到Git。
2. legacy
data/legacy保存旧流程产生的原始诊所、评论、时间线、NLP和面板文件。只作为历史输入，不直接修改。
3. raw
data/raw保存DataForSEO任务日志和原始JSON。目录按run name划分，文件按task ID追踪。
4. interim
data/interim保存解析表、审计表、候选审核表和profile到地点的crosswalk等中间文件。这些文件由脚本生成，不手动修改。人工决定写在`config/`，然后由脚本重新应用。
阶段46l的完成表以及从中提取的`remaining_profile_verified_additions.csv`由用户本地运行生成，保存在`data/interim/full_market_plan_v2/profile_eligibility_completion/`，不提交Git。阶段46m把版本化的251条基线与199条additions严格合并为450条最终资格冻结，并在`data/interim/full_market_plan_v2/profile_eligibility_final_application/`生成46a兼容决定表和物理地点审核文件。该目录仍是用户本地派生数据，不提交Git。

阶段46n读取46m的`physical_location_block_triage.csv`和`physical_location_block_profiles.csv`，在`data/interim/full_market_plan_v2/physical_location_policy_review/`生成唯一政策决定表、576块集中人工队列、对应profile明细和prepare summary。所有manual字段保持空白，真实输出仍由用户本地运行生成。

阶段46o不再要求继续人工审核576块。它在`data/interim/full_market_plan_v2/physical_location_final_freeze/`生成主口径profile到competition location crosswalk、22299个主口径地点、20762个地址合并敏感性地点和final freeze summary。主口径对576个歧义块保留逐profile地点，敏感性口径按当前同址块合并。
5. processed
data/processed保存可以进入面板和分析的冻结数据。
legacy\_v1        旧数据经过安全身份连接后的重建基线
corrected\_v1     替换Malone和Syracuse错误批次后的审计版本
full\_rebuild\_v1  未来全部市场统一重抓后生成的正式候选版本
当前`corrected\_v1`的主要输入是：
data/processed/corrected\_v1/clinics\_eligibility\_flagged.csv
data/processed/corrected\_v1/reviews\_eligibility\_flagged.csv
data/processed/corrected\_v1/clinic\_year\_panel.csv
`corrected\_v1`有5674家诊所、761007条评论和37474个clinic-year。它可以用于审计和模型开发，但因为13个市场仍主要来自legacy抓取，所以不能改名成最终数据。
6. external
data/external保存NPPES等外部数据。需要记录来源、下载日期和版本。

7. full rebuild评论数据
阶段47a在`data/interim/full_market_plan_v2/outcome_profile_review_collection/`生成29550个outcome profile的评论manifest、采集前coverage表和费用summary。阶段47b在`data/interim/full_market_plan_v2/existing_review_reuse_audit/`核对corrected_v1旧评论，只对稳定身份且覆盖完整的profile生成安全复用记录，并输出`reduced_outcome_profile_review_manifest.csv`。付费提交只能使用这个减量清单。付费任务日志与原始JSON保存在`data/raw/full_market_plan_v2/outcome_profile_reviews/`，避免与Malone和Syracuse历史修复批次混用。解析后的逐条评论和零评论profile表是用户本地派生数据，不提交Git。

阶段47c在`data/interim/full_market_plan_v2/enhanced_legacy_review_reuse_audit/`逐行合并legacy与replacement日期、评分和review key字段，并对完整地址一致的唯一身份候选生成增强复用结果。47c运行后，任何付费提交必须改用`enhanced_reduced_outcome_profile_review_manifest.csv`。
