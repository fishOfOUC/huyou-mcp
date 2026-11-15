"""用今天海大圈的全部帖子检验筛选规则命中情况。"""

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

useful, noise = [], []
for post in posts:
    verdict = classify(post.text, comment_count=post.comment_count)
    (useful if verdict.useful else noise).append((post, verdict))

print(f"共 {len(posts)} 条：判为有用 {len(useful)} 条（{len(useful)/max(len(posts),1):.0%}），噪音 {len(noise)} 条")
print("\n命中主题分布：")
for label, count in Counter(h for _, v in useful for h in v.useful_hits).most_common():
    print(f"  {label:<10} {count}")
print("\n噪音原因分布：")
for label, count in Counter((v.noise_hits[0] if v.noise_hits else v.note) for _, v in noise).most_common():
    print(f"  {str(label):<12} {count}")

print("\n=== 判为有用（前 18 条）===")
for post, verdict in useful[:18]:
    print(f" + {post.published_at[11:16]} {post.author}: {post.text[:56]!r}  [{verdict.reason}]")

print("\n=== 判为噪音（前 18 条）===")
for post, verdict in noise[:18]:
    print(f" - {post.published_at[11:16] if post.published_at else '??:??'} {post.author}: {post.text[:56]!r}  [{verdict.reason}]")
