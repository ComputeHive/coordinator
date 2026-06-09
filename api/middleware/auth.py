from __future__ import annotations

import inspect
from functools import wraps


from flask import Flask, jsonify, request, make_response

from core.domain.exceptions import (
    AuditFailedError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DatabaseError,
    CeraError,
    FileUnavailableError,
    FileLostError,
    NotFoundError,
    PaymentError,
    StorageUnavailableError,
    TerminatedError,
    ValidationError,
)
from core.services.auth_service import AuthService


def make_auth_decorator(auth_service: AuthService, verify_fn):
    """
    Factory that returns an `@auth_required` decorator.

    verify_fn(username: str) -> bool  — checks the user/storage node exists
    and is allowed to act.
    """

    def auth_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = request.headers.get("Authorization").split(" ")[1]
            if not token:
                return make_response(
                    jsonify({"error": "Token is missing."}), 401
                )
            try:
                username = auth_service.decode_token(token)
            except AuthenticationError as exc:
                return make_response(jsonify({"error": str(exc)}), 401)

            if not verify_fn(username):
                return make_response(
                    jsonify({"error": "Account not authorised."}), 401
                )

            return f(username=username, *args, **kwargs)

        return decorated

    return auth_required


def make_async_auth_decorator(auth_service: AuthService, verify_fn):

    def async_auth_required(f):
        @wraps(f)
        async def decorated(*args, **kwargs):
            auth_header = request.headers.get("Authorization")

            if not auth_header:
                return make_response(
                    jsonify({"error": "Token is missing."}),
                    401,
                )

            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return make_response(
                    jsonify({"error": "Invalid authorization header."}),
                    401,
                )

            try:
                username = auth_service.decode_token(token)

            except AuthenticationError as exc:
                return make_response(
                    jsonify({"error": str(exc)}),
                    401,
                )

            is_authorized = verify_fn(username)

            if inspect.isawaitable(is_authorized):
                is_authorized = await is_authorized

            if not is_authorized:
                return make_response(
                    jsonify({"error": "Account not authorised."}),
                    401,
                )

            return await f(username=username, *args, **kwargs)

        return decorated

    return async_auth_required


def register_error_handlers(app: Flask) -> None:
    """Translate domain exceptions to JSON HTTP responses."""

    _MAP = {
        ValidationError: 400,
        AuthenticationError: 401,
        AuthorizationError: 403,
        TerminatedError: 401,
        PaymentError: 402,
        NotFoundError: 404,
        ConflictError: 409,
        FileUnavailableError: 424,
        AuditFailedError: 400,
        StorageUnavailableError: 503,
        FileLostError: 500,
        DatabaseError: 500,
        CeraError: 500,
    }

    for exc_class, status_code in _MAP.items():
        # The closure needs a local copy of the variable
        def handler(exc, code=status_code):
            return make_response(jsonify({"error": str(exc)}), code)

        app.register_error_handler(exc_class, handler)
