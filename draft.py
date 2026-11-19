"""Vietnamese reply drafting via Anthropic Messages API (httpx)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import yaml

_ROOT = Path(__file__).resolve().parent
_API_URL = "https://api.anthropic.com/v1/messages"
_FALLBACK = "[AI draft failed - reply manually]"


def _load_config() -> dict[str, Any]:
    """Load config.local.yaml when present, else config.yaml."""
    path = _ROOT / "config.local.yaml"
    if not path.exists():
        path = _ROOT / "config.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _format_catalog(catalog: list[dict[str, Any]]) -> str:
    """Render catalog items as a short Vietnamese bullet list for the prompt."""
    if not catalog:
        return "(Chưa có danh mục sản phẩm trong config.)"
    lines: list[str] = []
    for item in catalog:
        name = item.get("name") or "Sản phẩm"
        tags = ", ".join(str(t) for t in (item.get("tag") or []))
        price = item.get("price_note") or ""
        usp = item.get("usp") or ""
        parts = [name]
        if tags:
            parts.append(f"tag: {tags}")
        if price:
            parts.append(f"giá: {price}")
        if usp:
            parts.append(f"USP: {usp}")
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines)


def draft_reply(post_text: str, author: str) -> str:
    """Draft a Vietnamese comment reply for a group post via Anthropic."""
    try:
        config = _load_config()
        company = config.get("company") or {}
        name = company.get("name") or "công ty"
        tone = company.get("tone") or "chuyên nghiệp, thân thiện"
        phone = (company.get("phone") or "").strip()
        ai = config.get("ai") or {}
        api_key = (ai.get("api_key") or "").strip()
        model = ai.get("model") or "claude-sonnet-4-6"
        catalog = config.get("catalog") or []

        phone_line = (
            f"Số điện thoại liên hệ công ty: {phone}. Có thể nhắc nhẹ trong CTA.\n"
            if phone
            else ""
        )
        system = (
            f"Bạn là chuyên viên tư vấn của {name}, công ty bán SỈ thực phẩm chức năng.\n"
            f"Tone: {tone}.\n"
            f"{phone_line}"
            "Đọc kỹ bài đăng và hiểu nhu cầu thật của khách.\n"
            "Đưa lời khuyên hữu ích TRƯỚC, bán hàng SAU.\n"
            "KHÔNG sáo rỗng, KHÔNG spam, tối đa 2 emoji. 3-5 câu.\n"
            "Gợi ý 1-2 sản phẩm phù hợp từ danh mục.\n"
            "Kết thúc CTA nhẹ nhàng. Chỉ trả về nội dung comment, không giải thích."
        )
        user_content = (
            "Danh mục sản phẩm:\n"
            f"{_format_catalog(catalog)}\n\n"
            f"Tác giả bài đăng: {author}\n"
            f"Nội dung bài đăng:\n{post_text}\n\n"
            "Viết comment trả lời:"
        )
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": model,
            "max_tokens": 400,
            "system": system,
            "messages": [{"role": "user", "content": user_content}],
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(_API_URL, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        return str(data["content"][0]["text"]).strip()
    except Exception:
        return _FALLBACK


if __name__ == "__main__":
    sample = (
        "Mình cần nhập sỉ vitamin C và dầu cá cho phòng khám, "
        "ai tư vấn giá buôn giúp mình với ạ?"
    )
    print(draft_reply(sample, "Anh Minh"))
