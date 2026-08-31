# 整理交接说明

本项目已经按照时间和研究阶段重新组织。`archive` 保存脱敏后的历史版本，`src` 保存可维护的共用代码，`scripts` 提供独立入口，`config` 保存全局参数。

正式使用前应先完成四件事：

1. 更换 DataForSEO 凭据。
2. 冻结 clinic-location identity crosswalk。
3. 明确 entry date、exit、strong competitor 和 market radius 的定义。
4. 指定唯一的 main specification。

建议主结果暂定为 clinic fixed effects 加 market-by-year fixed effects，并对 clinic 聚类。`log_votes_dynamic` 默认不进入主规格。当前 NLP、category split、event study、review inactivity 和 strong competitor 分支应归为 robustness 或 exploratory analysis。

历史 notebook 中仍保留部分原始中文注释，目的是忠实保存研究演化。所有新增的 active Python code 和代码注释均使用英文。
