# 奶蛙 Instagram 机器人 · GitHub 版

为 `unimelb.naiwaclub` 开发，运行在 GitHub Actions，通过 GitHub 网页控制。网站仍然是静态网站，机器人不需要常驻服务器。

## 已实现

- 每天 12:00（Australia/Sydney）发布一段奶蛙 Story 视频。
- 从首次恢复日期开始，每 3 个本地日历日的 18:00 发布一条 Reel 或图片 Post。有可用素材时交替选择视频、图片。
- 导入本仓库 `data/images.json`、`data/videos.json`，读取本地素材。现有清单为 24 张图片、3 段视频。
- 每天最多 3 次 Tavily 搜索，搜索结果进入候选库；人工确认内容和转载授权后，才进入自动发布池。
- 可选 AI 虚构日常视频：Gemini Interactions API，支持带角色参考图生成 9:16 视频，默认每天最多请求 1 次。
- WEBP/PNG 转成 1080×1350 JPEG；视频转成 1080×1920 H.264/AAC。Story 最长 15 秒，Reels 最长 60 秒；较长视频取开头片段。
- 所有媒体保留来源署名；AI 视频在画面中固定标注 `AI-GENERATED / FICTIONAL DAILY LIFE`，Feed 文案也明确说明。
- 内容哈希去重、30 天重复使用冷却、容器状态检查、失败重试上限、发布结果不确定时停止重发。
- Actions 每次运行提供中文 Summary，显示待审核素材、排期和最近发布记录。

**初始为暂停，现有 27 项素材全部为待授权。** 原网站清单明确表示作者和转载授权未核实；“来自我们的网站”不能自动等同于素材归我们所有。机器人不会替你声称已取得授权。

## 在 GitHub 部署

1. 将 `instagram-bot/` 和 `.github/workflows/naiwa-bot*.yml` 放进 `La-RO/Naiwa` 的默认分支。原有 `data/` 和 `assets/` 保持原路径。
2. 确认仓库是公开仓库，并已开启 Actions。此版本通过公开状态分支托管处理后的媒体，Instagram 必须能直接下载文件；私有仓库需要另接公开对象存储，当前版本会直接拒绝运行。
3. 进入 **Settings → Secrets and variables → Actions → New repository secret**，配置下表。密钥不要放进 GitHub 文件、Issue、Actions 参数或聊天里。
4. 进入 **Actions → Naiwa Bot Tests**，确认测试通过。
5. 进入 **Actions → Naiwa Instagram Bot → Run workflow**，选择 `import`。在本次 Summary 里查看素材 ID。
6. 用 `approve` 审核已有授权的素材，再运行 `preview`。没有授权素材时，预览会显示 `no_approved_material`。
7. 确认账号、素材和排期后运行 `resume`。这只启用机器人，不立即发帖。下次定时任务或手动 `run` 才执行当天已到时间的时段。

| Secret | 是否必需 | 用途 |
| --- | --- | --- |
| `IG_ACCESS_TOKEN` | 首次绑定必需 | Instagram Login 的长效 User Access Token |
| `IG_USER_ID` | 推荐 | 与 token 对应的 Instagram User ID，防止绑错账号 |
| `BOT_ENCRYPTION_KEY` | 发布必需 | 加密长期 token，生成方法见下方 |
| `TAVILY_API_KEY` | 联网搜素材时需要 | 搜索 API；缺失时跳过搜索，不影响已有素材发布 |
| `GEMINI_API_KEY` | 生成 AI 视频时需要 | 有视频生成权限和可用额度的 Gemini API key |

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

运行时会把 token 加密后保存在状态分支，至少间隔 7 天尝试续期。首次 `IG_ACCESS_TOKEN` 需要是有效长效 token；若长期停机、授权撤销或续期失败，需要重新授权。已有加密账户记录时，以该记录为准；重新绑定时，在暂停状态下按本地 OAuth 流程替换账号记录，或在备份后移除状态文件中的 `account` 对象，让下次运行读取新的 Secrets。

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

添加网络素材：

```json
{"kind":"video","title":"奶蛙的下午","url":"https://your-public-media.example/naiwa.mp4","source_url":"https://creator.example/original-post","ai_generated":false}
```

把示例域名换成真正的公开直链。普通视频网页、Bilibili/TikTok/Instagram 页面并不是媒体直链。搜索只帮助发现内容，不能自动授予下载或转载权限；获得作者许可并拿到可用文件后再 `add` 和 `approve`。工具不绕过登录、付费墙、防盗链或 DRM。公开 URL 不得携带账号密码，下载限制为 80 MB；发布时会重新校验内容哈希，链接内容变化就停止。

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

## AI 虚构日常

AI 生成初始关闭，也不会消耗 API 费用。准备有权使用的奶蛙参考图后，在默认分支修改 `instagram-bot/config.toml`：

```toml
[ai]
enabled = true
model = "gemini-omni-1.1-flash"
reference_image = "assets/your-licensed-naiwa-reference.png"
character_description = "Naiwa, a round yellow cartoon mascot with green eyes, a small head and a large soft belly"
character_rights_confirmed = true
auto_approve = false
max_requests_per_day = 1
daily_scenes = ["making breakfast", "reading in a library", "taking a walk in the park"]
```

并设置 `GEMINI_API_KEY`。当当天 Story 没有合适的已审核视频时，机器人最多申请指定次数的 AI 视频。输出初始进入待审核，先在状态分支的媒体文件中查看，再 `approve`。只有明确把 `auto_approve = true` 后，后续生成的视频才直接进入发布池；角色和参考图的权利确认仍然必需。

生成请求在发起前计入每日次数，超时也不退回次数，避免重复收费。每天 1 次是请求上限，并不是金额预算；实际价格和权限以服务商账户为准。生成效果、角色一致性和请求成功率都依赖供应商，配置可更换模型。AI 审核关闭、无授权素材、API 故障或额度不足时，机器人会记录阻塞/失败，不能保证每天都有成功发布。

截至 2026-10-22，OpenAI 官方停用清单说明 Sora 2 / Videos API 已于 2026-09-24 下线，因此此版本没有连接已失效的 Sora 接口。Google 当前官方文档提供 Gemini Omni Flash 的视频接口；该适配器已通过模拟响应测试，没有使用真实付费密钥调用。

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

本地默认只预览，不会发帖。模拟测试覆盖真实目录导入、授权门槛、日历周期、夏令时、hash 去重、视频转码、AI 画面标记、token 加密、账号核对、搜索限额、AI 请求限额和发布不确定时停止重试。真实 Instagram 发布、Meta App Review、GitHub 工作流执行与实际付费视频生成，需要连接账号后再验收。

## 官方参考

- [Meta Instagram Platform 内容发布](https://developers.facebook.com/docs/instagram-platform/content-publishing)
- [Meta 官方 Instagram API Collection](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api)
- [GitHub 定时与手动触发](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [GitHub 任务并发控制](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
- [Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- [Google 视频生成和 Interactions 接口](https://ai.google.dev/gemini-api/docs/omni)
- [OpenAI API 停用清单](https://developers.openai.com/api/docs/deprecations)
