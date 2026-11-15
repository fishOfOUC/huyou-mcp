# 海大圈子活动量统计：今天发了多少帖、活跃度如何

from __future__ import annotations

import datetime as dt

from huyou_mcp import HuyouAPI, HuyouSession

CIRCLE = "874712662708262400"  # 中国海洋大学
api = HuyouAPI(HuyouSession("data/cookies.json"))

now = dt.datetime.now().astimezone()
today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
yesterday_start = today_start - dt.timedelta(days=1)
week_start = today_start - dt.timedelta(days=7)

cursor = 0
total_today = total_24h = total_7d = 0
fetched = 0
oldest = None
pages = 0
per_page = 20

page0 = api.feeds(CIRCLE, sort="new", count=per_page, cursor=0)
print("圈子动态总数(totalCount):", page0.total_count)

while pages < 8:
    page = page0 if pages == 0 else api.feeds(CIRCLE, sort="new", count=per_page, cursor=cursor)
    pages += 1
    if not page.items:
        break
    for feed in page.items:
        if not feed.published_at:
            continue
        when = dt.datetime.fromisoformat(feed.published_at)
        fetched += 1
        if when >= today_start:
            total_today += 1
        if when >= now - dt.timedelta(hours=24):
            total_24h += 1
        if when >= week_start:
            total_7d += 1
        oldest = when
    cursor = page.next_cursor
    if not page.has_more or (oldest and oldest < week_start):
        break

print(f"翻页 {pages} 次，检查 {fetched} 条：")
print(f"  今天({today_start:%m-%d}) 发帖: {total_today}")
print(f"  最近 24 小时: {total_24h}")
print(f"  最近 7 天: {total_7d}")
print(f"  已翻到最早一条时间: {oldest}")

# 抽查一条帖子详情 + 评论
sample = page0.items[3]
detail, _ = api.feed_detail(sample.feed_id)
print(f"\n详情抽查: {detail.author} / {detail.published_at} / 配图{len(detail.pics)}张")
print("  ", detail.text[:60].replace("\n", " "))
print("  ", detail.url)
