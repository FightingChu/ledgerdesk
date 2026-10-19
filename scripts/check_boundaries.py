"""Check every nested domain module without executing it."""
import ast
from pathlib import Path

FORBIDDEN = {"sqlite3", "http", "persistence", "application", "server", "requests", "urllib"}


def check(root):
    failures = []
    for path in Path(root).rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                names = (node.module or "").split(".")
            elif isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            else:
                continue
            if set(names) & FORBIDDEN:
                failures.append(path.relative_to(root).as_posix())
    return sorted(set(failures))


if __name__ == "__main__":
    errors = check(Path(__file__).resolve().parent.parent / "ledgerdesk/domain")
    if errors:
        raise SystemExit("Domain dependency violations: " + ", ".join(errors))
    print("Domain dependency boundaries passed")
