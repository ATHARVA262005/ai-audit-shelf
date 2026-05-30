# 🚀 Production Deployment Guide — AI Audit Shelf

**Last Updated:** 2026-05-30  
**Target Version:** v0.2.0  
**Auditor:** Senior Security Architect (Antigravity)

This document provides a production-grade blueprint for deploying, securing, and maintaining AI Audit Shelf in cloud environments.

---

## 🔒 1. Production Security Architecture

### 1.1 SSL/TLS Termination
AI Audit Shelf must **never** be exposed directly to the public internet using cleartext HTTP. In production, configure an SSL reverse proxy (e.g. Caddy, Nginx) to terminate TLS connections:

#### Nginx Configuration example (`/etc/nginx/sites-available/audit`):
```nginx
server {
    listen 443 ssl http2;
    server_name audit.yourcompany.com;

    ssl_certificate /etc/letsencrypt/live/audit.yourcompany.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/audit.yourcompany.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 1.2 Mandatory Environment Configuration
Configure the following parameters in `/etc/environment` or docker env files:
```bash
# Security & Access Control
AUDIT_API_KEY="a_highly_secure_long_random_hex_key"
AUDIT_READ_API_KEY="an_optional_key_for_exclusive_read_access"
AUDIT_LOCKDOWN_READS="false"  # Set to true to require a key for read access

# CORS Controls
AUDIT_CORS_ORIGINS="https://dashboard.yourcompany.com,https://audit.yourcompany.com"

# Server Modes
AUDIT_DEV_MODE="false"  # STRICTLY FALSE IN PRODUCTION
```

---

## 🐋 2. Docker Container Deployment

Create a secure `Dockerfile` in the root workspace folder:

```dockerfile
FROM python:3.11-slim-buster

WORKDIR /app

# Non-root system user for runtime isolation
RUN groupadd -g 10001 appgroup && \
    useradd -u 10000 -g appgroup -m -s /bin/bash appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Change ownership of data directories to appuser
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

ENV AUDIT_DEV_MODE="false"

CMD ["uvicorn", "api.py:app", "--host", "0.0.0.0", "--port", "8000"]
```

Run inside `docker-compose.yml`:
```yaml
version: '3.8'

services:
  audit-shelf:
    build: .
    ports:
      - "127.0.0.1:8000:8000"
    environment:
      - AUDIT_API_KEY=a_highly_secure_long_random_hex_key
      - AUDIT_DEV_MODE=false
      - AUDIT_CORS_ORIGINS=http://localhost:8000
    volumes:
      - audit-db-data:/app/data
    restart: unless-stopped

volumes:
  audit-db-data:
```

---

## ⚙️ 3. Linux Systemd Service Deployment

Create the file `/etc/systemd/system/ai-audit-shelf.service`:

```ini
[Unit]
Description=AI Audit Shelf Daemon Service
After=network.target

[Service]
User=appuser
WorkingDirectory=/app
Environment="AUDIT_API_KEY=a_highly_secure_long_random_hex_key"
Environment="AUDIT_DEV_MODE=false"
ExecStart=/app/venv/bin/uvicorn api:app --host 127.0.0.1 --port 8000 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and boot the daemon:
```bash
systemctl daemon-reload
systemctl enable ai-audit-shelf.service
systemctl start ai-audit-shelf.service
```

---

## 💾 4. Automated Backup Cron Job

To automate point-in-time non-blocking WAL backups:
```bash
# Edit crontab
crontab -e

# Run daily backup trigger at 3:00 AM UTC
0 3 * * * curl -X POST -H "X-API-KEY: a_highly_secure_long_random_hex_key" http://localhost:8000/db/backup
```
