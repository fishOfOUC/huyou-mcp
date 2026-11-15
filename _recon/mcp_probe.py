"""用官方 MCP 客户端以 stdio 方式连上我们的 server，逐个调用工具做验收。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]


def _text(result) -> str:
    blocks = getattr(result, "content", None) or []
    for block in blocks:
        text = getattr(block, "text", None)
        if text:
            return text
    return json.dumps(str(result), ensure_ascii=False)


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "huyou_mcp.cli", "serve"],
        cwd=str(ROOT),
    )
    async with Client(params) as client:
        tools = await client.list_tools()
        names = [tool.name for tool in tools.tools]
        print(f"工具 {len(names)} 个：")
        for name in names:
            print("  -", name)

        print("\n[1] huyou_search_circles(中国政法大学)")
        result = await client.call_tool("huyou_search_circles", {"keyword": "中国政法大学", "limit": 3})
        payload = json.loads(_text(result))
        for circle in payload.get("circles", [])[:3]:
            print(f"    {circle['circle_id']} {circle['name']} {circle['url']}")
        circle_id = payload["circles"][0]["circle_id"]

        print(f"\n[2] huyou_circle_feeds({circle_id}, sort=new, count=3)")
        result = await client.call_tool(
            "huyou_circle_feeds", {"circle_id": circle_id, "sort": "new", "count": 3}
        )
        payload = json.loads(_text(result))
        for feed in payload["feeds"]:
            print(f"    {feed['published_at']} @{feed['author']} 评论{feed['comment_count']}")
            print(f"      {feed['text'][:60]!r}")
            print(f"      {feed['url']}")
        feed_id = payload["feeds"][0]["feed_id"]

        print(f"\n[3] huyou_feed_detail({feed_id})")
        result = await client.call_tool("huyou_feed_detail", {"feed_id": feed_id})
        payload = json.loads(_text(result))
        print(f"    {payload['feed']['author']}: {payload['feed']['text'][:60]!r}")

        print(f"\n[4] huyou_feed_comments({feed_id})")
        result = await client.call_tool("huyou_feed_comments", {"feed_id": feed_id, "count": 3})
        payload = json.loads(_text(result))
        print(f"    返回 {payload['count']} 条评论")

        print("\n[5] huyou_login_status()")
        result = await client.call_tool("huyou_login_status", {})
        print("   ", _text(result)[:200])

        print("\n[6] 写操作未开启时应被拒绝：huyou_post_comment(...)")
        result = await client.call_tool("huyou_post_comment", {"feed_id": feed_id, "content": "test"})
        print("   ", _text(result)[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
