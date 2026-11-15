"""临时诊断：category_type / category_id 的语义，确定「校园圈子」用哪组参数。"""

from __future__ import annotations

from huyou_mcp import HuyouSession

s = HuyouSession("data/cookies.json")
variants = [
    ("type=2 无id（热门圈子？）", {"category_type": 2, "score": 0, "count": 8}),
    ("type=1 id=4（校园）", {"category_type": 1, "category_id": "4", "score": 0, "count": 8}),
    ("type=3（新圈速报）", {"category_type": 3, "score": 0, "count": 8}),
    ("type=1 id=9（游戏）", {"category_type": 1, "category_id": "9", "score": 0, "count": 5}),
]
for label, params in variants:
    data = s.get("/v9/category/circle/list", params) or {}
    circles = data.get("circleList") or []
    names = [c.get("circleName") for c in circles]
    print(f"[{label}] n={len(circles)}")
    print("   ", "、".join(str(n) for n in names))
