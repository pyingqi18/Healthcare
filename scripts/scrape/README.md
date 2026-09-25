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

46. 十五市场统一专业关键词Maps补抓规划
    34a读取33a人工修正后的市场级联合召回结果，并从config/scrape_plans.yaml读取已经冻结的5个专业关键词：orthodontist、pediatric dentist、periodontist、prosthodontist和oral surgeon。15个市场全部使用同一组关键词，每个市场5项，共75项Standard Maps任务。不能只给当前召回率低的市场加关键词，否则不同市场的搜索强度会由已经观察到的结果决定，后续地点密度和进入冲击将不再处于同一测量口径。

    ```bash
    python -m pytest tests/test_maps_specialist_plan.py -q

    python scripts/scrape/34a_plan_uniform_maps_specialist_supplement.py \
      --run-name full_market_plan_v2
    ```

    本步只生成maps_specialist_manifest.csv和maps_specialist_plan_summary.json，不读取账号密码、不提交API任务。当前计划为15个市场乘5个关键词，共75项，按配置价格预计0.045美元。规划通过后才会补提交、Tasks Ready下载、解析、ZIP审核和来源联合代码；本步不会把新profile直接认定为物理诊所。

47. 专业关键词Maps任务提交、完成检查与解析
    35a严格要求34a生成的75项清单完整覆盖15个市场和5个冻结关键词。第一次不带confirm-submit运行时只验证清单、已有task log和准确确认文字，不读取凭据。确认后75项Standard Queue任务通过一个HTTP POST批次提交，task log保存每项task ID、参数哈希、提交时间和状态，重复运行只提交尚未成功的任务。

    ```bash
    python -m pytest tests/test_maps_specialist_plan.py tests/test_maps_specialist_execution.py tests/test_maps_supplement.py -q

    python scripts/scrape/35a_submit_maps_specialist_supplement.py \
      --run-name full_market_plan_v2

    python scripts/scrape/35a_submit_maps_specialist_supplement.py \
      --run-name full_market_plan_v2 \
      --confirm-submit SUBMIT_75_PAID_MAPS_SPECIALIST_TASKS
    ```

    36a先查询DataForSEO Tasks Ready，只对明确完成的task ID调用结果GET。未完成任务不会提前GET，已经保存的JSON不会重复下载。如果remaining_after_download大于0，稍后原样重跑带download-ready的命令。

    ```bash
    python scripts/scrape/36a_download_maps_specialist_supplement.py \
      --run-name full_market_plan_v2

    python scripts/scrape/36a_download_maps_specialist_supplement.py \
      --run-name full_market_plan_v2 \
      --download-ready
    ```

    只有remaining_after_download为0后才运行37a。解析器要求75个task和15个市场全部存在，检查原始JSON中的task tag，再去除付费广告结果，按Google profile身份在市场内去重，并保留每个profile由哪些专业关键词发现以及返回的主类别和附加类别证据。

    ```bash
    python scripts/scrape/37a_parse_maps_specialist_supplement.py \
      --run-name full_market_plan_v2
    ```

    37a仍未执行目标ZIP过滤、跨来源身份匹配或物理地点合并。下一步使用完整候选表统一进行ZIP审核，并与Business Listings、两关键词Maps和融合legacy external参考集合重算增量召回率。

48. 专业关键词目标ZIP、来源身份与联合召回率审核
    38a一次完成专业关键词profile的实际ZIP资格、与Business Listings和两关键词Maps的精确Google profile重合、与融合历史competition unit的冻结规则匹配，以及33a人工修正后来源联合召回率的增量重算。该步骤读取已保存文件，不读取API凭据、不提交任务、不修改回归BallTree、不自动合并物理地点。

    ```bash
    python -m pytest \
      tests/test_maps_specialist_source_audit.py \
      tests/test_maps_supplement_audit.py \
      tests/test_all_market_source_audit.py \
      tests/test_adjudicated_source_union.py -q

    python scripts/scrape/38a_audit_maps_specialist_source_union.py \
      --run-name full_market_plan_v2
    ```

    输出保存在data/interim/full_market_plan_v2/maps_specialist_source_union_audit。maps_specialist_profile_audit.csv保留全部3003个profile及ZIP和类别状态。源ZIP为空时，程序只从地址末尾明确的州缩写加五位ZIP恢复邮编，并在zip_resolution_method记录address_text_fallback。非空源ZIP不会被地址覆盖，任意位置出现的五位数字也不会被当成ZIP。exact overlap文件只说明相同Google profile；reference matches使用冻结的地址、电话、10米坐标加名称和100米电话规则；source_union_after_specialist只把33a之后仍未发现、现被专业关键词匹配的当前reference记为增量。人工排除的reference不会被重新放回分母。

    如果summary中的低于80%市场仍存在，下一步进入条件性小市场原因诊断。专业关键词独有profile仍需后续物理地点审核，不能直接作为新增诊所或竞争密度。

