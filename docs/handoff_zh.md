1. 当前正式数据
   data/processed/legacy_v1保存旧数据安全重建基线，共5778家诊所和769515条评论。
   data/processed/corrected_v1保存当前纠正版本，共5674家诊所和761007条评论。Malone和Syracuse的错误location code批次已经替换。

2. 当前资格结果
   地区合格诊所5663家、评论760555条。空间合格诊所5605家、评论750122条。
   28个新地点本次观测到零条评论，因此缺少entry_date并保留在诊所表中，但不能进入需要明确进入年份的面板。

3. 当前下一步
   使用corrected_v1资格表重新生成2008至2025年年度面板。
   必须核验clinic-year唯一性、评论数量守恒、2026年排除数量、entry_date缺失和空间资格传递。

4. 回归开始条件
   面板真实数据测试全部通过后，冻结样本、变量字典和主规格。
   主结果暂定为clinic fixed effects与market-by-year fixed effects，并按clinic聚类。log_votes_dynamic默认不进入主规格。
   NLP、category split、event study、review inactivity和strong competitor放入稳健性或探索性分析。

5. 全市场重新抓取
   当前53组关键词和Local Finder、Maps组合造成严重多抓，不能直接扩展到其他市场。
   全市场抓取前按search_scope_revision.md测试Business Listings Search和单关键词分层发现，并在评论抓取前完成CID去重、ZIP确认、类别审核和实体地点归并。

6. 代码边界
   archive和notebooks用于历史追溯。src保存公共逻辑，scripts保存运行入口，config保存参数和人工决定，tests保存验证。
   新代码和注释使用英文。阶段统计和研究决定记录在reports/整理内容.md。
