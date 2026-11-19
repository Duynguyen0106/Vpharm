# VPS deploy (option B)

Run the **monitor** (`main.py` + Playwright) and **dashboard** (Flask) 24/7 on one always-on VPS. This is not Cloudflare Workers/Pages.

## 1. Server requirements

- Ubuntu 22.04+ (or similar), 2 GB RAM minimum (4 GB safer for Chromium)
- Docker + Docker Compose plugin
- Outbound HTTPS (Facebook, Anthropic, Gmail SMTP `smtp.gmail.com:465`)

## 2. One-time setup

```bash
git clone <your-repo-url> vpharm && cd vpharm
cp config.yaml config.yaml.bak   # optional
# Edit config.yaml on the server: company, groups, keywords, intent_keywords,
# catalog, ai.api_key, email.*, dashboard.password (change from change-me).
```

Never commit filled secrets. Prefer editing `config.yaml` only on the VPS.

```bash
docker compose build
docker compose up -d
docker compose logs -f monitor
```

Dashboard: `http://<VPS_IP>:5000` (HTTP Basic Auth from `config.yaml`).

## 3. First Facebook login

The monitor uses a persistent Chromium profile under `/data/session` (Docker volume).

On first boot you will see a Vietnamese prompt asking for manual login. Because the browser runs inside **Xvfb** (virtual display):

**Easiest path — seed the session from your laptop**

1. On a desktop: `python main.py`, log into Facebook once, stop after login.
2. Copy the local `./session` folder onto the VPS volume, e.g.:

```bash
docker compose down
# find volume path: docker volume inspect vpharm_vpharm-data
sudo cp -a ./session/. /var/lib/docker/volumes/vpharm_vpharm-data/_data/session/
docker compose up -d
```

**Alternative — VNC into Xvfb** (advanced): attach a VNC server to the monitor container and complete login visually.

## 4. Day-2 operations

```bash
docker compose ps
docker compose logs -f monitor dashboard
docker compose restart monitor
docker compose pull   # after git pull + rebuild
docker compose up -d --build
```

SQLite DB path inside containers: `/data/leads.db` (shared volume).

Smoke-seed without Playwright:

```bash
docker compose exec dashboard python test_e2e.py
```

## 5. Hardening checklist

- [ ] Change `dashboard.password` from `change-me`
- [ ] Firewall: allow only `22` and `5000` (or put Nginx + TLS / Cloudflare Tunnel in front of **port 5000 only**)
- [ ] Keep `ai.api_key` and Gmail app password only on the server
- [ ] Snapshot / back up the `vpharm-data` volume (session cookies + leads.db)

## 6. Optional: Cloudflare Tunnel in front of the dashboard

Tunnel does **not** replace the VPS. It only publishes `localhost:5000` with HTTPS after the stack above is running. Use if you want a public URL without opening port 5000.
