"""业务编排：把配置、会话、接口、邮件串起来。

两层用法：
    - MCP 工具（server.py）用 HuyouApp 提供单次查询；
    - 每日任务（cli.py digest）用 HuyouApp.digest() 产出 + 发送摘要邮件。
"""

from __future__ import annotations

import html as html_lib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable

from . import constants as C
from . import filters
from .api import HuyouAPI
from .config import Config
from .mailer import send_mail
from .models import Circle, Comment, Feed
from .session import HuyouError, HuyouSession

SEEN_LIMIT = 800  # 每个圈子最多记住多少条已读动态 id


@dataclass
class WatchCircle:
    circle_id: str
    name: str
    source: str  # school / manual


class HuyouApp:
    def __init__(self, cfg: Config, session: HuyouSession | None = None):
        self.cfg = cfg
        self.session = session or HuyouSession(cfg.account.cookies_file)
        self.api = HuyouAPI(self.session)

    # ---------------- 圈子 ----------------
    def resolve_watch_circles(self, *, refresh: bool = False) -> list[WatchCircle]:
        cfg = self.cfg
        cache = self._load_circle_cache() if not refresh else {}
        out: list[WatchCircle] = []

        for school in cfg.watch.schools:
            key = f"school:{school}"
            entry = cache.get(key)
            if not entry:
                circle = self.api.resolve_school_circle(school)
                if circle is None:
                    out.append(WatchCircle(circle_id="", name=school, source="school"))
                    continue
                entry = {"circle_id": circle.circle_id, "name": circle.name}
                cache[key] = entry
            out.append(WatchCircle(entry["circle_id"], entry["name"], "school"))

        for cid in cfg.watch.circle_ids:
            entry = cache.get(f"circle:{cid}") or {"circle_id": cid, "name": cid}
            out.append(WatchCircle(entry["circle_id"], entry["name"], "manual"))

        if not refresh:
            self._save_circle_cache(cache)
        return out

    def _load_circle_cache(self) -> dict[str, Any]:
        path = self.cfg.circle_cache_file
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_circle_cache(self, cache: dict[str, Any]) -> None:
        try:
            self.cfg.circle_cache_file.write_text(
                json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    # ---------------- 采集 ----------------
    def collect(
        self,
        circles: Iterable[WatchCircle] | None = None,
        *,
        sorts: Iterable[str] | None = None,
        per_circle: int | None = None,
        since: datetime | None = None,
        max_pages: int | None = None,
    ) -> list[Feed]:
        """按配置抓取每个圈子的动态（默认「新发」排序）。

        活跃圈子（比如海大）一天上百条，只抓第一页会漏，所以按 score 游标翻页，
        直到：达到页数上限 / 没有更多 / 本页正常帖子里最早的一条已早于 since。
        """
        circles = list(circles if circles is not None else self.resolve_watch_circles())
        sorts = list(sorts or self.cfg.watch.sorts or ["new"])
        per_circle = per_circle or self.cfg.watch.per_circle
        max_pages = max_pages or self.cfg.watch.max_pages_per_circle
        collected: list[Feed] = []

        for circle in circles:
            if not circle.circle_id:
                continue
            for sort in sorts:
                cursor: Any = 0
                for _ in range(max(1, max_pages)):
                    try:
                        page = self.api.feeds(
                            circle.circle_id, sort=sort, count=per_circle, cursor=cursor
                        )
                    except HuyouError:
                        break
                    if not page.items:
                        break
                    for feed in page.items:
                        feed.circle_name = feed.circle_name or circle.name
                        collected.append(feed)
                    if not page.has_more:
                        break
                    # 页内时间不是严格倒序（页尾会混入置顶/推广/新回帖），所以只在
                    # 「本页最新的一条都已经早于 since」时才收工，宁可多翻一页也不漏帖
                    page_times = []
                    for feed in page.items:
                        if feed.is_top or not feed.published_at:
                            continue
                        try:
                            page_times.append(datetime.fromisoformat(feed.published_at))
                        except ValueError:
                            continue
                    if since and page_times and max(page_times) < since:
                        break
                    cursor = page.next_cursor
                    if cursor in (None, "", 0):
                        break
        return self._dedupe(collected)

    @staticmethod
    def _dedupe(feeds: Iterable[Feed]) -> list[Feed]:
        seen: set[str] = set()
        out: list[Feed] = []
        for feed in feeds:
            if not feed.feed_id or feed.feed_id in seen:
                continue
            seen.add(feed.feed_id)
            out.append(feed)
        return out

    # ---------------- 状态 ----------------
    def _comment_previews(self, feeds: list[Feed]) -> dict[str, list[Comment]]:
        """给「有讨论」的帖子取前几条评论，过滤掉 AI 助手的自动回复。"""
        if not self.cfg.mail.include_comments:
            return {}
        want = max(1, self.cfg.mail.comment_preview_count)
        previews: dict[str, list[Comment]] = {}
        for feed in feeds:
            if not feed.comment_count:
                continue
            try:
                page = self.api.comments(feed.feed_id, count=want + 3, include_replies=False)
            except HuyouError:
                continue
            picked = [c for c in page.items if not c.is_ai][:want]
            if picked:
                previews[feed.feed_id] = picked
        return previews

    def load_state(self) -> dict[str, Any]:
        path = self.cfg.state_file
        if not path.exists():
            return {"circles": {}}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"circles": {}}

    def save_state(self, state: dict[str, Any]) -> None:
        self.cfg.state_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ---------------- 每日摘要 ----------------
    def digest(
        self,
        *,
        dry_run: bool = False,
        send: bool = True,
        mark_seen: bool = True,
    ) -> dict[str, Any]:
        circles = self.resolve_watch_circles()
        state = self.load_state()
        per_circle_seen: dict[str, list[str]] = state.setdefault("circles", {})

        now = datetime.now().astimezone()
        cutoff = now - timedelta(hours=self.cfg.watch.max_age_hours)
        since = cutoff
        last_run_raw = state.get("last_run")
        if last_run_raw:
            try:
                last_run = datetime.fromisoformat(last_run_raw)
                if last_run.tzinfo is None:
                    last_run = last_run.astimezone()
                # 留 10 分钟重叠，避免两次抓取之间有漏网
                since = max(cutoff, last_run - timedelta(minutes=10))
            except ValueError:
                pass

        feeds = self.collect(circles, since=since)
        fresh = self._fresh_feeds(feeds, per_circle_seen, cutoff, since)
        fresh.sort(key=lambda f: f.published_at or "", reverse=True)

        # 只保留「有实用信息」的帖子：抱怨/骂人/无意义提问/广告不推（用户口径）
        useful, verdicts = self._filter_useful(fresh)
        self._save_pending(fresh, verdicts)

        threshold = self.cfg.watch.hot_comment_threshold
        hot = [f for f in useful if f.comment_count >= threshold]
        rest = [f for f in useful if f.comment_count < threshold]

        previews = self._comment_previews(hot[:HOT_CARDS_MAX])

        subject, html, text = render_digest(
            self.cfg,
            circles,
            useful,
            hot=hot,
            rest=rest,
            since=since,
            comment_previews=previews,
            total_new=len(fresh),
            filtered_out=len(fresh) - len(useful),
        )
        result: dict[str, Any] = {
            "circles": [f"{c.name}({c.circle_id})" for c in circles],
            "since": since.isoformat(timespec="minutes"),
            "total_fetched": len(feeds),
            "new_count": len(fresh),
            "useful_count": len(useful),
            "filtered_out": len(fresh) - len(useful),
            "hot_count": len(hot),
            "subject": subject,
            "links": [f.url for f in useful[:20]],
            "filtered_examples": [
                {"text": f.text.replace("\n", " ")[:40], "reason": verdicts[f.feed_id].reason}
                for f in fresh
                if f.feed_id in verdicts and not verdicts[f.feed_id].useful
            ][:8],
        }

        # 保留一份本地存档，方便对照（发信失败也能看）；按时间另存一份留档
        archive = self.cfg.outbox_dir / "last-digest.html"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_text(html, encoding="utf-8")
        stamped = self.cfg.outbox_dir / "archive" / f"digest-{now:%Y%m%d-%H%M}.html"
        stamped.parent.mkdir(parents=True, exist_ok=True)
        stamped.write_text(html, encoding="utf-8")
        result["archive"] = str(archive)
        result["archive_stamped"] = str(stamped)

        if send:
            result["mail"] = send_mail(
                self.cfg.mail,
                subject,
                text,
                html,
                dry_run=dry_run or not self.cfg.mail.enabled,
                outbox=self.cfg.outbox_dir,
            )

        if mark_seen:
            # 噪音也一起标记，避免下次再判定一遍
            self._mark_seen(fresh, per_circle_seen)
            state["last_run"] = datetime.now().astimezone().isoformat(timespec="seconds")
            self.save_state(state)
        return result

    # ---------------- 新帖 / 筛选 / 待发 ----------------
    def _fresh_feeds(
        self,
        feeds: list[Feed],
        per_circle_seen: dict[str, list[str]],
        cutoff: datetime,
        since: datetime | None = None,
    ) -> list[Feed]:
        floor = max(cutoff, since) if since else cutoff
        fresh: list[Feed] = []
        for feed in feeds:
            if feed.is_top and self.cfg.watch.skip_top:
                continue
            key = feed.circle_id or "unknown"
            if feed.feed_id in set(per_circle_seen.get(key, [])):
                continue
            if feed.published_at:
                try:
                    if datetime.fromisoformat(feed.published_at) < floor:
                        continue
                except ValueError:
                    pass
            fresh.append(feed)
        return fresh

    def _filter_useful(self, feeds: list[Feed]) -> tuple[list[Feed], dict[str, filters.Verdict]]:
        fcfg = self.cfg.filter
        verdicts: dict[str, filters.Verdict] = {}
        if not fcfg.enabled:
            for feed in feeds:
                verdicts[feed.feed_id] = filters.Verdict(True, 99, note="筛选已关闭")
            return list(feeds), verdicts

        useful: list[Feed] = []
        for feed in feeds:
            verdict = filters.classify(
                feed.text,
                comment_count=feed.comment_count,
                min_score=fcfg.min_score,
                extra_useful=fcfg.extra_useful,
                extra_noise=fcfg.extra_noise,
            )
            verdicts[feed.feed_id] = verdict
            if verdict.useful:
                useful.append(feed)
        return useful, verdicts

    def _save_pending(self, feeds: list[Feed], verdicts: dict[str, filters.Verdict]) -> None:
        """把本轮新帖落到 data/pending.json，供 MCP 的「预览→挑选→发送」两步走使用。"""
        payload = {
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "feeds": [
                {
                    "feed_id": f.feed_id,
                    "author": f.author,
                    "text": f.text,
                    "url": f.url,
                    "circle_name": f.circle_name,
                    "published_at": f.published_at,
                    "comment_count": f.comment_count,
                    "pics": f.pics,
                    "filter": verdicts[f.feed_id].to_dict() if f.feed_id in verdicts else {},
                }
                for f in feeds
            ],
        }
        try:
            self.cfg.pending_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    def load_pending(self) -> list[dict[str, Any]]:
        path = self.cfg.pending_file
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("feeds") or []
        except (OSError, json.JSONDecodeError):
            return []

    def _mark_seen(self, feeds: list[Feed], per_circle_seen: dict[str, list[str]]) -> None:
        for feed in feeds:
            key = feed.circle_id or "unknown"
            bucket = per_circle_seen.setdefault(key, [])
            bucket.append(feed.feed_id)
            if len(bucket) > SEEN_LIMIT:
                del bucket[: len(bucket) - SEEN_LIMIT]

    def preview_new(self, limit: int = 80) -> dict[str, Any]:
        """给模型看的「本轮新帖清单」：带规则判定，模型可以自己再筛一遍。不发信、不标记已读。"""
        circles = self.resolve_watch_circles()
        state = self.load_state()
        per_circle_seen: dict[str, list[str]] = state.setdefault("circles", {})
        now = datetime.now().astimezone()
        cutoff = now - timedelta(hours=self.cfg.watch.max_age_hours)
        since = cutoff
        last_run_raw = state.get("last_run")
        if last_run_raw:
            try:
                last_run = datetime.fromisoformat(last_run_raw)
                if last_run.tzinfo is None:
                    last_run = last_run.astimezone()
                since = max(cutoff, last_run - timedelta(minutes=10))
            except ValueError:
                pass

        feeds = self.collect(circles, since=since)
        fresh = self._fresh_feeds(feeds, per_circle_seen, cutoff, since)
        fresh.sort(key=lambda f: f.published_at or "", reverse=True)
        useful, verdicts = self._filter_useful(fresh)
        self._save_pending(fresh, verdicts)

        return {
            "circles": [f"{c.name}({c.circle_id})" for c in circles],
            "total_new": len(fresh),
            "useful_count": len(useful),
            "since": since.isoformat(timespec="minutes"),
            "feeds": [
                {
                    "feed_id": f.feed_id,
                    "author": f.author,
                    "time": f.published_at,
                    "comments": f.comment_count,
                    "text": f.text[:200],
                    "url": f.url,
                    "rule_says": verdicts[f.feed_id].reason,
                    "rule_useful": verdicts[f.feed_id].useful,
                }
                for f in fresh[: max(1, limit)]
            ],
        }

    def send_selected(
        self,
        feed_ids: "list[str] | None" = None,
        *,
        note: str = "",
        dry_run: bool = False,
        send: bool = True,
    ) -> dict[str, Any]:
        """按模型挑好的 feed_id 发信；不传 feed_ids 就发规则筛过的那些。"""
        pending = self.load_pending()
        by_id = {item["feed_id"]: item for item in pending}

        chosen: list[Feed] = []
        if feed_ids:
            for feed_id in feed_ids:
                item = by_id.get(feed_id)
                if item:
                    chosen.append(
                        Feed(
                            feed_id=item["feed_id"],
                            author=item.get("author") or "",
                            author_id="",
                            text=item.get("text") or "",
                            url=item.get("url") or "",
                            circle_name=item.get("circle_name"),
                            pics=item.get("pics") or [],
                            comment_count=int(item.get("comment_count") or 0),
                            published_at=item.get("published_at"),
                        )
                    )
                else:  # 不在本轮清单里（比如模型手动给了 id），现取详情
                    try:
                        feed, _ = self.api.feed_detail(feed_id)
                        chosen.append(feed)
                    except HuyouError:
                        continue
        else:
            chosen = [
                Feed(
                    feed_id=item["feed_id"],
                    author=item.get("author") or "",
                    author_id="",
                    text=item.get("text") or "",
                    url=item.get("url") or "",
                    circle_name=item.get("circle_name"),
                    pics=item.get("pics") or [],
                    comment_count=int(item.get("comment_count") or 0),
                    published_at=item.get("published_at"),
                )
                for item in pending
                if item.get("filter", {}).get("useful", True)
            ]

        chosen.sort(key=lambda f: f.published_at or "", reverse=True)
        threshold = self.cfg.watch.hot_comment_threshold
        hot = [f for f in chosen if f.comment_count >= threshold]
        rest = [f for f in chosen if f.comment_count < threshold]
        previews = self._comment_previews(hot[:HOT_CARDS_MAX])

        circles = self.resolve_watch_circles()
        subject, html, text = render_digest(
            self.cfg,
            circles,
            chosen,
            hot=hot,
            rest=rest,
            comment_previews=previews,
            note=note,
        )
        archive = self.cfg.outbox_dir / "last-digest.html"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_text(html, encoding="utf-8")

        result: dict[str, Any] = {
            "sent_posts": len(chosen),
            "subject": subject,
            "archive": str(archive),
            "links": [f.url for f in chosen],
        }
        if send:
            result["mail"] = send_mail(
                self.cfg.mail,
                subject,
                text,
                html,
                dry_run=dry_run or not self.cfg.mail.enabled,
                outbox=self.cfg.outbox_dir,
            )
        if send and not dry_run:
            # 整轮都标已读（包括被判为噪音的），避免下次重复推送
            state = self.load_state()
            per_circle_seen = state.setdefault("circles", {})
            for item in pending:
                key = self._circle_key_for(item.get("circle_name"))
                bucket = per_circle_seen.setdefault(key, [])
                bucket.append(item["feed_id"])
                if len(bucket) > SEEN_LIMIT:
                    del bucket[: len(bucket) - SEEN_LIMIT]
            state["last_run"] = datetime.now().astimezone().isoformat(timespec="seconds")
            self.save_state(state)
        return result

    def _circle_key_for(self, circle_name: str | None) -> str:
        for circle in self.resolve_watch_circles():
            if circle.name == circle_name:
                return circle.circle_id
        return "unknown"


