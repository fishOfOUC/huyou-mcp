"""临时诊断：评论列表参数对比。"""

from __future__ import annotations

import json

from huyou_mcp import HuyouSession

s = HuyouSession("data/cookies.json")
feed = "1497550572491047936"

variants = {
    "base(+source=1)": {"feed_id": feed, "score": 0, "count": 20, "stpl": "1,2,4,7,8,9,16", "source": 1},
    "no-source": {"feed_id": feed, "score": 0, "count": 20, "stpl": "1,2,4,7,8,9,16"},
    "order-time": {"feed_id": feed, "score": 0, "count": 20, "stpl": "1,2,4,7,8,9,16", "order": "time"},
    "stpl-full": {"feed_id": feed, "score": 0, "count": 20, "stpl": "1,2,3,4,7,9,11,12,13,16"},
    "sort-reply": {"feed_id": feed, "score": 0, "count": 20, "stpl": "1,2,4,7,8,9,16", "sort": 1},
}

for name, params in variants.items():
    result = s.request("/v8/comment/list", params=params, raise_on_error=False)
    data = result.data or {}
    listing = data.get("list") or []
    print(f"[{name}] status={result.status} desc={result.desc!r} keys={list(data.keys())} n={len(listing)}")
    if listing:
        first = listing[0]
        print("   first:", json.dumps({k: first.get(k) for k in ("commentId", "userName", "timeId", "likeCount")}, ensure_ascii=False))
    else:
        print("   pageInfo:", json.dumps(data.get("pageInfo"), ensure_ascii=False))

# 换一个确定有评论的 feed 再试
feed2 = "1497671078263325824"
r2 = s.request("/v8/comment/list", params={"feed_id": feed2, "score": 0, "count": 20, "stpl": "1,2,4,7,8,9,16"})
print(f"\n[feed {feed2}] status={r2.status} n={len(((r2.data or {}).get('list') or []))}")
