"""看看不同 min_score 门槛下筛出多少条，帮用户选默认值。"""

from __future__ import annotations

from collections import Counter

from huyou_mcp import HuyouAPI, HuyouSession
from huyou_mcp.filters import classify

CIRCLE = "874712662708262400"
api = HuyouAPI(HuyouSession("data/cookies.json"))

posts = []
cursor = 0
for _ in range(10):
    page = api.feeds(CIRCLE, sort="new", count=20, cursor=cursor)
    posts.extend(page.items)
    if not page.has_more:
        break
    cursor = page.next_cursor

scores = [classify(p.text, comment_count=p.comment_count, min_score=-99).score for p in posts]
hist = Counter(scores)
print("分数分布（score: 条数）：")
for score in sorted(hist):
    print(f"  {score:>3}: {hist[score]}")
print()
for threshold in (1, 2, 3, 4, 5):
    passed = sum(1 for s in scores if s >= threshold)
    print(f"min_score >= {threshold} → 推送 {passed} 条 / 共 {len(posts)} 条（{passed/len(posts):.0%}）")
