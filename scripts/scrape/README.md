1. 文件夹用途
   scripts/scrape负责Malone和Syracuse两个错误地区的诊所重新发现、地点核实、评论抓取和结果解析。
   当前批次名称为rescrape_malone_syracuse_20260907。所有脚本都应在项目根目录和已激活的.venv中运行。

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

9. 不应手动修改的文件
   原始JSON、任务日志以及脚本生成的CSV和JSON不应手动修改。
   需要修正人工判断时，应修改config中的决定文件，再重新运行对应脚本。
   data/raw和data/interim不提交到Git，但原始JSON和任务日志必须另外备份。

10. 多抓问题
    本次为保持旧数据口径，沿用了53组关键词和两个搜索接口，因此产生大量目标ZIP外候选。
    1120个CID中只有231个位于目标ZIP，最终只有187个资料通过牙科和地理资格审核。
    全市场重抓前应按docs/search_scope_revision.md精简关键词，并先完成CID去重、ZIP确认、类别审核和实体地点归并，再提交评论任务。

11. 当前下一步
    将109个新实体地点和14310条新评论与旧Malone及Syracuse错误批次进行替换审计。
    只移除错误location code产生的旧诊所和评论，保留其余13个地区的数据。
    替换后重新计算entry_date、地区资格和空间资格，再重建2008至2025年年度面板并运行完整测试。
