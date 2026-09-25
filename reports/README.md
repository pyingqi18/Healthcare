1. 文件夹用途
reports保存项目阶段记录和无法仅从代码看出的数据结论。
2. 整理内容.md
按处理顺序记录旧数据审计、错误修复、重新抓取、人工审核、评论解析和数据替换结果。
3. 记录要求
每个阶段记录输入数量、输出数量、排除数量、异常数量、关键决定和下一步。
4. 文件边界
行级数据和自动生成诊断不放在reports。它们分别保存在data和outputs。
5. 当前进度
整理内容.md已记录41a至44a的完整状态审核。44a实际应用后为3525个当前参考地点、来源联合发现3398个、召回率96.40%、剩余127个，15个市场全部达到90%门槛。45a负责冻结这套发现基准并正式取消75项条件性剩余关键词任务；下一阶段仍需完成跨来源profile与物理竞争地点归并。原冻结断点见`scrape_freeze_20260919.md`。

46a至46h已经完成跨来源profile准备、资格审核结构、外部证据队列、共享domain逐profile审核、原始基线冻结和剩余单例排序。正式原始人工复核基线是450条空白决定和410个review block，保存在`archive/profile_eligibility_review/original_manual_review_20260924`；583条和570条文件仅保留上游修正轨迹。共享domain审核已逐地址完成49条profile，并把冻结决定从163条增加到212条，其中累计纳入121条、排除91条，还剩238条未完成。46h确认这238条全部是单例，并把39条具有具体官网服务、地点或医生页面的记录放入第一审核批次。第8版163条和第9版212条均为进度快照。上述数量仍不是最终诊所数；只有450条资格决定完成并经过物理地点审核后，才能填写最终competition location和outcome profile数量。

6. Legacy回归报告
`scripts/16_build_legacy_regression_report.py`生成的报告保存在`outputs/legacy_reproduction/corrected_v1/report`，不手工复制进reports。报告入口为`legacy_regression_report.md`，图片和精确表格分别位于同目录的`figures`和`tables`。
