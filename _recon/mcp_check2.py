import asyncio, json, sys
from pathlib import Path
from mcp import Client
from mcp.client.stdio import StdioServerParameters
ROOT = Path("E:/Code/my_code/huyou_auto")
async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m","huyou_mcp.cli","serve"], cwd=str(ROOT))
    async with Client(params) as c:
        tools = [t.name for t in (await c.list_tools()).tools]
        print("tools:", len(tools))
        r = await c.call_tool("huyou_alumni_digest", {"preview_only": True})
        text = next((b.text for b in r.content if getattr(b, "text", None)), "")
        d = json.loads(text)
        print("preview:", {k: d.get(k) for k in ("new_count","hot_count","subject","archive")})
        r2 = await c.call_tool("huyou_feed_comments", {"feed_id": "1497647880360625152", "count": 2})
        d2 = json.loads(next((b.text for b in r2.content if getattr(b,"text",None)), "{}"))
        for cm in d2.get("comments", [])[:2]:
            print("  评论:", cm["author"], "|", cm["region"], "|", cm["text"][:40], "| 楼中楼", len(cm["replies"]))
asyncio.run(main())