# ---------------- 邮件渲染 ----------------
HOT_CARDS_MAX = 20  # 「有讨论」区最多几张卡片


def _fmt_time(published_at: str | None, now: datetime) -> str:
    if not published_at:
        return ""
    try:
        when = datetime.fromisoformat(published_at)
    except ValueError:
        return ""
    if when.date() == now.date():
        return when.strftime("%H:%M")
    return when.strftime("%m-%d %H:%M")


def render_digest(
    cfg: Config,
    circles: list[WatchCircle],
    feeds: list[Feed],
    *,
    hot: list[Feed] | None = None,
    rest: list[Feed] | None = None,
    since: datetime | None = None,
    comment_previews: dict[str, list[Comment]] | None = None,
    total_new: int | None = None,
    filtered_out: int = 0,
    note: str = "",
) -> tuple[str, str, str]:
    """渲染摘要邮件：有讨论的帖子用卡片，其余用紧凑列表，避免活跃圈子把邮件撑爆。"""
    now = datetime.now().astimezone()
    today = now.strftime("%m月%d日")
    circle_names = "、".join(c.name for c in circles)
    threshold = cfg.watch.hot_comment_threshold
    hot = hot if hot is not None else [f for f in feeds if f.comment_count >= threshold]
    rest = rest if rest is not None else [f for f in feeds if f.comment_count < threshold]

    subject = f"{cfg.mail.subject_prefix}{today} 有用动态 {len(feeds)} 条"

    filter_hint = f"，已过滤 {filtered_out} 条抱怨/闲聊/广告" if filtered_out else ""
    since_hint = f" · 统计自 {since.strftime('%m-%d %H:%M')}" if since else ""

    if not feeds:
        text = (
            f"{today}：关注的海大圈里暂时没有值得推送的新动态"
            f"{f'（本轮共 {total_new} 条，都判为抱怨/闲聊/广告）' if total_new else ''}。\n\n"
            f"圈子：{circle_names}"
        )
        html = (
            "<div style=\"font-family:-apple-system,'PingFang SC',sans-serif;max-width:640px;margin:0 auto\">"
            f"<h2 style=\"font-size:18px;margin:0 0 8px\">{html_lib.escape(today)} 有用动态</h2>"
            f"<p style=\"color:#666;font-size:14px\">关注的海大圈里暂时没有值得推送的新动态"
            f"{html_lib.escape(f'（本轮共 {total_new} 条，都判为抱怨/闲聊/广告）') if total_new else ''}。</p>"
            f"<p style=\"color:#999;font-size:13px\">圈子：{html_lib.escape(circle_names)}</p></div>"
        )
        return subject, html, text

    text_lines = [
        f"{today} 有用动态（共 {len(feeds)} 条，其中有讨论 {len(hot)} 条）{filter_hint}{since_hint}",
        "",
    ]
    subtitle = f"共 <b>{len(feeds)}</b> 条（有讨论 <b>{len(hot)}</b> 条"
    if filtered_out:
        subtitle += f" · 已过滤 <b>{filtered_out}</b> 条抱怨/闲聊/广告"
    subtitle += f"）· 来自 {html_lib.escape(circle_names)}"
    html_parts = [
        "<div style=\"font-family:-apple-system,'PingFang SC',sans-serif;max-width:640px;margin:0 auto;color:#1a1a1a\">",
        f"<h2 style=\"font-size:20px;margin:0 0 6px\">{html_lib.escape(today)} 有用动态</h2>",
        f"<p style=\"color:#888;font-size:13px;margin:0 0 4px\">{subtitle}</p>",
        f"<p style=\"color:#aaa;font-size:12px;margin:0 0 18px\">统计自 {html_lib.escape(since.strftime('%m-%d %H:%M'))}"
        if since
        else "",
        "</p>",
    ]
    if note:
        html_parts.append(
            "<div style=\"background:#fffbe6;border-radius:8px;padding:10px 12px;margin:0 0 16px;"
            f"font-size:13px;color:#8a6d3b\">{html_lib.escape(note)}</div>"
        )
        text_lines.insert(1, f"说明：{note}")

    def card(feed: Feed) -> str:
        body = feed.text.replace("\n", " ")
        excerpt = body[:160] + ("…" if len(body) > 160 else "")
        bits = [f"@{feed.author}", _fmt_time(feed.published_at, now), f"评论 {feed.comment_count}"]
        if feed.pics:
            bits.append(f"图 {len(feed.pics)}")
        if feed.is_top:
            bits.append("置顶")
        pic_html = ""
        if feed.pics:
            pic_html = (
                f"<div style=\"margin-top:8px\"><img src=\"{html_lib.escape(feed.pics[0])}\" "
                "style=\"max-width:200px;border-radius:8px\" alt=\"配图\"></div>"
            )
        comments_html = ""
        preview = (comment_previews or {}).get(feed.feed_id) or []
        if preview:
            rows = "".join(
                f"<div style=\"margin:3px 0\"><b>@{html_lib.escape(item.author)}</b>："
                f"{html_lib.escape(item.text.replace(chr(10), ' ')[:120])}</div>"
                for item in preview
            )
            comments_html = (
                "<div style=\"margin-top:10px;padding:8px 10px;background:#fafafa;border-radius:8px;"
                "font-size:12.5px;color:#555;line-height:1.6\">"
                f"{rows}</div>"
            )
        return (
            "<div style=\"border:1px solid #f0f0f0;border-radius:12px;padding:12px 14px;margin:0 0 10px\">"
            f"<div style=\"font-size:12px;color:#888;margin-bottom:6px\">{html_lib.escape(' · '.join(b for b in bits if b))}</div>"
            f"<div style=\"font-size:14px;line-height:1.6\">{html_lib.escape(excerpt) or '[无文字内容]'}</div>"
            f"{pic_html}{comments_html}"
            f"<div style=\"margin-top:10px\"><a href=\"{html_lib.escape(feed.url)}\" "
            "style=\"display:inline-block;background:#ffe807;color:#000;text-decoration:none;"
            "padding:6px 14px;border-radius:999px;font-size:13px;font-weight:600\">打开帖子</a></div>"
            "</div>"
        )

    def row(feed: Feed) -> str:
        body = feed.text.replace("\n", " ")
        excerpt = body[:70] + ("…" if len(body) > 70 else "")
        meta = [f"@{feed.author}", _fmt_time(feed.published_at, now)]
        if feed.comment_count:
            meta.append(f"评论 {feed.comment_count}")
        if feed.pics:
            meta.append(f"图 {len(feed.pics)}")
        return (
            "<div style=\"padding:8px 0;border-bottom:1px solid #f5f5f5\">"
            f"<span style=\"font-size:12px;color:#999\">{html_lib.escape(' · '.join(m for m in meta if m))}</span><br>"
            f"<span style=\"font-size:13px;line-height:1.6\">{html_lib.escape(excerpt) or '[无文字内容]'}</span> "
            f"<a href=\"{html_lib.escape(feed.url)}\" style=\"color:#3d5699;font-size:12px;text-decoration:none\">[打开]</a>"
            "</div>"
        )

    if hot:
        shown = hot[:HOT_CARDS_MAX]
        html_parts.append(
            "<h3 style=\"font-size:15px;margin:8px 0 10px;padding-bottom:6px;border-bottom:2px solid #ffe807\">"
            f"🔥 有讨论的帖子（{len(hot)} 条）</h3>"
        )
        text_lines.append(f"【有讨论】{len(hot)} 条")
        for feed in shown:
            html_parts.append(card(feed))
            text_lines.append(f"- @{feed.author} 评论{feed.comment_count}：{feed.text.replace(chr(10), ' ')[:100]}")
            for item in (comment_previews or {}).get(feed.feed_id) or []:
                text_lines.append(f"    @{item.author}: {item.text.replace(chr(10), ' ')[:80]}")
            text_lines.append(f"  {feed.url}")
        if len(hot) > len(shown):
            html_parts.append(
                f"<p style=\"color:#999;font-size:12px\">另有 {len(hot) - len(shown)} 条有讨论的帖子未展示</p>"
            )
        text_lines.append("")

    if rest and not cfg.mail.only_hot:
        room = max(cfg.mail.max_posts - len(hot[:HOT_CARDS_MAX]), 0)
        shown_rest = rest[:room]
        html_parts.append(
            "<h3 style=\"font-size:15px;margin:20px 0 4px;padding-bottom:6px;border-bottom:1px solid #eee\">"
            f"其他动态（{len(rest)} 条）</h3>"
        )
        html_parts.extend(row(feed) for feed in shown_rest)
        text_lines.append(f"【其他动态】{len(rest)} 条")
        for feed in shown_rest:
            text_lines.append(f"- {_fmt_time(feed.published_at, now)} @{feed.author}: "
                              f"{feed.text.replace(chr(10), ' ')[:70]}")
            text_lines.append(f"  {feed.url}")
        omitted = len(rest) - len(shown_rest)
        if omitted > 0:
            html_parts.append(
                f"<p style=\"color:#999;font-size:12px;margin-top:10px\">另有 {omitted} 条未在邮件里展示</p>"
            )
            text_lines.append(f"（另有 {omitted} 条未展示）")
        text_lines.append("")

    if rest and cfg.mail.only_hot:
        html_parts.append(
            f"<p style=\"color:#999;font-size:12px;margin-top:14px\">另有 {len(rest)} 条没有评论的日常动态未展示"
            "（only_hot = true）</p>"
        )
        text_lines.append(f"（另有 {len(rest)} 条没有评论的日常动态未展示）")

    html_parts.append(
        "<p style=\"color:#aaa;font-size:12px;margin-top:24px\">由 狐友 MCP 自动推送 · 只读订阅，不产生任何互动</p></div>"
    )
    return subject, "".join(html_parts), "\n".join(text_lines)
