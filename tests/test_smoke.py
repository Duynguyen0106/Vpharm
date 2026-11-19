"""Smoke tests for score, seen-posts, digest flags, and dashboard draft UI."""

from __future__ import annotations

import base64
import os
import tempfile
import unittest
from pathlib import Path


class ScoreTests(unittest.TestCase):
    """Keyword / intent scoring smoke checks."""

    def test_buy_and_catalog_score(self) -> None:
        import score

        score._CONFIG_OVERRIDE = {
            "intent_keywords": {
                "buy": ["mua"],
                "consult": ["tư vấn"],
                "urgency": ["gấp"],
                "supply": ["sỉ"],
            },
            "catalog": [
                {
                    "name": "Vitamin C 1000mg",
                    "tag": ["vitamin c"],
                    "price_note": "",
                    "usp": "",
                }
            ],
        }
        points, reasons = score.score(
            "Cần mua vitamin C gấp và tư vấn thêm chút nữa",
            ["mua"],
        )
        self.assertGreaterEqual(points, 8)
        self.assertTrue(any("buy-intent" in r for r in reasons))
        score._CONFIG_OVERRIDE = None


class StoreSeenDigestTests(unittest.TestCase):
    """Seen-posts and digest-pending persistence."""

    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        os.environ["LEADS_DB"] = self.tmp.name
        import store

        # Reload path binding after env change.
        store.DB_PATH = self.tmp.name
        store.init()
        self.store = store

    def tearDown(self) -> None:
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_mark_seen_and_digest_pending(self) -> None:
        store = self.store
        self.assertFalse(store.is_seen("p1"))
        store.mark_seen("p1")
        self.assertTrue(store.is_seen("p1"))

        store.insert(
            {
                "post_id": "p2",
                "group_url": "https://facebook.com/groups/demo",
                "author": "An",
                "text": "Cần nhập sỉ vitamin C",
                "url": "https://facebook.com/groups/demo/posts/p2",
            },
            ["sỉ"],
            8,
            ["+1 keyword match"],
            "Nháp trả lời",
        )
        self.assertTrue(store.is_seen("p2"))
        pending = store.list_digest_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["post_id"], "p2")
        store.mark_notified(["p2"])
        self.assertEqual(store.list_digest_pending(), [])


class DashboardDraftUiTests(unittest.TestCase):
    """Flask index includes copy-draft control for seeded leads."""

    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        os.environ["LEADS_DB"] = self.tmp.name
        import store

        store.DB_PATH = self.tmp.name
        store.init()
        store.insert(
            {
                "post_id": "dash1",
                "group_url": "https://facebook.com/groups/demo",
                "author": "Minh",
                "text": "Cần tư vấn collagen",
                "url": "https://facebook.com/groups/demo/posts/1",
            },
            ["tư vấn"],
            5,
            ["+1 keyword match"],
            "Chị ơi bên em có collagen peptide...",
        )
        from dashboard.app import app

        self.client = app.test_client()
        token = base64.b64encode(b"admin:change-me").decode()
        self.headers = {"Authorization": f"Basic {token}"}

    def tearDown(self) -> None:
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_copy_draft_button_present(self) -> None:
        html = self.client.get("/", headers=self.headers).get_data(as_text=True)
        self.assertIn("Sao chép nháp", html)
        self.assertIn("draft-body", html)
        self.assertIn("Chị ơi bên em có collagen peptide", html)
        self.assertRegex(html, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC")


class FbIdFilterTests(unittest.TestCase):
    """Numeric GraphQL id filtering."""

    def test_usable_post_id(self) -> None:
        from fb import _usable_post_id, _walk_posts

        self.assertEqual(_usable_post_id("1234567890"), "1234567890")
        self.assertIsNone(_usable_post_id("UzpfSTI6MTIz"))
        out: list = []
        _walk_posts(
            {
                "node": {
                    "id": "999888777",
                    "message": {"text": "Cần mua sỉ"},
                    "author": {"name": "An"},
                }
            },
            out,
        )
        self.assertEqual(out[0]["id"], "999888777")
        out2: list = []
        _walk_posts(
            {
                "node": {
                    "id": "opaqueToken",
                    "message": {"text": "skip me"},
                    "author": {"name": "B"},
                }
            },
            out2,
        )
        self.assertEqual(out2, [])


if __name__ == "__main__":
    unittest.main()
