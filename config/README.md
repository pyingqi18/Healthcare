1. 文件夹用途
   config保存研究参数、地区定义、类别规则和人工审核决定。

2. settings.yaml
   保存数据路径、年份范围、抓取批量和非敏感运行参数。不得写入账号或API password。

3. regions.yaml
   保存15个研究地区的ZIP范围、中心坐标和DataForSEO location code。

4. 类别文件
   provider_taxonomy.csv和google_category_rules.csv定义牙科类别及候选处理规则。

5. 人工决定
   candidate_manual_decisions_20260908.csv保存候选资格决定。
   profile_resolution_decisions_20260910.csv和location_group_decisions_20260910.csv保存资料排除和实体地点归并决定。

6. 修改规则
   需要改变人工判断时修改决定文件，再重跑下游脚本。不要直接修改脚本生成的审核结果。
