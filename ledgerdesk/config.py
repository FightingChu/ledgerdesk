"""Versioned local JSON configuration with strict, reversible defaults."""
from dataclasses import dataclass
import json
from pathlib import Path
from .domain.errors import InputError


@dataclass(frozen=True)
class Settings:
    port: int
    data_dir: Path
    open_browser: bool = False

    @classmethod
    def load(cls, config_path, default_data_dir):
        if config_path is None:
            return cls(8765, Path(default_data_dir).resolve())
        path = Path(config_path).resolve()
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, UnicodeError) as exc:
            raise InputError("无法读取 JSON 配置：" + str(exc), code="invalid_config") from None
        if not isinstance(value, dict) or set(value) - {"version", "port", "data_dir", "open_browser"}:
            raise InputError("配置须为对象，且不能包含未知字段", code="invalid_config")
        if type(value.get("version")) is not int or value["version"] != 1:
            raise InputError("仅支持 version=1 的配置文件", code="invalid_config")
        port, directory, open_browser = value.get("port", 8765), value.get("data_dir"), value.get("open_browser", False)
        if type(port) is not int or not 0 <= port <= 65535 or type(open_browser) is not bool:
            raise InputError("配置端口须为 0～65535 整数，open_browser 须为布尔值", code="invalid_config")
        if directory is None:
            data_dir = Path(default_data_dir)
        elif not isinstance(directory, str) or not directory.strip():
            raise InputError("配置 data_dir 必须是非空路径", code="invalid_config")
        else:
            data_dir = Path(directory)
            if not data_dir.is_absolute():
                data_dir = path.parent / data_dir
        return cls(port, data_dir.resolve(), open_browser)
