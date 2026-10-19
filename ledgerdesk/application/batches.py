"""Batch lifecycle validation and transactional audit."""
from ..domain.errors import InputError
from ..domain.values import identifier, require_text
from ..persistence.batches import BatchRepository


class BatchService:
    def __init__(self, store):
        self.store = store

    def create(self, name, description="", is_sample=False):
        name = require_text(name, "批次名称", 80)
        if not isinstance(description, str) or len(description) > 500:
            raise InputError("批次说明最多 500 字符")
        batch_id = identifier()
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            BatchRepository.create(con, batch_id, name, description.strip(), is_sample)
            self.store.audit(con, batch_id, "create_batch", {"is_sample": bool(is_sample)})
        return batch_id

    def update(self, batch_id, tags=None, archived=None):
        if tags is not None:
            if not isinstance(tags, list) or len(tags) > 20:
                raise InputError("批次最多包含 20 个标签")
            tags = list(dict.fromkeys(require_text(tag, "标签", 30) for tag in tags))
        if archived is not None and type(archived) is not bool:
            raise InputError("归档状态必须是布尔值")
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            original = BatchRepository.get(con, batch_id)
            updated = BatchRepository.update(con, batch_id, original["tags"] if tags is None else tags,
                                             original["archived"] if archived is None else archived)
            self.store.audit(con, batch_id, "update_batch", {"tags": updated["tags"], "archived": bool(updated["archived"])})
        return updated
