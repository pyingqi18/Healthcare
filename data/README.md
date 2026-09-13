1. 文件夹用途
   data保存研究输入、中间结果和正式冻结数据。实际数据不提交到Git。

2. legacy
   data/legacy保存旧流程产生的原始诊所、评论、时间线、NLP和面板文件。只作为历史输入，不直接修改。

3. raw
   data/raw保存DataForSEO任务日志和原始JSON。原始结果按run name和task_id保存，必须另行备份。

4. interim
   data/interim保存解析表、审计表、候选审核表和实体地点整理结果。这些文件由脚本生成，不手动修改。

5. processed
   data/processed保存可以进入面板和分析的冻结数据。
   legacy_v1是旧数据安全重建基线。corrected_v1是替换Malone与Syracuse错误批次后的当前正式版本。

6. external
   data/external保存NPPES等外部数据。需要记录来源、下载日期和版本。

7. 当前正式输入
   纠正后诊所表为data/processed/corrected_v1/clinics_eligibility_flagged.csv。
   纠正后评论表为data/processed/corrected_v1/reviews_eligibility_flagged.csv。
