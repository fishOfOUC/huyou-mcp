"""接口返回值的归一化模型：只保留对「刷校友动态」有用的字段。"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from . import constants as C

CST = timezone(timedelta(hours=8))


def _ms_to_iso(ms: int | float | None) -> str | None:
    if not ms:
        return None
    try:
        value = float(ms)
    except (TypeError, ValueError):
        return None
    # 秒/毫秒都兼容
    if value < 1e12:
        value *= 1000
    try:
        return datetime.fromtimestamp(value / 1000, CST).isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return None


def _approx_publish_ms(score: Any) -> int | None:
    """「新发」列表里 score 就是发帖时间的毫秒时间戳，用于确定发帖时间。

    只在结果落在合理区间时采用；热门/精华排序的 score 是复合值，不能当时间用。
    """
    try:
        value = abs(float(score))
    except (TypeError, ValueError):
        return None
    now_ms = time.time() * 1000
    if 1_500_000_000_000 < value < now_ms + 86_400_000:
        return int(value)
    return None


def _pic_urls(pic_feed: Mapping[str, Any] | None) -> list[str]:
    if not pic_feed:
        return []
    urls: list[str] = []
    for pic in pic_feed.get("pics") or []:
        if not isinstance(pic, Mapping):
            continue
        url = pic.get("rp") or pic.get("bp") or pic.get("tp")
        if url:
            urls.append(str(url))
    return urls


@dataclass
class Circle:
    circle_id: str
    name: str
    feed_count: int | None = None
    user_count: int | None = None
    logo: str | None = None
    url: str = ""

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> "Circle":
        cid = str(raw.get("circleId") or "")
        logo = raw.get("circleLogo")
        return cls(
            circle_id=cid,
            name=str(raw.get("circleName") or ""),
            feed_count=_maybe_int(raw.get("feedCount")),
            user_count=_maybe_int(raw.get("userCount")),
            logo=(logo or {}).get("url") if isinstance(logo, Mapping) else None,
            url=C.CIRCLE_URL.format(circle_id=cid) if cid else "",
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Feed:
    feed_id: str
    author: str
    author_id: str
    text: str
    url: str
    circle_id: str | None = None
    circle_name: str | None = None
    pics: list[str] = field(default_factory=list)
    comment_count: int = 0
    repost_count: int = 0
    is_top: bool = False
    anonymous: bool = False
    published_at: str | None = None
    published_at_source: str | None = None  # "estimated" / "exact"
    stpl: int | None = None
    score: Any = None

    @classmethod
    def from_api(cls, raw: Mapping[str, Any], *, sort: str | None = None) -> "Feed":
        # 列表接口把动态包在 sourceFeed 里（转发/热榜容器），详情接口同理
        data: Mapping[str, Any] = raw.get("sourceFeed") if isinstance(raw.get("sourceFeed"), Mapping) else raw
        feed_id = str(data.get("feedId") or "")
        circle = data.get("circle") if isinstance(data.get("circle"), Mapping) else {}
        publish_ms = _approx_publish_ms(data.get("score")) if sort == "new" else None
        content = data.get("content")
        if isinstance(content, Mapping):  # 详情偶尔给结构化 content
            content = content.get("text") or ""
        return cls(
            feed_id=feed_id,
            author=str(data.get("userName") or ""),
            author_id=str(data.get("userId") or ""),
            text=str(content or "").strip(),
            url=C.FEED_URL.format(feed_id=feed_id) if feed_id else "",
            circle_id=str(circle.get("circleId")) if circle.get("circleId") else None,
            circle_name=str(circle.get("circleName")) if circle.get("circleName") else None,
            pics=_pic_urls(data.get("picFeed")),
            comment_count=_maybe_int(data.get("commentCount")) or 0,
            repost_count=_maybe_int(data.get("repostCount")) or 0,
            is_top=bool(_maybe_int(data.get("isTopFeed"))),
            anonymous=bool(data.get("anonymous")),
            published_at=_ms_to_iso(publish_ms) if publish_ms else None,
            published_at_source="feed_score" if publish_ms else None,
            stpl=_maybe_int(data.get("stpl")),
            score=data.get("score"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Comment:
    comment_id: str
    author: str
    author_id: str
    text: str
    created_at: str | None = None
    like_count: int = 0
    liked: bool = False
    reply_count: int = 0
    anonymous: bool = False
    is_ai: bool = False
    region: str | None = None  # IP 属地（服务端给的部分评论带 sourceRegion）
    # 楼中楼：列表接口会顺带返回回复（通常已包含整层），需要完整列表时调 replylist
    reply_to: str | None = None
    replies: list["Comment"] = field(default_factory=list)

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> "Comment":
        author = str(raw.get("userName") or "")
        reply_to = raw.get("replyUserName")
        reply_block = raw.get("replies")
        replies: list[Comment] = []
        if isinstance(reply_block, Mapping):
            nested = reply_block.get("list") or []
        elif isinstance(reply_block, list):
            nested = reply_block
        else:
            nested = []
        for item in nested:
            if isinstance(item, Mapping):
                replies.append(cls.from_api(item))
        return cls(
            comment_id=str(raw.get("commentId") or ""),
            author=author,
            author_id=str(raw.get("userId") or ""),
            text=str(raw.get("content") or "").strip(),
            created_at=_ms_to_iso(raw.get("timeId")),
            like_count=_maybe_int(raw.get("likeCount")) or 0,
            liked=bool(raw.get("liked")),
            reply_count=_maybe_int(raw.get("replyCount")) or 0,
            anonymous=bool(raw.get("anonymous")),
            is_ai="AI" in author,
            region=str(raw["sourceRegion"]) if raw.get("sourceRegion") else None,
            reply_to=str(reply_to) if reply_to else None,
            replies=replies,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _maybe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def feeds_from_page(data: Mapping[str, Any] | None, *, sort: str | None = None) -> tuple[list[Feed], dict[str, Any]]:
    """把 feed/list 的 data 解成 (动态列表, 分页信息)。"""
    data = data or {}
    raw_list: Iterable[Mapping[str, Any]] = data.get("feedList") or []
    feeds: list[Feed] = []
    for raw in raw_list:
        if not isinstance(raw, Mapping):
            continue
        # tpl=29 是「圈子热榜容器」，里面再套一层 feedList
        container = raw.get("rcmdCircleHotFeedContainer")
        if container and container.get("feedList"):
            for inner in container["feedList"]:
                if isinstance(inner, Mapping):
                    feeds.append(Feed.from_api(inner, sort=sort))
            continue
        feeds.append(Feed.from_api(raw, sort=sort))
    page = data.get("pageInfo") or {}
    meta = {
        "has_more": bool(page.get("hasMore")),
        "next_cursor": page.get("score"),
        "total_count": _maybe_int(page.get("totalCount")),
    }
    return feeds, meta


def comments_from_page(data: Mapping[str, Any] | None) -> tuple[list[Comment], dict[str, Any]]:
    data = data or {}
    items = data.get("list") or []
    comments = [Comment.from_api(item) for item in items if isinstance(item, Mapping)]
    page = data.get("pageInfo") or {}
    meta = {
        "has_more": bool(page.get("hasMore")),
        "next_cursor": page.get("score"),
        "total_count": _maybe_int(page.get("totalCount")),
    }
    return comments, meta
