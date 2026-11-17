"""Errors meant for the person using PneuText: each carries a plain-language message.

Messages must never quote corpus text; name pages, lines, ids and files instead.
"""

from __future__ import annotations


class PneuTextError(Exception):
    """Base class; the API turns these into JSON error responses."""

    status = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidInput(PneuTextError):
    status = 400


class NotFound(PneuTextError):
    status = 404


class Conflict(PneuTextError):
    status = 409
