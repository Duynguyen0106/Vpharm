# Playwright Python image includes Chromium + system deps for VPS deploy.
FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

WORKDIR /app

# Xvfb so headed Chromium works on a server without a physical display.
RUN apt-get update \
    && apt-get install -y --no-install-recommends xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium

COPY . .

ENV PYTHONUNBUFFERED=1 \
    LEADS_DB=/data/leads.db \
    FB_SESSION_DIR=/data/session \
    FB_HEADLESS=0

RUN mkdir -p /data/session \
    && chmod +x /app/deploy/entrypoint-monitor.sh /app/deploy/entrypoint-dashboard.sh

VOLUME ["/data"]
