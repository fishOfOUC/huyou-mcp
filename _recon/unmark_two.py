"""把 --no-send 误标记为已读的最后两条退还回未读状态。"""

from __future__ import annotations

import json
from pathlib import Path

path = Path("data/state.json")
state = json.loads(path.read_text(encoding="utf-8"))
bucket = state["circles"]["874712662708262400"]
removed = bucket[-2:]
del bucket[-2:]
state["last_run"] = "2026-11-15T13:15:52+08:00"
path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
print("退还 2 条：", removed)
print("剩余已读：", len(bucket))
