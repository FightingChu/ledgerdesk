"""Escaped, printable HTML with fixed run and filter metadata."""
from html import escape
import json
from ..domain.report_profiles import COLUMNS
from .cells import cell
from .styles import PRINT_STYLE


def html_chunks(rows, context, columns):
    def text(value):
        return escape(str(value), quote=True)
    yield ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>LedgerDesk 核查报告</title><link rel='icon' href='data:,'><style>" + PRINT_STYLE + "</style><main>"
        "<h1>核查报告：" + text(context["batch"]["name"]) + "</h1><p>核对版本：" + text(context["run"]["id"]) +
        " · 配置：" + text(context["profile"]["name"]) + " / " + str(context["profile"]["revision"]) + "</p>"
        "<p>筛选：" + text(json.dumps(context["filters"], ensure_ascii=False)) + "</p>"
        "<p>金额为本工具核查口径；人工处理不改变金额一致性。通过浏览器打印功能可打印本报告。</p>"
        "<table><thead><tr>" + "".join("<th>" + text(COLUMNS[key]) + "</th>" for key in columns) + "</tr></thead><tbody>").encode()
    buffer = []
    for row in rows:
        buffer.append("<tr>" + "".join("<td>" + text(cell(key, row, context)) + "</td>" for key in columns) + "</tr>")
        if len(buffer) == 100:
            yield "".join(buffer).encode()
            buffer = []
    if buffer:
        yield "".join(buffer).encode()
    yield b"</tbody></table></main></html>"
