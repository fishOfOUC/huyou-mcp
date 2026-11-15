# 狐友 MCP（huyou-mcp）

用 MCP 帮你逛搜狐「狐友」的校园圈子，看校友发了什么，每条都给出可直接点开的帖子链接。

已经做到的：
- 免登录读取圈子动态、帖子详情、评论与楼中楼；
- **只挑「有实用信息」的帖子**（校园跑技巧、哪门课老师好、真题资料、办事流程、失物二手……），
  抱怨骂人、找对象、打探钱、八卦、广告、水贴不进邮箱；
- 汇总成邮件推送到 QQ 邮箱；
- 评论 / 点赞的代码也写好了，默认关闭（扫码登录后可开）。

> 站点：<https://hy.sns.sohu.com/?tab=circle>（狐友 Web 版，搜狐的校园/兴趣社区）

---

## 一、先调研：有没有现成能用的？

结论：**没有现成的狐友工具，狐友这一层必须自己实现；底层全部复用成熟件。**

| 调研方向 | 结果 |
| --- | --- |
| 现成 MCP（狐友 / 搜狐社交） | 没有。npm 上 `huyou` 只是阿里的 UI 主题包，PyPI 无同名包，GitHub 上没有狐友 Web 端的 MCP 或抓取库 |
| 官方 API | 没有。狐友只对 App/小程序开放，Web 端是 Nuxt 3 SPA 直接调内部 JSON 接口 |
| 通用浏览器自动化 MCP（如 Playwright MCP、Chrome DevTools MCP） | 可以做「点开网页看一眼」，但要长期无人值守地跑，就得常驻浏览器 + 每次让模型读页面，慢、贵、易碎，而且它不会自己发摘要邮件 |
| 社区逆向资料 | 只覆盖 App 端（unidbg 复刻 SO 里的 `SohuSign` 签名）。Web 端没人做过，签名算法这次是自己逆向 + 实测验证的 |
| 可复用的成熟件 | MCP 官方 Python SDK（`mcp` 2.3，`MCPServer`）、`httpx`、标准库 `smtplib`（QQ 邮箱）、Windows 计划任务 |

所以本项目的定位是：**只写「狐友接口 + 业务编排」这一层，其余不重复造轮子。**

---

## 二、实现原理：Web 端接口逆向结果

### 1. 接口与签名
- 网页数据全部走 `https://cs-ol.sns.sohu.com`（另有 `op-` / `dm-` 两个网关）。
- 每个业务请求都要签名，等价于前端 bundle 里的 `Hi()`：

  ```
  参数（GET 放 query / POST 放 form）里补 flyer、appid、app_key_vs
  pairs = [f"{k}={v}" ...] + [f"s-nonce={s-nonce}", f"S-VS={S-VS}"]
  sig   = md5("".join(sorted(pairs)) + app_key)
  ```
- 请求头：`S-PID(hyuid)` `S-PPID(pchypp)` `S-VS` `S-CID/gid=gidinf` `token(pchytk)` `P-APPID` `appid` `s-nonce` `flyer`。
- `gidinf`（设备号）不是登录态，访问一次 `https://passport.sohu.com` 就会下发，程序启动时自动领。
- 签名实现见 [`crypto.py`](src/huyou_mcp/crypto.py)，用 Node 版「前端逻辑复刻」生成的固定向量做交叉校验（[`tests/test_crypto.py`](tests/test_crypto.py)）。

### 2. 用到的接口

