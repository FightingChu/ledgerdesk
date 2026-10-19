"""Named filter revisions with optimistic updates."""
import json
from ..domain.errors import InputError
from ..domain.values import identifier, now, require_text
from ..domain.presets import validate_preset


class PresetRepository:
    @staticmethod
    def list(con):
        result = [dict(row) for row in con.execute("SELECT * FROM saved_filters ORDER BY name")]
        for row in result:
            row["payload"] = json.loads(row["payload"])
        return result

    @staticmethod
    def save(con, name, payload, expected_revision=0):
        name = require_text(name, "筛选名称", 80)
        value = validate_preset(payload)
        if type(expected_revision) is not int or expected_revision < 0:
            raise InputError("筛选版本无效", code="conflict")
        old = con.execute("SELECT * FROM saved_filters WHERE name=?", (name,)).fetchone()
        if (old["revision"] if old else 0) != expected_revision:
            raise InputError("筛选配置已变化，请刷新", code="conflict")
        key, revision = old["id"] if old else identifier(), expected_revision + 1
        con.execute("INSERT INTO saved_filters VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,revision=excluded.revision,updated_at=excluded.updated_at",
                    (key, name, json.dumps(value, ensure_ascii=False), revision, now()))
        return {"id": key, "name": name, "payload": value, "revision": revision}

    @staticmethod
    def delete(con, key, revision):
        if type(revision) is not int or revision < 1:
            raise InputError("筛选版本无效", code="conflict")
        if con.execute("DELETE FROM saved_filters WHERE id=? AND revision=?", (key, revision)).rowcount != 1:
            raise InputError("筛选配置已变化，请刷新", code="conflict")
        return {"deleted": True}
