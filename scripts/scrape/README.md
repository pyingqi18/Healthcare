1. 文件夹用途
   scripts/scrape负责Malone和Syracuse两个错误地区的诊所重新发现、地点核实、评论抓取和结果解析。
   历史修复批次名称为rescrape_malone_syracuse_20260907。所有脚本都应在项目根目录运行。
   该批次继续作为历史修复记录。未来批次不得依赖旧两地任务数量。

2. 诊所搜索
   00生成搜索任务，01提交付费任务，02检查认证，03抽查任务结果，04下载原始JSON。
   05至09审计和解析搜索结果，按CID合并重复观测，并标记地理和类别资格。
   本批次共解析13213条搜索观测，得到1120个唯一CID。

3. 补充地点资料
   10至14为缺少地理信息的769个CID补抓Business Info，并将地址、ZIP、坐标、类别和place_id合并回候选表。
   769个任务全部完成。1120个候选中最终确认231个位于目标ZIP。

4. 候选资格审核
   15应用人工类别和地理决定。最终保留187个符合牙科和地理资格的Google商家资料，未解决候选为0。
   人工决定保存在config/candidate_manual_decisions_20260908.csv。需要改变判断时修改该文件，再运行15及后续脚本。

5. 实体地点整理
   16生成可能重复的商家资料对，17建立建议地点组，18审计异常资料和跨组地点，19应用人工决定。
   10个异常资料被排除，177个资料最终归并为109个实体牙科地点，其中Malone 8个，Syracuse 101个。
   资料和地点决定保存在config/profile_resolution_decisions_20260910.csv及config/location_group_decisions_20260910.csv。

6. 评论任务
   20为109个实体地点规划评论抓取。21提交付费任务，22下载原始JSON，23进行完整性审计，24解析评论。
   109份原始JSON已全部下载。81个地点返回14310条评论，28个地点本次观测到零条评论。
   14310个review_id全部存在且唯一，评论时间和评分全部有效，没有需要增加抓取深度的任务。

7. 文件位置
   任务日志和原始JSON保存在data/raw/rescrape_malone_syracuse_20260907。
   解析表、审核表和最终结果保存在data/interim/rescrape_malone_syracuse_20260907。
   当前评论结果为reviews_parsed.csv、zero_review_locations.csv和review_parsing_summary.json。

8. 账号和费用
   01、11和21会提交付费任务，不能在没有确认任务日志的情况下重复运行。
   01至04、11、12、21和22统一通过config.require_dataforseo_credentials读取DATAFORSEO_LOGIN和DATAFORSEO_PASSWORD。
   所有HTTP请求统一经过DataForSEOClient；提交使用POST，结果读取使用GET。凭据不写入settings.yaml、代码或任务日志，也不再通过脚本交互输入。
   01、11和21先读取实际manifest及已有task log，再打印本次剩余任务所需的精确确认文本。例如还剩17个Business Info任务时，确认文本为SUBMIT_17_PAID_BUSINESS_INFO_TASKS。
   未提供精确文本时只做验证，不提交任务。剩余任务为0时不会读取凭据或发送请求。

9. 不应手动修改的文件
   原始JSON、任务日志以及脚本生成的CSV和JSON不应手动修改。
   需要修正人工判断时，应修改config中的决定文件，再重新运行对应脚本。
   data/raw和data/interim不提交到Git，但原始JSON和任务日志必须另外备份。

10. 多抓问题
    本次为保持旧数据口径，沿用了53组关键词和两个搜索接口，因此产生大量目标ZIP外候选。
    1120个CID中只有231个位于目标ZIP，最终只有187个资料通过牙科和地理资格审核。
    全市场重抓前应按docs/search_scope_revision.md精简关键词，并先完成CID去重、ZIP确认、类别审核和实体地点归并，再提交评论任务。

11. 通用化进度
    00不再默认选择Malone和Syracuse，运行时必须通过--target-regions明确指定地区。
    01的地点搜索确认数、11至13的Business Info任务数、21至24的评论任务数均由当前manifest、task log或audit文件推导。
    212、769和109仅保留在历史结果说明和测试样本名称中，不再控制未来批次能否执行。

12. 尚未完成的通用化
    00、01及03至24现在统一要求--run-name，并自动使用data/raw/<run_name>和data/interim/<run_name>。--raw-root、--interim-root及各脚本原有的单文件路径参数可以覆盖默认位置。
    run name只允许字母、数字、点、下划线和连字符，不允许斜杠、反斜杠、空格或..，防止输出逃逸到其他目录。
    15的candidate decisions以及19的profile和location decisions必须显式传入，新批次不会默认套用Malone与Syracuse的人工判断。
    25和26是corrected_v1历史替换专用脚本，其中旧location code、5674家诊所和761007条评论属于冻结审计边界，不应直接改造成全市场重抓逻辑。
    下一步为原15个市场建立只规划、不付费的抓取profile，冻结关键词、市场范围和费用估算。完整重抓仍不执行。

