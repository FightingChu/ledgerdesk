"""Result filters shared by report exports and application queries."""
from dataclasses import dataclass
from .errors import InputError
from .reconciliation import LABELS, REVIEW_LABELS


@dataclass(frozen=True)
class ResultFilter:
    group: str = "all"
    reason: str = "all"
    status: str = "all"
    q: str = ""

    def __post_init__(self):
        if (self.group not in ("all", "issues", "matched") or self.reason not in ("all", *LABELS)
                or self.status not in ("all", "outstanding", "not_required", *REVIEW_LABELS)
                or not isinstance(self.q, str) or len(self.q) > 128):
            raise InputError("结果筛选条件无效", code="invalid_filter")

    @classmethod
    def from_query(cls, query):
        values = {}
        for key in ("group", "reason", "status", "q"):
            items = query.get(key, ["" if key == "q" else "all"])
            if len(items) != 1:
                raise InputError("筛选参数不能重复", code="invalid_filter")
            values[key] = items[0]
        return cls(**values)

    def matches(self, row):
        matched = row["reasons"] == ["matched"]
        if self.group == "issues" and matched or self.group == "matched" and not matched:
            return False
        if self.reason != "all" and self.reason not in row["reasons"]:
            return False
        if self.status == "not_required" and not matched:
            return False
        if self.status not in ("all", "not_required"):
            if matched:
                return False
            if self.status == "outstanding":
                if row["review_status"] == "resolved":
                    return False
            elif row["review_status"] != self.status:
                return False
        return self.q.strip().lower() in (row["order_id"] + " " + row["channel"]).lower()

    def apply(self, rows):
        return [row for row in rows if self.matches(row)]
