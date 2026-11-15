"""狐友 MCP：只读浏览 + 扫码登录 + 每日邮件摘要。"""

from .api import HuyouAPI, Page
from .config import Config, load_config
from .constants import FEED_URL, CIRCLE_URL
from .models import Circle, Comment, Feed
from .service import HuyouApp
from .session import HuyouError, HuyouSession

__all__ = [
    "HuyouAPI",
    "HuyouApp",
    "HuyouError",
    "HuyouSession",
    "Page",
    "Circle",
    "Comment",
    "Feed",
    "Config",
    "load_config",
    "FEED_URL",
    "CIRCLE_URL",
]

__version__ = "0.1.0"
