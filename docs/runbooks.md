# 📖 Production Incident Runbooks — AI Audit Shelf

**Last Updated:** 2026-05-30  
**Version:** v0.2.0  
**Scope:** Operating & Restoring AI Audit Shelf in Production environments

This document contains standard operational procedures (SOPs) and runbooks for resolving incidents, rotating credentials, and managing data disaster recovery plans.

---

## 🛠️ Runbook 1: Database Corruption & Recovery

### 🔍 Identification
- API responses yield `503 Service Unhealthy` with `"Database is unreachable or corrupted"` detail.
- Uvicorn/App logs print `CRITICAL` traceback with `sqlite3.DatabaseError: database disk image is malformed`.

### 🚨 Remediation Procedure
AI Audit Shelf maintains an online point-in-time backup strategy using the non-blocking SQLite Backup API.

1. **Pause Incoming Write Traffic** (if possible, redirect clients to buffer queues).
2. **Access the Backup Directory**:
   ```bash
   cd /app/backups
   # List existing backups in cron/API storage sorted by date
   ls -la audit_backup_*
   ```
3. **Verify the Integrity of the Selected Backup**:
   ```bash
   sqlite3 audit_backup_20260530_030000.db "PRAGMA integrity_check;"
   # Output should display "ok"
   ```
4. **Hot-Swap Database File**:
   ```bash
   # Stop the server
   systemctl stop ai-audit-shelf.service
   
   # Backup corrupted file for forensic analysis
   mv /app/audit.db /app/audit.db.corrupt
   
   # Copy the selected healthy backup into active place
   cp /app/backups/audit_backup_20260530_030000.db /app/audit.db
   
   # Start the server
   systemctl start ai-audit-shelf.service
   ```
5. **Verify Application Health**:
   ```bash
   curl -i http://localhost:8000/health
   # Expected status code 200 with status: healthy
   ```

---

## 💾 Runbook 2: Full Disk Scenarios

### 🔍 Identification
- API requests fail with `500` or database writes throw `sqlite3.OperationalError: database or disk is full`.
- Host system alerts on partition capacity exceeding `90%`.

### 🚨 Remediation Procedure
1. **Locate Disk Consumables**:
   Identify large log files and aged backups:
   ```bash
   du -sh /app/backups/*
   du -sh /var/log/nginx/*
   ```
2. **Purge Excess/Aged Backups Safely**:
   Retain the 5 most recent backups, compressing or moving earlier ones to object storage (e.g. S3):
   ```bash
   # Clean up backups older than 7 days
   find /app/backups/ -name "audit_backup_*.db" -type f -mtime +7 -delete
   ```
3. **Verify Space Reclamation**:
   ```bash
   df -h
   ```

---

## 🔑 Runbook 3: API Key Rotation

### 🔍 Identification
- Leak of the shared secret `AUDIT_API_KEY` to public channels, unencrypted repositories, or compromised clients.

### 🚨 Remediation Procedure
1. **Generate a Secure Key**:
   ```bash
   openssl rand -hex 32
   # Example output: a2c4d6e8...
   ```
2. **Update the Environment Secret Configuration**:
   - For **Systemd**: Update `Environment="AUDIT_API_KEY=new_secret"` in `/etc/systemd/system/ai-audit-shelf.service`.
   - For **Docker Compose**: Update `.env` containing `AUDIT_API_KEY=new_secret`.
3. **Reload and Restart Services**:
   ```bash
   # Systemd Reload
   systemctl daemon-reload
   systemctl restart ai-audit-shelf.service
   ```
4. **Update Downstream Client Configurations** immediately.

---

## 🔄 Runbook 4: Deployment Rollback

### 🔍 Identification
- Elevated error rates (>1%) or performance degradation (p99 latency > 2s) observed immediately following a fresh deployment.

### 🚨 Remediation Procedure
1. **Locate Prior Release**:
   Identify the previous stable Git commit hash.
2. **Perform Git Rollback**:
   ```bash
   git checkout <previous_stable_commit>
   ```
3. **Restart the Application Server**:
   ```bash
   systemctl restart ai-audit-shelf.service
   ```
4. **Assert Health Check Status**:
   ```bash
   curl -i http://localhost:8000/health
   ```
