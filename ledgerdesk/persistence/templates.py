"""Validated, versioned reusable mappings and portable template bundles."""
import json
from ..domain.errors import InputError
from ..domain.mappings import normalize_aliases, validate_mapping
from ..domain.values import identifier, now, require_text


class TemplateRepository:
    def __init__(self, database):
        self.db = database

    def list(self, side=None):
        if side is not None and side not in ("orders", "payments"):
            raise InputError("模板数据侧无效")
        with self.db.connect() as con:
            query, args = "SELECT * FROM mapping_templates", ()
            if side:
                query += " WHERE side=?"
                args = (side,)
            return [dict(row) for row in con.execute(query + " ORDER BY updated_at DESC,name", args)]

    @staticmethod
    def validated(name, side, mapping, channel_aliases):
        return (require_text(name, "模板名称", 80), side, validate_mapping(side, mapping),
                normalize_aliases(channel_aliases))

    @staticmethod
    def save_in(con, name, side, mapping, aliases):
        timestamp = now()
        con.execute("""INSERT INTO mapping_templates
            (id,name,side,mapping,channel_aliases,created_at,updated_at,revision) VALUES(?,?,?,?,?,?,?,1)
            ON CONFLICT(name,side) DO UPDATE SET mapping=excluded.mapping,
            channel_aliases=excluded.channel_aliases,updated_at=excluded.updated_at,
            revision=mapping_templates.revision+1""", (identifier(), name, side,
            json.dumps(mapping, ensure_ascii=False, sort_keys=True),
            json.dumps(aliases, ensure_ascii=False, sort_keys=True), timestamp, timestamp))
        return dict(con.execute("SELECT * FROM mapping_templates WHERE name=? AND side=?", (name, side)).fetchone())

    def save(self, name, side, mapping, channel_aliases=None):
        data = self.validated(name, side, mapping, channel_aliases)
        with self.db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            return self.save_in(con, *data)

    @staticmethod
    def get_in(con, template_id):
        template_id = require_text(template_id, "模板 ID", 64)
        row = con.execute("SELECT * FROM mapping_templates WHERE id=?", (template_id,)).fetchone()
        if row is None:
            raise InputError("映射模板不存在", code="not_found")
        return dict(row)

    def delete(self, template_id):
        with self.db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self.get_in(con, template_id)
            con.execute("DELETE FROM mapping_templates WHERE id=?", (template_id,))
        return {"deleted": True, "id": template_id}

    def copy(self, template_id, name):
        name = require_text(name, "新模板名称", 80)
        with self.db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            original = self.get_in(con, template_id)
            if con.execute("SELECT 1 FROM mapping_templates WHERE name=? AND side=?", (name, original["side"])).fetchone():
                raise InputError("同名模板已存在，请使用新名称", code="conflict")
            return self.save_in(con, *self.validated(name, original["side"], json.loads(original["mapping"]),
                                                    json.loads(original["channel_aliases"])))

    def export(self):
        templates = [{"name": row["name"], "side": row["side"], "mapping": json.loads(row["mapping"]),
                      "channel_aliases": json.loads(row["channel_aliases"])} for row in self.list()]
        return {"format": "ledgerdesk.mapping-templates", "version": 1, "templates": templates}

    def import_bundle(self, bundle):
        if (not isinstance(bundle, dict) or bundle.get("format") != "ledgerdesk.mapping-templates"
                or type(bundle.get("version")) is not int or bundle["version"] != 1
                or not isinstance(bundle.get("templates"), list) or len(bundle["templates"]) > 100):
            raise InputError("模板文件格式或版本无效，最多 100 个模板", code="invalid_template_bundle")
        validated, keys = [], set()
        for item in bundle["templates"]:
            if not isinstance(item, dict):
                raise InputError("模板文件存在无效条目")
            data = self.validated(item.get("name"), item.get("side"), item.get("mapping"), item.get("channel_aliases"))
            if data[:2] in keys:
                raise InputError("模板文件包含重复名称与数据侧", code="conflict")
            keys.add(data[:2])
            validated.append(data)
        with self.db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            for data in validated:
                if con.execute("SELECT 1 FROM mapping_templates WHERE name=? AND side=?", data[:2]).fetchone():
                    raise InputError("模板已存在；导入不覆盖，请修改文件中的名称", code="conflict")
                self.save_in(con, *data)
        return {"imported": len(validated)}
