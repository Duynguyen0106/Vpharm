"""SQLite persistence for Facebook group leads."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

DB_PATH = "./leads.db"


def _connect() -> sqlite3.Connection:
    """Open a connection to leads.db with dict-like rows."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    """Create the leads table and indexes if they do not exist."""
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS leads (
              post_id TEXT PRIMARY KEY,
              group_url TEXT,
              author TEXT,
              text TEXT,
              url TEXT,
              matched_kw TEXT,
              score INTEGER,
              score_reasons TEXT,
              draft TEXT,
              status TEXT DEFAULT 'new',
              revenue INTEGER DEFAULT 0,
              notes TEXT,
              seen_at INTEGER,
              updated_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
            CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(score DESC);
            """
        )


def is_new(post_id: str) -> bool:
    """Return True if post_id is not already stored."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM leads WHERE post_id = ?",
            (post_id,),
        ).fetchone()
    return row is None


def insert(
    post: dict[str, Any],
    matched: list[str],
    score: int,
    reasons: list[str],
    draft: str,
) -> None:
    """Insert a scored lead; JSON fields use ensure_ascii=False."""
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO leads (
              post_id, group_url, author, text, url,
              matched_kw, score, score_reasons, draft,
              status, revenue, notes, seen_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', 0, NULL, ?, ?)
            """,
            (
                post.get("post_id"),
                post.get("group_url"),
                post.get("author"),
                post.get("text"),
                post.get("url"),
                json.dumps(matched, ensure_ascii=False),
                score,
                json.dumps(reasons, ensure_ascii=False),
                draft,
                now,
                now,
            ),
        )


def update_status(
    post_id: str,
    status: str,
    revenue: int = 0,
    notes: str | None = None,
) -> None:
    """Update status, revenue, and optional notes for a lead."""
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            """
            UPDATE leads
            SET status = ?, revenue = ?, notes = ?, updated_at = ?
            WHERE post_id = ?
            """,
            (status, revenue, notes, now, post_id),
        )


def list_leads(
    status: str | None = None,
    min_score: int = 0,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return leads filtered by optional status and minimum score."""
    clauses = ["score >= ?"]
    params: list[Any] = [min_score]
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    params.append(limit)
    sql = (
        f"SELECT * FROM leads WHERE {' AND '.join(clauses)} "
        "ORDER BY score DESC, seen_at DESC LIMIT ?"
    )
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def leads_since(ts: int, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent high-score lead summaries with seen_at greater than ts."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT post_id, author, score, text, url, seen_at
            FROM leads
            WHERE seen_at > ?
            ORDER BY score DESC, seen_at DESC
            LIMIT ?
            """,
            (ts, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def stats() -> dict[str, list[dict[str, Any]]]:
    """Aggregate lead counts and revenue by status and by group."""
    with _connect() as conn:
        by_status = conn.execute(
            """
            SELECT status AS status,
                   COUNT(*) AS n,
                   COALESCE(SUM(revenue), 0) AS rev
            FROM leads
            GROUP BY status
            ORDER BY n DESC
            """
        ).fetchall()
        # conv = leads with revenue > 0 (closed/won deals) per group.
        by_group = conn.execute(
            """
            SELECT group_url AS group_url,
                   COUNT(*) AS n,
                   SUM(CASE WHEN revenue > 0 THEN 1 ELSE 0 END) AS conv,
                   COALESCE(SUM(revenue), 0) AS rev
            FROM leads
            GROUP BY group_url
            ORDER BY n DESC
            """
        ).fetchall()
    return {
        "by_status": [dict(row) for row in by_status],
        "by_group": [dict(row) for row in by_group],
    }


if __name__ == "__main__":
    init()
    print("ok")
