# Vpharm — Facebook Group Lead Monitor

Monitor-only tool that watches Facebook groups for potential leads, scores posts, drafts reply suggestions, and notifies via email / browser. No auto-comment, auto-post, or auto-message.

## Stack

| Layer | Choice |
| --- | --- |
| Runtime | Python 3.11+ (async where possible) |
| Browser automation | Playwright `async_api` + `launch_persistent_context` |
| Storage | SQLite |
| Dashboard | Flask (all UI copy in Vietnamese) |
| HTTP / config | httpx, PyYAML |

**Not used:** Selenium, Facebook official Groups API, Telegram / messaging-app notifications.

## Planned modules

| File | Responsibility |
| --- | --- |
| `fb.py` | Playwright session + group post fetch (GraphQL shapes documented where fragile) |
| `store.py` | SQLite persistence |
| `score.py` | Lead scoring |
| `draft.py` | Draft reply suggestions (human sends manually) |
| `notify_email.py` | Email alerts |
| `main.py` | Orchestrator / entrypoint |
| `dashboard/app.py` | Vietnamese Flask dashboard + browser notifications |

## Agent / coding rules

Project constraints for Cursor live in [`.cursor/rules/facebook-group-lead-monitor.mdc`](.cursor/rules/facebook-group-lead-monitor.mdc) and apply to every chat in this repo.

## Status

Core pipeline implemented: `store`, `fb`, `score`, `draft`, `notify_email`, `main`, and Vietnamese Flask dashboard (`dashboard/app.py`).

## Run locally

```bash
pip install -r requirements.txt
playwright install chromium
# Fill config.yaml (groups, keywords, secrets)
python test_e2e.py          # seed sample leads
python dashboard/app.py     # http://localhost:5000
python main.py              # monitor loop (needs Facebook login)
```

## Deploy on a VPS (recommended)

Always-on host with Docker — see [`deploy/DEPLOY.md`](deploy/DEPLOY.md).

```bash
docker compose up -d --build
```

Cloudflare Pages/Workers cannot run Playwright; use a VPS (optionally put a Cloudflare Tunnel only in front of the dashboard).
