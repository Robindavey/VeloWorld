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
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # reduce console noise
        print("[http] %s - - %s" % (self.client_address[0], format % args))


def serve(certfile: str, keyfile: str, port: int, directory: str = "./"):
    if not os.path.isfile(certfile) or not os.path.isfile(keyfile):
        print("Certificate or key file not found. See README for mkcert instructions.")
        print(f"Missing: {certfile if not os.path.isfile(certfile) else ''} {keyfile if not os.path.isfile(keyfile) else ''}")
        return 2

    handler_class = QuietHandler
    server = ThreadingHTTPServer(("", port), handler_class)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=certfile, keyfile=keyfile)

    server.socket = context.wrap_socket(server.socket, server_side=True)

    print(f"Serving HTTPS on https://localhost:{port}/ (directory: {os.path.abspath(directory)})")
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
    parser.add_argument("--dir", default=".", help="Directory to serve (default: current)")
    args = parser.parse_args()

    os.chdir(args.dir)
    return serve(args.cert, args.key, args.port, directory=args.dir)


if __name__ == "__main__":
    raise SystemExit(main())
