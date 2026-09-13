1. 文件夹用途
   src保存可以被脚本和测试共同调用的正式Python模块。

2. 身份与旧数据
   identifiers.py处理名称、ZIP和clinic_key。legacy.py重建旧诊所、评论连接和entry_date。

3. 地理与面板
   geography.py计算地区资格。spatial.py计算空间资格和竞争暴露。panel.py构建年度及累计指标。

4. 重新抓取
   dataforseo.py处理API请求。parsing.py处理单个结果。result_audit.py及candidate相关模块处理搜索结果和资格审核。

5. 实体地点与评论
   duplicate_candidate_audit.py、physical_location_groups.py、location_resolution_audit.py和final_location_resolution.py处理资料到实体地点的归并。
   review_collection.py、review_result_audit.py和review_result_parsing.py处理评论任务及结果。

6. 数据替换
   replacement_audit.py核验替换边界。replacement_build.py生成corrected_v1诊所和评论表，不覆盖legacy_v1。

7. 修改规则
   模块函数不应依赖notebook全局状态。新增逻辑需要同步增加tests中的小样本测试。
