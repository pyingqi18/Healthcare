1. 文件夹用途
   scripts保存正式运行入口。所有命令都在项目根目录和已激活的.venv中执行。

2. 根目录脚本
   00_prepare_legacy_data.py和00_prepare_legacy_reviews.py重建旧诊所及评论。
   00_prepare_legacy_eligibility.py计算地区和空间资格。01_build_legacy_panel.py构建年度面板。

3. scrape
   scripts/scrape保存Malone与Syracuse重新抓取、审核、替换和纠正数据构建流程。

4. audit
   scripts/audit保存旧数据只读诊断。它们不修改legacy输入。

5. 回归入口
   03_run_main_regression.py属于后续回归入口。纠正面板完成并验证前不要运行。

6. 修改规则
   脚本只负责读取参数、调用src函数和写出结果。可复用的数据逻辑应放入src/medical_ratings。
