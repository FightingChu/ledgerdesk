"""Application services available to HTTP routing without global mutable state."""
from dataclasses import dataclass


@dataclass
class HttpContext:
    store: object
    data_manager: object
    import_validation: object
