# 奶蛙 Instagram 机器人 · GitHub 版

为 `unimelb.naiwaclub` 开发，运行在 GitHub Actions，通过 GitHub 网页控制。网站仍然是静态网站，机器人不需要常驻服务器。

## 已实现

- 每天 12:00（Australia/Sydney）发布一段奶蛙 Story 视频。
- 从首次恢复日期开始，每 3 个本地日历日的 18:00 发布一条 Reel 或图片 Post。有可用素材时交替选择视频、图片。
- 导入本仓库 `data/images.json`、`data/videos.json`，读取本地素材。现有清单为 24 张图片、3 段视频。
- Story 没有可用视频时，通过 Tavily 全网搜索奶蛙相关内容，每天最多 3 个搜索词。当前按运营者要求，自动检查最多 6 个网页、下载最多 1 段公开 MP4；成功后加入发布池，不再逐条人工审批。
- 自动下载的视频记录 `rights=unverified` 和运营者发布策略，保留来源、文件哈希与下载结果；这代表运营者选择自动发布，不代表系统已经核实第三方转载许可。
- 网络没有可用动态视频时，用 Runway Gen-4 Turbo 生成 3–5 秒奶蛙虚构日常；默认 5 秒、每天最多提交 1 次，成功校验后自动进入发布池。需配置 RUNWAYML_API_SECRET 和 Runway API 额度。
- WEBP/PNG 转成 1080×1350 JPEG；视频转成 1080×1920 H.264/AAC。Story 最长 15 秒，Reels 最长 60 秒；较长视频取开头片段。
- 所有媒体保留来源署名；AI 视频在画面中固定标注 `AI-GENERATED / FICTIONAL DAILY LIFE`，Feed 文案也明确说明。
- 内容哈希去重、30 天重复使用冷却、容器状态检查、失败重试上限、发布结果不确定时停止重发。
- Actions 每次运行提供中文 Summary，显示待审核素材、排期和最近发布记录。

**初始为暂停。** 导入器仍将新增网站清单设为待审核；现有 27 项素材的许可确认通过独立状态分支的运营者审核记录保存。网络自动发布通过下方的明确配置控制，不把未知授权写成“已获许可”。AI 仅作为网络缺片时的备用，已按运营者要求启用。

## 在 GitHub 部署

1. 将 `instagram-bot/` 和 `.github/workflows/naiwa-bot*.yml` 放进 `La-RO/Naiwa` 的默认分支。原有 `data/` 和 `assets/` 保持原路径。
2. 确认仓库是公开仓库，并已开启 Actions。此版本通过公开状态分支托管处理后的媒体，Instagram 必须能直接下载文件；私有仓库需要另接公开对象存储，当前版本会直接拒绝运行。
3. 进入 **Settings → Secrets and variables → Actions → New repository secret**，配置下表。密钥不要放进 GitHub 文件、Issue、Actions 参数或聊天里。
4. 进入 **Actions → Naiwa Bot Tests**，确认测试通过。
5. 进入 **Actions → Naiwa Instagram Bot → Run workflow**，选择 `import`。在本次 Summary 里查看素材 ID。
6. 用 `approve` 审核已有授权的素材，再运行 `check` 检查用户名、账号类型及 ID。该操作不会创建媒体、发帖、搜索或生成 AI 视频，也不会改变暂停状态。成功只说明账号连接及基本读取有效，发布权限和媒体接收仍需首次真实发布验证。随后运行 `preview`；没有授权素材时，预览会显示 `no_approved_material`。
7. 确认账号、素材和排期后运行 `resume`。这只启用机器人，不立即发帖。下次定时任务或手动 `run` 才执行当天已到时间的时段。

| Secret | 是否必需 | 用途 |
| --- | --- | --- |
| `IG_ACCESS_TOKEN` | 首次绑定必需 | Instagram Login 的长效 User Access Token |
| `IG_USER_ID` | 推荐 | 与 token 对应的 Instagram User ID，防止绑错账号 |
| `BOT_ENCRYPTION_KEY` | 发布必需 | 加密长期 token，生成方法见下方 |
| `TAVILY_API_KEY` | 联网搜素材时需要 | 搜索 API；缺失时跳过搜索，不影响已有素材发布 |
| `RUNWAYML_API_SECRET` | 缺片时生成 AI 视频需要 | Runway 开发者项目的 API key；需单独充值 API credits |

`GITHUB_TOKEN` 由 Actions 自动提供，工作流只申请 `contents: write`，用于写入独立状态分支。若组织策略、Ruleset 或分支保护禁止创建/更新 `naiwa-bot-state`，必须先允许这个分支被工作流写入；状态无法保存时，机器人停止发布。

