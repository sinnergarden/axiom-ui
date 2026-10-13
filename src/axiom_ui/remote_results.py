"""Authenticated, fixed-route HTML projections for the public static UI shell.

This process binds loopback only. HTTPS termination and network exposure are
separate, explicitly approved operator actions. It never serves local files.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from hmac import compare_digest
from html import escape
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import re
from threading import Lock
from urllib.parse import parse_qs, urlsplit

from .result_catalog import LocalResultCatalog
from .result_server import ITEM_ROUTE

RESULT = re.compile(r"/result/([0-9a-f]{64})\Z")
TOKEN = re.compile(r"[A-Za-z0-9_-]{43,128}\Z")
# Textual provenance can contain local paths even outside the artifact table.
LOCAL_PATH = re.compile(r"(?:file://\S+|(?:[A-Za-z]:[\\/]|(?<![\w])/(?:[^\s<>/]+/)|~/)[^\s<>]*)")
TAGS = {'h1', 'h2', 'h3', 'h4', 'p', 'section', 'small', 'code', 'span', 'details',
        'summary', 'ul', 'li', 'table', 'tbody', 'tr', 'th', 'td', 'div', 'a',
        'form', 'button', 'label', 'input', 'svg', 'polyline', 'dl', 'dt', 'dd'}
ATTRS = {'class', 'role', 'scope', 'title', 'aria-label', 'viewbox', 'fill', 'stroke',
         'stroke-width', 'points', 'type', 'name', 'value', 'method'}


class Projection(HTMLParser):
    """Allowlisted inert markup: no scripts, raw JSON, file references or URL loads."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.main = False
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'main':
            self.main = True
            return
        if not self.main:
            return
        if tag in {'pre', 'script', 'style'}:
            self.skip += 1
        if self.skip or tag not in TAGS:
            return
        clean = []
        for key, value in attrs:
            if value is None:
                continue
            if key in {'href', 'action'}:
                path = urlsplit(value)
                if path.scheme or path.netloc or path.fragment or not (
                        path.path in {'/', '/refresh'} or RESULT.fullmatch(path.path) or
                        ITEM_ROUTE.fullmatch(path.path)):
                    continue
            elif key not in ATTRS:
                continue
            value = LOCAL_PATH.sub('[本地路径已隐藏]', value) if key not in {'href', 'action'} else value
            clean.append(f' {key}="{escape(value, quote=True)}"')
        self.output.append('<' + tag + ''.join(clean) + '>')

    def handle_endtag(self, tag):
        if tag == 'main':
            self.main = False
        elif self.skip:
            if tag in {'pre', 'script', 'style'}:
                self.skip -= 1
        elif self.main and tag in TAGS and tag != 'input':
            self.output.append('</' + tag + '>')

    def handle_data(self, data):
        if self.main and not self.skip:
            self.output.append(escape(LOCAL_PATH.sub('[本地路径已隐藏]', data)))


def project(html):
    parser = Projection()
    parser.feed(html)
    return ''.join(parser.output).replace('本机只读', '只读结果').replace(
        '完整原件验证可使用 --detail-mode full 显式执行。', '此入口仅提供保存结果的必要展示。')


def _origin(value):
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in
            {'127.0.0.1', 'localhost'})) or not parsed.netloc or parsed.path or \
            parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError('origin must be an exact HTTPS origin (or local HTTP test origin)')
    return value


class RemoteHTTPServer(ThreadingHTTPServer):
    # Bound idle/preconnect and partial-request socket waits independently of
    # application work. Each accepted connection has its own daemon thread.
    request_timeout = 10

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(self.request_timeout)
        return connection, address


