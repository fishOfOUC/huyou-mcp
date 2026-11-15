"""命令行入口：既能当 MCP server 跑，也能单独当命令行工具/计划任务用。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from . import constants as C
from .api import HuyouAPI
from .auth import import_cookies_from_json, start_qr_login, wait_qr_login
from .config import load_config
from .service import HuyouApp
from .session import HuyouError, HuyouSession


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _app() -> HuyouApp:
    return HuyouApp(load_config())


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import run

    if args.http:
        run("streamable-http", host=args.host, port=args.http, path=args.path)
    else:
        run("stdio")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    app = _app()
    payload: dict[str, Any] = {
        "logged_in": app.session.logged_in,
        "cookies_file": str(app.cfg.account.cookies_file),
        "write_enabled": app.cfg.write.enabled,
    }
    if app.session.logged_in:
        try:
            payload["user"] = app.api.me()
        except HuyouError as exc:
            payload["user_error"] = exc.desc
    _print_json(payload)
    return 0


def cmd_circles(args: argparse.Namespace) -> int:
    app = _app()
    if args.search:
        circles = app.api.search_circles(args.search, limit=args.limit)
    elif args.category == "campus":
        circles = app.api.circles(
            category_type=C.CATEGORY_TYPE_TOPIC,
            category_id=C.CAMPUS_CATEGORY_ID,
            limit=args.limit,
        )
    elif args.category == "hot":
        circles = app.api.circles(category_type=C.CATEGORY_TYPE_HOT_AGG, category_id=None, limit=args.limit)
    else:  # new
        circles = app.api.circles(category_type=C.CATEGORY_TYPE_NEW_AGG, category_id=None, limit=args.limit)
    for circle in circles:
        print(f"{circle.circle_id}  {circle.name}  动态 {circle.feed_count}  {circle.url}")
    return 0


def cmd_feeds(args: argparse.Namespace) -> int:
    app = _app()
    page = app.api.feeds(args.circle_id, sort=args.sort, count=args.count, cursor=args.cursor)
    if args.json:
        _print_json(
            {
                "has_more": page.has_more,
                "next_cursor": page.next_cursor,
                "feeds": [feed.to_dict() for feed in page.items],
            }
        )
        return 0
    for idx, feed in enumerate(page.items, 1):
        when = feed.published_at or "-"
        text = feed.text.replace("\n", " ")
        print(f"{idx:2d}. {feed.author}  {when}  评论{feed.comment_count}  {feed.feed_id}")
        print(f"    {text[:100]}")
        print(f"    {feed.url}")
    print(f"\nhas_more={page.has_more} next_cursor={page.next_cursor}")
    return 0


def cmd_feed(args: argparse.Namespace) -> int:
    app = _app()
    feed, extra = app.api.feed_detail(args.feed_id)
    if args.json:
        _print_json({"feed": feed.to_dict(), "extra": extra})
        return 0
    print(f"{feed.author}  {feed.url}")
    print(feed.text)
    if feed.pics:
        print(f"\n配图 {len(feed.pics)} 张：")
        for url in feed.pics:
            print("  " + url)
    return 0


def cmd_comments(args: argparse.Namespace) -> int:
    app = _app()
    page = app.api.comments(args.feed_id, count=args.count, include_replies=not args.no_replies)
    if args.json:
        _print_json({"comments": [c.to_dict() for c in page.items], "has_more": page.has_more})
        return 0
    for comment in page.items:
        tag = "[AI]" if comment.is_ai else ""
        print(f"{comment.created_at} {comment.author}{tag} 赞{comment.like_count} id={comment.comment_id}")
        print("   " + comment.text.replace("\n", " ")[:120])
        for reply in comment.replies:
            target = f"回复 @{reply.reply_to}：" if reply.reply_to else ""
            print(f"     └ {reply.author} {target}{reply.text.replace(chr(10), ' ')[:100]}")
    print(f"\n共 {len(page.items)} 条一级评论，has_more={page.has_more}")
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    app = _app()
    login = start_qr_login(app.session, app.cfg.data_dir)
    print(f"二维码已保存: {login.image_path}")
    print(f"serialno: {login.serialno}")
    print("请用狐友 App 扫码并在手机上确认…")
    if args.no_wait:
        return 0

    deadline = time.time() + args.wait
    while time.time() < deadline:
        from .auth import poll_qr_login

        result = poll_qr_login(app.session, login.serialno)
        if result["state"] == "success":
            print("登录成功：", json.dumps(result.get("user", {}), ensure_ascii=False))
            print("cookie 已保存:", app.cfg.account.cookies_file)
            return 0
        if result["state"] != "pending":
            print("登录失败/二维码已失效：", result.get("raw"))
            return 1
        time.sleep(3)
    print("等待超时，可重新执行 login。")
    return 1


def cmd_import_cookies(args: argparse.Namespace) -> int:
    app = _app()
    cookies = import_cookies_from_json(app.session, args.source)
    print("已导入 cookie:", ", ".join(sorted(cookies)))
    try:
        print("当前用户:", json.dumps(app.api.me(), ensure_ascii=False))
    except HuyouError as exc:
        print("校验失败:", exc)
        return 1
    return 0


def cmd_digest(args: argparse.Namespace) -> int:
    app = _app()
    if args.schools:
        app.cfg.watch.schools = [s.strip() for s in args.schools.split(",") if s.strip()]
    if args.circles:
        app.cfg.watch.circle_ids = [s.strip() for s in args.circles.split(",") if s.strip()]
    # 只有真的发出去了才标记已读，否则 --no-send 会把帖子「吃掉」却没人看到
    mark_seen = not args.dry_run and not args.no_send
    result = app.digest(dry_run=args.dry_run, send=not args.no_send, mark_seen=mark_seen)
    _print_json(result)
    return 0


def cmd_mail_test(args: argparse.Namespace) -> int:
    """只发一封测试信，用来验证 QQ 邮箱授权码。"""
    from .mailer import send_mail

    cfg = load_config()
    if args.to:
        cfg.mail.to = [t.strip() for t in args.to.split(",") if t.strip()]
    print(f"发件: {cfg.mail.user}  收件: {', '.join(cfg.mail.recipients)}  host: {cfg.mail.host}:{cfg.mail.port}")
    result = send_mail(
        cfg.mail,
        subject=f"{cfg.mail.subject_prefix}测试邮件",
        text="这是一封来自狐友 MCP 的测试邮件。收到就说明 QQ 邮箱授权码配置正确。",
        html=(
            "<div style=\"font-family:-apple-system,'PingFang SC',sans-serif;font-size:14px\">"
            "<p>这是一封来自 <b>狐友 MCP</b> 的测试邮件。</p>"
            "<p>收到就说明 QQ 邮箱授权码配置正确，之后刷狐友的摘要会发到这个地址。</p></div>"
        ),
        dry_run=args.dry_run,
        outbox=cfg.outbox_dir,
    )
    _print_json(result)
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    """端到端自检：搜圈 → 拉动态 → 取详情 → 拉评论。"""
    cfg = load_config()
    session = HuyouSession(cfg.account.cookies_file)
    api = HuyouAPI(session)
    print("1) 校园圈子：")
    circles = api.circles(limit=5)
    for circle in circles:
        print(f"   - {circle.circle_id} {circle.name} 动态{circle.feed_count}")
    target = args.circle or (circles[0].circle_id if circles else None)
    if not target:
        print("没有可用圈子")
        return 1
    print(f"2) 圈 {target} 新发动态：")
    page = api.feeds(target, sort="new", count=5)
    for feed in page.items:
        print(f"   - {feed.author} {feed.published_at} 评论{feed.comment_count}")
        print(f"     {feed.text[:60].replace(chr(10), ' ')}")
        print(f"     {feed.url}")
    if not page.items:
        print("该圈暂无动态")
        return 0
    busiest = max(page.items, key=lambda f: f.comment_count)
    print(f"3) 详情 {busiest.feed_id}：")
    feed, _ = api.feed_detail(busiest.feed_id)
    print(f"   {feed.author}: {feed.text[:80]}")
    print(f"4) 评论（{feed.comment_count} 条）：")
    comments = api.comments(feed.feed_id, count=5)
    for comment in comments.items:
        print(f"   - {comment.author} 赞{comment.like_count}: {comment.text[:60]}")
    print("\nOK：只读链路全部打通")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="huyou-mcp", description="狐友 MCP / 命令行工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="以 MCP server 方式运行")
    p.add_argument("--http", type=int, default=0, help="用 streamable-http 模式并监听端口")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--path", default="/mcp")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("status", help="查看登录态")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("circles", help="列圈子 / 搜圈子")
    p.add_argument("--search", default="", help="按关键词搜索")
    p.add_argument("--category", default="campus", choices=["campus", "hot", "new"])
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_circles)

    p = sub.add_parser("feeds", help="拉圈子动态")
    p.add_argument("circle_id")
    p.add_argument("--sort", default="new", choices=list(C.SORT_LABELS))
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--cursor", default=0)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_feeds)

    p = sub.add_parser("feed", help="看单条动态详情")
    p.add_argument("feed_id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_feed)

    p = sub.add_parser("comments", help="看某条动态的评论（含楼中楼）")
    p.add_argument("feed_id")
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-replies", action="store_true", help="只看一级评论")
    p.set_defaults(func=cmd_comments)

    p = sub.add_parser("login", help="扫码登录（写操作需要）")
    p.add_argument("--wait", type=float, default=180, help="等待扫码的秒数")
    p.add_argument("--no-wait", action="store_true", help="只生成二维码不等待")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("import-cookies", help="导入浏览器里的 cookie")
    p.add_argument("source", help="JSON 文件路径，或 'k=v; k2=v2' 字符串")
    p.set_defaults(func=cmd_import_cookies)

    p = sub.add_parser("digest", help="生成/发送摘要（供 AI 或计划任务调用）")
    p.add_argument("--dry-run", action="store_true", help="只渲染到 data/outbox，不发信、不更新已读状态")
    p.add_argument("--no-send", action="store_true", help="只采集，不发信")
    p.add_argument("--schools", default="", help="临时覆盖配置里的学校名，逗号分隔")
    p.add_argument("--circles", default="", help="临时覆盖圈子 id，逗号分隔")
    p.set_defaults(func=cmd_digest)

    p = sub.add_parser("mail-test", help="发一封测试邮件，验证 QQ 邮箱授权码")
    p.add_argument("--to", default="", help="临时指定收件人，逗号分隔")
    p.add_argument("--dry-run", action="store_true", help="只渲染不发信")
    p.set_defaults(func=cmd_mail_test)

    p = sub.add_parser("smoke", help="端到端自检（只读）")
    p.add_argument("--circle", default="")
    p.set_defaults(func=cmd_smoke)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except HuyouError as exc:
        print(f"接口错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
