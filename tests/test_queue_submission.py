"""Duplicate requests and batch queues are transactional."""
from ledgerdesk.application.jobs import JobService
from ledgerdesk.domain.errors import InputError
from tests.support.workspace import WorkspaceTest


class QueueSubmissionTests(WorkspaceTest):
    def test_request_key_reuses_same_job_and_rejects_other_payload(self):
        service = JobService(self.store)
        a = service.enqueue("reconcile", self.batch, dedupe_key="one")
        b = service.enqueue("reconcile", self.batch, dedupe_key="one")
        self.assertEqual(a["id"], b["id"])
        with self.assertRaises(InputError):
            service.enqueue("backup", dedupe_key="one")

    def test_invalid_last_batch_rolls_back_entire_queue(self):
        service = JobService(self.store)
        with self.assertRaises(InputError):
            service.enqueue_batch([self.batch, "missing"], "queue")
        self.assertEqual(service.list()["total"], 0)
        with self.assertRaises(InputError):
            service.enqueue_batch([self.batch, self.batch], "queue")

    def test_unknown_kinds_paths_and_parameters_are_rejected(self):
        service = JobService(self.store)
        for kind, batch, payload in (("shell", None, {}), ("backup", None, {"path": "x"}), ("reconcile", self.batch, {"unexpected": 1}), ("report", self.batch, {"format": "exe"})):
            with self.subTest(kind=kind), self.assertRaises(InputError):
                service.enqueue(kind, batch, payload)
