"""Raised when the records store cannot be used safely."""

from __future__ import annotations


class StorageError(Exception):
    """The records could not be read, backed up or written."""
