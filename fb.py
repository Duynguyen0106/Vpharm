"""Playwright-based Facebook group scraper (monitor-only)."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any

import playwright_stealth
import yaml
from playwright.async_api import BrowserContext, Page, Playwright, Response, async_playwright

logger = logging.getLogger(__name__)

_POST_ID_RE = re.compile(r"/posts/(\d+)")
_NUMERIC_ID_RE = re.compile(r"^\d{5,}$")


def _load_config() -> dict[str, Any]:
    """Load config.local.yaml when present, else config.yaml."""
    root = Path(__file__).resolve().parent
    path = root / "config.local.yaml"
    if not path.exists():
        path = root / "config.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _usable_post_id(raw_id: Any) -> str | None:
    """Return a numeric post id suitable for /posts/{id} URLs, else None."""
    # WHY: GraphQL trees mix story/comment tokens with real post ids; only
    # digit ids form stable facebook.com/.../posts/{id} links operators can open.
    text = str(raw_id or "").strip()
    if _NUMERIC_ID_RE.match(text):
        return text
    match = _POST_ID_RE.search(text)
    return match.group(1) if match else None


async def start_browser(
    pw: Playwright,
    user_data_dir: str | None = None,
) -> tuple[BrowserContext, Page]:
    """Launch a persistent Chromium context and return (context, page)."""
    # Persistent profile keeps the Facebook login cookie across runs without
    # re-auth. Prefer headed (or Xvfb) over headless — FB often serves empty
    # GraphQL feeds to headless Chromium.
    session_dir = user_data_dir or os.environ.get("FB_SESSION_DIR", "./session")
    headless = os.environ.get("FB_HEADLESS", "0").strip() in {"1", "true", "True"}
    context = await pw.chromium.launch_persistent_context(
        session_dir,
        headless=headless,
        viewport={"width": 1280, "height": 900},
        args=["--disable-dev-shm-usage"],
    )
    page = context.pages[0] if context.pages else await context.new_page()
    await playwright_stealth.stealth_async(page)
    return context, page


def _walk_posts(node: Any, out: list[dict[str, Any]]) -> None:
    """Recursively collect post-like nodes from a GraphQL JSON tree."""
    # WHY: Facebook GraphQL nesting changes often; walking the whole tree is
    # more durable than hard-coding feed edge paths that break between deploys.
    if isinstance(node, dict):
        message = node.get("message")
        text = message.get("text") if isinstance(message, dict) else None
        post_id = _usable_post_id(node.get("id"))
        if text and post_id:
            author_obj = node.get("author") or {}
            author = author_obj.get("name") if isinstance(author_obj, dict) else None
            if not author:
                actors = node.get("actors") or [{}]
                first = actors[0] if actors else {}
                author = first.get("name", "Unknown") if isinstance(first, dict) else "Unknown"
            out.append({"id": post_id, "text": text, "author": author or "Unknown"})
        for value in node.values():
            _walk_posts(value, out)
    elif isinstance(node, list):
        for item in node:
            _walk_posts(item, out)


async def _article_body_text(article: Any) -> str:
    """Pick the longest dir=auto span as likely body (skip author/time chips)."""
    spans = article.locator('span[dir="auto"]')
    count = await spans.count()
    best = ""
    for i in range(count):
        try:
            text = (await spans.nth(i).inner_text()).strip()
        except Exception:
            continue
        if len(text) > len(best):
            best = text
    return best


async def _dom_fallback_posts(page: Page, group_url: str) -> list[dict[str, Any]]:
    """Scrape visible article nodes when GraphQL yielded no posts."""
    posts: list[dict[str, Any]] = []
    articles = page.locator('div[role="article"]')
    count = await articles.count()
    for i in range(count):
        article = articles.nth(i)
        text = await _article_body_text(article)
        post_id = None
        links = article.locator("a[href]")
        link_count = await links.count()
        for j in range(link_count):
            href = await links.nth(j).get_attribute("href") or ""
            match = _POST_ID_RE.search(href)
            if match:
                post_id = match.group(1)
                break
        if text and post_id:
            posts.append(
                {
                    "post_id": post_id,
                    "id": post_id,
                    "text": text,
                    "author": "Unknown",
                    "url": f"{group_url.rstrip('/')}/posts/{post_id}",
                    "group_url": group_url,
                    "group": group_url,
                }
            )
    return posts


async def scan_group(page: Page, group_url: str, scrolls: int = 3) -> list[dict[str, Any]]:
    """Scan a group feed via GraphQL sniffing (DOM fallback if empty)."""
    collected: list[dict[str, Any]] = []

    async def on_response(resp: Response) -> None:
        # WHY: Group feed items arrive as opaque /api/graphql POSTs; sniffing
        # responses avoids fragile DOM-only selectors that Facebook A/B tests.
        try:
            if resp.request.method != "POST":
                return
            if "/api/graphql" not in resp.url:
                return
            data = await resp.json()
        except Exception:
            # Many GraphQL payloads are non-JSON or unrelated to the feed.
            return
        _walk_posts(data, collected)

    page.on("response", on_response)
    try:
        await page.goto(group_url, wait_until="domcontentloaded")
        await asyncio.sleep(4)
        for _ in range(scrolls):
            await page.mouse.wheel(0, 2000)
            await asyncio.sleep(3)
    finally:
        page.remove_listener("response", on_response)

    deduped: dict[str, dict[str, Any]] = {}
    for post in collected:
        post_id = _usable_post_id(post.get("id"))
        if not post_id or post_id in deduped:
            continue
        enriched = {
            "post_id": post_id,
            "id": post_id,
            "text": post["text"],
            "author": post.get("author", "Unknown"),
            "url": f"{group_url.rstrip('/')}/posts/{post_id}",
            "group_url": group_url,
            "group": group_url,
        }
        deduped[post_id] = enriched

    posts = list(deduped.values())
    if not posts:
        logger.warning(
            "GraphQL yielded 0 posts for %s; using DOM fallback (div[role=article])",
            group_url,
        )
        posts = await _dom_fallback_posts(page, group_url)
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for post in posts:
            pid = post["post_id"]
            if pid in seen:
                continue
            seen.add(pid)
            unique.append(post)
        posts = unique
    return posts


async def _main() -> None:
    """Load config and print the first three posts from the first group."""
    config = _load_config()
    groups = config.get("groups") or []
    if not groups:
        print("No group configured in config.yaml (groups is empty).")
        return
    group_url = groups[0]
    if isinstance(group_url, dict):
        group_url = group_url.get("url") or group_url.get("group_url")
    scrolls = int(config.get("scroll_count", 3))
    async with async_playwright() as pw:
        context, page = await start_browser(pw)
        try:
            posts = await scan_group(page, str(group_url), scrolls=scrolls)
            for post in posts[:3]:
                print(post)
        finally:
            await context.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
