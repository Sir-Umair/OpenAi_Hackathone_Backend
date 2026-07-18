"""Application exception types independent of HTTP transport."""


class ApplicationError(Exception):
    """Base application exception with a stable machine-readable code."""

    status_code = 400
    code = "application_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(ApplicationError):
    """Requested entity does not exist."""

    status_code = 404
    code = "not_found"


class ConflictError(ApplicationError):
    """Operation conflicts with existing state."""

    status_code = 409
    code = "conflict"
