1. 文件夹用途
data保存研究输入、中间结果和正式冻结数据。实际数据不提交到Git。
2. legacy
data/legacy保存旧流程产生的原始诊所、评论、时间线、NLP和面板文件。只作为历史输入，不直接修改。
3. raw
data/raw保存DataForSEO任务日志和原始JSON。目录按run name划分，文件按task ID追踪。
4. interim
data/interim保存解析表、审计表、候选审核表和profile到地点的crosswalk等中间文件。这些文件由脚本生成，不手动修改。人工决定写在`config/`，然后由脚本重新应用。
阶段46l的`profile_eligibility_remaining_decisions_completed.csv`与`profile_eligibility_completion_final_summary.json`由用户本地运行生成，继续保存在`data/interim/full_market_plan_v2/profile_eligibility_completion/`，不提交Git。它们必须先经过46j应用验证，生成450条verified freeze后，才能进入物理地点审核。
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


