"""临时诊断：digest new_count=0 的原因。"""

from __future__ import annotations

from huyou_mcp import HuyouApp, load_config

cfg = load_config()
cfg.watch.schools = ["中国政法大学"]
cfg.watch.skip_ads = False
app = HuyouApp(cfg)
circles = app.resolve_watch_circles()
print("circles:", [(c.circle_id, c.name) for c in circles])
feeds = app.collect(circles)
print("collected:", len(feeds))
for feed in feeds[:6]:
    print(f"  is_ad={feed.is_ad} is_top={feed.is_top} at={feed.published_at} {feed.author} :: {feed.text[:30]!r}")
print("state file:", cfg.state_file, cfg.state_file.exists())
if cfg.state_file.exists():
    print("state:", cfg.state_file.read_text(encoding='utf-8')[:300])
