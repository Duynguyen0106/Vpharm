"""Hourly lead digest via Gmail SMTP."""

from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def _load_config() -> dict[str, Any]:
    """Load project config.yaml."""
    with _CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _lead_body(lead: dict[str, Any]) -> str:
    """Format one lead block for the digest body."""
    score = lead.get("score", 0)
    author = lead.get("author") or "Unknown"
    text = (lead.get("text") or "")[:300]
    draft = lead.get("draft") or ""
    url = lead.get("url") or ""
    return (
        f"[{score} pts] {author}\n"
        f"{text}\n\n"
        f"Draft:\n{draft}\n\n"
        f"{url}\n"
        "---"
    )


def send_digest(leads: list[dict[str, Any]]) -> bool:
    """Email a score-sorted digest of up to 10 leads; never raise.

    Returns True on success (or empty input), False if SMTP/send failed.
    """
    if not leads:
        return True
    try:
        config = _load_config()
        company = (config.get("company") or {}).get("name") or "Vpharm"
        email_cfg = config.get("email") or {}
        sender = email_cfg.get("from") or ""
        recipient = email_cfg.get("to") or ""
        app_password = email_cfg.get("app_password") or ""

        ranked = sorted(leads, key=lambda x: int(x.get("score") or 0), reverse=True)
        top = ranked[:10]
        top_score = int(top[0].get("score") or 0)
        body = "\n".join(_lead_body(lead) for lead in top)
        subject = f"🔔 {len(leads)} lead · {top_score}pts · {company}"

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipient

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, app_password)
            smtp.sendmail(sender, [recipient], msg.as_string())
        return True
    except Exception as exc:
        # Scraper/orchestrator must keep running if email fails.
        print(f"notify_email error: {exc}")
        return False


if __name__ == "__main__":
    send_digest(
        [
            {
                "score": 8,
                "author": "Anh Minh",
                "text": "Cần nhập sỉ vitamin C cho phòng khám, tư vấn giá giúp mình với.",
                "draft": "Chào anh Minh, bên em có Vitamin C sỉ...",
                "url": "https://facebook.com/groups/example/posts/1",
            }
        ]
    )
    print("digest attempted")
