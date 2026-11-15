"""狐友只读（以及后续写操作）业务接口封装。

路径全部来自前端 bundle 里的字面量，参数名与原前端调用一致，方便以后对着
网页 Network 面板核对。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping

from . import constants as C
from .models import Circle, Comment, Feed, comments_from_page, feeds_from_page
from .session import HuyouError, HuyouSession


@dataclass
class Page:
    items: list[Any]
    has_more: bool
    next_cursor: Any
    total_count: int | None


class HuyouAPI:
    def __init__(self, session: HuyouSession):
        self.s = session

    # ---------------- 圈子 ----------------
    def categories(self) -> list[dict[str, Any]]:
        """圈子分类（兴趣分类 校园/游戏/… + 热门圈子聚合 + 新圈速报）。"""
        data = self.s.get("/v9/circle/category/list")
        items = (data or {}).get("categoryList") or []
        return [
            {
                "id": item.get("categoryId"),
                "name": item.get("categoryName"),
                "type": item.get("categoryType"),
                "is_default": int(item.get("categoryEnum") or 0) == 1,
                "query": {
                    "category_type": item.get("categoryType"),
                    **({"category_id": str(item["categoryId"])} if item.get("categoryId") else {}),
                },
            }
            for item in items
            if isinstance(item, Mapping)
        ]

    def circles(
        self,
        *,
        category_type: int = C.CATEGORY_TYPE_TOPIC,
        category_id: str | None = C.CAMPUS_CATEGORY_ID,
        limit: int = 30,
    ) -> list[Circle]:
        """按分类拉圈子列表（默认：兴趣分类「校园」），自动翻页到 limit 条。"""
        out: list[Circle] = []
        cursor: Any = 0
        while len(out) < limit:
            params: dict[str, Any] = {
                "category_type": category_type,
                "score": cursor,
                "count": min(20, max(1, limit - len(out))),
            }
            if category_id:
                params["category_id"] = category_id
            data = self.s.get("/v9/category/circle/list", params) or {}
            raw_list = data.get("circleList") or []
            if not raw_list:
                break
            out.extend(Circle.from_api(item) for item in raw_list if isinstance(item, Mapping))
            page = data.get("pageInfo") or {}
            if not page.get("hasMore"):
                break
            cursor = page.get("score")
        return out[:limit]

    def search_circles(self, query: str, *, limit: int = 10) -> list[Circle]:
        """按关键词搜圈子，例如学校名。"""
        data = self.s.get(
            "/v8/circle/suggest/search",
            {"query": query, "page_index": 1},
        )
        raw_list = (data or {}).get("circleList") or []
        return [Circle.from_api(item) for item in raw_list if isinstance(item, Mapping)][:limit]

    def resolve_school_circle(self, school: str) -> Circle | None:
        """把学校名解析成圈子：优先精确同名，其次包含该名字且 feed 数最多的那个。"""
        candidates = self.search_circles(school, limit=20)
        if not candidates:
            return None
        exact = [c for c in candidates if c.name.strip() == school.strip()]
        pool = exact or [c for c in candidates if school in c.name] or candidates
        return max(pool, key=lambda c: (c.feed_count or 0))

    # ---------------- 动态 ----------------
    def feeds(
        self,
        circle_id: str,
        *,
        sort: str = "new",
        count: int = 20,
        cursor: Any = 0,
        board_id: str | None = None,
    ) -> Page:
        if sort not in C.SORT_LABELS:
            raise ValueError(f"sort 只支持 {sorted(C.SORT_LABELS)}")
        tpl = C.TPL_WITH_HOT_RCMD if sort in ("new", "reply") and not board_id else C.TPL_DEFAULT
        params: dict[str, Any] = {
            "circle_id": circle_id,
            "board_id": board_id or None,
            "tpl": tpl,
            "stpl": C.STPL_DEFAULT,
            "count": count,
            "withTop": 0 if board_id else 1,
            "score": cursor,
            "list_type": C.SORT_LABELS[sort],
            "extras": 1,
        }
        data = self.s.get("/v8/circle/feed/list", params) or {}
        items, meta = feeds_from_page(data, sort=sort)
        return Page(items=items, **meta)

    def feed_detail(self, feed_id: str) -> tuple[Feed, dict[str, Any]]:
        data = self.s.get("/v7/feeds/show", {"feed_id": feed_id}) or {}
        # 转发类动态 tpl=3/4 时正文在 linkContent[0]
        source = data.get("sourceFeed") if isinstance(data.get("sourceFeed"), Mapping) else {}
        feed = Feed.from_api({"sourceFeed": source} if source else data)
        if not feed.text:
            link = (data.get("linkContent") or [{}])[0]
            if isinstance(link, Mapping) and link.get("content"):
                feed.text = str(link["content"]).strip()
        raw_extra = {
            "tpl": data.get("tpl"),
            "comment_count": feed.comment_count,
            "repost_count": feed.repost_count,
            "fast_comment": data.get("fastComment"),
        }
        return feed, raw_extra

    def comments(
        self,
        feed_id: str,
        *,
        count: int = 20,
        cursor: Any = 0,
        order: str = "hot",
        include_replies: bool = True,
    ) -> Page:
        """评论列表。列表接口自带楼中楼回复（replies.list），需要完整回复时用 replies()。"""
        params = {
            "feed_id": feed_id,
            "score": cursor,
            "count": count,
            "stpl": C.STPL_DEFAULT,
            "source": 1,
        }
        if order == "new":
            params["order"] = "time"
        data = self.s.get("/v8/comment/list", params) or {}
        items, meta = comments_from_page(data)
        if not include_replies:
            for comment in items:
                comment.replies = []
        return Page(items=items, **meta)

    def replies(
        self, feed_id: str, comment_id: str, *, count: int = 20, cursor: Any = 0
    ) -> Page:
        """某条评论下的楼中楼回复（完整分页）。"""
        data = self.s.get(
            "/v8/comment/replylist",
            {
                "stpl": C.STPL_DEFAULT,
                "comment_id": comment_id,
                "score": cursor,
                "feed_id": feed_id,
                "count": count,
            },
        ) or {}
        items, meta = comments_from_page(data)
        return Page(items=items, **meta)

    # ---------------- 账号 ----------------
    def me(self) -> dict[str, Any]:
        """当前登录用户信息（需要登录态）。"""
        uid = self.s.cookies.get(C.COOKIE_UID_ALT) or self.s.cookies.get(C.COOKIE_UID) or ""
        data = self.s.post(
            "/v6/users/show_reduced",
            {"user_id": uid, "log_user_id": uid},
            need_login=True,
        ) or {}
        return {
            "user_id": str(data.get("userId") or uid),
            "nickname": data.get("userName"),
            "avatar": data.get("avatar"),
        }

    # ---------------- 写操作（默认关闭，需在配置里显式开启）----------------
    def post_comment(
        self,
        feed_id: str,
        content: str,
        *,
        reply_comment_id: str | None = None,
    ) -> dict[str, Any]:
        """发评论 / 回复评论（需要登录 + 配置开启写操作）。"""
        content = content.strip()
        if not content:
            raise ValueError("评论内容不能为空")
        if len(content) > 5000:
            raise ValueError("评论内容超过 5000 字")
        body: dict[str, Any] = {
            "feed_id": feed_id,
            "comment_type": "reply" if reply_comment_id else "comment",
            "content": content,
            "tid": int(time.time() * 1000),
        }
        if reply_comment_id:
            body["reply_comment_id"] = reply_comment_id
        result = self.s.request("/v8/comment/text", method="POST", body=body, need_login=True)
        data = result.data or {}
        comment = data.get("comment") if isinstance(data.get("comment"), Mapping) else data
        return {
            "status": result.status,
            "comment_id": str(comment.get("commentId") or "") if isinstance(comment, Mapping) else "",
            "raw": data,
        }

    def like_comment(self, feed_id: str, comment_id: str, *, like: bool = True) -> dict[str, Any]:
        """给评论点赞 / 取消点赞（type: 1=赞, 2=取消）。"""
        result = self.s.request(
            "/comment/like/v20",
            method="POST",
            body={"feed_id": feed_id, "comment_id": comment_id, "type": 1 if like else 2},
            need_login=True,
        )
        return {"status": result.status, "liked": like}


__all__ = ["HuyouAPI", "Page", "HuyouError"]