13. 原15市场搜索规划
    config/scrape_plans.yaml列出regions.yaml中的15个原市场。00a只生成search_profile_plan.csv和search_profile_summary.json，不读取凭据、不提交任务。
    旧方案作为对照保留：每个市场53组关键词组合乘Maps和Local Finder，共106项；15个市场共1590项。它不再是新抓取的默认方案。
    新方案先在Malone和Syracuse验证Business Listings，因为这两个市场已有人工审核后的CID参考集。15市场rollout、两个核心单关键词以及五个专科单关键词均保持conditional_not_approved。
    运行规划：

    ```bash
    python scripts/scrape/00a_plan_search_profile.py \
      --run-name full_market_plan_v1
    ```

    价格来自2026-09-18核验的DataForSEO公开价格页，只用于预算。正式提交前必须重新核验价格。Business Listings费用同时包含每次请求费用和实际返回item费用，因此规划表给出最低值和按每次最多1000 items计算的上限。

14. Business Listings两市场试验设计
    官方接口每次最多允许10个categories。研究规则包含13个include类别，因此每个市场必须拆成2次请求，Malone与Syracuse合计4次。上一阶段按每市场1次计算的2次请求不完整，不能执行。
    config/business_listings_dental_categories.csv来自2026-09-01官方类别快照。`Oral and maxillofacial surgeon`的接口名称为`oral_maxillofacial_surgeon`，不能从展示名称机械转换。
    Malone暂定5 km半径，Syracuse暂定15 km半径。它们用于覆盖当前corrected reference，不直接定义最终ZIP市场。00b会逐家检查reference clinic是否位于圆内。
    运行离线规划：

    ```bash
    python scripts/scrape/00b_plan_business_listings_pilot.py \
      --run-name full_market_plan_v1
    ```

    预期生成4行pilot manifest、109行reference coverage和1份summary。summary必须继续显示ready_for_paid_execution=false。

15. Business Listings执行代码状态
    01a读取00b生成的四行manifest。没有精确确认文本时只打印剩余请求数，不读取账号密码，也不调用API。首次执行需要的文本固定由程序计算为SUBMIT_4_PAID_BUSINESS_LISTINGS_REQUESTS；断点续跑时数字改为实际剩余请求数。
    收到Live响应后，01a先将完整JSON原子写入data/raw/<run-name>/business_listings_pilot/raw，再记录tag、参数哈希、费用、返回数量和时间。已完成tag不会重复提交。
    02a只读取已保存的四份结果，生成保留全部类别观测的business_listings_pilot_observations.csv，以及按CID或place_id合并后的business_listings_pilot_candidates.csv。它不调用API。
    当前先运行测试和01a验证模式，不提供confirm-submit。完成离线验证前不得提交四次付费请求。

    ```bash
    python -m pytest \
      tests/test_business_listings_pilot.py \
      tests/test_business_listings_live.py \
      tests/test_scrape_safety.py \
      tests/test_dataforseo_search.py -q

    python scripts/scrape/01a_run_business_listings_pilot.py \
      --run-name full_market_plan_v2
    ```

    第二条命令不得附加--confirm-submit。预期输出credentials_read=false、api_requests_submitted=0，并显示SUBMIT_4_PAID_BUSINESS_LISTINGS_REQUESTS。
    付费分支结束后必须再输出execution_completed=true、credentials_read=true、实际api_requests_submitted、实际api_cost_usd和剩余请求数。缺少这份结束摘要时不得把试验记为完成。
    如果raw JSON已经存在但result log没有completed记录，01a会停止，不会自动重交这一项。此状态可能代表请求已经收费但日志写入中断，必须先审计原始文件。

16. Business Listings试验比较
    03a同时读取493个唯一profile候选、四请求result log和corrected_v1竞争单位crosswalk。它先用normalize_zip处理ZIP+4等九位字符串，再按实际ZIP和主类别保留全部资格状态。
    旧实体地点匹配规则固定为同市场且目标ZIP内，并满足完全一致的标准化地址、相同电话且100米内，或10米内且名称相似度至少为0.8三者之一。只有10米坐标而没有身份佐证的pair会保留供审核，但不自动计为已发现。召回率以是否发现profile计算；主类别需要人工审核的profile不会被静默删除，另行报告provisional-include召回率。
    03a不执行profile合并、不生成最终实体地点，也不调用API。输出包括候选资格、109个参考地点逐项结果、全部匹配证据、分市场召回率和总摘要。

    ```bash
    python -m pytest \
      tests/test_business_listings_comparison.py \
      tests/test_business_listings_live.py -q

    python scripts/scrape/03a_audit_business_listings_pilot.py \
      --run-name full_market_plan_v2
    ```

    04a读取03a的资格、参考匹配和匹配对输出，再应用两份带证据的人工决定。它把当前竞争地点、可作为评分结果的profile和历史面板保留资格分开处理，不调用API，也不自动合并地点：

    ```bash
    python -m pytest tests/test_business_listings_manual_audit.py -q

    python scripts/scrape/04a_apply_business_listings_pilot_manual_audit.py \
      --run-name full_market_plan_v2
    ```

