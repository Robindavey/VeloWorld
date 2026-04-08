Local/LAN HTTPS for VeloWorld frontend (Web Bluetooth)

Why
----
Web Bluetooth requires a secure context (HTTPS) in modern browsers. For local development you can either:

- Serve the frontend from `localhost` (many browsers treat `http://localhost` as secure for testing), or
- Use a locally-trusted HTTPS certificate (recommended) via `mkcert`, then serve files over HTTPS.

Quick steps (recommended)
-------------------------
1. Install mkcert (https://mkcert.dev/). Example on Linux (Debian/Ubuntu):

   ```bash
   sudo apt install libnss3-tools
   curl -JLO "https://github.com/FiloSottile/mkcert/releases/latest/download/mkcert-$(uname -s)-$(uname -m)"
   chmod +x mkcert-*
   sudo mv mkcert-* /usr/local/bin/mkcert
   mkcert -install
   ```

2. Generate certs for localhost and your LAN identity:

   ```bash
   ./scripts/generate_lan_certs.sh
   ```

   This creates `frontend/lan.pem` and `frontend/lan-key.pem` including SAN entries for:
   - localhost
   - 127.0.0.1
   - current hostname
   - detected primary LAN IPv4

3. Start the full stack and frontend server:

   ```bash
   ./scripts/manage.sh start
   ```

4. Open from any device on your local network:
   - `https://<your-pi-lan-ip>:8443/demo.html` (when certs exist)
   - `http://<your-pi-lan-ip>:3000/demo.html` (fallback if no certs)

Alternative (quick test without mkcert)
-------------------------------------
You can launch Chrome with an insecure origin flag (UNSAFE) for quick testing, but this is less secure and not recommended for regular use:

```bash
google-chrome --user-data-dir=/tmp/chrome-dev --unsafely-treat-insecure-origin-as-secure="http://localhost:8000"
```

Notes
-----
- Using mkcert ensures the browser trusts the certificate and allows Web Bluetooth.
- This repository includes `serve_https.py` which wraps Python's `http.server` with TLS.
- If you prefer Node tools, `http-server` or `live-server` can also serve with TLS using mkcert-generated certs.
- If another device cannot connect, allow ports 8443 and 3000 on the Pi firewall/router.
