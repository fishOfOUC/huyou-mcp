"""诊断：评论详情字段（是否自带 initialReplies）、楼中楼回复接口。"""

from __future__ import annotations

import json

from huyou_mcp import HuyouSession

s = HuyouSession("data/cookies.json")
FEED = "1497550572491047936"  # 之前测过有 12 条评论

data = s.get("/v8/comment/list", {"feed_id": FEED, "score": 0, "count": 20, "stpl": "1,2,4,7,8,9,16"})
items = data.get("list") or []
print(f"评论 {len(items)} 条；第一条全部字段：")
first = items[0]
print(sorted(first.keys()))
print(json.dumps({k: first[k] for k in ("commentId", "userName", "replyCount", "likeCount", "timeId")}, ensure_ascii=False))

with_replies = [c for c in items if (c.get("replyCount") or 0) > 0]
print(f"\n有楼中楼回复的评论：{len(with_replies)} 条")
if with_replies:
    target = with_replies[0]
    print("目标评论:", target["commentId"], target["userName"], "replyCount=", target["replyCount"])
    print("initialReplies 存在？", "initialReplies" in target)
    if target.get("initialReplies"):
        print("initialReplies:", json.dumps(target["initialReplies"], ensure_ascii=False)[:600])

    replies = s.get(
        "/v8/comment/replylist",
        {
            "stpl": "1,2,3,4,7,9,11,12,13,16",
            "comment_id": target["commentId"],
            "score": 0,
            "feed_id": FEED,
            "count": 10,
        },
    )
    rl = replies.get("list") or []
    print(f"\nreplylist 返回 {len(rl)} 条：")
    for reply in rl:
        print(f"  - {reply.get('userName')} -> {reply.get('replyUserName') or reply.get('targetUserName') or ''}: "
              f"{str(reply.get('content'))[:40]}  赞{reply.get('likeCount')}")
    print("reply 字段:", sorted(rl[0].keys()) if rl else "-")
    print("pageInfo:", json.dumps(replies.get("pageInfo"), ensure_ascii=False))
