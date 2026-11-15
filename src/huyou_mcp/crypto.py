"""狐友 Web 端请求头与签名（sig）实现。

对应前端 bundle 里的三个函数（逆向得到的等价实现）：

    Iu()  -> 基础请求头（从 cookie 读登录态）
    OB()  -> 追加 appid / s-nonce / flyer / S-VS 四个动态头
    Hi()  -> 对 query（GET）或 body（POST）计算 sig

签名原文 = sort(["k=v", ...]) 后依次拼接 + app_key，取 md5 十六进制小写。
参与拼接的键包括业务参数 + flyer + appid + app_key_vs，以及从请求头带进来的
s-nonce / S-VS 两条。参数为 None 的键会被丢弃（前端 `if (l[f] == null) delete`）。
"""

from __future__ import annotations

import hashlib
import random
import time
from typing import Any, Mapping, MutableMapping

from . import constants as C


def new_nonce() -> str:
    """生成 s-nonce：Date.now() 的 16 进制 + 随机 16 进制，截断到 32 位。"""
    out = format(int(time.time() * 1000), "x")
    while len(out) < 32:
        out += format(random.getrandbits(16), "x").zfill(4)
    return out[:32]


def js_str(value: Any) -> str:
    """模拟 JS 的字符串化，避免 Python 的 True/False/1.0 与 JS 不一致。

    签名用的是字符串形式，真正发出去的请求也必须用同一份字符串，
    否则 float 会被 httpx 写成 "-1794717435133.0" 而签名算的是 "-1794717435133"，
    服务端就会返回 `n:sig check fail!`。
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def sign_params(
    params: Mapping[str, Any] | None,
    headers: Mapping[str, str],
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """返回带 sig 的参数副本（GET 用 query，POST 用 form body）。"""
    out: dict[str, Any] = dict(params or {})
    if out.get("sig"):
        return out

    out["flyer"] = int(now_ms if now_ms is not None else time.time() * 1000)
    out["appid"] = C.APP_ID
    out["app_key_vs"] = C.APP_KEY_VS

    pairs: list[str] = []
    for key in list(out.keys()):
        value = out[key]
        if value is None:
            del out[key]
            continue
        pairs.append(f"{key}={js_str(value)}")

    nonce = headers.get("s-nonce")
    if nonce:
        pairs.append(f"s-nonce={nonce}")
        pairs.append(f"S-VS={headers.get('S-VS') or headers.get('s-vs') or C.APP_KEY_VS}")

    pairs.sort()
    pairs.append(C.APP_KEY)
    out["sig"] = hashlib.md5("".join(pairs).encode("utf-8")).hexdigest()
    return out


def build_headers(cookies: Mapping[str, str], *, now_ms: int | None = None) -> dict[str, str]:
    """构造一整套请求头（等价前端 Iu() + OB() 的合并结果）。"""
    gid = cookies.get(C.COOKIE_GID, "")
    return {
        "Content-Type": "application/x-www-form-urlencoded",
        "S-PID": cookies.get(C.COOKIE_UID, ""),
        "S-PPID": cookies.get(C.COOKIE_UID_ALT, ""),
        "S-VS": C.APP_KEY_VS,
        "S-CID": gid,
        "gid": gid,
        "token": cookies.get(C.COOKIE_TOKEN, ""),
        "P-APPID": C.P_APPID,
        "appid": str(C.APP_ID),
        "s-nonce": new_nonce(),
        "flyer": str(int(now_ms if now_ms is not None else time.time() * 1000)),
    }


def sign_query(
    params: Mapping[str, Any] | None,
    cookies: Mapping[str, str],
) -> tuple[dict[str, Any], dict[str, str]]:
    """GET 用：返回 (签名后的 query, 请求头)。"""
    headers = build_headers(cookies)
    return sign_params(params, headers), headers