17. Business Listings地点审核block
    05a只读取04a已裁决的competition candidates，并复用现有重复pair和地点分组函数。输出中的physical_location_group是临时审核block；共享地址可能容纳多家独立诊所，连通关系也可能通过中间profile形成链，因此不得直接把block数量写成最终诊所数量。

    ```bash
    python -m pytest tests/test_business_listings_location_audit.py -q

    python scripts/scrape/05a_audit_business_listings_location_blocks.py \
      --run-name full_market_plan_v2
    ```

    输出包括business_listings_location_review_pairs.csv、business_listings_location_review_blocks.csv和business_listings_location_audit_summary.json。该步骤不调用API、不应用旧location决定文件，也不自动合并任何profile。

18. Business Listings地点block分档
    06a将49个多profile block压缩成一行一个block的人工审核清单。分档使用基础地址数量、组内最大坐标跨度、电话与domain覆盖、organization profile数量和强连接图密度。routine_shared_identity只表示证据整齐，仍需人工确认；focused_review和complex_review优先检查。

    ```bash
    python -m pytest tests/test_business_listings_location_triage.py -q

    python scripts/scrape/06a_triage_business_listings_location_blocks.py \
      --run-name full_market_plan_v2
    ```

    输出包括一行一个block的business_listings_location_block_triage.csv、按分档排序的business_listings_location_profiles_by_tier.csv和汇总JSON。该步骤不调用API，不写最终location ID，不执行合并。

19. Business Listings竞争地点定案
    07a把竞争地点和评分profile拆成两张crosswalk。94个singleton各自成为一个竞争地点；35个routine block按06a已经冻结的强证据规则接受为一个地点；14个complex或focused block必须在config/business_listings_pilot_location_decisions_20260919.csv中逐项有决定。

    ```bash
    python -m pytest tests/test_business_listings_location_resolution.py -q

    python scripts/scrape/07a_apply_business_listings_location_resolution.py \
      --run-name full_market_plan_v2
    ```

    竞争地点crosswalk允许多个profile指向同一个competition_location_id，用于避免把同一诊所的医生主页重复算成竞争者。outcome crosswalk始终令outcome_entity_id等于原clinic_key，不拼接、不平均也不覆盖rating历史。Hybridge的validated legacy carry-forward尚未在本步加入。

20. 两市场最终竞争地点清单
    08a将143个Business Listings地点与人工验证的Hybridge旧地点合并。carry-forward必须正好覆盖adjudicated references中retain_current且未发现的地点；如果其标准化地址与新地点相同，或同市场坐标在10米内，程序停止，防止重复计数。

    ```bash
    python -m pytest tests/test_business_listings_competition_universe.py -q

    python scripts/scrape/08a_build_business_listings_competition_universe.py \
      --run-name full_market_plan_v2
    ```

    Hybridge进入当前竞争地点清单并继续保留历史面板资格，但没有被本次Business Listings发现，因此不新增Business Listings outcome profile。其当前官网电话为315-888-5682，替代旧crosswalk中的315-888-4334；坐标继续使用corrected_v1已经审计的坐标。

21. Business Listings已保存响应分页检查
    09a读取付费阶段已经保存的原始JSON，逐页核对total_count、实际返回条数和offset token，并将同一市场、同一类别组的全部offset页合并检查。早期页显示仍有后续结果不等于整个类别组仍不完整，最终判断以offset区间是否从0连续覆盖到total_count为准。它不读取账号密码、不调用API，也不自动提交续页。

    ```bash
    python -m pytest tests/test_business_listings_live.py -q

    python scripts/scrape/09a_audit_business_listings_pagination.py \
      --run-name full_market_plan_v2
    ```

    输出包括逐页的business_listings_page_completeness.csv和按类别组汇总的business_listings_group_completeness.csv。如果all_saved_category_groups_complete为false，再根据不完整类别组规划续页和费用。15市场rollout不能默认每个类别组只有一页。

