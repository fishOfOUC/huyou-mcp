from __future__ import annotations
import json
from huyou_mcp import HuyouAPI, HuyouSession

api = HuyouAPI(HuyouSession("data/cookies.json"))
raw = api.s.get("/v8/circle/feed/list", {
    "circle_id": "796893005792620800", "tpl": "1,2,3,4,26,29", "stpl": "1,2,3,4,7,9,11,12,13,16",
    "count": 4, "withTop": 1, "score": 0, "list_type": 2, "extras": 1,
})
for item in raw["feedList"]:
    src = item.get("sourceFeed") or item
    keep = {k: src.get(k) for k in ("feedId","userName","isTopFeed","supportPaidTop","paidTopEnable","lottoFeed","publishSource","type","stpl","exposureCount","watch","sourceAppId","souceAppName")}
    print(json.dumps(keep, ensure_ascii=False))
