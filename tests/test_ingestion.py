"""The standard adapter and compatibility parser share one field and currency contract."""
import base64
import unittest
from ledgerdesk.adapters.registry import get_adapter
from ledgerdesk.domain.errors import InputError
from ledgerdesk.imports import decode_file, parse, preview
from ledgerdesk.ingestion.mappings import template_suggestions


def encoded(text, encoding="utf-8"):
    return base64.b64encode(text.encode(encoding)).decode()


class IngestionTests(unittest.TestCase):
    def test_encoding_multiline_and_leading_zero_survive_both_consumers(self):
        for encoding, label in (("utf-8", "utf-8"), ("utf-8-sig", "utf-8-bom"), ("gb18030", "gb18030")):
            data = encoded('order_id,amount,channel,说明\n00001,2.50,微信,"第一行\n第二行"\n', encoding)
            info = preview("orders", data)
            report = get_adapter().validate("orders", data, info["mapping"])
            self.assertEqual(info["encoding"], label)
            self.assertEqual(report["records"][0]["order_id"], "00001")
            self.assertEqual(report["records"][0]["line"], 3)
            self.assertEqual(parse("orders", data, info["mapping"]), (report["file_sha256"], report["records"]))
            self.assertEqual(len(decode_file(data)), 2)

    def test_ambiguous_missing_and_template_candidates_do_not_auto_choose(self):
        info = preview("orders", encoded("order_id,订单号,amount,other\nA,A,1,x\n"))
        self.assertEqual(info["mapping"]["order_id"], "")
        self.assertEqual(info["field_candidates"]["order_id"], ["order_id", "订单号"])
        self.assertEqual(info["missing_fields"], ["channel"])
        templates = [{"id": "a", "name": "合成模板", "side": "orders", "revision": 2,
                      "mapping": '{"order_id":"order_id","amount":"amount","channel":"other"}'},
                     {"id": "b", "name": "缺列", "side": "orders", "revision": 1,
                      "mapping": '{"order_id":"order_id","amount":"amount","channel":"missing"}'}]
        self.assertEqual([r["id"] for r in template_suggestions("orders", info["headers"], templates)], ["a"])
        self.assertEqual(info["mapping"]["channel"], "")

    def test_every_invalid_row_is_available_beyond_the_legacy_thirty_error_limit(self):
        data = encoded("order_id,amount,channel\n" + "\n".join(f"A{i},bad,x" for i in range(101)))
        report = get_adapter().validate("orders", data, preview("orders", data)["mapping"])
        self.assertEqual(len(report["errors"]), 101)
        self.assertEqual(report["errors"][-1]["line"], 102)
        self.assertEqual(report["records"], [])
        with self.assertRaises(InputError) as error:
            parse("orders", data, preview("orders", data)["mapping"])
        self.assertEqual(len(error.exception.errors), 30)

    def test_currency_after_preview_and_conflicting_columns_are_never_ignored(self):
        data = encoded("order_id,amount,channel,Currency,币种\n" + "A,1,x,CNY,RMB\n" * 6 + "B,1,x,CNY,USD\n")
        info = preview("orders", data)
        self.assertFalse(info["currency"]["valid"])
        report = get_adapter().validate("orders", data, info["mapping"])
        self.assertEqual(report["errors"][0]["line"], 8)

    def test_unknown_adapter_and_version_are_rejected_without_fallback(self):
        for identity, version in (("wechat", 1), ("standard_csv", 2), ("standard_csv", True), ([], 1)):
            with self.subTest(identity=identity), self.assertRaises(InputError) as error:
                get_adapter(identity, version)
            self.assertEqual(error.exception.code, "unsupported_adapter")
