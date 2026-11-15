"""补充验收：categories / campus_circles / watch_list / digest 四个工具。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]


def _text(result) -> str:
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            return text
    return "{}"


async def main() -> int:
    params = StdioServerParameters(command=sys.executable, args=["-m", "huyou_mcp.cli", "serve"], cwd=str(ROOT))
    async with Client(params) as client:
        cat = json.loads(_text(await client.call_tool("huyou_categories", {})))
        print("categories:", [(c["name"], c["type"], c["id"]) for c in cat["categories"][:5]])

        campus = json.loads(_text(await client.call_tool("huyou_campus_circles", {"limit": 5})))
        print("campus:", [(c["name"], c["feed_count"]) for c in campus["circles"]])

        watch = json.loads(_text(await client.call_tool("huyou_watch_list", {})))
        print("watch_list:", watch)

        digest = json.loads(_text(await client.call_tool("huyou_alumni_digest", {"dry_run": True, "send": False})))
        print("digest(new_count):", digest.get("new_count"), "| circles:", digest.get("circles"))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