49. 专业关键词后续人工队列与市场缺口诊断
    39a读取38a的完整profile资格表、精确来源重合、历史匹配pair、剩余未匹配reference和15市场召回表。程序一次生成两类人工队列：第一类只包含仍未匹配且专业关键词给出10米内坐标弱证据的历史地点；第二类只包含专业关键词精确新增profile中的人工类别记录，以及所有缺ZIP记录。类别或缺ZIP profile不会被当成历史reference匹配，也不会自动提高召回率。

    ```bash
    python -m pytest tests/test_specialist_followup_audit.py -q

    python scripts/scrape/39a_build_specialist_followup_review.py \
      --run-name full_market_plan_v2
    ```

    输出保存在data/interim/full_market_plan_v2/maps_specialist_followup_review。market_coverage_gap_diagnostic.csv同时计算每个市场即使把所有待核实身份都确认后的理论最高召回率。当前数据中Saranac Lake和Vidalia没有这类待确认身份，因此不能靠放宽身份规则达到80%；两地会被明确标记为完成当前状态审核后需要统一发现方式重设计。本步不调用API、不自动确认身份、不自动归并profile，也不改变15市场统一搜索原则。

    2026-09-19复核发现，首次39a的10个缺ZIP profile中有5个地址文本已经明确写出ZIP。安装地址ZIP回退修复后，需要用--overwrite依次重跑38a和39a。修正预计将目标ZIPprofile由2347调整为2350，目标ZIP外由646调整为648，真正缺ZIP由10调整为5；Syracuse新增补回1个历史reference。旧的38a与39a输出不应继续作为下一步人工决定输入。

50. 专业关键词后续统一人工决定与应用
    40a将39a的110个identity pair压缩成21个reference级决定，并把它们与79个类别决定和5个地理决定合并成一份105行CSV。每个历史身份决定仍可在specialist_identity_review_queue.csv查看全部候选；统一决定表只显示38a最佳候选和候选总数，避免要求审核人填写110行重复reference决定。

    第一次运行只生成决定表：

    ```bash
    python -m pytest tests/test_specialist_followup_adjudication.py -q

    python scripts/scrape/40a_adjudicate_specialist_followup.py \
      --run-name full_market_plan_v2
    ```

    输出的specialist_followup_decisions.csv需要填写manual_decision、decision_evidence、reviewed_by和reviewed_on。确认同一或改名地点时，还必须从对应pair block中填写selected_candidate_key。缺ZIP profile被判定为目标ZIP且原类别规则仍需人工判断时，需要同时填写secondary_category_decision。

    填完后使用同一入口应用决定：

    ```bash
    python scripts/scrape/40a_adjudicate_specialist_followup.py \
      --run-name full_market_plan_v2 \
      --decisions "data/interim/full_market_plan_v2/maps_specialist_followup_adjudication/specialist_followup_decisions.csv" \
      --overwrite
    ```

    脚本一次输出校验后的决定、确认身份、profile最终资格、reference级联合表、15市场召回率和summary。historical_location_closed与historical_reference_out_of_scope退出当前发现基准，但不会删除历史面板记录。本步不调用API，也不执行物理地点合并。

51. 人工决定后的缺口收口规划
    40a应用结果共有3575个当前历史参考地点，来源联合发现3398个，联合召回率95.05%，剩余177个。达到90%门槛的10个市场停止扩大主发现层；Eureka、FortBragg和Toccoa进入逐地点当前状态审核；SaranacLake和Vidalia同时进入逐地点状态审核及条件性发现方式重设计。

    40a原summary把3个未决profile在reviewed表和profile结果表各数一次，因此显示remaining_unresolved_decisions为7。实际唯一未决决定为4行，即1条历史身份和3条profile。修正后重跑40a只改变该摘要数字，不改变人工决定、3575个分母、3398个发现地点、177个缺口或市场分档。

    41a一次生成市场行动表、177个剩余reference完整清单、5个低于90%市场的逐地点状态查询清单、15市场统一剩余关键词清单和4条未决决定清单。逐地点查询只核对旧reference当前状态，明确标记为不进入主发现样本。统一发现层只使用family dentist、general dentistry、cosmetic dentist、dental implants和emergency dentist五个单关键词，共75项；不恢复旧53组关键词组合。

    ```bash
    python -m pytest \
      tests/test_specialist_followup_adjudication.py \
      tests/test_post_adjudication_completion.py -q

    python scripts/scrape/40a_adjudicate_specialist_followup.py \
      --run-name full_market_plan_v2 \
      --decisions "data/interim/full_market_plan_v2/maps_specialist_followup_adjudication/specialist_followup_decisions.csv" \
      --overwrite

    python scripts/scrape/41a_plan_post_adjudication_completion.py \
      --run-name full_market_plan_v2 \
      --overwrite
    ```

    41a不读取账号密码，也不提交API。reference_status_audit_manifest.csv需要先检查title和address查询是否合理；uniform_residual_keyword_manifest.csv虽然已经统一生成，但仍为prepared_conditional_not_approved，不能与逐地点状态审核混为同一主发现数据。

