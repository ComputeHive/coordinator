"""
Domain exceptions.

Raised by services and repositories; translated to HTTP responses at the
API boundary (see api/middleware/error_handlers.py).  Nothing below the API
layer should know about Flask or HTTP status codes.
"""


class CeraError(Exception):
    """Base class for all application errors."""


class NotFoundError(CeraError):
    """Requested resource does not exist."""


class ConflictError(CeraError):
    """Resource already exists (e.g. duplicate username or filename)."""


class AuthenticationError(CeraError):
    """Credentials are wrong or token is invalid/expired."""


class AuthorizationError(CeraError):
    """Authenticated principal is not allowed to perform this action."""


class ValidationError(CeraError):
    """Request payload is malformed or missing required fields."""


class PaymentError(CeraError):
    """Contract has not been paid or payment is insufficient."""


class StorageUnavailableError(CeraError):
    """Not enough active storage nodes to fulfill a request."""


class FileUnavailableError(CeraError):
    """File exists but cannot be served right now (temporary)."""


class FileLostError(CeraError):
    """Too many shards are permanently lost; file cannot be recovered."""


class TerminatedError(AuthorizationError):
    """Storage node has been terminated."""


class DatabaseError(CeraError):
    """Unexpected database failure."""


class AuditFailedError(CeraError):
    """Storage node failed a data-integrity audit."""
