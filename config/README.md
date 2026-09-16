1. 文件夹用途
config保存研究参数、地区定义、类别规则和人工审核决定。
2. settings.yaml
保存数据目录、DataForSEO非敏感参数、面板截止年份和抓取批量。正式模型细节不再重复写在这里，只通过`analysis.contract`指向`config/final\_analysis.yaml`
3. final\_analysis.yaml
冻结完整重抓前的正式分析协议。2015至2025年分析期、2-mile上年进入冲击、竞争密度、clinic与market-year fixed effects、共同样本以及哪些空间方法属于稳健性或探索性分析。
4. pipeline.yaml
保存统一运行入口的profile、阶段顺序、输入、输出和命令。corrected\_v1\_audit可以执行；full\_rebuild在全市场抓取和最终exposure构建完成前保持blocked。
5. regions.yaml
保存当前15个研究市场的州、规模、ZIP范围、中心坐标和DataForSEO location code。这里的location code表示搜索位置，不等于商家地址一定在目标ZIP，所以抓回来的候选还要单独做ZIP资格检查
6. 类别文件
provider\_taxonomy.csv和google\_category\_rules.csv保存哪些类别属于牙科、哪些需要人工审核、哪些应排除。
7. 人工决定
candidate\_manual\_decisions\_20260908.csv保存候选资格决定。
profile\_resolution\_decisions\_20260910.csv和location\_group\_decisions\_20260910.csv保存资料排除和实体地点归并决定。
8. 修改规则
如果只是某一条人工判断需要改变，就改对应决定文件并重跑下游步骤，不直接改脚本生成的CSV。年份、主exposure、fixed effects这类研究设计改变则必须修改`final\_analysis.yaml`，同时在报告里说明为什么改变以及改变发生在看结果之前还是之后。账号和API password不属于config内容，只能放在本地环境变量里。