52. 五个低门槛市场的历史地点状态审核提交与下载
    42a只接受41a冻结的reference_status_audit_manifest.csv和对应摘要。它检查50项任务、Eureka、FortBragg、SaranacLake、Toccoa、Vidalia五个市场、reference key、查询文字和0.03美元预计费用完全一致，并强制included_in_main_discovery_pipeline为false。第一次运行仅验证，不读取凭据、不提交任务。

    ```bash
    python -m pytest tests/test_reference_status_audit_execution.py tests/test_post_adjudication_completion.py -q

    python scripts/scrape/42a_submit_reference_status_audit.py \
      --run-name full_market_plan_v2
    ```

    确认输出仍为50项、五个指定市场且确认文字为SUBMIT_50_PAID_REFERENCE_STATUS_AUDIT_TASKS后，才执行付费提交：

    ```bash
    python scripts/scrape/42a_submit_reference_status_audit.py \
      --run-name full_market_plan_v2 \
      --confirm-submit SUBMIT_50_PAID_REFERENCE_STATUS_AUDIT_TASKS
    ```

    43a默认只检查task log和本地已保存结果，不读取凭据。加入download-ready后只下载Tasks Ready明确列出的task ID，并核对返回tag与原清单身份一致。

    ```bash
    python scripts/scrape/43a_download_reference_status_audit.py \
      --run-name full_market_plan_v2

    python scripts/scrape/43a_download_reference_status_audit.py \
      --run-name full_market_plan_v2 \
      --download-ready
    ```

    这50项查询只为审核旧reference当前状态，结果不能直接计为新增诊所发现。41a准备的75项uniform residual discovery任务仍保持未批准，本阶段不得一起提交。

53. 解析50项状态结果并统一人工判定
    43a已经确认50个task全部ready并下载完成，未发生提前GET。44a一次解析全部保存结果，按reference整理候选名称、地址、电话、域名、坐标距离和provider返回的状态字段，并生成一份50行人工决定表。没有返回候选不等于停业，出现关闭字段也不直接删除历史地点，所有最终状态均需人工确认。

    ```bash
    python -m pytest \
      tests/test_reference_status_adjudication.py \
      tests/test_reference_status_audit_execution.py \
      tests/test_parsing.py -q

    python scripts/scrape/44a_adjudicate_reference_status_audit.py \
      --run-name full_market_plan_v2
    ```

    第一遍输出目录为`data/interim/full_market_plan_v2/reference_status_audit_adjudication`。主要查看`reference_status_candidate_evidence.csv`，并在`reference_status_decisions.csv`中填写manual_decision、selected_candidate_key、decision_evidence、evidence_url、reviewed_by和reviewed_on。

    manual_decision只允许以下值：

    * `active_same_historical_location`：确认返回profile与历史地点相同。
    * `active_renamed_or_relocated_location`：确认历史实体仍有效，但已经改名或搬迁。
    * `active_reference_not_rediscovered`：确认旧地点仍应在当前分母中，但本次查询没有可靠匹配。
    * `historical_location_closed`：确认历史地点已经关闭，从当前reference分母退出，历史panel不删除。
    * `historical_reference_out_of_scope`：确认该地点不属于当前研究范围，从当前reference分母退出。
    * `unresolved`：证据不足，暂不改变分母。

    前两项必须从对应candidate evidence中填写selected_candidate_key。其余决定不得填写selected_candidate_key。全部填完后运行：

    ```bash
    python scripts/scrape/44a_adjudicate_reference_status_audit.py \
      --run-name full_market_plan_v2 \
      --decisions "config/reference_status_manual_decisions_20260919.csv" \
      --overwrite
    ```

    应用阶段输出校验后的决定、更新后的reference级来源联合表、15市场新召回率和summary。定向查询中确认找到的profile只记为targeted_status_profile_found，main discovery numerator increase固定为0。75项统一剩余关键词任务仍不自动批准，必须根据44a后的分母、缺口和市场行动重新决定。

    本轮实际证据中50项均为非牙科provider历史reference。49项返回美甲、宠物、药房、医院、普通医疗、眼科、妇产科、保险、政府或其他非牙科类别；Claudio Dental Laboratory命中冻结规则中明确排除的Dental laboratory。逐条决定已冻结在`config/reference_status_manual_decisions_20260919.csv`，运行应用命令前仍由44a校验决定覆盖、证据字段和reference身份。

