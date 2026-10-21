"""Bounded CSV decoding and physical source line tracking."""
import base64
import binascii
import csv
import io
from ..domain.errors import InputError

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 10000

def decode_document(content):
    if not isinstance(content, str) or len(content) > MAX_BYTES * 4 // 3 + 16:
        raise InputError("文件超过 5 MiB 上限")
    try:
        raw = base64.b64decode(content, validate=True)
    except (ValueError, binascii.Error):
        raise InputError("文件编码无效，请重新选择 CSV") from None
    if not raw or len(raw) > MAX_BYTES:
        raise InputError("文件为空或超过 5 MiB 上限")
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise InputError("文件须为 UTF-8 或 GB18030 编码")
    if "\x00" in text:
        raise InputError("文件包含二进制内容，请导出标准 CSV")
    return raw, text, "utf-8-bom" if raw.startswith(b"\xef\xbb\xbf") else "utf-8" if encoding == "utf-8-sig" else encoding


def read_csv(text):
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader, None)
        if header is None:
            raise InputError("CSV 缺少表头")
        headers = [value.strip() for value in header]
        if not all(headers) or len(headers) != len(set(headers)) or len(headers) > 80:
            raise InputError("表头不能空白或重名，最多 80 列")
        rows = []
        for row in reader:
            line = reader.line_num
            if not row or not any(value.strip() for value in row):
                continue
            if len(row) != len(headers):
                raise InputError(f"第 {line} 行列数与表头不一致")
            if any(len(value) > 2048 for value in row):
                raise InputError(f"第 {line} 行存在超过 2048 字符的字段")
            rows.append((line, dict(zip(headers, row))))
            if len(rows) > MAX_ROWS:
                raise InputError("单文件最多 10000 行")
    except csv.Error as exc:
        raise InputError("CSV 格式错误：" + str(exc)) from None
    if not rows:
        raise InputError("CSV 只有表头，没有数据")
    return headers, rows
