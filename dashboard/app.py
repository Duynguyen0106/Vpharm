"""Vietnamese Flask dashboard with HTTP Basic Auth."""

from __future__ import annotations

import csv
import io
import json
import sys
import time
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable

import yaml
from flask import (
    Flask,
    Response,
    redirect,
    render_template,
    request,
    url_for,
)

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import store  # noqa: E402

app = Flask(__name__)


def _load_config() -> dict[str, Any]:
    """Load config.local.yaml when present, else config.yaml."""
    path = ROOT / "config.local.yaml"
    if not path.exists():
        path = ROOT / "config.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _parse_json_list(value: Any) -> list[Any]:
    """Parse a JSON list column; return [] on empty or invalid data."""
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _format_seen_at(ts: Any) -> str:
    """Format unix seconds as a local-looking YYYY-MM-DD HH:MM string."""
    try:
        value = int(ts)
    except (TypeError, ValueError):
        return "—"
    return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def requires_auth(view: Callable[..., Any]) -> Callable[..., Any]:
    """Require HTTP Basic Auth against dashboard.username/password."""

    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        cfg = _load_config()
        dash = cfg.get("dashboard") or {}
        username = str(dash.get("username") or "")
        password = str(dash.get("password") or "")
        auth = request.authorization
        if (
            auth is None
            or auth.username != username
            or auth.password != password
        ):
            return Response(
                "Yêu cầu xác thực",
                401,
                {"WWW-Authenticate": 'Basic realm="Vpharm Dashboard"'},
            )
        return view(*args, **kwargs)

    return wrapped


@app.get("/")
@requires_auth
def index() -> str:
    """Render the leads dashboard with optional status/min_score filters."""
    cfg = _load_config()
    status = request.args.get("status") or None
    if status == "":
        status = None
    min_score_raw = request.args.get("min_score") or "0"
    try:
        min_score = int(min_score_raw)
    except ValueError:
        min_score = 0

    leads = store.list_leads(status=status, min_score=min_score)
    for lead in leads:
        lead["matched_kw"] = _parse_json_list(lead.get("matched_kw"))
        lead["score_reasons"] = _parse_json_list(lead.get("score_reasons"))
        lead["seen_at_human"] = _format_seen_at(lead.get("seen_at"))

    return render_template(
        "index.html",
        leads=leads,
        stats=store.stats(),
        cfg=cfg,
        current_status=status or "",
        now=int(time.time()),
    )


@app.post("/update/<path:post_id>")
@requires_auth
def update(post_id: str) -> Response:
    """Update lead status/revenue/notes from the dashboard form."""
    status = request.form.get("status") or "new"
    revenue_raw = request.form.get("revenue")
    notes = request.form.get("notes")
    revenue: int | None
    if revenue_raw is None or revenue_raw == "":
        revenue = None
    else:
        try:
            revenue = int(revenue_raw)
        except ValueError:
            revenue = None
    store.update_status(post_id, status, revenue=revenue, notes=notes)
    return redirect(request.referrer or url_for("index"))


@app.get("/api/leads/since/<int:ts>")
@requires_auth
def api_leads_since(ts: int) -> dict[str, Any]:
    """JSON feed of notify-worthy leads newer than ts for browser alerts."""
    cfg = _load_config()
    min_score = int(cfg.get("min_score_to_notify") or 3)
    return {
        "leads": store.leads_since(ts, min_score=min_score),
        "now": int(time.time()),
    }


@app.get("/export.csv")
@requires_auth
def export_csv() -> Response:
    """Download all leads as CSV."""
    leads = store.list_leads(min_score=0, limit=100_000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "post_id",
            "group",
            "author",
            "text",
            "score",
            "status",
            "revenue",
            "url",
            "draft",
        ]
    )
    for lead in leads:
        writer.writerow(
            [
                lead.get("post_id") or "",
                lead.get("group_url") or "",
                lead.get("author") or "",
                lead.get("text") or "",
                lead.get("score") or 0,
                lead.get("status") or "",
                lead.get("revenue") or 0,
                lead.get("url") or "",
                lead.get("draft") or "",
            ]
        )
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=leads.csv",
        },
    )


store.init()

if __name__ == "__main__":
    _cfg = _load_config()
    _dash = _cfg.get("dashboard") or {}
    app.run(
        host=str(_dash.get("host") or "0.0.0.0"),
        port=int(_dash.get("port") or 5000),
        debug=False,
    )
