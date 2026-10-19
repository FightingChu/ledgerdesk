"""Local-only HTTP interface. No external service or runtime packages required."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import secrets
import socket
from urllib.parse import parse_qs, urlsplit

from . import __version__
from .imports import InputError, preview
from .domain.filters import ResultFilter
from .application.reports import safe_cell, export_csv
from .application.data_management import DataManagementService
from .persistence.diagnostics import inspect_database
from .store import LABELS, REVIEW_LABELS, Store

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "ledgerdesk" / "static"
MAX_REQUEST = 8 * 1024 * 1024
LOGGER = logging.getLogger("ledgerdesk")


def instance_identity(db_path):
    path = os.path.normcase(str(Path(db_path).resolve()))
    return {"application_id": "ledgerdesk", "instance_protocol": 1,
            "workspace_id": hashlib.sha256(path.encode("utf-8")).hexdigest()}


class LocalHTTPServer(ThreadingHTTPServer):
    def server_bind(self):
        # Windows SO_REUSEADDR permits a second listener on an occupied port.
        if os.name == "nt":
            self.allow_reuse_address = False
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def filtered_results(detail, query):
    return ResultFilter.from_query(query).apply(detail["results"])


def create_demo(store):
    batch_id = store.create_batch("样例 · 十月订单核查", "程序附带的合成数据，用于熟悉操作，不代表真实客户。", is_sample=True)
    for side in ("orders", "payments"):
        raw = (ROOT / "samples" / (side + ".csv")).read_bytes()
        content = base64.b64encode(raw).decode("ascii")
        mapping = preview(side, content)["mapping"]
        store.import_file(batch_id, side, side + ".csv", content, mapping)
    store.reconcile(batch_id)
    return batch_id


def make_server(db_path, port=8765):
    token = secrets.token_urlsafe(32)
    identity = instance_identity(db_path)
    data_manager = DataManagementService(db_path)

    class Handler(BaseHTTPRequestHandler):
        server_version = "LedgerDesk/" + __version__
        sys_version = ""

        def log_message(self, format, *args):
            # Avoid logging customer filenames or bodies.
            LOGGER.info("%s %s", self.command, args[1] if len(args) > 1 else "")

        def respond(self, status, body, content_type="application/json; charset=utf-8", extra=None):
            if isinstance(body, dict) and status >= 400 and "error" in body:
                body.setdefault("code", {403: "forbidden", 404: "not_found", 500: "internal_error"}.get(status, "invalid_input"))
                body.setdefault("errors", [])
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def trusted_host(self):
            port = self.server.server_address[1]
            return self.headers.get("Host", "").lower() in (f"127.0.0.1:{port}", f"localhost:{port}")

        def read_json(self):
            if not secrets.compare_digest(self.headers.get("X-LedgerDesk-Token", ""), token):
                raise PermissionError("页面会话已失效，请刷新页面")
            origin = self.headers.get("Origin")
            allowed = {f"http://127.0.0.1:{self.server.server_address[1]}", f"http://localhost:{self.server.server_address[1]}"}
            if origin is not None and origin not in allowed:
                raise PermissionError("请求来源不被接受")
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise InputError("请求须使用 JSON")
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise InputError("请求长度无效") from None
            if not 0 < size <= MAX_REQUEST or self.headers.get("Transfer-Encoding"):
                raise InputError("请求为空或超过大小限制")
            try:
                payload = json.loads(self.rfile.read(size))
            except (ValueError, UnicodeError):
                raise InputError("JSON 无效") from None
            if not isinstance(payload, dict):
                raise InputError("请求须为 JSON 对象")
            return payload

        @staticmethod
        def single(query, name, default=None):
            values = query.get(name, [default])
            if len(values) != 1:
                raise InputError("查询参数不能重复", code="invalid_input")
            return values[0]

        def paging(self, query):
            values = []
            for name, default in (("page", "1"), ("page_size", "50")):
                value = self.single(query, name, default)
                if not value or not value.isascii() or not value.isdecimal() or len(value) > 9:
                    raise InputError("分页参数必须是正整数", code="invalid_pagination")
                values.append(int(value))
            return values

        def batch_get(self, path):
            parts = path.strip("/").split("/")
            if len(parts)<3:
                self.respond(404,{"error":"接口不存在"})
                return
            batch = parts[2]
            query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
            if len(parts) == 3:
                # Legacy bulk API remains available to existing integrations.
                detail = store.detail(batch)
                detail["history"] = store.history(batch)
                self.respond(200, detail)
            elif len(parts) == 4 and parts[3] == "overview":
                self.respond(200, store.overview(batch))
            elif len(parts) == 4 and parts[3] == "results":
                page, size = self.paging(query)
                self.respond(200, store.result_page(batch, ResultFilter.from_query(query), page, size,
                                                   run_id=self.single(query, "run_id")))
            elif len(parts) == 5 and parts[3] == "cases":
                self.respond(200, store.case_detail(batch, parts[4], run_id=self.single(query, "run_id")))
            elif len(parts) == 5 and parts[3] == "runs":
                self.respond(200, store.run_detail(batch, parts[4]))
            elif len(parts) == 6 and parts[3] == "runs" and parts[5] == "results":
                page, size = self.paging(query)
                self.respond(200, store.result_page(batch, ResultFilter.from_query(query), page, size,
                                                   run_id=parts[4], historical=True))
            elif len(parts) == 7 and parts[3] == "runs" and parts[5] == "cases":
                self.respond(200, store.case_detail(batch, parts[6], run_id=parts[4], historical=True))
            elif len(parts) == 4 and parts[3] == "history":
                self.respond(200, {"history": store.history(batch)})
            elif len(parts) == 4 and parts[3] == "compare":
                self.respond(200, store.compare_runs(batch, self.single(query, "from", ""), self.single(query, "to", "")))
            elif len(parts) == 4 and parts[3] == "compare-page":
                page, size = self.paging(query)
                self.respond(200, store.compare_page(batch, self.single(query, "from", ""), self.single(query, "to", ""), page, size))
            elif len(parts) == 4 and parts[3] == "export":
                detail = store.overview(batch)
                run_id = detail["run"]["id"] if detail["run"] else ""
                if self.single(query, "run_id", run_id) != run_id:
                    raise InputError("显示的核对版本已变化，请刷新后导出", code="stale_result")
                rows = store.export_rows(batch, ResultFilter.from_query(query), run_id)
                self.respond(200, export_csv(detail, rows), "text/csv; charset=utf-8",
                             {"Content-Disposition": 'attachment; filename="ledgerdesk-reconciliation.csv"'})
            else:
                self.respond(404, {"error": "接口不存在"})

        def do_GET(self):
            if not self.trusted_host():
                self.respond(403, {"error": "仅接受本机访问"})
                return
            path = urlsplit(self.path).path
            try:
                if path == "/api/bootstrap":
                    self.respond(200, {**identity, "version": __version__, "token": token,
                        "batches": store.list_batches(), "reason_labels": LABELS, "review_labels": REVIEW_LABELS})
                elif path == "/api/batches":
                    self.respond(200, {"batches": store.list_batches()})
                elif path == "/api/data":
                    self.respond(200, {"backups": data_manager.list_backups(), "backup_directory": str(data_manager.backup_dir),
                                       "restore_directory": str(data_manager.restore_dir)})
                elif path == "/api/data/diagnostics":
                    self.respond(200, inspect_database(db_path))
                elif path == "/api/data/diagnostics/export":
                    report = json.dumps(inspect_database(db_path), ensure_ascii=False, indent=2).encode("utf-8")
                    self.respond(200, report, extra={"Content-Disposition": 'attachment; filename="ledgerdesk-diagnostics.json"'})
                elif path == "/api/templates":
                    self.respond(200, {"templates": store.list_templates()})
                elif path == "/api/templates/export":
                    data = json.dumps(store.export_templates(), ensure_ascii=False, indent=2).encode("utf-8")
                    self.respond(200, data, extra={"Content-Disposition": 'attachment; filename="ledgerdesk-templates.json"'})
                elif path.startswith("/api/batches/"):
                    self.batch_get(path)
                elif path in ("/", "/app.js", "/data.js", "/results.js", "/style.css"):
                    name, mime = {"/": ("index.html", "text/html; charset=utf-8"),
                                  "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                                  "/data.js": ("data.js", "text/javascript; charset=utf-8"),
                                  "/results.js": ("results.js", "text/javascript; charset=utf-8"),
                                  "/style.css": ("style.css", "text/css; charset=utf-8")}[path]
                    self.respond(200, (ASSETS / name).read_bytes(), mime)
                elif path in ("/samples/orders.csv", "/samples/payments.csv"):
                    name = path.rsplit("/", 1)[1]
                    self.respond(200, (ROOT/"samples"/name).read_bytes(), "text/csv; charset=utf-8",
                                 {"Content-Disposition": f'attachment; filename="{name}"'})
                else:
                    self.respond(404, {"error": "页面不存在"})
            except InputError as exc:
                self.respond(400, {"error": str(exc), "errors": exc.errors, "code": exc.code})
            except Exception:
                LOGGER.exception("Read failed")
                self.respond(500, {"error": "读取失败，请检查终端日志"})

        def do_POST(self):
            if not self.trusted_host():
                self.respond(403, {"error": "仅接受本机访问"})
                return
            path = urlsplit(self.path).path
            try:
                payload = self.read_json()
                if path == "/api/batches":
                    result = {"batch_id": store.create_batch(payload.get("name"), payload.get("description", ""))}
                elif path == "/api/preview":
                    result = preview(payload.get("side"), payload.get("content"))
                elif path == "/api/demo":
                    result = {"batch_id": create_demo(store)}
                elif path.startswith("/api/batches/"):
                    parts = path.strip("/").split("/")
                    if len(parts) != 4:
                        self.respond(404, {"error": "接口不存在"})
                        return
                    batch_id, action = parts[2:]
                    if action == "import":
                        result = store.import_file(batch_id, payload.get("side"), payload.get("filename"),
                                                   payload.get("content"), payload.get("mapping"),
                                                   replace_id=payload.get("replace_id"), reason=payload.get("reason", ""),
                                                   channel_aliases=payload.get("channel_aliases"))
                    elif action == "revoke-import":
                        result = store.revoke_import(batch_id, payload.get("import_id"), payload.get("reason"))
                    elif action == "reconcile":
                        result = store.reconcile(batch_id)
                    elif action == "review":
                        store.review(batch_id, payload.get("case_key"), payload.get("evidence_sha256"),
                                     payload.get("status"), payload.get("note", ""))
                        result = {"saved": True}
                    elif action == "update":
                        result = store.update_batch(batch_id, tags=payload.get("tags"), archived=payload.get("archived"))
                    else:
                        self.respond(404, {"error": "接口不存在"})
                        return
                elif path == "/api/templates":
                    result = store.save_template(payload.get("name"), payload.get("side"),
                                                 payload.get("mapping"), payload.get("channel_aliases"))
                elif path == "/api/templates/delete":
                    result = store.delete_template(payload.get("id"))
                elif path == "/api/templates/copy":
                    result = store.copy_template(payload.get("id"), payload.get("name"))
                elif path == "/api/templates/import":
                    result = store.import_templates(payload.get("bundle"))
                elif path == "/api/data/backup":
                    result = data_manager.create_backup()
                elif path == "/api/data/verify":
                    result = data_manager.verify_backup(payload.get("id"))
                elif path == "/api/data/restore":
                    result = data_manager.restore_backup(payload.get("id"), payload.get("workspace_name"))
                else:
                    self.respond(404, {"error": "接口不存在"})
                    return
                self.respond(200, result)
            except InputError as exc:
                self.respond(400, {"error": str(exc), "errors": exc.errors, "code": exc.code})
            except PermissionError as exc:
                self.respond(403, {"error": str(exc)})
            except Exception:
                LOGGER.exception("Write failed")
                self.respond(500, {"error": "操作失败，数据未提交；请检查终端日志"})

    # Reserve the port before opening or migrating the requested workspace.
    server = LocalHTTPServer(("127.0.0.1", port), Handler)
    try:
        store = Store(db_path)
    except Exception:
        server.server_close()
        raise
    server.daemon_threads = True
    return server
