"""回拨已读状态：把 last_run 设为 6 小时前，让下一封邮件覆盖最近 6 小时。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

path = Path("data/state.json")
state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"circles": {}}
state.setdefault("circles", {})["874712662708262400"] = []
state["last_run"] = (datetime.now().astimezone() - timedelta(hours=6)).isoformat(timespec="seconds")
path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
print("last_run =", state["last_run"], "| 已读已清空")