本地 Python 环境安装依赖后生成加密 key：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

将输出保存为 `BOT_ENCRYPTION_KEY`，不要重新生成来替换已使用的 key，除非同时重新绑定账号。

## Instagram 账号与 Meta 应用

账号必须是 **Instagram Business 账号**，因为本项目包含自动 Story。代码每次发布前检查 token 对应的用户名是 `unimelb.naiwaclub`、账号类型是 `BUSINESS`，并核对 `IG_USER_ID`。

1. 在 Meta for Developers 创建支持 **Instagram API with Instagram Login** 的应用，添加 Instagram 产品。
2. 将账号作为应用允许的测试/业务账号并接受邀请，或完成适用的 App Review 和上线配置。
3. 申请 `instagram_business_basic` 与 `instagram_business_content_publish`。发布不需要 Instagram 密码。
4. 取得长效 User Access Token，再填写 GitHub Secrets。不要把 Facebook Login 的 Page token 混用到这个实现。
5. 在 `config.toml` 的 `instagram.api_version` 配置 Meta 应用支持的版本；本项目保守使用 `v24.0`，上线时按应用后台和官方参考确认。

运行时会把 token 加密后保存在状态分支，至少间隔 7 天尝试续期。首次 `IG_ACCESS_TOKEN` 需要是有效长效 token；若长期停机、授权撤销或续期失败，需要重新授权。正常运行优先读取已保存的加密账户记录，避免把自动续期后的 token 换回旧 Secret。

### 更新 token 与重新绑定

仅更新 `IG_ACCESS_TOKEN` 不会覆盖已有绑定。重新授权后按以下步骤操作：