22. Business Listings剩余市场分阶段规划
    10a保留原15个研究市场。Malone和Syracuse已经完成，不重复规划；Atlanta作为下一项大型市场验证；纽约和洛杉矶保留在专项审核阶段；其余10个市场只有在Atlanta验证后才进入条件rollout。

    ```bash
    python -m pytest tests/test_business_listings_rollout.py -q

    python scripts/scrape/10a_plan_business_listings_rollout.py \
      --run-name full_market_plan_v2
    ```

    本步只生成26项第一页规划，不读取账号密码，也不允许提交。半径检查先按regions.yaml的实际ZIP规则排除旧数据中的跨市场记录，再核对已知corrected_v1参考地点。它不能证明ZIP区域中从未出现于旧数据的角落已经被覆盖。

23. 分阶段Business Listings付费入口
    11a读取10a生成的26项冻结计划。large_market_validation必须正好包含Atlanta的2项第一页请求。Atlanta完成后，standard_rollout还必须读取修正ZIP口径的比较摘要；只有Atlanta召回率至少为90%、决定为approve_as_primary或maps_supplement_required且397个分母与reference universe一致时，才允许一次选择10个普通市场的20项第一页请求。

    第一次只运行验证：

    ```bash
    python scripts/scrape/11a_run_business_listings_rollout_stage.py \
      --run-name full_market_plan_v2 \
      --stage large_market_validation
    ```

    验证输出会给出当次精确确认文本。确认后再次运行并加入confirm-submit。程序保存完整原始JSON、逐请求费用、total_count和是否需要续页；即使第一页不完整，也不会自动提交续页。

    Atlanta比较通过后，普通市场批量入口为：

    ```bash
    python scripts/scrape/11a_run_business_listings_rollout_stage.py \
      --run-name full_market_plan_v2 \
      --stage standard_rollout
    ```

    首次运行只验证20项请求并给出批量市场、最低费用、理论最高费用和精确确认文本，不读取账号密码、不提交请求。纽约和洛杉矶不包含在该批次中。付费运行只有在Live响应顶层和task状态均为20000、任务数与错误数正确、result结构完整且count等于items数量时才保存为completed；其他状态记录failed并停止批次。第一页执行器允许共享result log中存在由已知p01标签派生的p02及以后续页，但这些续页不会被误算为第一页完成记录；无法追溯到冻结p01计划的标签继续报错。

    普通市场完成后，同一入口允许major_metro_review，但它只是纽约和洛杉矶的四项第一页探测：

    ```bash
    python scripts/scrape/11a_run_business_listings_rollout_stage.py \
      --run-name full_market_plan_v2 \
      --stage major_metro_review
    ```

    运行前会重新核对corrected legacy参考地点是否全部位于纽约45公里和洛杉矶75公里冻结半径内，并使用单独的MAJOR_METRO付费确认文本。即使第一页报告更多结果，本步也不会自动续页。先读取两地两个类别组的total_count，再决定使用numeric offset、offset token，还是改用更精细的地理切片，避免直接对超大圆形范围盲目翻页。

24. Atlanta审计后续页
    12a读取09a的分页完整性结果。当前Atlanta第一类别组total_count为3640，第一页已经保存1000条，程序据此冻结offset 1000、2000和3000三项续页。第二类别组482条已经完整，不进入续页。

    第一次只运行验证：

    ```bash
    python scripts/scrape/12a_run_business_listings_continuations.py \
      --run-name full_market_plan_v2
    ```

    三项续页预计返回1000、1000和640条，按当前价格预计新增费用0.9864美元。程序拒绝超过10000条的numeric offset计划，不自动增加第四项续页，并在每页记录total_count是否漂移。

    普通市场批量完成后，再次运行09a会同时审计Atlanta既有完整页和10个普通市场第一页。12a按整个市场类别组的连续offset覆盖判断是否需要续页，已经完整的Atlanta不会再次进入计划。当前普通市场预计只规划Buffalo g01的offset 1000，以及SanFrancisco g01的offset 1000和2000。

25. Atlanta完整分页解析
    13a只接受分页分组审计已经完整的市场。Atlanta必须有2个完整类别组和5个完成页。程序逐页核对原始JSON与result log中的item_count，再按CID或place_id跨页、跨类别去重。它不读取凭据，也不调用API。

    ```bash
    python scripts/scrape/13a_parse_business_listings_rollout_market.py \
      --run-name full_market_plan_v2 \
      --market Atlanta_GA_L
    ```

    输出包括原始解析观测、唯一profile候选和解析摘要。本步只建立Atlanta候选profile，还没有执行目标ZIP筛选、类别审核、物理地点合并或与corrected legacy参考样本比较。

