"""带签名的 HTTP 会话：cookie 持久化 + 统一响应解包 + 登录态判定。"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import httpx

from . import constants as C
from .crypto import build_headers, js_str, sign_params

# httpx 默认会把每个请求打到日志里，MCP 场景下太吵
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

PROXY_ENV_KEYS = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy")


def resolve_proxy(mode: str | None) -> str | None:
    """决定是否走代理。

    为什么不直接用 httpx 的 trust_env：本机 NO_PROXY 里常见 `[::1]` 这种写法，
    httpx 0.28 解析时会抛 InvalidURL，所以代理由我们自己挑。
    mode: "auto"（默认，读环境变量）/ "none" / 显式代理地址。
    """
    if mode is None:
        mode = "auto"
    text = str(mode).strip()
    if text.lower() in ("none", "off", "false", "direct", ""):
        return None
    if text.lower() == "auto":
        for key in PROXY_ENV_KEYS:
            value = os.environ.get(key)
            if value and "://" in value:
                return value
        return None
    return text


def make_client(*, timeout: float = 15.0, proxy: str | None = "auto") -> httpx.Client:
    kwargs: dict[str, Any] = {
        "timeout": timeout,
        "follow_redirects": True,
        "trust_env": False,  # 避免 NO_PROXY 解析问题，代理显式传入
        "headers": {
            "User-Agent": C.USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        },
    }
    proxy_url = resolve_proxy(proxy)
    if proxy_url:
        kwargs["proxy"] = proxy_url
    return httpx.Client(**kwargs)


class HuyouError(RuntimeError):
    """接口返回非成功状态。"""

    def __init__(self, status: int, desc: str, *, path: str = ""):
        self.status = status
        self.desc = desc
        self.path = path
        super().__init__(f"[{status}] {desc}{(' @ ' + path) if path else ''}")

    @property
    def login_required(self) -> bool:
        return self.status in C.STATUS_LOGIN_REQUIRED

    @property
    def account_blocked(self) -> bool:
        return self.status in C.STATUS_ACCOUNT_BLOCKED


@dataclass
class ApiResult:
    status: int
    desc: str
    data: Any
    raw: dict[str, Any]


class HuyouSession:
    """一个可复用的狐友会话。

    - cookies 默认从磁盘读写，扫码登录一次后长期有效；
    - 首次请求前会自动去 passport 领取 gidinf（设备号），否则部分接口报 200003；
    - 所有业务请求自动签名。
    """

    def __init__(
        self,
        cookies_file: Path | str | None = None,
        *,
        timeout: float = 15.0,
        client: httpx.Client | None = None,
        proxy: str | None = "auto",
    ):
        self.cookies_file = Path(cookies_file) if cookies_file else None
        self._client = client or make_client(timeout=timeout, proxy=proxy)
        self.cookies: dict[str, str] = {}
        self._gid_ready = False
        if self.cookies_file and self.cookies_file.exists():
            self.load_cookies()

    # ---------------- cookie 管理 ----------------
    def load_cookies(self) -> None:
        if not self.cookies_file or not self.cookies_file.exists():
            return
        data = json.loads(self.cookies_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            self.cookies = {k: str(v) for k, v in data.items() if v is not None}

    def save_cookies(self) -> None:
        if not self.cookies_file:
            return
        self.cookies_file.parent.mkdir(parents=True, exist_ok=True)
        self.cookies_file.write_text(
            json.dumps(self.cookies, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _absorb(self, response: httpx.Response) -> None:
        for cookie in response.cookies.jar:
            self.cookies[cookie.name] = cookie.value

    @property
    def logged_in(self) -> bool:
        # 前端判定登录态：pchytk 与 hyuid 都存在
        return bool(self.cookies.get(C.COOKIE_TOKEN)) and bool(self.cookies.get(C.COOKIE_UID))

    def logout(self) -> None:
        self.cookies = {}
        if self.cookies_file and self.cookies_file.exists():
            self.cookies_file.unlink()

    # ---------------- gidinf 引导 ----------------
    def ensure_gid(self, force: bool = False) -> str:
        if self._gid_ready and not force and self.cookies.get(C.COOKIE_GID):
            return self.cookies[C.COOKIE_GID]
        try:
            resp = self._client.get(C.PASSPORT_HOME)
            self._absorb(resp)
        except httpx.HTTPError:
            pass
        self._gid_ready = bool(self.cookies.get(C.COOKIE_GID))
        if self._gid_ready:
            self.save_cookies()
        return self.cookies.get(C.COOKIE_GID, "")

    # ---------------- 请求 ----------------
    def _cookie_header(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self.cookies.items() if v != "")

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        params: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
        base: str = C.BASE_CS,
        need_login: bool = False,
        raise_on_error: bool = True,
    ) -> ApiResult:
        self.ensure_gid()
        if need_login and not self.logged_in:
            raise HuyouError(304023, "未登录：请先调用 login_qrcode_start 扫码登录")

        headers = build_headers(self.cookies)
        url = f"{base.rstrip('/')}/{path.lstrip('/')}"
        send: dict[str, Any] = {"headers": headers}
        cookie_header = self._cookie_header()
        if cookie_header:
            send["headers"]["Cookie"] = cookie_header

        if method.upper() == "GET":
            signed = sign_params(params or {}, headers)
            # 一律转成字符串再发：签名用的是 js_str() 的结果，URL 里必须一模一样
            send["params"] = {key: js_str(value) for key, value in signed.items()}
        else:
            signed = sign_params(body or {}, headers)
            send["data"] = {key: js_str(value) for key, value in signed.items()}

        resp = self._client.request(method.upper(), url, **send)
        self._absorb(resp)

        try:
            payload = resp.json()
        except ValueError as exc:  # 非 JSON（网关 502 等）
            raise HuyouError(-1, f"HTTP {resp.status_code}: {resp.text[:200]}", path=path) from exc

        if not isinstance(payload, dict) or "status" not in payload:
            raise HuyouError(-1, f"响应格式异常: {str(payload)[:200]}", path=path)

        status = int(payload["status"])
        desc = str(payload.get("desc") or "")
        if status != C.STATUS_OK:
            if raise_on_error:
                raise HuyouError(status, desc or "未知错误", path=path)
        return ApiResult(status=status, desc=desc, data=payload.get("data"), raw=payload)

    # ---------------- 便捷方法 ----------------
    def get(self, path: str, params: Mapping[str, Any] | None = None, **kw: Any) -> Any:
        return self.request(path, method="GET", params=params, **kw).data

    def post(self, path: str, body: Mapping[str, Any] | None = None, **kw: Any) -> Any:
        return self.request(path, method="POST", body=body, **kw).data

    def passport_post(self, url: str, form: Mapping[str, Any]) -> dict[str, Any]:
        """通行证接口：不签名，但仍需带 cookie。"""
        cookie_header = self._cookie_header()
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": C.USER_AGENT,
        }
        if cookie_header:
            headers["Cookie"] = cookie_header
        resp = self._client.post(url, data=dict(form), headers=headers)
        self._absorb(resp)
        try:
            return resp.json()
        except ValueError:
            return {"code": -1, "msg": resp.text[:200]}

    def wait_for_gid(self, timeout: float = 5.0) -> str:
        """等待 gidinf 就绪（passport 会下发 cookie，偶发慢）。"""
        deadline = time.time() + timeout
        gid = self.ensure_gid()
        while not gid and time.time() < deadline:
            time.sleep(0.2)
            gid = self.ensure_gid(force=True)
        return gid

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HuyouSession":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
