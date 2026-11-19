"""Lead scoring for Facebook group posts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

with _CONFIG_PATH.open(encoding="utf-8") as _f:
    CONFIG: dict[str, Any] = yaml.safe_load(_f) or {}

# Optional in-memory override (used by __main__ demos / tests).
_CONFIG_OVERRIDE: dict[str, Any] | None = None

# Competitor-style CTAs at end of post ("ib giá ạ", "inbox sỉ nhé").
_COMPETITOR_RE = re.compile(
    r"(ib|inbox)\s*(giá|sỉ)?\s*(ạ|nhé)?\s*$",
    re.IGNORECASE,
)


def _contains(haystack: str, needle: str) -> bool:
    """Return True if needle appears in haystack (case-insensitive)."""
    if not needle:
        return False
    return needle.casefold() in haystack.casefold()


def _reload_config() -> dict[str, Any]:
    """Reload config.yaml so intent/catalog edits apply without restart."""
    global CONFIG
    if _CONFIG_OVERRIDE is not None:
        CONFIG = _CONFIG_OVERRIDE
        return CONFIG
    with _CONFIG_PATH.open(encoding="utf-8") as f:
        CONFIG = yaml.safe_load(f) or {}
    return CONFIG


def score(post_text: str, matched_keywords: list[str]) -> tuple[int, list[str]]:
    """Score a post from keyword hits, intent, catalog, and spam signals."""
    cfg = _reload_config()
    text = post_text or ""
    reasons: list[str] = []
    total = 0

    n_kw = len(matched_keywords)
    if n_kw:
        total += n_kw
        reasons.append(f"+{n_kw} keyword match")

    intent = cfg.get("intent_keywords") or {}
    for kind, points, label in (
        ("buy", 3, "buy"),
        ("consult", 2, "consult"),
        ("urgency", 2, "urgency"),
        ("supply", 4, "supply"),
    ):
        for kw in intent.get(kind) or []:
            if _contains(text, str(kw)):
                total += points
                reasons.append(f"+{points} {label}-intent ({kw})")
                break

    for item in cfg.get("catalog") or []:
        name = (item or {}).get("name") or "unknown"
        for tag in (item or {}).get("tag") or []:
            if _contains(text, str(tag)):
                total += 2
                reasons.append(f"+2 catalog product ({name})")
                break
        else:
            continue
        break

    if _COMPETITOR_RE.search(text.strip()):
        total -= 2
        reasons.append("-2 competitor ad pattern")

    if len(text) < 20:
        total -= 1
        reasons.append("-1 short post")

    if total < 0:
        total = 0
    return total, reasons


if __name__ == "__main__":
    # Demo intents/catalog so sample posts exercise the full rubric
    # even when config.yaml lists are still empty.
    _CONFIG_OVERRIDE = {  # noqa: F480 — module-scope demo override
        **CONFIG,
        "intent_keywords": {
            "buy": ["mua", "cần mua", "giá bao nhiêu"],
            "consult": ["tư vấn", "hỏi"],
            "urgency": ["gấp", "hôm nay", "liên hệ ngay"],
            "supply": ["sỉ", "buôn", "nhập hàng", "wholesale"],
        },
        "catalog": [
            {
                "name": "Vitamin C 1000mg",
                "tag": ["vitamin c", "vit C"],
                "price_note": "",
                "usp": "",
            }
        ],
    }

    samples: list[tuple[str, list[str]]] = [
        (
            "Mình cần mua vitamin C gấp hôm nay, ai tư vấn giúp với ạ?",
            ["mua", "vitamin"],
        ),
        (
            "Shop mình bán sỉ thuốc bổ, inbox giá ạ",
            ["sỉ"],
        ),
        (
            "Ib",
            [],
        ),
    ]
    for text, matched in samples:
        points, reasons = score(text, matched)
        print(f"score={points} text={text!r}")
        for reason in reasons:
            print(f"  {reason}")
        print()
