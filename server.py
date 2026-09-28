#!/usr/bin/env python3
"""
Local server for arXiv Swipe.

Why this exists: arXiv's API (export.arxiv.org) doesn't send CORS headers,
so a browser calling it directly from a web page gets blocked with
"No 'Access-Control-Allow-Origin' header is present". This script serves
the app AND fetches arXiv on the app's behalf from the same origin, so the
browser never makes a cross-origin request in the first place.

Usage:
    python3 server.py
Then open:
    http://localhost:8000/arxiv-swipe.html
"""
import http.server
import urllib.request
import urllib.parse
import urllib.error
import ssl
import os

PORT = 8000
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

# On some Python installs (notably python.org's macOS installer), HTTPS requests
# fail with CERTIFICATE_VERIFY_FAILED because no CA bundle is wired up. Prefer
# certifi's bundle if it's installed; otherwise fall back to the system default.
try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_GET(self):
        if self.path.startswith('/arxiv-proxy'):
            self.proxy_arxiv()
        else:
            super().do_GET()

    def proxy_arxiv(self):
        parsed = urllib.parse.urlparse(self.path)
        query = parsed.query
        upstream_url = f'https://export.arxiv.org/api/query?{query}'
        try:
            req = urllib.request.Request(
                upstream_url,
                headers={'User-Agent': 'arxiv-swipe-local-proxy/1.0'},
            )
            with urllib.request.urlopen(req, timeout=20, context=_SSL_CONTEXT) as resp:
                data = resp.read()
            self.send_response(200)
            self.send_header('Content-Type', 'application/atom+xml; charset=UTF-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            print(f'[proxy error] {type(e).__name__}: {e}')
            message = str(e)
            if 'CERTIFICATE_VERIFY_FAILED' in message:
                message = (
                    f'{message}\n\n'
                    "This is a local Python SSL certificate issue, not an arXiv problem. Fix with:\n"
                    "  pip3 install certifi\n"
                    "then restart server.py. On macOS with the python.org installer, running\n"
                    "'/Applications/Python 3.x/Install Certificates.command' also fixes it."
                )
            body = f'Proxy error reaching arXiv: {message}'.encode()
            self.send_response(502)
            self.send_header('Content-Type', 'text/plain; charset=UTF-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)

    # Quiet the default request logging a little
    def log_message(self, format, *args):
        print(f'[server] {self.address_string()} - {format % args}')


if __name__ == '__main__':
    import sys
    print(f'[diagnostic] python executable: {sys.executable}')
    print(f'[diagnostic] python version: {sys.version.split()[0]}')
    try:
        import certifi as _certifi_check
        print(f'[diagnostic] certifi found at: {_certifi_check.__file__}')
        print(f'[diagnostic] certifi bundle:   {_certifi_check.where()}')
    except ImportError:
        print('[diagnostic] certifi NOT importable in this Python — this is likely the problem.')

    with http.server.ThreadingHTTPServer(('127.0.0.1', PORT), Handler) as httpd:
        print(f'arXiv Swipe running at http://localhost:{PORT}/arxiv-swipe.html')
        print('Press Ctrl+C to stop.')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\nStopped.')