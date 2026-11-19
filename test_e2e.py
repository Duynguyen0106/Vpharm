"""Fast smoke seed for dashboard + polling (no Playwright / external APIs)."""

from __future__ import annotations

import time

import store


def main() -> None:
    """Insert three fake Vietnamese leads and print the dashboard URL."""
    store.init()
    now = int(time.time())

    samples = [
        {
            "post": {
                "post_id": f"e2e-high-{now}",
                "group_url": "https://facebook.com/groups/vpharm-demo",
                "author": "Anh Minh",
                "text": "Mình cần nhập sỉ vitamin C và dầu cá cho phòng khám, tư vấn giá buôn giúp với ạ.",
                "url": f"https://facebook.com/groups/vpharm-demo/posts/e2e-high-{now}",
            },
            "matched": ["sỉ", "vitamin"],
            "score": 11,
            "reasons": ["+2 keyword match", "+4 supply-intent (sỉ)", "+2 catalog product"],
            "draft": "Chào anh Minh, bên em có Vitamin C và dầu cá sỉ cho phòng khám...",
            "status": "new",
            "revenue": 0,
        },
        {
            "post": {
                "post_id": f"e2e-mid-{now}",
                "group_url": "https://facebook.com/groups/vpharm-demo",
                "author": "Chị Lan",
                "text": "Ai tư vấn giúp mình nên dùng loại collagen nào cho da khô?",
                "url": f"https://facebook.com/groups/vpharm-demo/posts/e2e-mid-{now}",
            },
            "matched": ["tư vấn"],
            "score": 5,
            "reasons": ["+1 keyword match", "+2 consult-intent (tư vấn)"],
            "draft": "Chị Lan ơi, với da khô mình thường gợi ý collagen peptide kèm vitamin C...",
            "status": "approved",
            "revenue": 0,
            "notes": "Đã trả lời trên group",
        },
        {
            "post": {
                "post_id": f"e2e-low-{now}",
                "group_url": "https://facebook.com/groups/vpharm-other",
                "author": "Shop ABC",
                "text": "Shop bán sỉ thuốc bổ, inbox giá ạ",
                "url": f"https://facebook.com/groups/vpharm-other/posts/e2e-low-{now}",
            },
            "matched": ["sỉ"],
            "score": 3,
            "reasons": ["+1 keyword match", "+4 supply-intent (sỉ)", "-2 competitor ad pattern"],
            "draft": "",
            "status": "lost",
            "revenue": 0,
            "notes": "Đối thủ quảng cáo",
        },
    ]

    for sample in samples:
        post_id = sample["post"]["post_id"]
        if not store.is_new(post_id):
            continue
        store.insert(
            sample["post"],
            sample["matched"],
            sample["score"],
            sample["reasons"],
            sample["draft"],
        )
        store.update_status(
            post_id,
            sample["status"],
            revenue=sample.get("revenue", 0),
            notes=sample.get("notes"),
        )

    print("OK — open dashboard at http://localhost:5000")


if __name__ == "__main__":
    main()
