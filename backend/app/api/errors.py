"""An error the API answers with `{"error": {"code", "message"}}`; the message is safe to show."""


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