54. 冻结15市场主发现基准并取消条件性75项任务
    44a实际应用结果为3525个当前reference、3398个来源联合发现地点、96.40%联合召回率和127个仍未匹配reference。15个市场全部达到冻结的90%市场门槛，50项状态审核没有增加主发现分子，没有自动合并profile或地点，也没有修改回归BallTree。

    45a同时核对44a summary、15市场表、reference级来源联合表和41a的75项条件性清单。只有四份输入逐项守恒且15个市场全部为`freeze_primary_discovery`时，才输出冻结表。75项任务会逐行保留，但最终状态改为`cancelled_not_needed_after_gate`，不会读取凭据或提交API。

    ```bash
    python -m pytest \
      tests/test_discovery_benchmark_freeze.py \
      tests/test_reference_status_adjudication.py \
      tests/test_post_adjudication_completion.py -q

    python scripts/scrape/45a_freeze_primary_discovery_benchmark.py \
      --run-name full_market_plan_v2 \
      --overwrite
    ```

    输出目录为`data/interim/full_market_plan_v2/primary_discovery_benchmark_freeze`。其中`frozen_active_reference_source_union.csv`冻结当前参考基准，`frozen_discovery_benchmark_by_market.csv`保存15市场实际召回率，`validated_legacy_carry_forward_inventory.csv`保存127个仍有效但未被新来源发现的历史地点，`uniform_residual_keyword_manifest_cancelled.csv`保存75项不执行决定，`discovery_benchmark_freeze_summary.json`保存输入SHA256和下一阶段边界。

    这一步只冻结历史reference覆盖率，不代表已经得到最终诊所数。下一阶段必须合并Business Listings、两关键词Maps、专业关键词Maps和validated legacy carry-forward的目标ZIP内profile，再分别冻结Google outcome profile与物理competition location。

55. 统一跨来源profile并建立15市场地点审核block
    46a读取四类已经冻结的输入：全市场Business Listings资格表、两关键词Maps核心profile、五关键词Maps专业profile和127个validated legacy carry-forward。第一遍先按市场加CID或place_id形成的稳定profile key精确去重，不用标题或坐标自动合并Google profile。已完成的pilot人工决定由`config/candidate_manual_decisions_20260908.csv`按稳定profile key继承，专业profile人工决定由专业审核输出继承；继承时再次核对标题，身份不一致会停止运行。若一个pending profile的全部observed category都已有冻结exclude规则，46a直接执行该规则并保留逐类别原因，不再把规则应用伪装为新的人工审核。其余类别冲突、manual category和未知类别进入同一份决定表。

    ```bash
    python -m pytest \
      tests/test_cross_source_profile_resolution.py \
      tests/test_discovery_benchmark_freeze.py -q

    python scripts/scrape/46a_prepare_cross_source_location_review.py \
      --run-name full_market_plan_v2 \
      --overwrite
    ```

    第一遍输出`unified_cross_source_profile_inventory.csv`、`profile_eligibility_decisions.csv`、`legacy_carry_forward_location_anchors.csv`、`legacy_carry_forward_outcome_lineage.csv`和准备摘要。准备摘要同时记录复用的早期人工决定数。只需填写决定表中的manual_decision、decision_evidence、evidence_url、reviewed_by和reviewed_on，其余身份和来源列不得修改。

    决定完成后使用同一入口应用：

    ```bash
    python scripts/scrape/46a_prepare_cross_source_location_review.py \
      --run-name full_market_plan_v2 \
      --decisions "data/interim/full_market_plan_v2/cross_source_profile_location_review/profile_eligibility_decisions.csv" \
      --overwrite
    ```

    应用阶段先生成最终纳入的Google profile，再把127个legacy carry-forward作为competition location anchor加入地点审核。carry-forward表示按冻结的市场召回门槛继续保留，不代表127个地点逐一确认仍在营业，因此输出明确标记current_status_individually_verified=false，并要求最终exposure保留一项排除未逐一验证carry-forward的敏感性比较。候选pair使用标准化地址、电话、domain和每个市场内部500米BallTree建立，不执行全市场两两笛卡尔比较。BallTree仅缩小人工地点审核候选范围，不修改回归的空间邻居或exposure。输出的连通block和routine、focused、complex分档都只是审核顺序，自动地点合并仍为0。

