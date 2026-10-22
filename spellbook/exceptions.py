"""
Exceptions raised by Spellbook.

Every failure path raises one of these rather than returning an empty result, so that a
caller - whether a person in a notebook or an automated agent - can tell the difference
between "the query matched nothing" and "the query never ran".
"""


class SpellbookError(Exception):
    """Base class for every Spellbook error. Catch this to catch anything Spellbook raises."""


class ConfigError(SpellbookError):
    """The configuration file is missing, unreadable, or incomplete."""


class DatabaseNotFoundError(ConfigError):
    """No database in the configuration file matches the requested name."""


class AuthenticationError(SpellbookError):
    """Credentials could not be obtained or were rejected."""


class ConnectionFailedError(SpellbookError):
    """A connection to the database could not be established."""


class QueryError(SpellbookError):
    """The database rejected the query, or the query failed while running."""


__all__ = [
    'SpellbookError',
    'ConfigError',
    'DatabaseNotFoundError',
    'AuthenticationError',
    'ConnectionFailedError',
    'QueryError',
]
