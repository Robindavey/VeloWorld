#!/usr/bin/env python3
"""Serve the `frontend/` directory over HTTPS using a cert/key pair.

Usage examples:
  # generate locally-trusted certs with mkcert (recommended)
  mkcert -install
  mkcert -cert-file localhost.pem -key-file localhost-key.pem localhost 127.0.0.1 ::1

  # then run the server
  python3 serve_https.py --cert localhost.pem --key localhost-key.pem --port 8443

Notes:
- Browsers require a trusted certificate (mkcert) for Web Bluetooth.
- If you don't have mkcert, you can use Chrome's insecure-origin flag for testing.
"""

import argparse
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler


class QuietHandler(SimpleHTTPRequestHandler):
    backend_base = "http://127.0.0.1:8080"

    def log_message(self, format, *args):
        # reduce console noise
        print("[http] %s - - %s" % (self.client_address[0], format % args))

    def _proxy_api_request(self):
        # Proxy /api/* to backend service so browser calls can stay same-origin HTTPS.
        target_path = self.path
        if target_path.startswith("/api"):
            target_path = target_path[4:] or "/"
        target_url = urllib.parse.urljoin(self.backend_base.rstrip("/") + "/", target_path.lstrip("/"))

        content_length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(content_length) if content_length > 0 else None

        req = urllib.request.Request(target_url, data=body, method=self.command)
        for key, value in self.headers.items():
            lower_key = key.lower()
            if lower_key in {"host", "content-length", "connection", "accept-encoding"}:
                continue
            req.add_header(key, value)

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = resp.read()
                self.send_response(resp.status)
                for key, value in resp.getheaders():
                    lower_key = key.lower()
                    if lower_key in {"transfer-encoding", "content-encoding", "connection"}:
                        continue
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(payload)
        except urllib.error.HTTPError as err:
            payload = err.read() if hasattr(err, "read") else b""
            self.send_response(err.code)
            self.send_header("Content-Type", err.headers.get("Content-Type", "text/plain"))
            self.end_headers()
            if payload:
                self.wfile.write(payload)
        except Exception as exc:
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"API proxy error: {exc}".encode("utf-8"))

    def _maybe_proxy(self):
        if self.path.startswith("/api/") or self.path == "/api":
            self._proxy_api_request()
            return True
        return False

    def do_GET(self):
        if self._maybe_proxy():
            return
        super().do_GET()

    def do_POST(self):
        if self._maybe_proxy():
            return
        super().do_POST()

    def do_PUT(self):
        if self._maybe_proxy():
            return
        self.send_error(405, "Method Not Allowed")

    def do_DELETE(self):
        if self._maybe_proxy():
            return
        self.send_error(405, "Method Not Allowed")

    def do_OPTIONS(self):
        if self._maybe_proxy():
            return
        self.send_response(204)
        self.send_header("Allow", "GET, HEAD, OPTIONS")
        self.end_headers()


def serve(certfile: str, keyfile: str, port: int, directory: str = "./", host: str = "0.0.0.0", backend: str = "http://127.0.0.1:8080"):
    if not os.path.isfile(certfile) or not os.path.isfile(keyfile):
        print("Certificate or key file not found. See README for mkcert instructions.")
        print(f"Missing: {certfile if not os.path.isfile(certfile) else ''} {keyfile if not os.path.isfile(keyfile) else ''}")
        return 2

    handler_class = QuietHandler
    handler_class.backend_base = backend
    server = ThreadingHTTPServer((host, port), handler_class)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=certfile, keyfile=keyfile)

    server.socket = context.wrap_socket(server.socket, server_side=True)

    display_host = host
    if host == "0.0.0.0":
        display_host = "<this-machine-ip>"
    print(f"Serving HTTPS on https://{display_host}:{port}/ (directory: {os.path.abspath(directory)})")
    print(f"Proxying /api/* to {backend}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down")
        server.server_close()
    return 0


def main():
    parser = argparse.ArgumentParser(description="Serve frontend/ over HTTPS using cert+key")
    parser.add_argument("--cert", default="localhost.pem", help="Path to cert file (PEM)")
    parser.add_argument("--key", default="localhost-key.pem", help="Path to key file (PEM)")
    parser.add_argument("--port", type=int, default=8443, help="Port to serve on (default 8443)")
    parser.add_argument("--host", default="0.0.0.0", help="Host/IP to bind (default: 0.0.0.0)")
    parser.add_argument("--dir", default=".", help="Directory to serve (default: current)")
    parser.add_argument("--backend", default="http://127.0.0.1:8080", help="Backend API base URL for /api proxy")
    args = parser.parse_args()

    os.chdir(args.dir)
    return serve(args.cert, args.key, args.port, directory=args.dir, host=args.host, backend=args.backend)


if __name__ == "__main__":
    raise SystemExit(main())
