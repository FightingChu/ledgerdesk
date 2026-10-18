"""Local-only HTTP interface. No external service or runtime packages required."""
import base64
import csv
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import logging
import os
from pathlib import Path
import secrets
import socket
from urllib.parse import parse_qs, urlsplit

from . import __version__
from .imports import InputError, preview
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


def safe_cell(value):
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def filtered_results(detail, query):
    rows = detail["results"]
    reason = query.get("reason", ["all"])[0]
    status = query.get("status", ["all"])[0]
    if reason != "all":
        rows = [row for row in rows if reason in row["reasons"]]
    if status == "not_required":
        rows = [row for row in rows if row["reasons"] == ["matched"]]
    elif status != "all":
        rows = [row for row in rows if row["review_status"] == status]
    return rows


def export_csv(detail, rows=None):
    if not detail["run"]:
        raise InputError("请先执行核对")
    if detail["stale"]:
        raise InputError("数据有更新，请重新核对后再导出")
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(["数据性质", "渠道", "订单号", "预计净到账(元)", "账单净额(元)", "差额(元)",
                     "业务单行数", "账单行数", "核查结果", "处理状态", "处理备注", "核对时间UTC"])
    for row in detail["results"] if rows is None else rows:
        writer.writerow(["合成样例" if detail["batch"]["is_sample"] else "用户导入（来源未核验）",
            safe_cell(row["channel"]), safe_cell(row["order_id"]), row["expected"].replace(",", ""),
            row["actual"].replace(",", ""), row["difference"].replace(",", ""), row["order_count"], row["payment_count"],
            " / ".join(row["reason_labels"]), "无需处理" if row["reasons"] == ["matched"] else REVIEW_LABELS[row["review_status"]],
            safe_cell(row["note"]), detail["run"]["created_at"]])
    return out.getvalue().encode("utf-8-sig")


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

    class Handler(BaseHTTPRequestHandler):
        server_version = "LedgerDesk/" + __version__
        sys_version = ""

        def log_message(self, format, *args):
            # Avoid logging customer filenames or bodies.
            LOGGER.info("%s %s", self.command, args[1] if len(args) > 1 else "")

        def respond(self, status, body, content_type="application/json; charset=utf-8", extra=None):
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
                elif path == "/api/templates":
                    self.respond(200, {"templates": store.list_templates()})
                elif path.startswith("/api/batches/"):
                    parts = path.strip("/").split("/")
                    if len(parts) not in (3, 4) or (len(parts) == 4 and parts[3] not in ("export", "history", "compare")):
                        self.respond(404, {"error": "接口不存在"})
                        return
                    detail = store.detail(parts[2])
                    if len(parts) == 4:
                        query = parse_qs(urlsplit(self.path).query)
                        if parts[3] == "history":
                            self.respond(200, {"history": store.history(parts[2])})
                        elif parts[3] == "compare":
                            self.respond(200, store.compare_runs(parts[2], query.get("from", [""])[0], query.get("to", [""])[0]))
                        else:
                            rows = filtered_results(detail, query)
                            self.respond(200, export_csv(detail, rows), "text/csv; charset=utf-8",
                                         {"Content-Disposition": 'attachment; filename="ledgerdesk-reconciliation.csv"'})
                    else:
                        detail["history"] = store.history(parts[2])
                        self.respond(200, detail)
                elif path in ("/", "/app.js", "/style.css"):
                    name, mime = {"/": ("index.html", "text/html; charset=utf-8"),
                                  "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                                  "/style.css": ("style.css", "text/css; charset=utf-8")}[path]
                    self.respond(200, (ASSETS / name).read_bytes(), mime)
                elif path in ("/samples/orders.csv", "/samples/payments.csv"):
                    name = path.rsplit("/", 1)[1]
                    self.respond(200, (ROOT/"samples"/name).read_bytes(), "text/csv; charset=utf-8",
                                 {"Content-Disposition": f'attachment; filename="{name}"'})
                else:
                    self.respond(404, {"error": "页面不存在"})
            except InputError as exc:
                self.respond(400, {"error": str(exc), "errors": exc.errors})
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
                    else:
                        self.respond(404, {"error": "接口不存在"})
                        return
                elif path == "/api/templates":
                    result = store.save_template(payload.get("name"), payload.get("side"),
                                                 payload.get("mapping"), payload.get("channel_aliases"))
                elif path == "/api/templates/delete":
                    result = store.delete_template(payload.get("id"))
                else:
                    self.respond(404, {"error": "接口不存在"})
                    return
                self.respond(200, result)
            except InputError as exc:
                self.respond(400, {"error": str(exc), "errors": exc.errors})
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
