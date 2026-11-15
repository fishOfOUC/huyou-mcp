"""扫码登录（狐友 App 扫一扫），以及从浏览器导入 cookie 的兜底方案。

流程（与网页版一致）：
    1. 先访问 passport.sohu.com 拿 gidinf 设备号；
    2. POST /v8/login/qrcode/create → serialno + 二维码图片(base64)；
    3. 用户用狐友 App 扫码并确认；
    4. 轮询 https://pol.passport.sohu.com/passportapi/polling/apptkbyhy
       code=100 等待、code=0 成功、其他为失效；成功后响应会下发 pchytk/hyuid 等 cookie；
    5. 用 /v6/users/show_reduced 校验登录态并落盘。
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import constants as C
from .session import HuyouError, HuyouSession

QR_PENDING = 100
QR_SUCCESS = 0


@dataclass
class QrLogin:
    serialno: str
    image_bytes: bytes
    image_path: str

    def to_dict(self) -> dict[str, Any]:
        return {"serialno": self.serialno, "image_path": self.image_path}


def start_qr_login(session: HuyouSession, out_dir: Path | str) -> QrLogin:
    session.wait_for_gid()
    if not session.cookies.get(C.COOKIE_GID):
        raise HuyouError(200003, "未能获取 gidinf 设备号（passport.sohu.com 不可达）")
    data = session.request("/v8/login/qrcode/create", method="POST", body={})
    payload = data.data or {}
    serialno = str(payload.get("serialno") or "")
    b64 = str(payload.get("codeBase64") or "")
    if not serialno or not b64:
        raise HuyouError(-1, f"二维码接口返回异常: {payload}")
    raw = base64.b64decode(b64.split(",", 1)[-1])
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "huyou-login-qrcode.jpg"
    path.write_bytes(raw)
    return QrLogin(serialno=serialno, image_bytes=raw, image_path=str(path))


def poll_qr_login(session: HuyouSession, serialno: str, *, verify: bool = True) -> dict[str, Any]:
    form = {
        "serialno": serialno,
        "appid": C.P_APPID,
        "timestamp": str(int(time.time() * 1000)),
        "gid": session.cookies.get(C.COOKIE_GID, ""),
    }
    payload = session.passport_post(C.PASSPORT_QR_POLL, form)
    code = payload.get("code")
    if code == QR_PENDING:
        return {"state": "pending", "raw": payload}
    if code != QR_SUCCESS:
        return {"state": "expired", "raw": payload}

    # 成功后通行证会下发 cookie，落盘
    session.save_cookies()
    result: dict[str, Any] = {"state": "success", "raw": payload}
    if verify:
        try:
            result["user"] = session_me(session)
        except HuyouError as exc:
            result["verify_error"] = str(exc)
    return result


def session_me(session: HuyouSession) -> dict[str, Any]:
    from .api import HuyouAPI

    return HuyouAPI(session).me()


def wait_qr_login(
    session: HuyouSession,
    serialno: str,
    *,
    timeout: float = 180.0,
    interval: float = 3.0,
    on_pending: Any = None,
) -> dict[str, Any]:
    """阻塞轮询，直到扫码成功 / 二维码失效 / 超时。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = poll_qr_login(session, serialno)
        if result["state"] != "pending":
            return result
        if on_pending:
            on_pending(result)
        time.sleep(interval)
    return {"state": "timeout"}


def import_cookies_from_json(session: HuyouSession, payload: str | Path) -> dict[str, str]:
    """从 JSON 文件或 JSON/Cookie 字符串导入登录态（浏览器 F12 里复制即可）。"""
    text: str
    if isinstance(payload, Path) or (isinstance(payload, str) and Path(payload).exists()):
        text = Path(payload).read_text(encoding="utf-8")
    else:
        text = str(payload)
    text = text.strip()
    cookies: dict[str, str] = {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):  # Chrome cookie 导出格式
        cookies = {str(c["name"]): str(c["value"]) for c in parsed if "name" in c}
    elif isinstance(parsed, dict):
        cookies = {str(k): str(v) for k, v in parsed.items()}
    else:  # "k=v; k2=v2" 形式
        for part in text.replace("\n", ";").split(";"):
            if "=" in part:
                key, value = part.split("=", 1)
                cookies[key.strip()] = value.strip()
    wanted = {C.COOKIE_TOKEN, C.COOKIE_UID, C.COOKIE_UID_ALT, C.COOKIE_GID}
    cookies = {k: v for k, v in cookies.items() if k in wanted or k == "reqtype"}
    if not cookies.get(C.COOKIE_TOKEN):
        raise ValueError("导入的 cookie 里没有 pchytk（登录 token），请确认已登录 hy.sns.sohu.com")
    session.cookies.update(cookies)
    session.save_cookies()
    return cookies
