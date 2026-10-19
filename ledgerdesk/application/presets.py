"""Atomic saved filter management."""
from ..persistence.presets import PresetRepository


class PresetService:
    def __init__(self, store):
        self.store = store

    def list(self):
        with self.store.connect() as con:
            return PresetRepository.list(con)

    def save(self, name, payload, expected_revision=0):
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            return PresetRepository.save(con, name, payload, expected_revision)

    def delete(self, key, revision):
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            return PresetRepository.delete(con, key, revision)
