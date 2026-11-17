"""Pydantic models for API requests and responses."""

from __future__ import annotations

from pydantic import BaseModel


class LibraryOut(BaseModel):
    """What the app shows about the open library."""

    app_version: str
    schema_version: int
    created_at: str
