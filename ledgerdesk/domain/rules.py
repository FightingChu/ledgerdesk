"""Immutable reconciliation policies; tolerance remains a reviewable exception."""
from dataclasses import dataclass, asdict
from .errors import InputError


@dataclass(frozen=True)
class RulePolicy:
    id: str | None = None
    name: str = "默认精确核对"
    revision: int = 0
    tolerance_cents: int = 0

    def __post_init__(self):
        if type(self.tolerance_cents) is not int or not 0 <= self.tolerance_cents <= 1000000:
            raise InputError("容差须为 0～1000000 的整数分", code="invalid_rule")

    def snapshot(self):
        return asdict(self)

    def within_tolerance(self, reasons, difference):
        return reasons == ["amount_mismatch"] and 0 < abs(difference) <= self.tolerance_cents
