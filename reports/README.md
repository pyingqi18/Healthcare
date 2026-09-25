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

46a至46j已经完成跨来源profile准备、资格审核结构、证据队列、原始基线冻结、优先官网审核和剩余决定表生成。正式原始人工复核基线是450条空白决定和410个review block，保存在`archive/profile_eligibility_review/original_manual_review_20260924`；583条和570条文件仅保留上游修正轨迹。46i结束时累计核实251条，其中纳入141条、排除110条。46l已经在冻结的199条剩余队列上生成完整决定，结果为76条纳入、123条排除、0条未决。该用户本地输出已经通过行数、profile key、锁定字段和五个决定字段检查，但还必须由46j的`--decisions`应用入口生成450条最终verified freeze。上述数量仍不是最终诊所数；只有资格冻结应用成功并完成物理地点审核后，才能填写最终competition location和outcome profile数量。

6. Legacy回归报告
`scripts/16_build_legacy_regression_report.py`生成的报告保存在`outputs/legacy_reproduction/corrected_v1/report`，不手工复制进reports。报告入口为`legacy_regression_report.md`，图片和精确表格分别位于同目录的`figures`和`tables`。

7. Slides英文文案
`slides_english_copy_20260925.md`依据legacy报告、历史notebook和中间结果PDF整理。它把描述性preliminary study、legacy regression comparison和未来full rebuild主回归分开，不把corrected_v1诊断结果写成最终因果结论。