26. Atlanta候选资格与corrected legacy覆盖比较
    14a在一次无费用运行中完成目标ZIP筛选、Google主类别初审和corrected legacy参考地点匹配。它保留pilot已经冻结的规则，不为Atlanta重新选择距离或recall门槛。

    ```bash
    python scripts/scrape/14a_audit_business_listings_rollout_market.py \
      --run-name full_market_plan_v2 \
      --market Atlanta_GA_L
    ```

    Atlanta旧crosswalk先按competition_unit_id折叠为物理竞争地点，再按实际ZIP区分目标区内、目标区外和缺ZIP地点。召回率分母只保留目标ZIP内旧地点，然后使用标准化地址相同、电话相同且在100米内，或10米内且名称相似度至少为0.8进行匹配。只有坐标在10米内但缺少身份佐证的记录只进入审核，不计入召回率。输出中的新profile数量仍不能解释为新物理诊所数量，后续需要对目标ZIP内的合格profile做共址审核。

27. 普通市场批量解析
    15a从共享result log中选择standard_rollout的10个市场。运行前要求每个市场的两个类别组均通过09a分页审计，并要求完成日志中的页数与审计页数一致。程序逐市场解析并去重，因此同一profile即使出现在相邻市场，也不会在解析阶段被错误地跨市场合并。它不读取凭据，也不调用API。

    ```bash
    python -m pytest tests/test_business_listings_stage_parse.py -q

    python scripts/scrape/15a_parse_business_listings_rollout_stage.py \
      --run-name full_market_plan_v2 \
      --stage standard_rollout
    ```

    每个市场保留独立的observations、candidates和summary。stage目录另存10个市场合并后的观测表、候选表和逐市场汇总表。这里的unique profile仍是市场内Google资料身份，不是最终物理竞争地点，也没有执行目标ZIP资格和legacy召回率比较。

28. 普通市场批量资格与召回率审计
    16a读取15a生成的10市场候选表，逐市场执行目标ZIP分类、Google主类别初审、corrected legacy competition unit参考折叠和分层身份匹配。真正没有邮编的候选保留为maps_missing_zip；加拿大邮编标为non_us_postal并归入目标ZIP外，无法识别的非空邮编另标为unrecognized_postal，不再把三者混在一起。每个市场单独保存审核证据，stage总表按参考地点数量计算加权整体召回率，不对大小市场的召回率做简单平均。

    ```bash
    python -m pytest tests/test_business_listings_stage_comparison.py -q

    python scripts/scrape/16a_audit_business_listings_rollout_stage.py \
      --run-name full_market_plan_v2 \
      --stage standard_rollout
    ```

    本步不调用API，也不把新增profile自动解释为新物理地点。输出的approve_as_primary、maps_supplement_required或reject_or_redesign只描述相对legacy参考集的覆盖表现，不再决定主补抓选择哪些市场；目标ZIP内候选仍需地点归并，未匹配legacy参考地点仍需证据审核。

29. Maps补抓与未匹配legacy地点核验规划
    17a把主发现补抓和legacy核验彻底分开。主发现直接读取冻结的15市场配置，不再从某个rollout阶段或legacy召回率挑市场；15个市场统一生成dentist和dental clinic两项核心任务，共30项，并单独形成可付费执行的manifest。standard rollout的未匹配legacy地点仍按名称和地址形成核验清单，但该清单不进入主发现manifest，也不能用于构造最终统一抓取样本。程序只计算计划、证据分档和费用，不读取凭据、不提交任务。

    ```bash
    python -m pytest tests/test_rollout_maps_supplement_plan.py -q

    python scripts/scrape/17a_plan_rollout_maps_supplement.py \
      --run-name full_market_plan_v2 \
      --stage standard_rollout
    ```

    recall gap中的close_identity_review和possible_relocation_or_coordinate_shift只是legacy核验优先级，不会自动改写匹配结果，也不会进入主发现manifest。缺ZIP表现在只保留原始邮编确实为空的候选。Google Maps Standard Queue当前配置按每个最多100条结果的SERP页0.0006美元估算，正式提交前仍需再次核对manifest、费用和精确确认文本。

30. 统一Maps Standard补抓提交与下载
    18a只接受冻结配置中的15个市场、每市场两个核心关键词和共30项主发现任务。legacy核验任务、少于或多于30项、遗漏Atlanta等任一市场以及市场任务数不一致都会被拒绝。30项任务使用一次批量POST提交，验证模式不读取凭据。

    ```bash
    python -m pytest tests/test_dataforseo_search.py tests/test_rollout_maps_standard_execution.py -q

    python scripts/scrape/18a_submit_rollout_maps_supplement.py \
      --run-name full_market_plan_v2 \
      --stage standard_rollout
    ```

    18a首先打印按剩余任务数生成的精确确认文本。19a默认只检查本地task log，不联网；加入download-ready后先调用免费的maps_tasks_ready，只对明确出现在完成列表中的task ID下载结果。未完成任务不调用GET，也不会重新提交。

    ```bash
    python scripts/scrape/19a_download_rollout_maps_supplement.py \
      --run-name full_market_plan_v2 \
      --stage standard_rollout
    ```

