"""Tiny CORS proxy for museum API benchmark. Run: python3 proxy.py"""
import http.server
import urllib.request
import urllib.parse
import json
import os
import ssl
import sys

# Allow museum API HTTPS connections (some have cert chain issues behind corporate proxies)
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

PORT = 9999
PUBLIC_DIR = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=PUBLIC_DIR, **kw)

    def do_GET(self):
        if self.path.startswith('/proxy?'):
            self._proxy()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith('/proxy?'):
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length) if length else None
            self._proxy(body)
        else:
            self.send_error(404)

    def _proxy(self, body=None):
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        url = params.get('url', [''])[0]
        if not url:
            self.send_error(400, 'Missing url param')
            return
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'WorldSeed-Benchmark/1.0')
            if body:
                req.data = body
                req.add_header('Content-Type', 'application/json')
            with urllib.request.urlopen(req, timeout=15, context=_ssl_ctx) as resp:
                data = resp.read()
                self.send_response(200)
                self.send_header('Content-Type', resp.headers.get('Content-Type', 'application/json'))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data)
        except Exception as e:
            self.send_response(502)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, fmt, *args):
        if '/proxy' in str(args[0]):
            sys.stderr.write(f"  proxy: {args[0]}\n")

if __name__ == '__main__':
    print(f"Serving {PUBLIC_DIR} on :{PORT} (with /proxy endpoint)")
    http.server.HTTPServer(('', PORT), Handler).serve_forever()
