"""Interface shared by preview, preflight and import consumers."""
from typing import Protocol


class InputAdapter(Protocol):
    id: str
    version: int
    name: str

    def preview(self, side: str, content: str) -> dict: ...
    def validate(self, side: str, content: str, mapping: dict) -> dict: ...