31. Maps核心结果解析与三类映射
    20a读取30项已下载原始JSON，不调用API。它保留每条结果的市场、关键词、排名、CID、place_id、主类别、附加类别和category IDs，再在每个请求市场内按CID或place_id去重。Google返回类别通过config/google_dental_category_groups.csv映射到legacy的General、Special和Surgery；搜索关键词不会直接决定类别。

    ```bash
    python -m pytest tests/test_parsing.py tests/test_maps_supplement.py -q

    python scripts/scrape/20a_parse_rollout_maps_supplement.py \
      --run-name full_market_plan_v2 \
      --stage standard_rollout
    ```

    输出包括全部观测、市场内唯一profile、逐市场关键词重叠和汇总JSON。此时尚未按实际ZIP筛选，也没有把同一地点的多个profile归并成竞争地点，所以unique profile不能直接写成诊所数量。

32. Maps实际ZIP与跨来源profile审计
    21a不调用API。它重新读取20a的候选和观测，将普通Maps结果中的真实关键词重复与付费广告记录分开统计；随后按实际ZIP和主类别规则审核候选，并与两市场pilot、Atlanta及10个普通rollout市场中的全部Business Listings profile按市场和Google稳定ID精确匹配。输出另外标记该profile是否已经纳入竞争候选，防止把Business Listings已经抓到但因类别被排除的记录误写为Maps新发现。这里的精确重合只说明同一Google profile已经出现，不能代替物理地点归并。

    ```bash
    python -m pytest tests/test_maps_supplement.py tests/test_maps_supplement_audit.py -q

    python scripts/scrape/21a_audit_maps_supplement_sources.py \
      --run-name full_market_plan_v2 \
      --stage standard_rollout
    ```

    输出包括全部目标ZIP Maps profile的来源状态、逐市场重合统计、Maps独有profile审核表和汇总JSON。`primary_legacy_category_group`只使用Google主类别；三个`has_*_category_evidence`字段保留主类别与附加类别中的多标签证据。旧`legacy_category_group`继续保留any-evidence优先级算法以便复核，但不作为最终互斥诊所分类。纽约和洛杉矶没有Business Listings主抓取时会明确列入未覆盖市场，不会把Maps top-100结果误写为完整市场。

33. Maps独有profile类别与身份分档
    22a不调用API。它只把Business Listings已覆盖的13个市场纳入“Maps独有”判断；纽约和洛杉矶的Maps结果进入未覆盖市场文件，等待主抓取后再比较。真正独有profile按主类别资格、强牙科provider标题冲突和明显非provider类别分配审核队列。随后将需要继续审核的Maps profile与全部Business Listings profile在同一市场内比较地址、电话、domain、50米坐标和名称相似度，只生成跨来源身份候选pair。

    ```bash
    python -m pytest tests/test_maps_only_review.py -q

    python scripts/scrape/22a_triage_maps_only_profiles.py \
      --run-name full_market_plan_v2 \
      --stage standard_rollout
    ```

    所有队列和pair都只是人工审核优先级。该步骤不会自动接受或排除牙科profile，不会把Google profile合并为物理地点，也不会把纽约和洛杉矶的top-100 Maps结果当作完整市场。

34. 纽约和洛杉矶第一页范围效率审计
    23a只读取已经保存的四项Business Listings第一页和09a分页结果，不读取凭据、不调用API。它按regions.yaml的冻结ZIP规则分别计算每个市场、每个类别组第一页中目标ZIP、目标ZIP外和缺ZIP记录，并报告跨类别组的精确Google profile重合。第一页排序可能与后续页不同，因此目标ZIP比例只用于判断宽圆翻页是否明显浪费，不能直接推算最终召回率。

    ```bash
    python -m pytest tests/test_business_listings_rollout.py -q

    python scripts/scrape/23a_audit_major_metro_first_pages.py \
      --run-name full_market_plan_v2
    ```

    对reported_total_count超过10000的类别组，本步只标记review_filter_or_partition_before_continuation，不会自动生成或提交offset-token请求。对不超过10000的类别组，也只计算有界续页数量和预计费用，仍需单独批准后才能付费执行。

35. Business Listings服务端ZIP过滤能力检查
    02b通过官方available_filters GET端点读取当前可用过滤字段，并只打印包含zip、postal或address_info的JSON路径。它会读取已有环境变量凭据，但不会创建Business Listings任务、不会提交付费请求，也不会执行纽约或洛杉矶续页。完整响应保存在当前run的interim目录，供后续冻结过滤表达式。

    ```bash
    python -m pytest tests/test_dataforseo_search.py -q

    python scripts/scrape/02b_check_business_listings_available_filters.py \
      --run-name full_market_plan_v2
    ```

    只有输出明确包含可过滤的ZIP或postal字段，才允许设计服务端目标ZIP过滤请求。单纯看到结果对象含有address_info.zip不等于该字段可作为筛选条件。