56. 剩余profile资格批量审核辅助
    46b读取46a的空白决定表、统一profile inventory和`config/google_category_rules.csv`。它把每条pending profile拆成冻结类别规则、标题牙科信号、标题非牙科信号和未知类别，再输出逐profile triage、147个类别证据组、未知类别规则候选表和汇总。它只给出审核建议，不填写manual_decision，不调用API，也不改变provider taxonomy。

    ```bash
    python -m pytest \
      tests/test_profile_eligibility_triage.py \
      tests/test_cross_source_profile_resolution.py -q

    python scripts/scrape/46b_prepare_profile_eligibility_triage.py \
      --run-name full_market_plan_v2 \
      --overwrite
    ```

    修正后的46a应先把120个一致冻结排除规则直接应用，使待审profile从570降至450。46b预计把450条分成33条类别冲突、91条标题牙科证据、43条辅助或非provider类别证据和283条需要进一步证据的记录。建议不是最终决定；任何批量接受都必须保留具体规则或外部证据，最终仍通过46a的完整决定覆盖和身份列不变检查。

57. 组合类别组决定与逐profile例外
    46b实际输出已核对为450条profile、147个类别组和104个未知类别值，三者逐项守恒且没有重复profile key或decision ID。80条建议纳入和87条建议排除只用于排序，不能直接视为最终资格。类别冲突中存在同时带牙科和非provider类别的profile，标题信号中也存在类别明显冲突的记录，因此46c不自动接受任何建议。

    46c第一遍为每个稳定Google profile生成可直接打开的证据URL，同时从46a统一inventory带入已有网站、domain、电话、票数和坐标，再生成两份可同时使用的人工审核表。实际450条中357条已有网站，440条有电话，445条至少有网站或电话，只有5条两者都没有。审核应先查已有网站，再核对Google profile，不应重新提交API任务取得已经存在的身份资料。

    147个`category_group_id`只用于分析，不充当决定单元。最大的`Medical clinic`分析组有110条，内部证据不同，整组决定会制造分类错误。进一步检查还发现非external层的标题或类别证据组也会混入无关机构，例如26条`Medical clinic`标题证据、10条`Veterinarian`和8条`Dental school`。因此所有层统一使用同一条规则：只有同一类别组内重复出现同一非空domain时才能组成共享审核块，其余记录全部保持单例。最终group文件共有410个唯一`review_block_id`，其中27个共享domain块覆盖67条profile，383个为单例。block表允许审核者在检查块内全部成员后给出统一决定，也允许标记`individual_review`。row表用于块内例外。一个块若使用统一决定，`reviewed_member_count`必须等于`profile_count`；逐条决定优先于block决定。

    ```bash
    python -m pytest \
      tests/test_profile_eligibility_review.py \
      tests/test_profile_eligibility_triage.py \
      tests/test_cross_source_profile_resolution.py -q

    python scripts/scrape/46c_prepare_apply_profile_eligibility_review.py \
      --run-name full_market_plan_v2 \
      --overwrite
    ```

    第一遍输出目录为`data/interim/full_market_plan_v2/profile_eligibility_review`。46c会先读取`config/profile_eligibility_verified_decisions_20260924.csv`，按稳定profile key、市场、标题和地址四重校验后预填已有官网证据的决定；身份发生变化会停止运行。其余记录按`review_block_id`填写`profile_eligibility_review_groups.csv`中的group_manual_decision、reviewed_member_count、group_decision_evidence、reviewed_by和reviewed_on。异质块填`individual_review`，然后在`profile_eligibility_review_rows.csv`中逐条填写manual_decision、decision_evidence、evidence_url、reviewed_by和reviewed_on。row决定也可覆盖块内少量例外。不要按`category_group_id`把多个review block重新合并。

    截至2026-09-24，冻结决定表已有163条逐profile决定，其中87条纳入牙科provider、76条排除非provider。33条`focused_category_conflict`记录中32条已预填；Emory Clinic的官网确认1365 Clifton Road提供口腔颌面外科，Humiston Bridget的精确地址证据确认其接收牙科患者，仍保留官网当前地址与profile地址不同的Dr. Benjamin Blackburn。43条`focused_category_evidence`已全部完成；UB的320 Hayes Rd是正畸患者诊所，UCLA PatientAccess也明确把10833 Le Conte Ave列为School of Dentistry Dental Clinics地址，因此两条均纳入。91条`focused_title_evidence`中86条已经逐profile核实。审核没有机械接受标题建议：APLA CDU/MLK、Golden Valley Hanshaw、NEMS Stockton、NEMS San Bruno、Southside Medical Center、Ezra 13th Avenue和One Brooklyn Health Brookdale虽然标题是综合医疗机构，但官网明确显示该地址提供牙科，因此纳入；Altadena Dental Center和Daria Vasilyeva的1244 Amsterdam地址也已有精确患者服务证据。Tooth Preventive Dental的链接和类别指向整形外科且没有牙科证据，因此排除。DENTAL CLINIC LLC、Taylor Judy a DDS、Dr. mihai M. oral、Urgent Care Dentist 24/7和All Dental Technology五条仍缺少可靠的当前患者服务或身份注册证据。保留记录不是默认排除，不能用搜索不到替代排除证据。重新运行46c后应得到163条预填决定，剩余287条包括281条`external_evidence_required`、5条`focused_title_evidence`和1条`focused_category_conflict`。

    全部审核完成后运行：

    ```bash
    python scripts/scrape/46c_prepare_apply_profile_eligibility_review.py \
      --run-name full_market_plan_v2 \
      --apply-reviewed \
      --row-decisions "data/interim/full_market_plan_v2/profile_eligibility_review/profile_eligibility_review_rows.csv" \
      --group-decisions "data/interim/full_market_plan_v2/profile_eligibility_review/profile_eligibility_review_groups.csv" \
      --overwrite
    ```

    应用阶段必须覆盖全部450条，否则停止运行。输出的`profile_eligibility_decisions_completed.csv`保持46a原决定表的身份列和列结构，可直接传给46a；`profile_eligibility_decision_audit.csv`另行记录每条决定来自group还是row。46c不调用API、不改变类别规则、不合并profile或地点，也不修改回归BallTree。

