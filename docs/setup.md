# VeloWorld Setup Guide

This guide provides individual commands to start each component of the VeloWorld application. Run them in order for a complete setup.

## Prerequisites

- Install Docker and Docker Compose.
- Install mkcert for local HTTPS certificates: `sudo apt install libnss3-tools && curl -JLO "https://github.com/FiloSottile/mkcert/releases/latest/download/mkcert-$(uname -s)-$(uname -m)" && chmod +x mkcert-* && sudo mv mkcert-* /usr/local/bin/mkcert && mkcert -install`.
- Generate certificates: `cd frontend && mkcert -cert-file localhost.pem -key-file localhost-key.pem localhost 127.0.0.1 ::1`.

## 1. Start Docker Compose Stack

This starts PostgreSQL, Redis, MinIO, API backend, and pipeline worker.

```bash
cd /home/robin/Desktop/Programs/VeloWorld
docker-compose -f infra/docker-compose.yml up -d --build
```

Verify services are running:

```bash
docker-compose -f infra/docker-compose.yml ps
```

Expected output: All services (infra_api-backend_1, infra_postgres_1, etc.) should show "Up".

## 2. Start Frontend HTTPS Server

This serves the demo page over HTTPS with API proxying.

```bash
cd /home/robin/Desktop/Programs/VeloWorld/frontend
python3 serve_https.py --cert localhost.pem --key localhost-key.pem --port 8443 --dir .
```

The server will run in the foreground. Open a new terminal to continue.

Verify:

```bash
curl -k https://localhost:8443/demo.html
```

Should return HTML content.

## 3. Verify Full Setup

- API: `curl -k https://localhost:8443/auth/me` (should proxy to backend, return 401 if no token).
- Demo: Open https://localhost:8443/demo.html in a browser.
- Pipeline: Check logs: `docker-compose -f infra/docker-compose.yml logs pipeline-worker`.

## Stopping Components

Stop Docker stack:

```bash
cd /home/robin/Desktop/Programs/VeloWorld
docker-compose -f infra/docker-compose.yml down -v
```

Stop frontend (if running in background):

```bash
pkill -f serve_https.py
```

## Troubleshooting

- If certificates are missing, run the mkcert commands again.
- If ports are in use, check with `ss -ltnp | grep :8443` and kill conflicting processes.
- For mixed-content issues, ensure frontend is served over HTTPS.</content>
<parameter name="filePath">/home/robin/Desktop/Programs/VeloWorld/docs/setup.md