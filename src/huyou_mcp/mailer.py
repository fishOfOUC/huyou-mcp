"""QQ 邮箱 SMTP 发信（smtp.qq.com:465，SSL，密码用「授权码」）。"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

from .config import MailConfig


class MailError(RuntimeError):
    pass


def _build_message(cfg: MailConfig, subject: str, text: str, html: str | None) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg.sender_name, cfg.user))
    msg["To"] = ", ".join(cfg.recipients)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="qq.com")
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def send_mail(
    cfg: MailConfig,
    subject: str,
    text: str,
    html: str | None = None,
    *,
    dry_run: bool = False,
    outbox: Path | None = None,
) -> dict[str, str]:
    """发送邮件；dry_run=True 时只把渲染结果写到 outbox 目录，便于检查样式。"""
    if dry_run:
        if outbox is None:
            raise ValueError("dry_run 需要提供 outbox 目录")
        outbox.mkdir(parents=True, exist_ok=True)
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in subject)[:80]
        html_path = outbox / f"{safe}.html"
        text_path = outbox / f"{safe}.txt"
        html_path.write_text(html or f"<pre>{text}</pre>", encoding="utf-8")
        text_path.write_text(text, encoding="utf-8")
        return {"mode": "dry-run", "html": str(html_path), "text": str(text_path)}

    missing = [
        name
        for name, value in (("mail.user", cfg.user), ("mail.password", cfg.password))
        if not value
    ]
    if missing:
        raise MailError(f"缺少邮箱配置: {', '.join(missing)}（password 填 QQ 邮箱授权码）")
    if not cfg.recipients:
        raise MailError("缺少收件人: mail.to")

    msg = _build_message(cfg, subject, text, html)
    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(cfg.host, cfg.port, context=context, timeout=20) as smtp:
            smtp.login(cfg.user, cfg.password)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        raise MailError(
            "SMTP 认证失败：password 必须填 QQ 邮箱生成的「授权码」"
            "（mail.qq.com → 设置 → 账户 → 开启 POP3/SMTP → 生成授权码）"
        ) from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"发送失败: {exc}") from exc
    return {"mode": "sent", "to": ", ".join(cfg.recipients), "subject": subject}
