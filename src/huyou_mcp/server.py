"""MCP 工具层：把狐友的浏览能力暴露给 AI 客户端。

启动方式：
    huyou-mcp serve                # 默认 stdio
    huyou-mcp serve --http 8765    # streamable-http（可选）

设计约定：
    - 只读工具不需要登录，可直接用；
    - 需要登录的工具（评论/点赞）额外受 config.toml 的 [write] enabled 控制；
    - 所有工具返回 JSON 字符串，字段名保持稳定，方便下游解析。
"""

from __future__ import annotations

import functools
import json
from typing import Any, Callable

from mcp.server.mcpserver import MCPServer

from . import constants as C
from .auth import poll_qr_login, start_qr_login
from .config import Config, load_config
from .service import HuyouApp
from .session import HuyouError

mcp = MCPServer(
    "huyou",
    instructions=(
        "狐友（搜狐校园社交）MCP：浏览「中国海洋大学」等校园圈子里校友的最新动态，并按需发邮件。\n"
        "\n"
        "【浏览】先用 huyou_search_circles 找学校圈子，再用 huyou_circle_feeds 看动态，"
        "每条动态都有可直接点开的链接（https://hy.sns.sohu.com/?feedDetail=<id>），"
        "huyou_feed_comments / huyou_comment_replies 看评论和楼中楼。\n"
        "\n"
        "【发邮件：只发“有实用信息”的帖子】用户明确要求过滤，判断口径如下——\n"
        "  ✅ 要发：校园跑怎么更省事、体测/体育课技巧；哪门课老师好或不好、给分/点名/选课建议；"
        "考试真题、复习资料、绩点保研考研实习招聘；办事流程（校医院、户籍、报销、校园卡、报修、电费网费）；"
        "食堂外卖快递、失物招领、二手闲置这类具体信息；讲座比赛社团活动、学校通知政策。\n"
        "  ❌ 不发：纯抱怨和情绪发泄（“烦死了”“受不了了”）、骂人/脏话；"
        "与学习和校园生活无关的无意义提问（找女朋友/找对象、问大家有多少钱/生活费多少）；"
        "八卦吃瓜挂人；抽奖拉群等广告商单；纯水贴（几个字、无信息量）。\n"
        "  ⚠️ 判不准时倾向不发（宁可漏，不要噪音）。\n"
        "\n"
        "【两种推送方式】\n"
        "  1) 一步到位：huyou_alumni_digest() —— 抓新帖、按上面的口径用规则筛一遍、直接发信；\n"
        "  2) 你先筛：huyou_new_feeds() 拿到本轮新帖（带规则判定），你按上面的口径挑出真正有用的，"
        "再调 huyou_send_digest(feed_ids=[...], note=\"筛选说明\") 发送。用户说“刷一下狐友/看看校友发了啥”时优先用方式 2。\n"
        "\n"
        "【其它】需要评论/点赞时才要登录：huyou_login_qrcode → 用户用狐友 App 扫码 → huyou_login_poll；"
        "写操作默认关闭。"
    ),
)

_cfg: Config | None = None
_app: HuyouApp | None = None


def get_app() -> HuyouApp:
    global _cfg, _app
    if _app is None:
        _cfg = load_config()
        _app = HuyouApp(_cfg)
    return _app


