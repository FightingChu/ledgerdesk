"""Serialized claims cannot run the same queued job twice."""
from concurrent.futures import ThreadPoolExecutor
from ledgerdesk.application.jobs import JobService
from ledgerdesk.persistence.jobs import JobRepository
from tests.support.workspace import WorkspaceTest


class JobClaimTests(WorkspaceTest):
    def test_concurrent_claims_return_distinct_jobs(self):
        service = JobService(self.store)
        jobs = [service.enqueue("backup", dedupe_key=str(i)) for i in range(6)]
        def claim(_):
            with self.store.connect() as con:
                con.execute("BEGIN IMMEDIATE")
                return JobRepository.claim(con)
        with ThreadPoolExecutor(max_workers=6) as pool:
            claimed = list(pool.map(claim, range(6)))
        self.assertEqual({j["id"] for j in claimed}, {j["id"] for j in jobs})
        self.assertTrue(all(j["state"] == "running" for j in claimed))
        self.assertIsNone(claim(0))
