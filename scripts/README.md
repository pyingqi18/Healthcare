1. 文件夹用途
   scripts保存正式运行入口。所有命令都在项目根目录和已激活的.venv中执行。

2. 根目录脚本
   00_prepare_legacy_data.py和00_prepare_legacy_reviews.py重建旧诊所及评论。
   00_prepare_legacy_eligibility.py计算地区和空间资格。01_build_legacy_panel.py构建年度面板。
   run_pipeline.py读取config/pipeline.yaml，默认只显示计划；只有增加--run才执行阶段。

3. scrape
   scripts/scrape保存Malone与Syracuse重新抓取、审核、替换和纠正数据构建流程。

4. audit
   scripts/audit保存旧数据只读诊断。它们不修改legacy输入。

5. 回归入口
   03_run_main_regression.py属于后续正式回归入口。04_run_legacy_2mile_reproduction.py复现legacy基线。05_compare_self_excluded_2mile.py只修正自身entry shock。06_compare_year_fixed_effects.py加入年份固定效应。07_compare_market_year_fixed_effects.py用市场年份固定效应替代共同年份固定效应。
   08_run_legacy_distance_rings.py复现009a中的三个固定距离圆环联合模型和单独0.5-mile模型，不属于正式修正版。
   09_compare_distance_rings_year_fixed_effects.py保持08生成的exposure和样本不变，只加入共同年份固定效应。
   10_compare_distance_rings_market_year_fixed_effects.py保持圆环exposure和样本不变，用市场年份固定效应替代共同年份固定效应。
   11_run_strict_legacy_2mile_corrected_data.py恢复009a原始2-mile样本筛选与最终Entity FE公式，只用corrected_v1替换错误数据和不安全身份连接。
   12_compare_strict_009a_self_exclusion.py直接读取11生成的strict panel，在相同样本和Entity FE公式下只排除focal clinic自身entry shock。
   13_compare_strict_009a_year_fixed_effects.py直接读取12生成的self-excluded strict panel，保持exposure和样本不变，只加入共同年份固定效应。
   14_compare_strict_009a_market_year_fixed_effects.py保持strict self-excluded样本不变，用009a ZIP市场年份固定效应替代共同年份固定效应。
   15_run_strict_spatial_suite.py一次运行strict 009a的gravity、KNN、半英里和三段圆环方法，并为每种方法比较Entity、Entity加Year和Entity加Market-Year固定效应。

   运行legacy复现：

   ```bash
   python scripts/04_run_legacy_2mile_reproduction.py \
     --panel "data/processed/corrected_v1/clinic_year_panel.csv" \
     --clinics "data/processed/corrected_v1/clinics_eligibility_flagged.csv" \
     --output-directory "outputs/legacy_reproduction/corrected_v1/legacy_2mile"
   ```

   输出包括exposure panel、exposure metadata、regression metadata、模型摘要和系数表。如果回归失败，exposure文件仍会保存，并生成`legacy_2mile_regression_error.json`。

   运行自身entry shock修正比较：

   ```bash
   python scripts/05_compare_self_excluded_2mile.py \
     --panel "data/processed/corrected_v1/clinic_year_panel.csv" \
     --clinics "data/processed/corrected_v1/clinics_eligibility_flagged.csv" \
     --output-directory "outputs/legacy_reproduction/corrected_v1/self_excluded_2mile"
   ```

   比较诊所固定效应与诊所加年份固定效应：

   ```bash
   python scripts/06_compare_year_fixed_effects.py \
     --panel "outputs/legacy_reproduction/corrected_v1/self_excluded_2mile/self_excluded_2mile_panel.csv" \
     --output-directory "outputs/legacy_reproduction/corrected_v1/entity_year_fe"
   ```

   比较年份固定效应与市场年份固定效应：

   ```bash
   python scripts/07_compare_market_year_fixed_effects.py \
     --panel "outputs/legacy_reproduction/corrected_v1/self_excluded_2mile/self_excluded_2mile_panel.csv" \
     --output-directory "outputs/legacy_reproduction/corrected_v1/market_year_fe"
   ```

   运行legacy固定距离圆环复现：

   ```bash
   python scripts/08_run_legacy_distance_rings.py \
     --panel "data/processed/corrected_v1/clinic_year_panel.csv" \
     --clinics "data/processed/corrected_v1/clinics_eligibility_flagged.csv" \
     --output-directory "outputs/legacy_reproduction/corrected_v1/distance_rings"
   ```

   比较legacy圆环诊所固定效应与诊所加年份固定效应：

   ```bash
   python scripts/09_compare_distance_rings_year_fixed_effects.py \
     --panel "outputs/legacy_reproduction/corrected_v1/distance_rings/legacy_distance_rings_panel.csv" \
     --output-directory "outputs/legacy_reproduction/corrected_v1/distance_rings_year_fe"
   ```

   比较圆环共同年份固定效应与市场年份固定效应：

   ```bash
   python scripts/10_compare_distance_rings_market_year_fixed_effects.py \
     --panel "outputs/legacy_reproduction/corrected_v1/distance_rings/legacy_distance_rings_panel.csv" \
     --output-directory "outputs/legacy_reproduction/corrected_v1/distance_rings_market_year_fe"
   ```

   运行严格009a 2-mile corrected-data基线：

   ```bash
   python scripts/11_run_strict_legacy_2mile_corrected_data.py \
     --panel "data/processed/corrected_v1/clinic_year_panel.csv" \
     --clinics "data/processed/corrected_v1/clinics_eligibility_flagged.csv" \
     --output-directory "outputs/legacy_reproduction/corrected_v1/strict_009a_2mile"
   ```

   在strict 009a相同样本上比较自身entry shock修正：

   ```bash
   python scripts/12_compare_strict_009a_self_exclusion.py \
     --strict-panel "outputs/legacy_reproduction/corrected_v1/strict_009a_2mile/strict_009a_2mile_panel.csv" \
     --clinics "data/processed/corrected_v1/clinics_eligibility_flagged.csv" \
     --output-directory "outputs/legacy_reproduction/corrected_v1/strict_009a_self_excluded_2mile"
   ```

   比较strict self-excluded模型的Entity FE与Entity加Year FE：

   ```bash
   python scripts/13_compare_strict_009a_year_fixed_effects.py \
     --panel "outputs/legacy_reproduction/corrected_v1/strict_009a_self_excluded_2mile/strict_009a_self_excluded_2mile_panel.csv" \
     --output-directory "outputs/legacy_reproduction/corrected_v1/strict_009a_entity_year_fe"
   ```

   比较strict共同年份固定效应与严格ZIP市场年份固定效应：

   ```bash
   python scripts/14_compare_strict_009a_market_year_fixed_effects.py \
     --panel "outputs/legacy_reproduction/corrected_v1/strict_009a_self_excluded_2mile/strict_009a_self_excluded_2mile_panel.csv" \
     --clinics "data/processed/corrected_v1/clinics_eligibility_flagged.csv" \
     --output-directory "outputs/legacy_reproduction/corrected_v1/strict_009a_market_year_fe"
   ```

   一次运行strict剩余空间方法：

   ```bash
   python scripts/15_run_strict_spatial_suite.py \
     --panel "data/processed/corrected_v1/clinic_year_panel.csv" \
     --clinics "data/processed/corrected_v1/clinics_eligibility_flagged.csv" \
     --output-directory "outputs/legacy_reproduction/corrected_v1/strict_spatial_suite"
   ```

6. 统一pipeline入口
   当前可执行profile为corrected_v1_audit，用于一次运行已冻结的严格009a审计链。先预览计划：

   ```bash
   python scripts/run_pipeline.py --profile corrected_v1_audit
   ```

   确认输入路径后执行：

   ```bash
   python scripts/run_pipeline.py --profile corrected_v1_audit --run
   ```

   已有完整输出时断点续跑：

   ```bash
   python scripts/run_pipeline.py --profile corrected_v1_audit --run --resume
   ```

   可以用--from-stage和--to-stage选择连续阶段。每次执行在outputs/pipeline_runs下保存run_manifest.json，记录配置、命令、阶段状态及文件SHA-256。
   full_rebuild当前明确阻塞，因为抓取脚本仍包含Malone/Syracuse批次路径、固定任务数和替换总数。正式分析协议已冻结在config/final_analysis.yaml，但统一抓取和最终exposure尚未实现，因此该profile仍不能执行。
   未来付费阶段必须同时使用--run和--confirm-paid STAGE_ID；pipeline不会在计划模式或普通运行中自动提交付费任务。

7. 修改规则
   脚本只负责读取参数、调用src函数和写出结果。可复用的数据逻辑应放入src/medical_ratings。