def get_config() -> Config:
    get_app()
    assert _cfg is not None
    return _cfg


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _guard(fn: Callable[..., Any]) -> Callable[..., str]:
    """统一异常 → 结构化错误，避免 MCP 客户端只看到裸异常。

    必须用 functools.wraps 保留原函数签名，否则 MCPServer 生成不出正确的参数 schema。
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return _json(fn(*args, **kwargs))
        except HuyouError as exc:
            return _json(
                {
                    "error": exc.desc,
                    "status": exc.status,
                    "login_required": exc.login_required,
                    "hint": "登录失效请重新扫码：huyou_login_qrcode_start",
                }
            )
        except (ValueError, RuntimeError) as exc:
            return _json({"error": str(exc)})

    return wrapper


# ---------------------------------------------------------------- 浏览类工具


@mcp.tool(description="列出狐友圈子分类（校园/热门/游戏…），返回分类 id 与名字。")
@_guard
def huyou_categories() -> Any:
    return {"categories": get_app().api.categories()}


@mcp.tool(description="列出「校园」分类下的高校圈子（可按热度取前 N 个）。")
@_guard
def huyou_campus_circles(limit: int = 30) -> Any:
    circles = get_app().api.circles(
        category_type=C.CATEGORY_TYPE_TOPIC,
        category_id=C.CAMPUS_CATEGORY_ID,
        limit=max(1, min(limit, 100)),
    )
    return {"count": len(circles), "circles": [c.to_dict() for c in circles]}


@mcp.tool(description="按关键词搜圈子，例如学校名「中国政法大学」，返回圈子 id、链接、动态数。")
@_guard
def huyou_search_circles(keyword: str, limit: int = 10) -> Any:
    circles = get_app().api.search_circles(keyword, limit=max(1, min(limit, 30)))
    return {"keyword": keyword, "count": len(circles), "circles": [c.to_dict() for c in circles]}


@mcp.tool(
    description=(
        "拉取某个圈子的动态列表。sort: new=新发 / reply=新回 / hot=热门 / elite=精华。"
        "每条含 feed_id、作者、正文、配图、评论数、可直接打开的链接。"
        "翻页把返回的 next_cursor 作为 cursor 再调一次。"
    )
)
@_guard
def huyou_circle_feeds(
    circle_id: str,
    sort: str = "new",
    count: int = 20,
    cursor: Any = 0,
) -> Any:
    page = get_app().api.feeds(circle_id, sort=sort, count=max(1, min(count, 50)), cursor=cursor)
    return {
        "circle_id": circle_id,
        "sort": sort,
        "count": len(page.items),
        "has_more": page.has_more,
        "next_cursor": page.next_cursor,
        "total_count": page.total_count,
        "feeds": [feed.to_dict() for feed in page.items],
    }


@mcp.tool(description="取单条动态的详情（正文、图片、评论数、链接）。")
@_guard
def huyou_feed_detail(feed_id: str) -> Any:
    feed, extra = get_app().api.feed_detail(feed_id)
    return {"feed": feed.to_dict(), "extra": extra}


@mcp.tool(
    description=(
        "取某条动态下的评论（含楼中楼回复、评论 id 可用于点赞/回复）。"
        "include_replies=false 只看一级评论。"
    )
)
@_guard
def huyou_feed_comments(
    feed_id: str, count: int = 20, cursor: Any = 0, include_replies: bool = True
) -> Any:
    page = get_app().api.comments(
        feed_id, count=max(1, min(count, 50)), cursor=cursor, include_replies=include_replies
    )
    return {
        "feed_id": feed_id,
        "count": len(page.items),
        "has_more": page.has_more,
        "next_cursor": page.next_cursor,
        "comments": [comment.to_dict() for comment in page.items],
    }


@mcp.tool(description="取某条评论下的全部楼中楼回复（分页）。")
@_guard
def huyou_comment_replies(
    feed_id: str, comment_id: str, count: int = 20, cursor: Any = 0
) -> Any:
    page = get_app().api.replies(
        feed_id, comment_id, count=max(1, min(count, 50)), cursor=cursor
    )
    return {
        "feed_id": feed_id,
        "comment_id": comment_id,
        "count": len(page.items),
        "has_more": page.has_more,
        "next_cursor": page.next_cursor,
        "replies": [comment.to_dict() for comment in page.items],
    }


@mcp.tool(description="查看 config.toml 里配置的关注圈子（会按学校名自动解析成圈子 id）。")
@_guard
def huyou_watch_list(refresh: bool = False) -> Any:
    circles = get_app().resolve_watch_circles(refresh=refresh)
    return {
        "count": len(circles),
        "circles": [
            {"circle_id": c.circle_id, "name": c.name, "source": c.source} for c in circles
        ],
    }


@mcp.tool(
    description=(
        "【一键推送】抓关注圈子的新帖 → 按「有用信息」口径自动过滤（去掉抱怨、骂人、"
        "找对象、打探钱、八卦、广告）→ 发 QQ 邮件，每帖带可直接打开的链接。"
        "preview_only=True 只渲染到 data/outbox、不发信也不更新已读状态。"
        "连续调用只会推送上次之后的新帖。"
    )
)
@_guard
def huyou_alumni_digest(send: bool = True, preview_only: bool = False) -> Any:
    # 没真发出去就不算已读，避免帖子被「吃掉」
    mark_seen = send and not preview_only
    return get_app().digest(dry_run=preview_only, send=send, mark_seen=mark_seen)


@mcp.tool(
    description=(
        "【先筛后发 · 第一步】列出本轮新帖（带规则初筛结果 rule_useful / rule_says），"
        "不发信、不标记已读。你可以按 instructions 里的口径再筛一遍，"
        "把真正有用的 feed_id 交给 huyou_send_digest。"
    )
)
@_guard
def huyou_new_feeds(limit: int = 80) -> Any:
    return get_app().preview_new(limit=max(1, min(limit, 200)))


@mcp.tool(
    description=(
        "【先筛后发 · 第二步】按你挑选的 feed_id 发邮件（不传 feed_ids 就发规则筛过的那些）。"
        "note 会显示在邮件顶部，用来写这次筛掉了什么。发送成功后整轮标记已读。"
        "dry_run=True 只渲染不发信。"
    )
)
@_guard
def huyou_send_digest(
    feed_ids: list[str] | None = None,
    note: str = "",
    dry_run: bool = False,
) -> Any:
    return get_app().send_selected(feed_ids, note=note, dry_run=dry_run, send=True)


# ---------------------------------------------------------------- 账号类工具


@mcp.tool(description="查看当前登录态（只读浏览不需要登录，评论/点赞才需要）。")
@_guard
def huyou_login_status() -> Any:
    app = get_app()
    info: dict[str, Any] = {
        "logged_in": app.session.logged_in,
        "cookies_file": str(app.cfg.account.cookies_file),
        "write_enabled": app.cfg.write.enabled,
    }
    if app.session.logged_in:
        try:
            info["user"] = app.api.me()
        except HuyouError as exc:
            info["user_error"] = exc.desc
    return info


@mcp.tool(
    description=(
        "生成登录二维码（返回图片路径 + serialno）。用户用狐友 App 扫码确认后，"
        "再用 huyou_login_poll 查询结果。"
    )
)
@_guard
def huyou_login_qrcode() -> Any:
    app = get_app()
    login = start_qr_login(app.session, app.cfg.data_dir)
    return {
        "serialno": login.serialno,
        "image_path": login.image_path,
        "hint": "用狐友 App 扫码并在手机上确认，然后调用 huyou_login_poll",
    }


@mcp.tool(description="查询扫码登录结果：pending / success / expired。")
@_guard
def huyou_login_poll(serialno: str) -> Any:
    app = get_app()
    result = poll_qr_login(app.session, serialno)
    if result["state"] == "success":
        app.session.save_cookies()
    return result


# ---------------------------------------------------------------- 写操作（需显式开启）


def _require_write() -> HuyouApp:
    app = get_app()
    if not app.cfg.write.enabled:
        raise RuntimeError(
            "写操作未开启：请在 config.toml 设置 [write] enabled = true（并先扫码登录）"
        )
    if not app.session.logged_in:
        raise RuntimeError("未登录：先调用 huyou_login_qrcode_start / huyou_login_qrcode 扫码")
    return app


@mcp.tool(description="给动态发评论（写操作，需登录 + config.toml [write] enabled=true）。")
@_guard
def huyou_post_comment(feed_id: str, content: str) -> Any:
    app = _require_write()
    return app.api.post_comment(feed_id, content)


@mcp.tool(description="给评论点赞/取消（写操作，需登录 + [write] enabled=true）。")
@_guard
def huyou_like_comment(feed_id: str, comment_id: str, like: bool = True) -> Any:
    app = _require_write()
    return app.api.like_comment(feed_id, comment_id, like=like)


def run(transport: str = "stdio", **kwargs: Any) -> None:
    mcp.run(transport=transport, **kwargs)
