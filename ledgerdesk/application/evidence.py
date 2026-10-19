"""Bind paginated source evidence to a batch and immutable run."""
from ..persistence.evidence import EvidenceRepository
from ..persistence.result_queries import ResultQueryRepository
from ..domain.errors import InputError


class EvidenceService:
    def __init__(self, store):
        self.store = store

    def read(self, batch_id, case_key, run_id=None, historical=False, kind=None, page=1, page_size=25):
        with self.store.connect() as con:
            con.execute("BEGIN")
            run = ResultQueryRepository.resolve(con, batch_id, run_id, historical)
            if run is None:
                raise InputError("请先执行核对", code="not_found")
            item = EvidenceRepository.info(con, batch_id, run, case_key, historical)
            base = {"run_id": run["id"], "stale": not historical and run["input_sha256"] != self.store.source_fingerprint(con, batch_id),
                    "read_only": historical or bool(self.store.batch(con, batch_id)["archived"])}
            return {**base, "item": item} if kind is None else {**base,
                **EvidenceRepository.page(con, run["id"], case_key, kind, page, page_size)}