| 用途 | 方法 & 路径 | 关键参数 | 是否需要登录 |
| --- | --- | --- | --- |
| 圈子分类 | `GET /v9/circle/category/list` | – | 否 |
| 分类下的圈子 | `GET /v9/category/circle/list` | `category_type=1&category_id=4`（校园）/ `2`（热门聚合）/ `3`（新圈速报） | 否 |
| 搜圈子 | `GET /v8/circle/suggest/search` | `query`、`page_index` | 否 |
| 圈子动态列表 | `GET /v8/circle/feed/list` | `circle_id`、`list_type`(1 热门/2 新发/3 精华/4 新回)、`score`(翻页游标)、`count` | 否 |
| 动态详情 | `GET /v7/feeds/show` | `feed_id` | 否 |
| 评论列表 | `GET /v8/comment/list` | `feed_id`、`score`、`count`；返回项自带 `replies.list`（楼中楼） | 否 |
| 楼中楼回复 | `GET /v8/comment/replylist` | `feed_id`、`comment_id`、`score`、`count` | 否 |
| 发评论 | `POST /v8/comment/text` | `feed_id`、`content`、`comment_type`、`tid`（回复时带 `reply_comment_id`） | **是** |
| 评论点赞 | `POST /comment/like/v20` | `feed_id`、`comment_id`、`type`(1 赞 / 2 取消) | **是** |
| 扫码登录 | `POST /v8/login/qrcode/create` + 轮询 `pol.passport.sohu.com/passportapi/polling/apptkbyhy` | `serialno` | – |
| 当前用户 | `POST /v6/users/show_reduced` | `user_id` | **是** |

### 3. 两个关键细节
- **帖子链接**：前端把详情做成弹窗，深链就是 `https://hy.sns.sohu.com/?feedDetail=<feed_id>`，点开直接是那条动态的详情。
- **发帖时间**：「新发」列表里每条动态的 `score` 就是发帖时间的毫秒时间戳（热门/精华排序的 score 是复合打分，不能当时间用，代码里已做区分）。

评论同样是**免登录可读**的：`/v8/comment/list` 一次就带回一级评论 + 每条的 `replies.list`（楼中楼），
字段有 `userName`、`content`、`timeId`（毫秒）、`likeCount`、`liked`、`replyCount`、`replyUserName`。
列表里若带 `sourceRegion` 就是评论者 IP 属地（比如「北京」）。狐友AI助手的自动回复会带 AI 字样，摘要里已过滤。

---

## 三、现在能做什么

### MCP 工具（16 个）
浏览类（不需要登录）：

| 工具 | 作用 |
| --- | --- |
| `huyou_categories` | 圈子分类 |
| `huyou_campus_circles` | 校园分类下的高校圈子 |
| `huyou_search_circles` | 按学校名搜圈子 |
| `huyou_circle_feeds` | 圈子动态（新发/新回/热门/精华，带游标翻页，每条含链接） |
| `huyou_feed_detail` | 单条动态详情 |
| `huyou_feed_comments` | 评论列表（含楼中楼回复、comment_id，可用于回复/点赞） |
| `huyou_comment_replies` | 某条评论下的全部楼中楼回复（分页） |
| `huyou_watch_list` | 配置里关注的圈子 |

推送类（只发「有实用信息」的帖子，见下方筛选口径）：

| 工具 | 作用 |
| --- | --- |
| `huyou_new_feeds` | **两步走第一步**：列出本轮新帖（带规则判定 `rule_useful` / `rule_says`），不发信、不标已读 |
| `huyou_send_digest` | **两步走第二步**：按你挑的 `feed_ids` 发信，`note` 写在邮件顶部；不传则发规则筛过的那些 |
| `huyou_alumni_digest` | **一键**：抓新帖 → 规则过滤 → 发 QQ 邮件；`preview_only=true` 只渲染不发信 |

账号/写操作类：

| 工具 | 说明 |
| --- | --- |
| `huyou_login_status` / `huyou_login_qrcode` / `huyou_login_poll` | 扫码登录（二维码落盘成图片路径） |
| `huyou_post_comment` / `huyou_like_comment` | 评论 / 给评论点赞，**默认关闭**，需 `[write] enabled = true` |

### 推送筛选口径（写进了 MCP instructions，模型每次都会看到）

用户明确要求：**只发有实用信息的帖子**。

- ✅ 发：校园跑怎么更省事、体测技巧；哪门课老师好/不好、给分点名选课建议；考试真题复习资料、
  绩点保研考研实习招聘；办事流程（校医院、户籍、报销、校园卡、报修、电费网费）；
  食堂外卖快递、失物招领、二手闲置等具体信息；讲座比赛社团活动、学校通知政策。
