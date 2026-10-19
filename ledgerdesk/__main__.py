import argparse
import logging
import json
import sqlite3
from pathlib import Path
import threading
import webbrowser
from urllib.request import urlopen

from . import __version__
from .imports import InputError
from .server import ROOT, instance_identity, make_server
from .store import Store
from .config import Settings


def main():
    parser = argparse.ArgumentParser(description="LedgerDesk 本地订单与支付账单核对工具")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--open", action="store_true", default=None, help="启动后打开本机浏览器")
    parser.add_argument("--no-open", dest="open", action="store_false", default=None, help="启动时不打开浏览器")
    parser.add_argument("--config", type=Path, help="读取 version=1 的本地 JSON 配置")
    parser.add_argument("--check-config", action="store_true", help="校验最终配置后退出，不打开数据库")
    parser.add_argument("--backup", type=Path, help="备份当前数据库到新文件后退出")
    args = parser.parse_args()
    try:
        settings = Settings.load(args.config, ROOT / "data")
    except InputError as exc:
        parser.error(str(exc))
    args.port = settings.port if args.port is None else args.port
    args.data_dir = settings.data_dir if args.data_dir is None else args.data_dir
    args.open = settings.open_browser if args.open is None else args.open
    if not 0 <= args.port <= 65535:
        parser.error("端口须在 0～65535 之间")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db = args.data_dir.resolve()/"ledgerdesk.sqlite3"
    if args.check_config:
        print(json.dumps({"version": 1, "port": args.port, "data_dir": str(args.data_dir.resolve()),
                          "open_browser": args.open}, ensure_ascii=False))
        return
    if args.backup:
        try:
            summary = Store.backup_existing(db, args.backup)
        except (InputError, OSError, sqlite3.Error) as exc:
            parser.exit(1, str(exc) + "\n")
        print("Backup saved:", args.backup.resolve())
        print("Source:", db, "| Batches:", summary["batches"], "| Rows:", summary["entries"],
              "| Schema:", summary["schema_version"])
        return
    if args.open and args.port:
        # A second double-click opens this app instead of starting another copy.
        try:
            with urlopen(f"http://127.0.0.1:{args.port}/api/bootstrap", timeout=1) as response:
                existing = json.load(response)
            expected = instance_identity(db)
            if (isinstance(existing, dict) and existing.get("application_id") == expected["application_id"]
                    and existing.get("instance_protocol") == expected["instance_protocol"]):
                if existing.get("workspace_id") != expected["workspace_id"]:
                    parser.exit(1, "该端口的 LedgerDesk 使用不同的数据目录；请使用 --port 8766。\n")
                webbrowser.open(f"http://127.0.0.1:{args.port}")
                print("LedgerDesk is already running; opened its page.")
                return
        except (OSError, ValueError):
            pass
    try:
        server = make_server(db, args.port)
    except OSError as exc:
        parser.exit(1, "Cannot start local server: "+str(exc)+". Try --port 8766.\n")
    except InputError as exc:
        parser.exit(1, str(exc) + "\n")
    except sqlite3.Error as exc:
        parser.exit(1, "Cannot open database: " + str(exc) + ". Check the data directory and backup.\n")
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"LedgerDesk {__version__} | Personal validation build", flush=True)
    print("Open:", url, "| Data:", db, flush=True)
    print("Press Ctrl+C to stop. Data remains on this computer.", flush=True)
    if args.open:
        timer = threading.Timer(0.4, webbrowser.open, args=(url,))
        timer.daemon = True
        timer.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
