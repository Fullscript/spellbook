"""Spellbook: connect to databases, spreadsheets and Drive, and run analyses."""

from spellbook.exceptions import (
    AuthenticationError,
    ConfigError,
    ConnectionFailedError,
    DatabaseNotFoundError,
    QueryError,
    SpellbookError,
)

__all__ = [
    'SpellbookError',
    'ConfigError',
    'DatabaseNotFoundError',
    'AuthenticationError',
    'ConnectionFailedError',
    'QueryError',
]