- ❌ 不发：纯抱怨和情绪发泄、骂人脏话；与学习/校园无关的无意义提问（找女朋友、大家有多少钱）；
  八卦吃瓜挂人；抽奖拉群广告商单；几个字的纯水贴。
- ⚠️ 判不准时倾向不发。

实现分两层：[`filters.py`](src/huyou_mcp/filters.py) 规则初筛（关键词打分，保证命令行/定时任务单独跑也有效），
MCP 里再由模型用 `huyou_new_feeds` 复核一遍。今天海大圈实测：6 小时 54 条新帖 → 36 条有用（过滤 18 条）。

### 命令行

```powershell
huyou-mcp smoke                                   # 端到端自检：搜圈→动态→详情→评论
huyou-mcp circles --category campus --limit 10    # 校园圈子
huyou-mcp circles --search 中国海洋大学            # 搜学校圈子
huyou-mcp feeds 874712662708262400 --sort new     # 看新帖（打印帖子链接）
huyou-mcp feed <feed_id>                          # 看详情（含配图 URL）
huyou-mcp comments <feed_id>                      # 看评论
huyou-mcp digest --dry-run                        # 渲染今日摘要到 data/outbox（不发信）
huyou-mcp digest                                  # 抓 + 按筛选口径过滤 + 发 QQ 邮件
huyou-mcp mail-test                               # 发测试信，验证 QQ 授权码
huyou-mcp login                                   # 扫码登录（写操作前需要）
huyou-mcp serve                                   # 以 MCP server 方式跑（stdio）
```

---

## 四、安装

已在本机 Windows + Python 3.12 验证。

```powershell
cd <你的目录>\huyou_auto
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
copy config.example.toml config.toml     # 之后按需改
.\.venv\Scripts\python.exe -m huyou_mcp.cli smoke
```

单元测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

### 注册到 MCP 客户端

DSH / Claude Desktop / Cursor 这类客户端都吃同样的结构（命令写绝对路径）：

```json
{
  "mcpServers": {
    "huyou": {
      "command": "<你的目录>\\huyou_auto\\.venv\\Scripts\\python.exe",
      "args": ["-m", "huyou_mcp.cli", "serve"],
      "cwd": "<你的目录>\\huyou_auto"
    }
  }
}
```

---

## 五、推送配置（当前：随叫随刷）

> 现状：**没有注册任何计划任务**。你想刷的时候说一句「刷一下狐友」，AI 就调
> `huyou_alumni_digest` 抓新帖并发 QQ 邮件；也可以自己跑 `huyou-mcp digest`。
> 已推送过的帖子记录在 `data/state.json`，重复刷只会推新的。

当前 `config.toml`（凭证在本地文件里，`.gitignore` 已排除，不进版本库）：

```toml
[watch]
schools = ["中国海洋大学"]      # 自动搜圈子并缓存 id（海大 = 874712662708262400）
circle_ids = []                # 也可以直接写圈子 id
sorts = ["new"]                # new 新发 / reply 新回 / hot 热门 / elite 精华
per_circle = 20                # 每页条数
max_pages_per_circle = 10      # 最多翻几页（10 页 ≈ 200 条，覆盖活跃圈一天）
max_age_hours = 36             # 只推这个时间窗内的帖子
hot_comment_threshold = 2      # 评论数 ≥ 2 算「有讨论」，邮件里重点展示
skip_top = false               # true = 跳过置顶（多是圈公告/商单）

[mail]
enabled = true
user = "发件QQ号@qq.com"
password = "QQ邮箱授权码"      # 不是登录密码
to = ["收件邮箱@qq.com"]
max_posts = 120                # 一封邮件最多展示多少条
only_hot = false               # true = 只推「有讨论」的帖子
include_comments = true        # 给「有讨论」的帖子附上评论
comment_preview_count = 3      # 每条帖子附几条评论

[filter]
enabled = true                 # 只推有实用信息的帖子（抱怨/骂人/找对象/打探钱/八卦/广告/水贴都过滤）
min_score = 2                  # 2=较宽（命中一个实用主题就推）；3=更严；1=更宽
extra_useful = []              # 额外「一定推」的词，例如 ["实习","考研"]
extra_noise = []               # 额外「一定不推」的词，例如 ["二手","失物"]
```

