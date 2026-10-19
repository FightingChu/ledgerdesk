"""Cancellation checkpoints and durable, bounded progress updates."""
from ..domain.jobs.errors import JobCancelled, JobInterrupted
from ..persistence.jobs import JobRepository
from ..domain.values import now


class JobContext:
    def __init__(self, store, job, stop):
        self.store, self.job, self.stop = store, job, stop

    def checkpoint(self):
        if self.stop.is_set():
            raise JobInterrupted()
        with self.store.connect() as con:
            current = JobRepository.get(con, self.job["id"])
            if current["cancel_requested"]:
                raise JobCancelled()

    def progress(self, done, total, phase):
        self.checkpoint()
        if type(done) is not int or type(total) is not int or not 0 <= done <= total:
            raise ValueError("Invalid progress")
        with self.store.connect() as con:
            con.execute("UPDATE jobs SET progress=?,total=?,phase=?,updated_at=? WHERE id=? AND state='running'",
                        (done, total, phase[:200], now(), self.job["id"]))
