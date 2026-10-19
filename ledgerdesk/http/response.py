"""Structured results and streaming responses validated before headers are sent."""
from dataclasses import dataclass, field
from ..reporting.styles import STYLE_HASH


def security_headers():
    return {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer", "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'sha256-" + STYLE_HASH + "'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}


@dataclass
class Response:
    body: object
    status: int = 200
    content_type: str = "application/json; charset=utf-8"
    headers: dict = field(default_factory=dict)
    stream: bool = False

    def send(self, handler):
        if not self.stream:
            return handler.respond(self.status, self.body, self.content_type, self.headers)
        iterator = iter(self.body)
        try:
            first = next(iterator, b"")
            handler.send_response(self.status)
            for key, value in {**security_headers(), "Content-Type": self.content_type, "Connection": "close", **self.headers}.items():
                handler.send_header(key, value)
            handler.end_headers()
            handler.close_connection = True
            try:
                if first:
                    handler.wfile.write(first)
                for chunk in iterator:
                    handler.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                import logging
                logging.getLogger("ledgerdesk.http").exception("Streaming response interrupted")
                handler.close_connection = True
        finally:
            close = getattr(iterator, "close", None)
            if close:
                close()
