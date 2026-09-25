回归历史参考

`006`是早期cross section OLS和Logit。`008`开始加入诊所固定效应。`009a`至`013`又加入不同距离、市场年份固定效应、NLP outcome和event study。
notebook之间的样本、年份、控制变量和固定效应并不统一，所以系数不能直接横向排序。
04至15号正式脚本已经把关键方法分开复现。最终主规格写在`config/final_analysis.yaml`，正式入口仍是待改造的`scripts/03_run_main_regression.py`。在统一全市场数据和最终exposure完成前，不把任何历史notebook结果叫作主结果。

`scripts/16_build_legacy_regression_report.py`整理04至15的现有结果，并复现旧notebook中有明确解释价值的评分、地域、城市规模、entry group和回归系数图。它不执行新的模型选择；旧notebook中大量逐市场重复图不会原样复制，精确数值以生成报告目录中的CSV表为准。