36. 纽约和洛杉矶ZIP过滤计数探测
    24a读取已冻结的四项major-metro类别组，但把limit降为1，并为LA和NYC分别加入与regions.yaml完全一致的address_info.zip正则过滤。程序会遍历全部五位ZIP验证正则既不漏掉目标ZIP也不纳入范围外ZIP，然后才生成四项计数请求。每项只需要一条结果即可读取过滤后的total_count，预计总费用0.04944美元。

    首次只运行验证：

    ```bash
    python -m pytest tests/test_business_listings_live.py tests/test_business_listings_rollout.py -q

    python scripts/scrape/24a_run_major_metro_filtered_count_probe.py \
      --run-name full_market_plan_v2
    ```

    验证输出会给出精确确认文本。即使过滤后仍有后续结果，本步也不会提交续页；它只比较过滤前后的total_count，为最终limit=1000分页计划提供依据。

37. 纽约和洛杉矶ZIP过滤正式分页
    25a读取24a已经完成的四项计数结果，为LA和NYC两个类别组建立四条独立token链。当前过滤后总数为27555条，按每页最多1000条预计需要29次请求，预计费用10.2678美元。第一页使用完整类别、半径与ZIP过滤条件，后续页使用上一页响应中的offset_token；同一链的API tag保持不变，本地文件使用独立页号保存。

    首次只运行验证：

    ```bash
    python -m pytest tests/test_major_metro_filtered_pagination.py -q

    python scripts/scrape/25a_run_major_metro_zip_filtered_pages.py \
      --run-name full_market_plan_v2
    ```

    验证输出会根据尚未完成的页数生成精确确认文本。执行器逐页核对total_count、实际返回数、offset_token是否连续以及token是否重复，并在每页后更新断点。若抓取过程中total_count上升，程序最多只执行本次明确确认的页数，不会自动提交新增页；若原始JSON已经存在但完成日志缺失，也会停止以避免重复付费。

38. 纽约和洛杉矶完整性审计与解析
    26a将分页审计和结果解析合并为一个离线步骤。它要求LA和NYC四条token链全部完成，重新核对页号、token衔接、原始JSON、API tag、每页item_count和总保存数量，并逐条确认返回ZIP满足该市场的服务端正则过滤。任一缺页、断链、原始文件缺失或ZIP越界都会停止，不会生成半成品候选表。

    ```bash
    python -m pytest tests/test_major_metro_filtered_parse.py -q

    python scripts/scrape/26a_audit_parse_major_metro_zip_filtered.py \
      --run-name full_market_plan_v2
    ```

    输出保留27555条分页观测，再按CID或place_id在每个市场内去重。跨类别组重复可以合并为同一Google profile；同一token链内部出现重复稳定身份则视为分页异常并停止。这里仍不按地址合并物理竞争地点，也不执行类别人工决定。

39. 纽约和洛杉矶三来源对比
    27a同时读取26a生成的Business Listings候选、21a生成的Maps Standard profile审核表和corrected_v1 competition-unit crosswalk。该crosswalk是legacy与external已经融合后的历史参考，程序不会把external重复加入，也不会把融合基准误写成纯legacy。两种新来源先使用相同的目标ZIP和主类别规则，再分别使用冻结的地址、电话、距离和名称证据规则计算对同一融合历史参考的召回率。空间索引只缩小需要核对的身份候选，不修改回归使用的2-mile或5-mile BallTree。最后单独计算Maps Standard与Business Listings的精确Google profile重合。

    ```bash
    python -m pytest tests/test_business_listings_comparison.py tests/test_major_metro_source_audit.py -q

    python scripts/scrape/27a_audit_major_metro_sources.py \
      --run-name full_market_plan_v2
    ```

    本步不调用API，不自动合并profile或物理地点。三个指标必须分开解释：Business Listings历史参考召回率、Maps Standard历史参考召回率、Maps与Business Listings精确profile重合率。Maps Standard只有每市场两个核心关键词任务，不能被解释为完整市场普查。现有crosswalk没有保留融合前的逐行来源，因此只能确认基准已经包含legacy和external，不能再拆分二者贡献。

40. 十五市场统一三来源对比
    28a把四批Business Listings结果按固定市场归属接在一起：Malone与Syracuse使用pilot人工审核后的profile表，Atlanta使用大型市场验证表，10个普通市场使用standard rollout批量表，LA与NYC使用ZIP-filtered完整分页表。随后用同一份corrected_v1融合历史competition-unit crosswalk、同一套目标ZIP口径和同一套地址、电话、距离、名称匹配规则，重新计算全部15个市场，避免把不同阶段旧summary直接拼接。

    ```bash
    python -m pytest tests/test_all_market_source_audit.py -q

    python scripts/scrape/28a_audit_all_market_sources.py \
      --run-name full_market_plan_v2
    ```

    本步不调用API，不修改回归BallTree，不自动合并profile或物理地点。统一汇总使用目标ZIP内的融合历史竞争单位作为分母。Malone与Syracuse已经完成的当前有效性人工审核仍单独保存，不会替换其他13个市场尚未审核的统一历史分母。

