"""临时诊断：api.comments() 为什么空。"""

from __future__ import annotations

from huyou_mcp import HuyouAPI, HuyouSession

api = HuyouAPI(HuyouSession("data/cookies.json"))
page = api.comments("1497550572491047936", count=3)
print("items:", len(page.items), "has_more:", page.has_more, "next:", page.next_cursor)
for item in page.items:
    print(" ", item.author, item.created_at, item.like_count, item.text[:30])

raw = api.s.get("/v8/comment/list", {"feed_id": "1497550572491047936", "score": 0, "count": 3, "stpl": "1,2,3,4,7,9,11,12,13,16", "source": 1})
print("raw keys:", list(raw.keys()), "list len:", len(raw.get("list") or []))
