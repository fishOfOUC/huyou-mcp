"""临时诊断脚本：确认 score 与发帖时间的关系、评论字段。"""

from __future__ import annotations

import datetime as dt

from huyou_mcp import HuyouAPI, HuyouSession

api = HuyouAPI(HuyouSession("data/cookies.json"))
page = api.feeds("796893005792620800", sort="new", count=5)
for feed in page.items:
    raw = float(feed.score)
    for label, value in (("score", raw), ("-score", -raw)):
        try:
            when = dt.datetime.fromtimestamp(value / 1000).strftime("%Y-%m-%d %H:%M:%S")
        except (OverflowError, OSError, ValueError):
            when = "n/a"
        print(f"  {label}={value:.0f} -> {when}")
    print(f"  feed={feed.feed_id} author={feed.author} published_at={feed.published_at}")
print("page next_cursor:", page.next_cursor)

print("\ncomments on a busy feed:")
comments = api.comments("1497550572491047936", count=3)
for item in comments.items:
    print(f"  {item.created_at} {item.author} 赞{item.like_count} :: {item.text[:40]}")
print("has_more:", comments.has_more, "next:", comments.next_cursor)
