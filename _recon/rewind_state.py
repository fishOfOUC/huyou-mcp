"""演示用：把已读状态回拨到今天 08:00，让第一封「筛选后」的邮件包含今天上午以来的帖子。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

path = Path("data/state.json")
state = json.loads(path.read_text(encoding="utf-8"))
state["circles"]["874712662708262400"] = []
today = datetime.now().astimezone().replace(hour=8, minute=0, second=0, microsecond=0)
state["last_run"] = today.isoformat(timespec="seconds")
path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
print("已回拨 last_run ->", state["last_run"], "| 已读清空")