41. 十五市场地点级来源联合召回
    29a读取28a生成的两份历史地点匹配表，在market与reference_key上逐行连接Business Listings和Maps Standard结果。它把历史地点分成两种来源共同找到、仅Business Listings找到、仅Maps补回、两种来源都未找到四类，再计算去重后的联合召回率。两种来源各自召回率不能直接相加，Maps精确profile独有数量也不能代替历史地点增量。

    ```bash
    python -m pytest tests/test_source_union_audit.py -q

    python scripts/scrape/29a_audit_all_market_source_union.py \
      --run-name full_market_plan_v2
    ```

    本步不调用API。市场分档复用冻结门槛：联合召回率至少0.90标记为达到单市场主来源门槛，0.80至0.90之间进入历史缺口定向审核，低于0.80要求重新检查发现范围。任何分档都不会自动触发付费任务；两种来源均未找到的旧地点要先区分关闭、改名、身份变化和真实漏抓。

42. 双来源未发现历史地点审核队列
    30a读取29a的地点级联合结果，并连接28a保存的融合历史参考表及两种来源最近候选证据。队列只保留两种来源都未找到的历史地点，按100米内弱身份证据、500米内附近候选、需要定向核对当前状态和历史身份信息不足四种审核类型排序。市场整体召回率低会提高审核优先级，但不会直接证明Business Listings在小市场必然失效。

    ```bash
    python -m pytest tests/test_unmatched_reference_audit.py -q

    python scripts/scrape/30a_build_unmatched_reference_review.py \
      --run-name full_market_plan_v2
    ```

    本步不调用API，不自动判断旧地点已经关闭，也不自动把附近profile合并为同一地点。审核队列保留manual_decision、manual_evidence、reviewed_by和reviewed_on空列，后续决定付费补抓前必须先完成证据审核。

43. 放宽历史身份规则的人工验证集
    31a针对30a发现的近距离未匹配记录，计算标准化名称是否完全一致、门牌号是否一致、地址相似度、名称相似度和距离。候选规则包括精确名称100米内、名称相似度至少0.8且门牌号一致100米内，以及名称相似度至少0.6、地址相似度至少0.8、门牌号一致100米内。规则阈值只用于缩小人工验证范围，不会直接改变原matcher。

    ```bash
    python -m pytest tests/test_identity_rule_validation.py -q

    python scripts/scrape/31a_build_identity_rule_validation.py \
      --run-name full_market_plan_v2
    ```

    输出中的identity_rule_manual_validation_candidates.csv保留proposed_decision与decision_evidence空列。只有人工确认其误匹配率足够低后，才能把新规则加入正式身份匹配；共享办公楼、医院和多牙医地址仍必须保持谨慎。

44. 应用放宽身份规则的逐条人工决定
    32a读取31a生成的22条候选和config/identity_rule_manual_decisions_20260919.csv。人工证据确认18条为同一历史地点，2条为改名或重新标记后的同一地点，2条旧记录不属于牙科竞争样本。原始候选规则确认20/22，样本内正预测值为90.91%，低于0.95门槛，因此本步只补回这20个已经核实的reference key，不把规则自动推广到其他历史记录。

    ```bash
    python -m pytest tests/test_identity_rule_adjudication.py -q

    python scripts/scrape/32a_apply_identity_rule_manual_decisions.py \
      --run-name full_market_plan_v2
    ```

    本步不调用API，不自动合并rating profile。输出会分开保存确认匹配、参考分母排除以及完整复核表。下一步应使用这两类决定重新计算15个市场的联合召回率。

45. 人工身份决定后的十五市场联合召回率
    33a将32a确认的20个历史地点补回29a来源联合表，并将2个超出牙科范围的旧记录从当前参考分母排除。程序保留每条reference key原来的来源状态，只根据人工验证表中的Business Listings或Maps证据更新对应来源。输出同时报告原始召回率、调整后召回率、各市场增量及门槛分档是否变化。

    ```bash
    python -m pytest tests/test_adjudicated_source_union.py -q

    python scripts/scrape/33a_recalculate_source_union_after_identity_review.py \
      --run-name full_market_plan_v2
    ```

    本步不调用API、不重新抓取、不删除历史面板记录，也不修改回归BallTree。调整后的剩余未匹配地点才是后续停业审核或定向补抓的输入。