def build_remote_server(*, research_root, engine_root, token, origins,
                        port=0, public_host=None, engine_limits=None):
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise ValueError('use a random URL-safe token with at least 256 bits (43 characters)')
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('invalid loopback port')
    origins = frozenset(_origin(value) for value in origins)
    if not origins:
        raise ValueError('at least one exact allowed origin is required')
    if public_host is not None and not re.fullmatch(r'[a-zA-Z0-9.-]+(?::[0-9]{1,5})?', public_host):
        raise ValueError('public_host must be a hostname with optional port')
    token_hash = sha256(token.encode()).digest()
    catalog = LocalResultCatalog(research_root=research_root, engine_root=engine_root,
                                 engine_limits=engine_limits)
    catalog_lock = Lock()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, body='', cors=True):
            data = body.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'")
            self.send_header('Vary', 'Origin')
            origin = self.headers.get('Origin')
            if cors and origin in origins:
                self.send_header('Access-Control-Allow-Origin', origin)
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Authorization')
            self.end_headers()
            self.wfile.write(data)

        def _host(self):
            return bool(self.headers.get('Host')) and self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', public_host}

        def _authorize(self):
            if not self._host() or self.headers.get('Origin') not in origins | {None}:
                self._send(403, '请求来源不允许。', cors=False)
                return False
            auth = self.headers.get('Authorization', '')
            if len(auth) > 136 or not auth.startswith('Bearer ') or not compare_digest(
                    sha256(auth[7:].encode()).digest(), token_hash):
                self._send(401, '未授权：访问码缺失、错误或已失效。')
                return False
            return True

        def do_OPTIONS(self):
            if (not self._host() or self.headers.get('Origin') not in origins or
                    self.headers.get('Access-Control-Request-Method') not in {'GET', 'POST'} or
                    self.headers.get('Access-Control-Request-Headers', '').lower() != 'authorization'):
                self._send(403, '请求来源不允许。', cors=False)
                return
            self._send(204)

        def do_GET(self):
            if not self._authorize():
                return
            try:
                parsed = urlsplit(self.path)
                if len(self.path) > 512 or parsed.fragment:
                    raise ValueError('invalid request')
                query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True,
                                 max_num_fields=2)
                if any(len(v) != 1 for v in query.values()):
                    raise ValueError('duplicate query')
                # Refresh and render are one transaction: the catalog and its
                # owner reader contain mutable state shared by all requests.
                with catalog_lock:
                    if parsed.path == '/':
                        if set(query) - {'page', 'page_size'}:
                            raise ValueError('unknown query')
                        # Read the formal index for every list request; no copied snapshot.
                        catalog.refresh()
                        html = catalog.index_html(page=int(query.get('page', ['1'])[0]),
                                                  page_size=int(query.get('page_size', ['25'])[0]), remote=True)
                    elif RESULT.fullmatch(parsed.path) and not query:
                        html = catalog.detail_html('sha256:' + RESULT.fullmatch(parsed.path)[1], remote=True)
                    elif (match := ITEM_ROUTE.fullmatch(parsed.path)):
                        result_id = 'sha256:' + match[1]
                        if match[4] is not None and not set(query) - {'start', 'end'}:
                            html = catalog.account_html(result_id, int(match[4]),
                                start=query.get('start', [None])[0] or None,
                                end=query.get('end', [None])[0] or None, remote=True)
                        elif match[4] is None and not query:
                            html = catalog.signal_html(result_id, int(match[2]), int(match[3]), remote=True)
                        else:
                            raise ValueError('unknown query')
                    else:
                        self._send(404, '未找到：此入口只提供登记结果的必要展示。')
                        return
                self._send(200, project(html))
            except (OSError, ImportError, ValueError, KeyError, TypeError, AttributeError):
                self._send(422, '结果暂不可用：保存索引、引用或请求未通过校验。')

        def do_POST(self):
            if not self._authorize():
                return
            if self.path != '/refresh' or self.headers.get('Content-Length', '0') != '0' or self.headers.get('Transfer-Encoding'):
                self._send(400, '只允许无正文的索引刷新。')
                return
            try:
                with catalog_lock:
                    catalog.refresh()
                    html = catalog.index_html(remote=True)
                self._send(200, project(html))
            except (OSError, ImportError, ValueError, KeyError, TypeError, AttributeError):
                self._send(422, '刷新失败：保存索引未通过读取校验。')

        def log_message(self, *_args):
            pass

    return RemoteHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description='Loopback-only authenticated saved-result projection')
    parser.add_argument('--research-root', required=True)
    parser.add_argument('--engine-root', required=True)
    parser.add_argument('--origin', action='append', required=True)
    parser.add_argument('--public-host')
    parser.add_argument('--port', type=int, default=61024)
    args = parser.parse_args()
    token = os.environ.pop('AXIOM_RESULTS_TOKEN', '')
    try:
        with build_remote_server(research_root=args.research_root, engine_root=args.engine_root,
                origins=args.origin, public_host=args.public_host, port=args.port, token=token) as server:
            print(f'Authenticated results on http://127.0.0.1:{server.server_port}', flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, ImportError):
        parser.exit(2, 'Cannot start: check token, roots, owner packages and bind configuration.\n')


if __name__ == '__main__':
    main()
