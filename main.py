"""Orchestrator: poll Facebook groups, score leads, draft, email digest."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import yaml
from playwright.async_api import Page, async_playwright

import draft
import fb
import notify_email
import score
import store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("main")

last_flush: float = time.time()


def _load_config() -> dict[str, Any]:
    """Load config.local.yaml when present, else config.yaml."""
    root = Path(__file__).resolve().parent
    path = root / "config.local.yaml"
    if not path.exists():
        path = root / "config.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _group_url(entry: Any) -> str:
    """Normalize a groups list entry to a URL string."""
    if isinstance(entry, dict):
        return str(entry.get("url") or entry.get("group_url") or "")
    return str(entry)


async def _login_required(page: Page) -> bool:
    """Return True when the current page looks like a Facebook login wall."""
    # WHY: Persistent sessions expire; detecting login/checkpoint URLs avoids
    # scanning groups while unauthenticated (empty GraphQL feeds).
    url = (page.url or "").lower()
    if any(token in url for token in ("/login", "checkpoint", "/recover")):
        return True
    login_form = page.locator('input[name="email"], input#email')
    try:
        return await login_form.count() > 0 and await login_form.first.is_visible()
    except Exception:
        return False


async def _ensure_logged_in(page: Page) -> None:
    """Open Facebook and block until the user finishes manual login."""
    await page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
    await asyncio.sleep(2)
    if not await _login_required(page):
        return
    print(
        "Chưa đăng nhập Facebook. Hãy đăng nhập thủ công trong cửa sổ trình duyệt, "
        "rồi nhấn Enter tại đây để tiếp tục..."
    )
    await asyncio.to_thread(input)


async def _maybe_flush_digest(digest_seconds: int) -> None:
    """Send persisted pending digests when the interval has elapsed."""
    global last_flush
    if time.time() - last_flush <= digest_seconds:
        return
    pending = store.list_digest_pending()
    if not pending:
        last_flush = time.time()
        return
    if notify_email.send_digest(pending):
        store.mark_notified([str(p["post_id"]) for p in pending])
        last_flush = time.time()
        logger.info("Digest sent for %s leads", len(pending))
    else:
        logger.warning(
            "Digest send failed; keeping %s pending leads in SQLite",
            len(pending),
        )


async def run() -> None:
    """Run the monitor loop until interrupted."""
    cfg = _load_config()
    store.init()

    async with async_playwright() as pw:
        context, page = await fb.start_browser(pw)
        try:
            await _ensure_logged_in(page)
            while True:
                cfg = _load_config()
                keywords = [str(k) for k in (cfg.get("keywords") or [])]
                groups = cfg.get("groups") or []
                scrolls = int(cfg.get("scroll_count") or 3)
                min_score = int(cfg.get("min_score_to_notify") or 3)
                digest_minutes = int(
                    (cfg.get("email") or {}).get("digest_interval_minutes") or 60
                )
                digest_seconds = digest_minutes * 60
                poll_seconds = int(cfg.get("poll_interval_seconds") or 120)

                for entry in groups:
                    group_url = _group_url(entry)
                    if not group_url:
                        continue
                    try:
                        posts = await fb.scan_group(page, group_url, scrolls)
                        for post in posts:
                            post_id = str(post.get("id") or post.get("post_id") or "")
                            if not post_id:
                                continue
                            if store.is_seen(post_id):
                                continue
                            # Mark every scanned id so non-leads are not rescored.
                            store.mark_seen(post_id)

                            text = post.get("text") or ""
                            hits = [
                                kw for kw in keywords if kw.lower() in text.lower()
                            ]
                            if not hits:
                                continue
                            score_val, reasons = score.score(text, hits)
                            if score_val < min_score:
                                continue
                            if not store.is_new(post_id):
                                continue
                            draft_text = draft.draft_reply(
                                text, post.get("author") or "Unknown"
                            )
                            store.insert(post, hits, score_val, reasons, draft_text)
                            logger.info(
                                "Lead %s score=%s author=%s",
                                post_id,
                                score_val,
                                post.get("author"),
                            )
                    except Exception:
                        logger.exception("Error scanning group %s", group_url)
                        continue

                await _maybe_flush_digest(digest_seconds)
                await asyncio.sleep(poll_seconds)
        finally:
            await context.close()


if __name__ == "__main__":
    asyncio.run(run())