常用命令：

```powershell
huyou-mcp digest                 # 抓新帖 + 发邮件（AI 就是调这个）
huyou-mcp digest --dry-run       # 只渲染，不发信、不更新已读
huyou-mcp mail-test              # 发一封测试信，验证授权码对不对
```

- 授权码获取：`mail.qq.com` → 设置 → 账户 → 开启「POP3/SMTP 服务」→ 生成授权码。
- 改完 `password` 后跑一次 `huyou-mcp mail-test`，收到就说明通了。
- 授权码等于邮箱的发送权限，**别提交到 git、别贴到公开地方**；怀疑泄露就去 QQ 邮箱「删除授权码」再生成新的。
- 想改回定时推送：`scripts\daily-digest.ps1` + `schtasks` 一行即可（脚本已就绪，日志写 `data\digest.log`）。

### 推送量怎么调（以海大圈实测为准）

中国海洋大学圈（`874712662708262400`）**一天大约 160～200 条新帖**，其中约 70 条有评论。
默认一封信 = 「有讨论」卡片最多 20 张 + 「其他动态」紧凑列表，合计不超过 `max_posts`。

| 想要的效果 | 改法 |
| --- | --- |
| 只要有人讨论的 | `only_hot = true`（约 70 条/天） |
| 邮件更短 | 调小 `max_posts`（比如 40），其余进本地存档 |
| 想连更早的也补推 | 临时把 `max_age_hours` 调大，再 `huyou-mcp digest` |
| 连置顶公告也不要 | `skip_top = true` |
| 只想看某个时段 | 想刷的时候再让 AI 调一次，`since` 会自动接上次的位置 |

---

## 六、下一阶段：评论 / 点赞

代码已经写好，只是默认关着：

1. `huyou-mcp login`（或 MCP 里 `huyou_login_qrcode` + `huyou_login_poll`）用狐友 App 扫码，登录态存 `data/cookies.json`；
2. `config.toml` 里 `[write] enabled = true`；
3. 之后 `huyou_post_comment` / `huyou_like_comment` 才可用。

注意两点：
- 发评论接口带风控（前端在失败后会用 `vcode_token` 重试一次），首次真实发评建议手动盯一次；
- 这是拿真实账号操作，建议低频、内容自己把关，别当刷量工具用。

---

## 七、目录结构

```
src/huyou_mcp/
  constants.py   接口常量（网关、App 凭证、路径、链接模板）—— 搜狐改版先改这里
  crypto.py      签名：nonce + md5(sig)
  session.py     带签名的会话、cookie 持久化、gidinf 引导、代理处理
  models.py      Circle / Feed / Comment 归一化
  api.py         业务接口（圈子、动态、详情、评论、评论点赞、扫码登录校验）
  auth.py        扫码登录 + 从浏览器导入 cookie
  filters.py     筛选规则：实用主题 / 噪音主题打分
  service.py     编排：关注圈子解析、采集去重、筛选、摘要渲染、已读状态
  mailer.py      QQ 邮箱 SMTP
  server.py      MCP 工具层（工具定义 + 筛选口径写进 instructions）
  cli.py         命令行 / 计划任务入口
tests/           单测 34 个：签名交叉校验、模型归一化、筛选规则
_recon/          逆向时的探测脚本（下载的第三方 bundle / 页面快照 / 接口样本不入库）
```

## 八、已知限制

- 非官方接口。搜狐改版可能导致签名或参数变化，`_recon/` 里的脚本可以重新抓 bundle、比对路径。
- 只读浏览完全不需要账号；写操作一旦开启就是真实账号行为，风险自负。
- `data/cookies.json` 等于账号凭证，别提交、别外发（`.gitignore` 已排除）。
- 仓库里不带任何真实凭证：`config.toml`、`data/` 全部被忽略，模板见 `config.example.toml`。

## 九、免责声明

仅供个人学习与自用阅读，不提供任何绕过登录、批量刷量或商业化能力。
接口来自前端逆向，与搜狐官方无关；使用产生的任何后果由使用者自负。
抓到的帖子内容版权属于原作者，请勿转载或用于训练/发布。
