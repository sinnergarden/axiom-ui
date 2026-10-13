"""Short-lived loopback UI for one trusted, read-only Research result index."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import re
from urllib.parse import parse_qs, urlsplit

from .result_catalog import LocalResultCatalog, ResultCatalogError, _page


ITEM_ROUTE = re.compile(r"/result/([0-9a-f]{64})/(?:signal/([0-9]{1,9})/([0-9]{1,9})|account/([0-9]{1,9}))\Z")


RESULT_ROUTE = re.compile(r"/result/([0-9a-f]{64})(/full)?\Z")


def build_result_server(*, research_root, engine_root, engine_limits=None,
                        port: int = 0) -> HTTPServer:
    """Return a server bound only to IPv4 loopback; caller owns its lifetime."""
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("invalid loopback port")
    catalog = LocalResultCatalog(research_root=research_root, engine_root=engine_root,
                                 engine_limits=engine_limits)

    class Handler(BaseHTTPRequestHandler):
        def _allowed_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def _send(self, status, body):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self._allowed_host():
                self._send(403, _page("请求已拒绝", "<p>主机地址不匹配。</p>"))
                return
            parsed = urlsplit(self.path)
            try:
                if parsed.fragment or len(parsed.query) > 256:
                    raise ValueError("invalid query")
                query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True,
                                 max_num_fields=4)
                if any(len(values) != 1 for values in query.values()):
                    raise ValueError("duplicate query")
                if parsed.path in ("/", "/index.html"):
                    if set(query) - {"page", "page_size"}:
                        raise ValueError("unknown pagination parameter")
                    self._send(200, catalog.index_html(
                        page=int(query.get("page", ["1"])[0]),
                        page_size=int(query.get("page_size", ["25"])[0])))
                    return
                item = ITEM_ROUTE.fullmatch(parsed.path)
                if item:
                    result_id = "sha256:" + item.group(1)
                    if item.group(4) is not None:
                        if set(query) - {"start", "end"}:
                            raise ValueError("unknown date parameter")
                        self._send(200, catalog.account_html(result_id, int(item.group(4)),
                            start=query.get("start", [None])[0] or None,
                            end=query.get("end", [None])[0] or None))
                    else:
                        if query:
                            raise ValueError("unexpected signal query")
                        self._send(200, catalog.signal_html(
                            result_id, int(item.group(2)), int(item.group(3))))
                    return
                match = RESULT_ROUTE.fullmatch(parsed.path)
                if match and not query:
                    result_id = "sha256:" + match.group(1)
                    self._send(200, catalog.detail_html(
                        result_id, detail_mode="full" if match.group(2) else "summary"))
                    return
            except (OSError, ImportError, ResultCatalogError, KeyError, TypeError, ValueError):
                self._send(404, _page("结果不可用", "<p>请求参数、登记引用或保存内容无效。曲线区间最多 1000 行，请缩小日期范围。</p>"))
                return
            self._send(404, _page("未找到", "<p>没有此页面。</p>"))

        def do_POST(self):
            origin = self.headers.get("Origin")
            expected = f"http://127.0.0.1:{self.server.server_port}"
            if (not self._allowed_host() or origin not in (None, expected) or
                    self.path != "/refresh" or self.headers.get("Content-Length", "0") != "0"):
                self._send(403, _page("请求已拒绝", "<p>只允许本机页面刷新索引。</p>"))
                return
            try:
                catalog.refresh()
            except (OSError, ImportError, ValueError, KeyError, TypeError):
                self._send(422, _page("刷新失败", "<p>保存索引未通过读取校验，当前列表未变。</p>"))
                return
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def log_message(self, format, *args):
            # Local result IDs, paths and requests are not copied to logs.
            pass

    return HTTPServer(("127.0.0.1", port), Handler)


def serve_result_catalog(*, research_root, engine_root, engine_limits=None,
                         port: int = 0) -> None:
    with build_result_server(research_root=research_root, engine_root=engine_root,
                             engine_limits=engine_limits, port=port) as server:
        print(f"http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