58. 本地profile资格人工审核页面
    第三版46c输出已核对为450条profile、410个review block、27个共享domain块和383个单例，最大块为6条。46d再次检查decision ID、profile key、review_block_id、block人数和共享domain约束，然后生成单一HTML文件。页面不需要本地服务器，直接用浏览器打开即可。它逐块显示已有网站、Google profile、电话、地址和类别，自动保存本机浏览器中的审核进度，并提供未完成、已完成和individual review筛选。

    ```bash
    python -m pytest \
      tests/test_profile_eligibility_review_app.py \
      tests/test_profile_eligibility_review.py \
      tests/test_profile_eligibility_triage.py \
      tests/test_cross_source_profile_resolution.py -q

    python scripts/scrape/46d_build_profile_eligibility_review_app.py \
      --run-name full_market_plan_v2 \
      --overwrite
    ```

    页面位置为`data/interim/full_market_plan_v2/profile_eligibility_review/profile_eligibility_review.html`。对于统一block决定，必须打开并检查全部成员，勾选完整审核，并填写决定证据、审核人和日期。共享domain不保证所有地点都提供同样服务；证据混合时选择`individual_review`并逐条填写。两个导出按钮分别生成`profile_eligibility_review_groups_reviewed.csv`和`profile_eligibility_review_rows_reviewed.csv`。中途可以导出备份，但只有页面显示410块全部完成后才运行46c的`--apply-reviewed`。

    页面只在浏览器中保存人工输入，不会上传资料、调用API、修改原CSV、执行profile或地点合并，也不修改回归BallTree。

