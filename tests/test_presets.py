"""Filter persistence uses revisions rather than silently overwriting another page."""
from ledgerdesk.application.presets import PresetService
from ledgerdesk.domain.errors import InputError
from tests.support.workspace import WorkspaceTest


class PresetTests(WorkspaceTest):
    def test_round_trip_and_conflicting_update(self):
        service = PresetService(self.store)
        first = service.save("open", {"group": "issues", "status": "outstanding"})
        second = service.save("open", {"group": "issues", "q": "0001"}, 1)
        self.assertEqual(second["revision"], 2)
        with self.assertRaises(InputError):
            service.save("open", {}, 1)
        with self.assertRaises(InputError):
            service.delete(first["id"], 1)
        service.delete(second["id"], 2)
        self.assertEqual(service.list(), [])

    def test_unknown_fields_invalid_values_and_types(self):
        service = PresetService(self.store)
        for value in ({"unknown": 1}, {"group": "bad"}, {"q": "x" * 129}, []):
            with self.subTest(value=value), self.assertRaises(InputError):
                service.save("bad", value)
