"""SQLite persistence for Facebook group leads."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any

DB_PATH = os.environ.get("LEADS_DB", "./leads.db")


def _connect() -> sqlite3.Connection:
    """Open a connection to leads.db with dict-like rows."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    """Add a column when missing (SQLite has no IF NOT EXISTS for ADD COLUMN)."""
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init() -> None:
    """Create leads/seen_posts tables and indexes if they do not exist."""
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
              updated_at INTEGER,
              notified INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
            CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(score DESC);
            CREATE INDEX IF NOT EXISTS idx_leads_notified ON leads(notified);

            CREATE TABLE IF NOT EXISTS seen_posts (
              post_id TEXT PRIMARY KEY,
              seen_at INTEGER
            );
            """
        )
        _ensure_column(conn, "leads", "notified", "INTEGER DEFAULT 0")


def is_seen(post_id: str) -> bool:
    """Return True if post_id was already scanned (lead or non-lead)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM seen_posts WHERE post_id = ?",
            (post_id,),
        ).fetchone()
    return row is not None


def mark_seen(post_id: str) -> None:
    """Record that a post_id was observed in a group scan."""
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO seen_posts (post_id, seen_at) VALUES (?, ?)
            ON CONFLICT(post_id) DO UPDATE SET seen_at = excluded.seen_at
            """,
            (post_id, now),
        )


def is_new(post_id: str) -> bool:
    """Return True if post_id is not already stored as a lead."""
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
    post_id = post.get("post_id") or post.get("id")
    group_url = post.get("group_url") or post.get("group")
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO leads (
              post_id, group_url, author, text, url,
              matched_kw, score, score_reasons, draft,
              status, revenue, notes, seen_at, updated_at, notified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', 0, NULL, ?, ?, 0)
            """,
            (
                post_id,
                group_url,
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
        if post_id:
            conn.execute(
                """
                INSERT INTO seen_posts (post_id, seen_at) VALUES (?, ?)
                ON CONFLICT(post_id) DO UPDATE SET seen_at = excluded.seen_at
                """,
                (str(post_id), now),
            )


def update_status(
    post_id: str,
    status: str,
    revenue: int | None = None,
    notes: str | None = None,
) -> None:
    """Update status; only touch revenue/notes when explicitly provided."""
    now = int(time.time())
    sets = ["status = ?", "updated_at = ?"]
    params: list[Any] = [status, now]
    if revenue is not None:
        sets.append("revenue = ?")
        params.append(revenue)
    if notes is not None:
        sets.append("notes = ?")
        params.append(notes)
    params.append(post_id)
    with _connect() as conn:
        conn.execute(
            f"UPDATE leads SET {', '.join(sets)} WHERE post_id = ?",
            params,
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


def leads_since(
    ts: int,
    limit: int = 20,
    min_score: int = 0,
) -> list[dict[str, Any]]:
    """Return recent lead summaries with seen_at > ts and score >= min_score."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT post_id, author, score, text, url, seen_at
            FROM leads
            WHERE seen_at > ? AND score >= ?
            ORDER BY score DESC, seen_at DESC
            LIMIT ?
            """,
            (ts, min_score, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def list_digest_pending(limit: int = 50) -> list[dict[str, Any]]:
    """Return notify-worthy leads not yet included in a successful digest."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT post_id, author, score, text, draft, url, seen_at
            FROM leads
            WHERE notified = 0
            ORDER BY score DESC, seen_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_notified(post_ids: list[str]) -> None:
    """Mark leads as included in a sent digest."""
    if not post_ids:
        return
    now = int(time.time())
    with _connect() as conn:
        conn.executemany(
            """
            UPDATE leads
            SET notified = 1, updated_at = ?
            WHERE post_id = ?
            """,
            [(now, pid) for pid in post_ids],
        )


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
