"""配置加载：config.toml + 环境变量覆盖。"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_ENV = "HUYOU_CONFIG"
DEFAULT_CONFIG_NAME = "config.toml"


@dataclass
class AccountConfig:
    cookies_file: Path


@dataclass
class WatchConfig:
    schools: list[str] = field(default_factory=list)
    circle_ids: list[str] = field(default_factory=list)
    sorts: list[str] = field(default_factory=lambda: ["new"])
    per_circle: int = 20
    max_age_hours: int = 36
    # 活跃圈一天上百条，翻页上限控制抓取量（10 页 ≈ 200 条/圈）
    max_pages_per_circle: int = 10
    # 评论数达到这个门槛的帖子算「有讨论」，邮件里重点展示
    hot_comment_threshold: int = 2
    # 置顶帖通常是圈公告或商单推广，想只看普通动态就打开
    skip_top: bool = False


@dataclass
class MailConfig:
    enabled: bool = False
    host: str = "smtp.qq.com"
    port: int = 465
    user: str = ""
    password: str = ""  # QQ 邮箱「授权码」，不是登录密码
    sender_name: str = "狐友小助手"
    to: list[str] = field(default_factory=list)
    subject_prefix: str = "【狐友】"
    # 一封信最多展示多少条（超出只在本地完整列表里）
    max_posts: int = 120
    # true = 只推「有讨论」的帖子（评论区有人回的那种），其余只在本地存档
    only_hot: bool = False
    # 邮件里给「有讨论」的帖子附上前几条评论，直接能看出大家在聊什么
    include_comments: bool = True
    comment_preview_count: int = 3

    @property
    def recipients(self) -> list[str]:
        return self.to or ([self.user] if self.user else [])


@dataclass
class WriteConfig:
    """写操作（评论/点赞）总开关，默认关闭。"""

    enabled: bool = False


@dataclass
class FilterConfig:
    """邮件内容筛选：只推有实用信息的帖子。"""

    enabled: bool = True
    min_score: int = 2
    extra_useful: list[str] = field(default_factory=list)  # 额外的「有用」关键词
    extra_noise: list[str] = field(default_factory=list)  # 额外的「噪音」关键词


@dataclass
class Config:
    root: Path
    data_dir: Path
    account: AccountConfig
    watch: WatchConfig = field(default_factory=WatchConfig)
    mail: MailConfig = field(default_factory=MailConfig)
    write: WriteConfig = field(default_factory=WriteConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)

    @property
    def outbox_dir(self) -> Path:
        return self.data_dir / "outbox"

    @property
    def pending_file(self) -> Path:
        return self.data_dir / "pending.json"

    @property
    def state_file(self) -> Path:
        return self.data_dir / "state.json"

    @property
    def circle_cache_file(self) -> Path:
        return self.data_dir / "circles.json"


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def load_config(path: str | Path | None = None) -> Config:
    """读取配置；找不到文件时使用默认值（只读浏览不需要任何配置）。"""
    root = Path(__file__).resolve().parents[2]
    cfg_path: Path | None = None
    for candidate in (path, os.environ.get(CONFIG_ENV), root / DEFAULT_CONFIG_NAME):
        if candidate and Path(candidate).exists():
            cfg_path = Path(candidate)
            break

    raw: dict[str, Any] = {}
    if cfg_path:
        with cfg_path.open("rb") as fh:
            raw = tomllib.load(fh)
        base = cfg_path.parent
    else:
        base = root

    data_dir = Path(raw.get("paths", {}).get("data_dir") or "data")
    if not data_dir.is_absolute():
        data_dir = (base / data_dir).resolve()

    cookies = Path(raw.get("account", {}).get("cookies_file") or (data_dir / "cookies.json"))
    if not cookies.is_absolute():
        cookies = (base / cookies).resolve()

    watch_raw = raw.get("watch", {})
    mail_raw = raw.get("mail", {})
    write_raw = raw.get("write", {})
    filter_raw = raw.get("filter", {})

    cfg = Config(
        root=root,
        data_dir=data_dir,
        account=AccountConfig(cookies_file=cookies),
        watch=WatchConfig(
            schools=_as_list(watch_raw.get("schools")),
            circle_ids=_as_list(watch_raw.get("circle_ids")),
            sorts=_as_list(watch_raw.get("sorts")) or ["new"],
            per_circle=int(watch_raw.get("per_circle") or 20),
            max_age_hours=int(watch_raw.get("max_age_hours") or 36),
            max_pages_per_circle=int(watch_raw.get("max_pages_per_circle") or 10),
            hot_comment_threshold=int(watch_raw.get("hot_comment_threshold") or 2),
            skip_top=bool(watch_raw.get("skip_top", False)),
        ),
        mail=MailConfig(
            enabled=bool(mail_raw.get("enabled")),
            host=str(mail_raw.get("host") or "smtp.qq.com"),
            port=int(mail_raw.get("port") or 465),
            user=str(mail_raw.get("user") or ""),
            password=str(mail_raw.get("password") or ""),
            sender_name=str(mail_raw.get("sender_name") or "狐友小助手"),
            to=_as_list(mail_raw.get("to")),
            subject_prefix=str(mail_raw.get("subject_prefix") or "【狐友】"),
            max_posts=int(mail_raw.get("max_posts") or 120),
            only_hot=bool(mail_raw.get("only_hot", False)),
            include_comments=bool(mail_raw.get("include_comments", True)),
            comment_preview_count=int(mail_raw.get("comment_preview_count") or 3),
        ),
        write=WriteConfig(enabled=bool(write_raw.get("enabled"))),
        filter=FilterConfig(
            enabled=bool(filter_raw.get("enabled", True)),
            min_score=int(filter_raw.get("min_score") or 2),
            extra_useful=_as_list(filter_raw.get("extra_useful")),
            extra_noise=_as_list(filter_raw.get("extra_noise")),
        ),
    )

    # 环境变量覆盖（方便用 Windows 计划任务 / CI 注入密钥）
    if os.environ.get("HUYOU_COOKIES_FILE"):
        cfg.account.cookies_file = Path(os.environ["HUYOU_COOKIES_FILE"]).resolve()
    if os.environ.get("HUYOU_MAIL_USER"):
        cfg.mail.user = os.environ["HUYOU_MAIL_USER"]
    if os.environ.get("HUYOU_MAIL_PASSWORD"):
        cfg.mail.password = os.environ["HUYOU_MAIL_PASSWORD"]
    if os.environ.get("HUYOU_MAIL_TO"):
        cfg.mail.to = _as_list(os.environ["HUYOU_MAIL_TO"])
    if os.environ.get("HUYOU_SCHOOLS"):
        cfg.watch.schools = _as_list(os.environ["HUYOU_SCHOOLS"])
    if os.environ.get("HUYOU_WRITE_ENABLED"):
        cfg.write.enabled = os.environ["HUYOU_WRITE_ENABLED"].lower() in ("1", "true", "yes")

    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    return cfg