1. 在工作流运行 `pause`，等操作完成。
2. 在 Meta 应用中重新授权 `unimelb.naiwaclub`，使用 Instagram Login 的长效 User Access Token，确认授予 `instagram_business_basic` 与 `instagram_business_content_publish`。权限名称见 [Meta 官方 Collection](https://www.postman.com/meta/instagram/folder/6raa77c/instagram-api-with-instagram-login)。
3. 更新 GitHub Secret `IG_ACCESS_TOKEN`；`IG_USER_ID` 应与该 token 对应账号的 ID 一致。
4. 在同一个工作流选择 `check`，payload 填：

```json
{"use_secret_token":true}
```

此模式直接读取 Secret 中的 token，先验证用户名、账号 ID 和 Business 类型；验证成功后才加密替换旧账户记录。失败时保留原绑定，不修改素材、发布记录或暂停状态。它不创建媒体、不发布内容、不调用 Runway，也不清除状态分支。

成功结果含 `connected: true`、`binding_updated: true` 和 `token_source: IG_ACCESS_TOKEN`。之后普通 `check` 和 `run` 继续读取已保存、可自动续期的绑定；确认连接后按计划运行 `resume` / `run`。

如果新 token 仍在账号校验时返回 HTTP 400、code=200，保持暂停并核对 Meta 应用对该账号的授权、应用角色及权限访问级别。token 显示 Valid 只表示 token 校验有效，不能代替接口权限检查。原始远程错误正文不会写入公开日志；账号校验失败会增加 `Instagram account verification` 阶段标识。

如果应用提供了可用的开发者 token 生成入口，可用它完成初始设置。也附带本地 OAuth helper：

```bash
cd instagram-bot
python -m venv .venv
# 激活虚拟环境后：
python -m pip install -r requirements.txt
# 复制 .env.example 为 .env，配置 IG_APP_ID、IG_APP_SECRET、IG_REDIRECT_URI、BOT_ENCRYPTION_KEY
python -m naiwa_bot oauth-url
# 打开返回的授权 URL。在你登记的 redirect URI 中读取 code 与 state，填入 .env：
# IG_OAUTH_CODE=...
# IG_OAUTH_STATE=...
python -m naiwa_bot oauth-exchange
```

helper 会验证 15 分钟有效的 state，并将 token 写成加密形式。它不提供托管回调网页，你需要使用应用中已登记且可访问的 redirect URI。成功后，先在 GitHub 执行 `import` 创建状态分支，再将本地 `state/state.json` 中已验证的 `account` 对象复制到该分支 `state.json` 的 `account` 字段，两端保持相同 `BOT_ENCRYPTION_KEY`。此路径不需要再填写 `IG_ACCESS_TOKEN`；不要把 `.env`、key 或完整本地工作目录上传。

## 在 GitHub 控制

所有操作都从 **Actions → Naiwa Instagram Bot → Run workflow** 发起。`payload` 填 JSON 对象；不填参数用 `{}`。工作流仅允许在默认分支运行，共享串行并发组，避免多个操作同时写状态。GitHub 默认只保留一个待执行任务，新任务可能替换正在等待的旧任务；请等前一个管理操作完成后再发起下一个，并查看运行结果。

| command | 效果 |
| --- | --- |
| `import` | 导入网站素材，全部先标记待审核，重复执行不会重复添加 |
| `preview` | 预览当天已到时间的时段和可选素材；不会发帖、占用时段或调用搜索/AI |
| `status` | 查看运行状态、素材数和发布记录 |
| `check` | 核对 Instagram 账号连接；payload 为 `{"use_secret_token":true}` 时验证并更新 Secret 中的新 token；保持原暂停状态，不创建或发布媒体 |
| `discover` | 执行当天还没调用过的搜索词，结果只作为来源候选 |
| `add` | 添加可直接下载的公开图片/视频 URL，并锁定审核时的内容哈希 |
| `approve` | 确认版权依据、署名和内容审核，加入发布池 |
| `reject` | 拒绝素材，撤销其发布资格 |
| `resume` / `pause` | 启用 / 暂停后续自动发布和自动搜索 |
| `run` | 按排期执行今天已到时间的时段；暂停时不执行 |
| `retry` | 重新允许一个在调用发布接口前失败的时段再试 3 次 |
| `reconcile` | 人工核实已发出后，补记媒体 ID，关闭结果不确定的任务 |
| `abandon` | 关闭未完成时段，不再补发；结果不确定的素材会被隔离 |

授权已有图片/视频（只有确实取得授权时才填写；下面只是格式示例）：

```json
{"asset_ids":["repo:sanctuary-tour"],"rights":"permission","evidence":"授权记录编号 PERM-001","credit":"Original Creator / used with permission"}
```

`rights` 可选 `owned`、`permission`、`licensed`、`ai`。AI 素材只能用 `ai`；`evidence` 保存不敏感的授权记录编号或许可证链接，`credit` 保存发布时显示的署名。原始授权信件和私人信息不要放在公开状态分支。

## 缺视频时自动网络补片

当前默认配置按运营者指示启用自动网络补片，AI 只在成功搜索且确认没有可用视频后作为备用：

```toml
[discovery]
enabled = true
hour = 9
only_when_story_empty = true
auto_publish = true
operator_policy = "Operator requested automatic web video publication without individual review on 2026-10-23; reuse rights unverified."
keywords = ["奶蛙", "naiwa"]
max_results = 6
max_auto_videos_per_day = 1
max_candidate_checks_per_day = 6
queries = ["奶蛙 视频 mp4", "Naiwa 奶蛙 视频", "奶蛙 短视频"]
```

在 GitHub Secrets 添加 `TAVILY_API_KEY` 使用搜索服务；添加 `RUNWAYML_API_SECRET` 并为 Runway 开发者项目充值，才可使用备用生成。已有可用 Story 视频时不自动调用搜索；库存为空时，在搜索时段之后收集候选，并在当天 Story 时段尝试提取和下载视频。暂停时不会自动搜索或下载。

自动流程支持公开 MP4 直链，以及静态网页的 `<video>`、Open Graph 和 JSON-LD 视频地址。只依据标题和搜索摘要筛选奶蛙相关性，不进行 AI 视觉识别。不能保证每个搜索结果都能下载；需要登录、播放器脚本或不可直接取出媒体的网站会跳过。没有可用结果时记录 `blocked`，不会发布一个网页链接冒充视频。

下载上限为 80 MB，验证 MP4、可读时长及前 60 秒的解码，再保存文件。原始视频须为 3 秒到 10 分钟，发布时仍裁成 Story 最长 15 秒、Reels 最长 60 秒。重复哈希不入库；临时文件放在 scratch，不提交到公开媒体分支。每日搜索、网页检查和成功入库计数先写状态，重复小时运行不会无限下载。

自动素材的 `rights=unverified`、`approval_mode=automatic_operator_policy`、`evidence` 会明确保存发布策略；`reviewed=true` 在此表示流程已自动接纳，不表示经过人工内容或版权审核。关闭 `auto_publish` 停止新的自动入库；已接纳的素材可用 `reject` 撤销，或先 `pause` 停止发布。

“AI 生成”本身不构成全网素材可以自由转载的证明。相关解释见 [IP Australia 的 AI 与知识产权说明](https://ipfirstresponse.ipaustralia.gov.au/options/considerations-when-using-artificial-intelligence-create-ip-0)。此流程不会自动作出法律许可判断。

添加网络素材：

```json
{"kind":"video","title":"奶蛙的下午","url":"https://your-public-media.example/naiwa.mp4","source_url":"https://creator.example/original-post","ai_generated":false}
```

把示例域名换成真正的公开直链。普通视频网页并不一定包含可直接取出的 MP4。手动 `add` 的素材继续走 `approve`；自动入库采用上方独立的运营者策略。工具不绕过登录、付费墙或 DRM。公开 URL 不得携带账号密码，下载限制为 80 MB；自动入库会保存审核时下载的文件，发布前重新校验哈希。

拒绝素材：

```json
{"asset_ids":["repo:sanctuary-tour"]}
```

发布前失败后重试：

```json
{"slot":"story:2026-10-22"}
```

发布结果超时后，先查看 Instagram。确认已经发出，再 `reconcile`：

```json
{"slot":"story:2026-10-22","media_id":"实际的数字媒体ID","evidence":"运营人员已在账号中核对，记录 CHECK-001"}
```

不确定是否已发出而决定跳过，选择 `abandon`：

```json
{"slot":"story:2026-10-22","evidence":"已人工核对并决定关闭该时段，记录 CHECK-002"}
```

`needs_review` 状态永远不会自动重发。`reconcile` 的媒体 ID 是人工核对结果，本命令不会替你证明该 ID 的归属。暂停不会撤回已经发出的内容；若运行正在发帖，请等它结束，随后执行暂停。不要在 `publishing` 阶段直接取消运行；即使取消，下一次运行也会要求人工核对。

## 图片、Reels 与备用短视频

图片只发 JPEG 图片 Post；不会把图片加上平移、缩放或转场再发成 Reels。Reels/Story 必须使用实际可解码且有动态画面的视频。网站原有三段 `sanctuary-tour`、`wallpaper-tunnel`、`laughing-gallery` 是图片画廊巡展，现标记为 `videoStyle=slideshow`，不再进入自动视频池；每次导入都会把该标记同步到已有状态，保留原来的许可和发布记录。

未完成任务在使用旧缓存或旧 Instagram 容器前重新检查素材类型与内容规则。旧缓存会按新版本重新生成；如果素材被归类为图集，未发布任务重新选片。正在发布但结果不明的任务继续进入人工核对，防止重复发出。

备用生成使用 **Runway Gen-4 Turbo**：

```toml
[ai]
provider = "runway"
enabled = true
duration_seconds = 5
model = "gen4_turbo"
reference_image = "assets/gallery/l-18.webp"
character_description = "Naiwa, a round yellow cartoon mascot with green eyes, a small head and a large soft belly"
character_rights_confirmed = true
auto_approve = true
max_requests_per_day = 1
daily_scenes = ["making breakfast", "reading in a library", "taking a walk in the park"]
```

`duration_seconds` 只接受 3、4、5，默认生成 5 秒、720×1280 竖屏视频。参考图片交给视频模型保持奶蛙外观；机器人不会在本地把图片拼成循环或平移视频。提示词要求角色身体动作，生成结果须通过 MP4、解码、动态画面采样、时长及哈希去重校验。发布转码保留 3–5 秒限制，烧录 AI 虚构日常标记；Feed 文案也有说明。

在 [Runway Dev](https://dev.runway.com/) 注册开发者账户并创建项目，在 **API Keys** 新建 key，然后在仓库 **Settings → Secrets and variables → Actions** 添加 `RUNWAYML_API_SECRET`。在 Runway 项目的 Billing 充值 API credits。不要把 key 填进工作流参数或提交为文件。

按 2026-10-24 核实的 [Runway 官方 API 价格](https://docs.dev.runwayml.com/guides/pricing/)，`gen4_turbo` 每秒 5 credits，每 credit US$0.01，5 秒约 **US$0.25**（税费另计）。开发者平台首次充值最低 US$10，见 [官方设置指南](https://docs.dev.runwayml.com/guides/setup/)。已有网络视频时不提交生成请求；没有 Runway key 时已有图片 Post 和合格网络视频仍正常发布。

只有成功搜索、检查候选后确认没有可用视频，才允许提交新的生成任务。搜索 key 缺失、搜索超时、限流或网页临时不可访问，不会触发新的付费任务。每次提交先保存每日请求占用，拿到任务编号后立即保存。提交结果不明时保留当日占用，不自动重复提交；历史 Gemini 请求记录也继续计入同日总限额。

Runway 是异步接口。本次运行查询一次状态；未完成时 Story 记录为 `generating`，本次结果为 `waiting`。后续每小时运行继续查询**同一个任务**，完成后下载并发布，所以首次需要生成的 Story 可能延后一个或多个小时。手动 `run` 也可以继续检查，机器人对同一个任务至少间隔 5 秒查询。

已保存的任务优先续查，跨日或当天搜索失败时也不会重新提交。查询或下载临时失败保留任务编号，下一次只重试查询/下载；任务失败、取消、失效或视频校验不合格时，保留当日次数并记录原因。生成服务失败不阻止同日图片 Post 发布。临时下载链接不会写入公开状态；完成视频保存在状态分支，以稳定链接交给 Instagram。

画面变化检测可以拦截纯静止MP4，但不能可靠识别所有带缩放或转场的第三方图集。已知三个图集通过内容元数据明确排除。测试使用本地真实转码与模拟 Runway 响应，没有调用实际付费生成。

## 排期、存储与恢复

- Story 使用视频素材；图片用于 Feed。Feed 在有可用素材时交替选择 Reel 和图片，无对应类型素材时使用另一种。
- 排期使用悉尼本地日历，自动处理夏令时。默认 Story 12:00、Feed 18:00；每三天从首次 `resume` 当天起算。也可以提前设置 `schedule.start_date = "2026-10-22"`。
- GitHub 每个 UTC 小时的第 17 分钟唤醒一次，代码判断本地时段是否到达。GitHub 计划任务可能延迟、漏触发或因仓库长期无活动被停用；这是低频内容发布方案，不承诺分钟级准点。没有补发过去日期的积压队列。
- 素材不足时保留 `blocked` 记录。补充并审核素材后，当天后续运行可以继续；跨过日期则等待下一次正常排期。
- 状态存于独立分支 `naiwa-bot-state` 的 `state.json`，处理后的公开媒体存于同分支 `media/`，不会修改官网目录。
- Instagram 拉取的是带提交 SHA 的公开媒体链接。它无需知道 GitHub token。token 本身只以 Fernet 密文保存，key 只在 Secrets。
- 每次关键操作先推送状态，再调用发布接口；推送失败会停止后续动作。网络系统无法保证绝对 exactly-once，因此未知结果采用人工核对，优先避免重复公开内容。
- 状态分支是公开数据，包括素材来源、署名、非敏感授权记录编号和操作时间；切勿写入私信、邮件原文或其他隐私。日志与上传的 Summary 不包含 API key 或明文 token。
- 媒体保存在 Git 历史中，长期生成视频会增加仓库体积。当前限制媒体工作树合计 400 MB，达到后停止写入并需要维护；删除文件不会自动清理历史。长期运营建议更换到公开对象存储，保留本项目的 GitHub 控制入口和排期。不得在仍有 `waiting` / `publishing` 任务时清理它依赖的文件。

常见问题：

| 表现 | 处理 |
| --- | --- |
| 账号类型错误 | 将账号转为 Business，重新授权 |
| 绑定用户名不匹配 | 重新取得 `unimelb.naiwaclub` 的 token，不要忽略校验 |
| 没有已审核素材 | `import` / `add` 后，在有授权依据时 `approve` |
| `failed` | 看 Summary / 状态分支；修复授权、媒体格式、网络或 Meta 权限，必要时 `retry` |
| `needs_review` | 先人工检查 Instagram；用 `reconcile` 或 `abandon`，不要重新发同一条 |
| 已 `resume` 但没发 | 检查本地时段、三天周期、素材审核与 Actions 最近运行时间 |
| `Public media` / state push 失败 | 确认仓库公开、工作流有写权限、状态分支未被策略阻止 |

## 本地验证

在完整 Naiwa 仓库内执行：

```bash
cd instagram-bot
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m naiwa_bot preview
```

本地默认只预览，不会发帖。模拟测试覆盖真实目录导入、授权门槛、日历周期、夏令时、hash 去重、视频转码、AI 画面标记、token 加密、账号核对、搜索限额、Runway 每日限额、异步任务恢复、输出校验和发布不确定时停止重试。真实 Instagram 发布、Meta App Review、GitHub 工作流执行与实际付费视频生成，需要连接账号后再验收。

## 官方参考

- [Meta Instagram Platform 内容发布](https://developers.facebook.com/docs/instagram-platform/content-publishing)
- [Meta 官方 Instagram API Collection](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api)
- [GitHub 定时与手动触发](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [GitHub 任务并发控制](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
- [Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- [Runway API 入门](https://docs.dev.runwayml.com/guides/using-the-api/)
- [Runway API 价格](https://docs.dev.runwayml.com/guides/pricing/)
- [Runway 输出与临时链接](https://docs.dev.runwayml.com/assets/outputs/)
