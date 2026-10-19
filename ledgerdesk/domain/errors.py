"""User-facing validation failures with stable API codes."""
class InputError(ValueError):
    def __init__(self, message, errors=None, code="invalid_input"):
        super().__init__(message)
        self.errors = errors or []
        self.code = code