59. 外部证据批量审核队列
    第8版46c文件已核对为450条profile、410个冻结审核块和163条已预填决定。剩余287条中，281条属于`external_evidence_required`，其余为5条标题证据和1条类别冲突。46e只选择这281条外部证据记录，并把它们整理成审核单元、逐profile证据表和domain导航表，不再要求审核者在450条总表里反复筛选。

    真实数据中281条外部证据记录形成252个审核单元：20个共享domain块覆盖49条profile，232个单例；217条已有网站，273条有电话，276条至少有一种现成联系证据，5条两者都没有。审核顺序固定为共享domain块、已有官网单例、只有电话的单例、没有现成联系证据的单例。代码给每条记录生成精确标题、地址和电话搜索链接，也生成限定现有domain的站内搜索链接。搜索链接只是证据入口，不是决定。

    ```bash
    python -m pytest \
      tests/test_profile_eligibility_external_evidence.py \
      tests/test_profile_eligibility_review.py \
      tests/test_profile_eligibility_triage.py \
      tests/test_cross_source_profile_resolution.py -q

    python scripts/scrape/46e_prepare_profile_eligibility_external_evidence.py \
      --run-name full_market_plan_v2 \
      --overwrite
    ```

    输出目录为`data/interim/full_market_plan_v2/profile_eligibility_external_evidence_audit`。`external_evidence_audit_units.csv`用于按252个单元安排审核，`external_evidence_profiles.csv`保留281条精确profile证据和搜索入口，`external_evidence_domains.csv`用于复用网站导航工作，summary记录当前口径。相同domain只允许复用查找路径，不能证明不同地址都提供牙科，也不能直接批量纳入或排除。46e不请求API、不抓取复杂HTML、不填写最终决定、不合并profile或地点，也不修改回归BallTree。

60. 冻结第8版证据并应用共享domain逐profile审核
    46f同时解决两个问题。第一，它把第8版row、group、summary和46e四个输出连同审核前后的决定表保存为独立冻结档案，因此安装用zip删除后仍能复核。第二，它要求20个共享domain单元中的49条profile全部逐地址决定，拒绝profile key、市场、标题或地址变化，也拒绝缺少证据、URL、审核来源或日期的决定。

    ```bash
    python -m pytest \
      tests/test_profile_eligibility_audit_freeze.py \
      tests/test_profile_eligibility_external_evidence.py \
      tests/test_profile_eligibility_review.py -q

    python scripts/scrape/46f_freeze_shared_domain_profile_audit.py \
      --review-rows "data/interim/full_market_plan_v2/profile_eligibility_review/profile_eligibility_review_rows.csv" \
      --review-groups "data/interim/full_market_plan_v2/profile_eligibility_review/profile_eligibility_review_groups.csv" \
      --review-summary "data/interim/full_market_plan_v2/profile_eligibility_review/profile_eligibility_review_prepare_summary.json" \
      --external-profiles "data/interim/full_market_plan_v2/profile_eligibility_external_evidence_audit/external_evidence_profiles.csv" \
      --external-units "data/interim/full_market_plan_v2/profile_eligibility_external_evidence_audit/external_evidence_audit_units.csv" \
      --external-domains "data/interim/full_market_plan_v2/profile_eligibility_external_evidence_audit/external_evidence_domains.csv" \
      --external-summary "data/interim/full_market_plan_v2/profile_eligibility_external_evidence_audit/external_evidence_audit_summary.json" \
      --overwrite
    ```

    真实审核结果为20个单元、49条profile、34条纳入和15条排除。旧163条决定与49条新增决定合并后共有212条，其中121条纳入、91条排除，还剩238条profile未完成。本次代码包已经带有完成的冻结目录`archive/profile_eligibility_review/20260924_v8`，正常继续分析时不必再次运行46f；上面的命令用于以后从本地原始文件重新生成并核验档案。脚本既接受163条审核前决定，也接受内容完全一致的212条审核后决定，但拒绝只混入部分新增决定的中间状态。`profile_eligibility_review_freeze_20260924_v8.zip`是以后人工复核所需的数据档案，不是安装包，也不需要解压才能继续当前pipeline。`MANIFEST.sha256.csv`逐文件记录大小和哈希，`freeze_archive_metadata.json`记录冻结包自身哈希。46f不调用API、不自动合并profile或地点，也不修改回归BallTree。

61. 冻结未经填写的原始profile复核基线
    46g用于纠正“原始版”和“进度版”的命名混淆。真实生成链为583条初始空白待审profile，复用13条旧决定后得到570条，再由120条一致冻结类别排除得到450条正式人工复核profile。最终可执行审核结构是450条全空白row和410个全空白review block。第8版163条预填和第9版212条预填都属于后续进度快照。

    原始基线已经冻结在`archive/profile_eligibility_review/original_manual_review_20260924`。真正用于以后重新人工复核的文件是`data/02_canonical_manual_review_rows_450_blank.csv`，对应块文件是`data/03_canonical_manual_review_groups_410_blank.csv`。`REVIEW_NOTE.md`说明每个文件的作用；583条与570条文件只解释筛选轨迹，不能作为当前人工任务量。

    ```bash
    python -m pytest \
      tests/test_profile_eligibility_original_freeze.py \
      tests/test_profile_eligibility_audit_freeze.py -q
    ```

    46g会检查三个队列全部为空白决定、profile key唯一、13与120的差额准确、450条身份与triage完全相同、410块人数合计450，并验证450条都存在于29,984条统一inventory。输出档案带逐文件SHA-256；不调用API、不改变当前212条进度、不合并profile或地点，也不修改回归BallTree。

