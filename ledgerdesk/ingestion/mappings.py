"""Field candidates and exact template coverage; suggestions never select a template."""
import json
from ..domain.mappings import FIELDS

ALIASES = {
    "order_id": ("order_id", "订单号", "商户订单号", "业务单号"),
    "transaction_id": ("transaction_id", "交易流水号", "流水号", "渠道流水号"),
    "amount": ("amount", "金额", "金额（元）", "金额(元)", "预计净到账", "预计净到账(元)"),
    "event_type": ("event_type", "类型", "交易类型", "收支类型"),
    "channel": ("channel", "渠道", "支付渠道"),
}


def mapping_diagnostics(side, headers):
    mapping, ambiguous, candidates = {}, {}, {}
    for field in FIELDS[side]:
        aliases = {name.casefold() for name in ALIASES[field]}
        matches = [header for header in headers if header.casefold() in aliases]
        candidates[field] = matches
        mapping[field] = matches[0] if len(matches) == 1 else ""
        if len(matches) > 1:
            ambiguous[field] = matches
    return {"mapping": mapping, "ambiguous_fields": ambiguous, "field_candidates": candidates,
            "missing_fields": [field for field, matches in candidates.items() if not matches]}


def template_suggestions(side, headers, templates):
    result = []
    for template in templates:
        if template["side"] != side:
            continue
        mapping = json.loads(template["mapping"])
        if set(mapping) == set(FIELDS[side]) and set(mapping.values()).issubset(headers):
            result.append({"id": template["id"], "name": template["name"], "revision": template["revision"]})
    return result
