"""Opt-in startup backups and conservative retention limits."""
from dataclasses import dataclass, asdict
from .errors import InputError


@dataclass(frozen=True)
class BackupPolicy:
    startup: bool = False
    retain_count: int = 10
    max_age_days: int = 0

    def __post_init__(self):
        if (type(self.startup) is not bool or type(self.retain_count) is not int or not 1 <= self.retain_count <= 100
                or type(self.max_age_days) is not int or not 0 <= self.max_age_days <= 3650):
            raise InputError("备份策略须包含启动开关、1～100 份保留数和 0～3650 天期限", code="invalid_policy")

    def payload(self):
        return asdict(self)


def validate_policy(value):
    if not isinstance(value, dict) or set(value) - {"startup", "retain_count", "max_age_days"}:
        raise InputError("备份策略字段无效", code="invalid_policy")
    return BackupPolicy(**value)
