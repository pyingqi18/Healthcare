1. 文件夹用途
   src保存可以被脚本和测试共同调用的正式Python模块。

2. 身份与旧数据
   identifiers.py处理名称、ZIP和clinic_key。legacy.py重建旧诊所、评论连接和entry_date。

3. 地理与面板
   geography.py计算地区资格。spatial.py计算空间资格和竞争暴露。panel.py构建年度及累计指标。
   legacy_two_mile.py只保存已冻结的legacy-compatible 2-mile exposure和entity fixed-effects复现。two_mile_variants.py保存排除自身entry shock、年份固定效应和市场年份固定效应的新规格。
   strict_legacy_two_mile.py按009a原始ZIP和关键词类别规则恢复样本，再将原2-mile邻居池、exposure和Entity FE公式应用于corrected_v1；已经过审核的corrected replacement商家类别继续保留。
   strict_two_mile_variants.py读取已冻结的strict 009a panel，依次支持排除focal clinic自身entry shock、加入共同年份固定效应和严格ZIP市场年份固定效应，并在每次比较中保持其他设置不变。
   strict_spatial_suite.py在同一strict 009a邻居池中一次构建gravity、KNN、半英里和三段圆环exposure，并统一比较三种固定效应结构。
   strict_legacy_sample_audit.py逐家诊所比较严格009a与04兼容版本的邻居池、corrected panel覆盖和回归样本差异，不修改任何模型或样本。
   legacy_distance_rings.py复现009a中的0至0.5、0.5至2、2至5 mile圆环和单独0.5-mile模型，并保留其截至2024年的年份循环。
   distance_ring_variants.py保持legacy圆环exposure和样本不变，为联合圆环与单独0.5-mile模型比较共同年份固定效应和市场年份固定效应。

4. 重新抓取
   config.py统一从环境读取DataForSEO凭据。dataforseo.py统一处理认证检查、POST任务提交和GET结果读取；parsing.py处理单个结果，result_audit.py及candidate相关模块处理搜索结果和资格审核。

5. 实体地点与评论
   duplicate_candidate_audit.py、physical_location_groups.py、location_resolution_audit.py和final_location_resolution.py处理资料到实体地点的归并。
   review_collection.py、review_result_audit.py和review_result_parsing.py处理评论任务及结果。

6. 数据替换
   replacement_audit.py核验替换边界。replacement_build.py生成corrected_v1诊所和评论表，不覆盖legacy_v1。

7. Pipeline控制
   pipeline.py读取config/pipeline.yaml，检查阶段依赖和输入，支持计划预览、范围运行、断点续跑、付费阶段双重确认，并为输入输出保存校验值和运行manifest。

8. 修改规则
   模块函数不应依赖notebook全局状态。新增逻辑需要同步增加tests中的小样本测试。
