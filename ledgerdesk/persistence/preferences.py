"""Optimistic workspace preferences, separate from immutable run rules."""
import json
from ..domain.errors import InputError


class PreferenceRepository:
    @staticmethod
    def get(con, key, default):
        row = con.execute("SELECT payload,revision FROM preferences WHERE key=?", (key,)).fetchone()
        return {"payload": json.loads(row[0]), "revision": row[1]} if row else {"payload": default, "revision": 0}

    @staticmethod
    def save(con, key, payload, expected_revision):
        old = PreferenceRepository.get(con, key, {})
        if type(expected_revision) is not int or expected_revision < 0 or old["revision"] != expected_revision:
            raise InputError("设置已变化，请刷新后保存", code="conflict")
        revision = expected_revision + 1
        con.execute("INSERT INTO preferences VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,revision=excluded.revision",
                    (key, json.dumps(payload, ensure_ascii=False), revision))
        return {"payload": payload, "revision": revision}