62. 第9版剩余单例审核排序
    46h直接读取第9版450条row文件，要求已有212条决定、剩余238条，并拒绝剩余队列中仍出现共享block。实际核对后，238条全部是单例，其中169条有保存官网、69条没有保存官网；232条属于`external_evidence_required`，5条属于`focused_title_evidence`，1条属于`focused_category_conflict`。

    ```bash
    python -m pytest \
      tests/test_profile_eligibility_singleton_audit.py \
      tests/test_profile_eligibility_original_freeze.py \
      tests/test_profile_eligibility_audit_freeze.py -q

    python scripts/scrape/46h_prepare_singleton_profile_audit.py \
      --run-name full_market_plan_v2 \
      --overwrite
    ```

    输出目录为`data/interim/full_market_plan_v2/profile_eligibility_singleton_audit`。`singleton_profile_audit.csv`完整保留238条未决定profile，`specific_official_page_priority_batch.csv`只保留39条证据最具体的官网页面，summary记录守恒与路由数量。39条优先记录包括4条牙科服务路径、28条名称与页面路径匹配的地点或医生页，以及7条官网结构化地点、医生或服务页。其余5条官网子页、125条官网主页、64条电话加Google profile和5条仅Google profile依次处理。

    页面分类只是审核顺序，不是最终资格判断。即使URL中出现dental，也仍要核对该页面是否对应当前profile地址并提供面向患者的牙科服务；只有主页或搜索不到网页也不能作为排除依据。46h生成的五个`audit_`决定字段全部为空，不会自动修改212条冻结决定、不调用API、不合并profile或地点，也不修改回归BallTree。

63. 39条具体官网记录的一次性应用
    46i不再拆分新的审核小步骤。配套决定文件是人工官网审核输入，不由代码自动生成。脚本负责读取46h的238条和39条文件，逐条核对人工决定的profile key、顺序、证据字段和完整覆盖，再生成四份data输出；profile key、优先序号、决定值或证据字段不一致都会停止。

    ```bash
    python -m pytest \
      tests/test_profile_eligibility_priority_audit.py \
      tests/test_profile_eligibility_singleton_audit.py \
      tests/test_profile_eligibility_audit_freeze.py -q

    python scripts/scrape/46i_apply_specific_official_page_audit.py \
      --run-name full_market_plan_v2 \
      --overwrite
    ```

    真实核对结果为39条中20条纳入、19条排除。212条既有决定追加后变为251条，剩余199条单例。输出目录为`data/interim/full_market_plan_v2/profile_eligibility_priority_audit`，其中更新后的verified文件是下一轮唯一决定基线；remaining文件是下一轮完整工作队列。脚本不提交API、不自动合并profile或地点，也不修改回归BallTree。

64. 剩余199条profile的一次性完成入口
    46j把46i留下的199条单例合并成一份决定表。第一次运行生成`remaining_profile_decisions.csv`，每条同时给出官网、精确Google profile、电话和精确标题地址搜索入口。`remaining_profile_organization_index.csv`只用于复用官网导航，不允许按机构整批决定。

    ```bash
    python -m pytest \
      tests/test_profile_eligibility_completion.py \
      tests/test_profile_eligibility_priority_audit.py \
      tests/test_profile_eligibility_audit_freeze.py -q

    python scripts/scrape/46j_complete_remaining_profile_eligibility.py \
      --run-name full_market_plan_v2 \
      --overwrite
    ```

    只填写同一份CSV中的`manual_decision`、`decision_evidence`、`evidence_url`、`reviewed_by`和`reviewed_on`。199条全部完成后，用同一个脚本应用，不再创建按官网、电话或Google profile拆分的后续脚本：

    ```bash
    python scripts/scrape/46j_complete_remaining_profile_eligibility.py \
      --run-name full_market_plan_v2 \
      --decisions "data/interim/full_market_plan_v2/profile_eligibility_completion/remaining_profile_decisions.csv" \
      --overwrite
    ```

    应用阶段要求199条完整覆盖、身份字段不变、决定值合法且五个审核字段无空白；通过后输出450条最终verified决定。脚本不根据`Medical clinic`自动排除社区医疗中心，因为机构提供牙科不等于当前地址提供牙科，反过来也不能仅凭通用医疗类别判定没有牙科。
