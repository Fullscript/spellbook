import base64
import logging
import os
import re
import subprocess
from typing import Any
from urllib.parse import parse_qs, quote_plus

import pandas as pd
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from snowflake.snowpark import Session
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from spellbook.exceptions import (
    AuthenticationError,
    ConfigError,
    ConnectionFailedError,
    DatabaseNotFoundError,
    QueryError,
)
from spellbook.utils import (
    CONFIG_FILENAME,
    describe_unresolved,
    load_and_parse_config,
    load_sql_file,
    show_wizard,
)

logger = logging.getLogger(__name__)


# Needs a very specific pip install
# pip install "snowflake-connector-python[pandas]"

# How long to wait for `rx` to mint an RDS IAM token. The first call of the day can
# be slow because `rx` has to walk through AWS SSO before it reaches RDS.
RDS_TOKEN_TIMEOUT = 120

# `rx` colourises its progress output, which has to come off before we can read the token.
_ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

# Built on first use so that pymysql is only imported when an IAM connection is made.
_IAM_CURSOR_CLASS = None

SUPPORTED_DB_TYPES = ('snowflake', 'mysql')

# Settings a connection genuinely cannot be made without, checked only for the database
# being used. Anything absent from here is optional and may resolve to an empty value:
# `private_key_passphrase`, `schema`, `port`, `ssl_ca` and `rds_db_name` all have defaults
# or meaningful empty behaviour. See required_fields() for the per-database adjustments.
REQUIRED_FIELDS = {
    'mysql': ('host', 'user', 'database'),
    'snowflake': ('account', 'user', 'role', 'warehouse', 'database'),
}


def required_fields(db_config: dict[str, Any]) -> tuple[str, ...]:
    """
    Work out which settings this particular database cannot do without.

    MySQL needs a `password` unless it authenticates with an IAM token, and conversely an
    IAM database does not need a `user`, because the token says who it was issued to.

    :param db_config: The configuration block for the database.
    :return: The names of the settings that must be present and non-empty.
    """
    fields = REQUIRED_FIELDS.get(db_config.get('type'), ())

    if db_config.get('type') == 'mysql':
        if db_config.get('iam_auth'):
            return tuple(field for field in fields if field != 'user')
        return fields + ('password',)

    return fields


def db_user_from_token(token: str) -> str | None:
    """
    Read the database user out of an AWS RDS IAM token.

    The token is a presigned URL and carries the user it was issued for as its `DBUser`
    parameter, so the user does not have to be repeated in the configuration file.

    :param token: The token returned by `rx rds password`.
    :return: The database user, or None if the token does not name one.
    """
    _, _, query = (token or '').partition('?')
    users = parse_qs(query).get('DBUser') or []
    return users[0] or None if users else None


def _strip_ansi(text_value: str | None) -> str:
    """
    Remove ANSI colour and cursor codes from CLI output.

    :param text_value: The raw text written by the CLI.
    :return: The same text with escape codes removed.
    """
    return _ANSI_ESCAPE.sub('', text_value or '')


def _validate_db_config(db_name: str, db_config: dict[str, Any]) -> dict[str, Any]:
    """
    Check that the settings this database cannot work without are actually filled in.

    Only the database being used is checked. Settings that are legitimately optional, such as
    a Snowflake private key passphrase or an `ssl_ca` bundle, are allowed to stay empty.

    :param db_name: The name of the database, for the error message.
    :param db_config: The configuration block for that database.
    :return: The same configuration block.
    :raises ConfigError: If a required setting is missing or resolved to an empty value.
    """
    unresolved = db_config.pop('_unresolved_env', {})

    for key in required_fields(db_config):
        if db_config.get(key):
            continue
        if key in unresolved:
            raise ConfigError(describe_unresolved(db_name, key, unresolved[key]))
        raise ConfigError(
            f"Database '{db_name}' is missing the required '{key}' setting. "
            f"Add it to {CONFIG_FILENAME}."
        )

    return db_config


def get_db_config(db_name: str) -> dict[str, Any]:
    """
    Look up a single database block from the configuration file.

    :param db_name: The name of the database as defined in the config file.
    :return: The configuration for that database.
    :raises ConfigError: If the config cannot be read, or this database is incomplete.
    :raises DatabaseNotFoundError: If no database matches the given name.
    """
    config = load_and_parse_config(configurations='databases')

    databases = config.get('databases') or []
    for db in databases:
        if db.get('name') == db_name:
            return _validate_db_config(db_name, db)

    available = ', '.join(sorted(str(db.get('name')) for db in databases)) or '<none>'
    raise DatabaseNotFoundError(
        f"Database configuration for '{db_name}' not found. Available databases: {available}."
    )


def snowflake_connect(db_name: str) -> Session:
    """
    Create a Snowflake session using credentials from the config file or environment.

    :param db_name: The name of the database as defined in the config file.
    :return: Snowpark session object.
    :raises AuthenticationError: If the private key cannot be loaded.
    :raises ConnectionFailedError: If the session cannot be created.
    """
    db_config = get_db_config(db_name)

    use_private_key = db_config.get('private_key') or os.getenv('SNOW_PK')

    settings = {
        'account': db_config['account'],
        'user': db_config['user'],
        'role': db_config['role'],
        'warehouse': db_config['warehouse'],
        'database': db_config['database'],
        'schema': db_config.get('schema', 'public'),
    }

    if use_private_key:
        passphrase = db_config.get('private_key_passphrase')
        try:
            p_key = serialization.load_pem_private_key(
                base64.b64decode(db_config.get('private_key')),
                password=passphrase.encode('ascii') if passphrase else None,
                backend=default_backend(),
            )
            settings['private_key'] = p_key.private_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        except Exception as e:
            raise AuthenticationError(
                f"Could not load the private key for Snowflake database '{db_name}': {e}"
            ) from e
    else:
        settings['password'] = db_config.get('password')

    try:
        return Session.builder.configs(settings).create()
    except Exception as e:
        method = 'private key' if use_private_key else 'password'
        raise ConnectionFailedError(
            f"Could not create a Snowflake session for '{db_name}' using {method} "
            f"authentication: {e}"
        ) from e


def _iam_cursor_class():
    """
    Build the pymysql cursor used for IAM connections.

    pymysql substitutes parameters whenever `args is not None`, so the empty parameter set
    pandas passes turns a `like '%value%'` clause into a format string and raises
    "unsupported format character". mysql-connector guards on `if params:` instead, which
    leaves such queries alone, so this keeps both drivers behaving the same way.

    :return: A pymysql cursor class that treats an empty parameter set as no parameters.
    """
    global _IAM_CURSOR_CLASS
    if _IAM_CURSOR_CLASS is None:
        import pymysql.cursors

        class LiteralPercentCursor(pymysql.cursors.Cursor):
            def execute(self, query, args=None):
                return super().execute(query, args if args else None)

        _IAM_CURSOR_CLASS = LiteralPercentCursor
    return _IAM_CURSOR_CLASS


def get_rds_iam_token(rds_db_name: str, timeout: int = RDS_TOKEN_TIMEOUT) -> str:
    """
    Generate a temporary AWS RDS IAM authentication token using the `rx` CLI.

    The token stands in for a stored password and expires after about 15 minutes, so it
    has to be fetched fresh for every connection rather than cached in the config file.

    :param rds_db_name: The remote database name, as listed by `rx rds list`.
    :param timeout: Seconds to wait for `rx` before giving up.
    :return: The token to use as the connection password.
    :raises AuthenticationError: If `rx` is unavailable, times out, fails, or returns nothing.
    """
    command = ['rx', 'rds', 'password', rds_db_name]
    printable = ' '.join(command)

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise AuthenticationError(
            "AWS RDS IAM authentication failed: the 'rx' command is not installed or not on "
            "your PATH. Install the Fullscript developer tooling, or drop 'iam_auth' from the "
            "database configuration to go back to password authentication."
        ) from None
    except subprocess.TimeoutExpired:
        raise AuthenticationError(
            f"AWS RDS IAM authentication failed: '{printable}' did not finish within {timeout} "
            f"seconds. It is probably waiting on AWS SSO - run '{printable}' in a terminal once "
            "to sign in, then try again."
        ) from None

    if result.returncode != 0:
        detail = _strip_ansi(result.stderr or result.stdout or '').strip()
        raise AuthenticationError(
            f"AWS RDS IAM authentication failed: '{printable}' exited with status "
            f"{result.returncode}. Check that '{rds_db_name}' appears in 'rx rds list' and that "
            f"you are signed in to AWS. Output from rx: {detail or '<none>'}"
        )

    # `rx` writes progress lines before the token, so the token is the last thing it prints.
    lines = [line.strip() for line in _strip_ansi(result.stdout).splitlines() if line.strip()]
    if not lines:
        raise AuthenticationError(
            f"AWS RDS IAM authentication failed: '{printable}' succeeded but returned no token."
        )

    return lines[-1]


def mysql_connect(db_name: str) -> Connection:
    """
    Create a MySQL connection using either AWS RDS IAM authentication or a stored password.

    Set `iam_auth: true` on the database in the config file to authenticate with a temporary
    IAM token from `rx rds password`. Without it, the `password` field is used as before.

    :param db_name: The name of the database as defined in the config file.
    :return: SQLAlchemy connection object. Close it when you are done with it.
    :raises AuthenticationError: If an IAM token could not be obtained.
    :raises ConnectionFailedError: If the connection could not be established.
    """
    db_config = get_db_config(db_name)
    iam_auth = bool(db_config.get('iam_auth'))

    try:
        host = db_config['host']
        port = db_config.get('port', 3306)
        database = db_config['database']
    except KeyError as e:
        raise ConfigError(
            f"MySQL database '{db_name}' is missing the required '{e.args[0]}' field."
        ) from None

    if iam_auth:
        # RDS instance names rarely match the alias used in the config file, so allow an
        # override and fall back to the alias when the two happen to line up.
        token = get_rds_iam_token(db_config.get('rds_db_name', db_config['name']))

        # The token names the user it was issued for, so `user` is optional in the config.
        token_user = db_user_from_token(token)
        user = db_config.get('user') or token_user
        if not user:
            raise ConfigError(
                f"Database '{db_name}' has no 'user', and the token from 'rx rds password' "
                f"did not name one either. Add a 'user' to {CONFIG_FILENAME}."
            )
        if token_user and db_config.get('user') and db_config['user'] != token_user:
            # The token is signed for one user, so connecting as another is rejected by RDS
            # with a bare access-denied. Say what is actually wrong instead.
            raise ConfigError(
                f"Database '{db_name}' is configured for user "
                f"{db_config['user']!r}, but 'rx rds password' issued a token for "
                f"{token_user!r}. Remove 'user' from {CONFIG_FILENAME} to use the token's "
                "own user, or correct it to match."
            )

        # IAM tokens are URL shaped, so they have to be escaped inside the connection
        # string. AWS also requires TLS, and only pymysql completes the token handshake.
        ssl_ca = db_config.get('ssl_ca')
        connection_string = (
            f"mysql+pymysql://{quote_plus(user)}:{quote_plus(token)}"
            f"@{host}:{port}/{database}"
        )
        # A CA bundle gets the certificate verified too; without one we still insist on
        # an encrypted connection, we just cannot prove who is on the other end.
        connect_args = {
            'ssl': {'ca': ssl_ca} if ssl_ca else {'check_hostname': False},
            'cursorclass': _iam_cursor_class(),
        }
    else:
        connection_string = (
            f"mysql+mysqlconnector://{db_config['user']}:{db_config['password']}"
            f"@{host}:{port}/{database}"
        )
        connect_args = {}

    try:
        engine = create_engine(connection_string, connect_args=connect_args)
        return engine.connect()
    except Exception as e:
        method = 'AWS RDS IAM' if iam_auth else 'password'
        raise ConnectionFailedError(
            f"Could not connect to MySQL database '{db_name}' at {host}:{port} using "
            f"{method} authentication: {e}"
        ) from e


def read_mysql(db_name: str, query: str) -> pd.DataFrame:
    """
    Read data from a MySQL database into a Pandas DataFrame.

    :param db_name: Name of the database as defined in the config file.
    :param query: SQL query to execute, or the path to a .sql file.
    :return: A DataFrame of results, with column names lower-cased. Empty if the query
        matched no rows.
    :raises QueryError: If the query could not be run.
    """
    sql = load_sql_file(query)
    con = mysql_connect(db_name)
    try:
        df = pd.read_sql(sql, con)
        df.columns = df.columns.str.lower()
        return df
    except Exception as e:
        raise QueryError(f"Query against MySQL database '{db_name}' failed: {e}") from e
    finally:
        con.close()


def execute_mysql(db_name: str, query: str) -> None:
    """
    Execute a query on a MySQL database without returning results.

    :param db_name: Database name as defined in the config file.
    :param query: SQL query to execute, or the path to a .sql file.
    :raises QueryError: If the query could not be run.
    """
    sql = load_sql_file(query)
    con = mysql_connect(db_name)
    try:
        con.execute(text(sql))
        con.commit()
    except Exception as e:
        raise QueryError(
            f"Statement against MySQL database '{db_name}' failed: {e}"
        ) from e
    finally:
        con.close()


def execute_snowflake(db_name: str, query: str) -> None:
    """
    Execute a query on Snowflake using Snowpark.

    :param db_name: Database name as defined in the config file.
    :param query: SQL query to execute, or the path to a .sql file.
    :raises QueryError: If the query could not be run.
    """
    sql = load_sql_file(query)
    session = snowflake_connect(db_name)
    try:
        session.sql(sql).collect()
        logger.info("Statement executed successfully against Snowflake database '%s'.", db_name)
    except Exception as e:
        raise QueryError(f"Statement against Snowflake database '{db_name}' failed: {e}") from e
    finally:
        session.close()


def read_snowflake(db_name: str, query: str) -> pd.DataFrame:
    """
    Fetch data from Snowflake into a Pandas DataFrame using Snowpark.

    :param db_name: Database name as defined in the config file.
    :param query: SQL query to execute, or the path to a .sql file.
    :return: A DataFrame of results, with column names lower-cased. Empty if the query
        matched no rows.
    :raises QueryError: If the query could not be run.
    """
    sql = load_sql_file(query)
    session = snowflake_connect(db_name)
    try:
        df = session.sql(sql).to_pandas()
        df.columns = df.columns.str.lower()
        return df
    except Exception as e:
        raise QueryError(f"Query against Snowflake database '{db_name}' failed: {e}") from e
    finally:
        session.close()


def write_data(
    db_name: str,
    schema: str,
    df: pd.DataFrame,
    table_name: str,
    overwrite: bool = True,
    chunk_size: int = 1000,
    **kwargs: Any,
) -> None:
    """
    Write a Pandas DataFrame to a Snowflake table using Snowpark.

    :param db_name: Database name as defined in the config file.
    :param schema: Schema where the table exists.
    :param df: Pandas DataFrame to write.
    :param table_name: Table name to write to.
    :param overwrite: Whether to overwrite the table if it exists.
    :param chunk_size: Number of rows to write per chunk.
    :raises QueryError: If the data could not be written.
    """
    session = snowflake_connect(db_name)
    try:
        session.write_pandas(
            df=df,
            schema=schema,
            table_name=table_name,
            auto_create_table=True,
            overwrite=overwrite,
            quote_identifiers=False,
            chunk_size=chunk_size,
            **kwargs,
        )
        logger.info('Data written successfully to %s.%s.', schema, table_name)
    except Exception as e:
        raise QueryError(f"Could not write to {schema}.{table_name} in '{db_name}': {e}") from e
    finally:
        session.close()


def _require_supported_type(db_name: str, db_config: dict[str, Any]) -> str:
    """
    Check that a database block declares a type Spellbook can talk to.

    :param db_name: The name of the database, for the error message.
    :param db_config: The configuration block for that database.
    :return: The database type.
    :raises ConfigError: If the type is missing or unsupported.
    """
    db_type = db_config.get('type')
    if db_type not in SUPPORTED_DB_TYPES:
        raise ConfigError(
            f"Database '{db_name}' has type {db_type!r}. "
            f"Valid types are: {', '.join(SUPPORTED_DB_TYPES)}."
        )
    return db_type


def get_data(db_name: str, query: str) -> pd.DataFrame:
    """
    Get data from a database.

    :param db_name: The name of the database as defined in the config file.
    :param query: SQL query to execute, or the path to a .sql file.
    :return: A DataFrame of results, with column names lower-cased. Empty if the query
        matched no rows.
    :raises ConfigError: If the database is not configured correctly.
    :raises QueryError: If the query could not be run.
    """
    db_config = get_db_config(db_name)
    db_type = _require_supported_type(db_name, db_config)

    show_wizard()

    if db_type == 'snowflake':
        return read_snowflake(db_name, query)
    return read_mysql(db_name, query)


def run_sql(db_name: str, query: str) -> None:
    """
    Run a SQL statement on a database without returning results.

    :param db_name: The name of the database as defined in the config file.
    :param query: SQL statement to execute, or the path to a .sql file.
    :raises ConfigError: If the database is not configured correctly.
    :raises QueryError: If the statement could not be run.
    """
    db_config = get_db_config(db_name)
    db_type = _require_supported_type(db_name, db_config)

    show_wizard()

    if db_type == 'snowflake':
        execute_snowflake(db_name, query)
    else:
        execute_mysql(db_name, query)


def list_databases() -> pd.DataFrame:
    """
    List the databases available in the configuration file.

    Useful as a starting point when you do not already know what is configured.

    :return: A DataFrame with one row per configured database, with its name, type, and
        whether it uses AWS RDS IAM authentication. No credentials are included.
    :raises ConfigError: If the configuration file cannot be read.
    """
    config = load_and_parse_config(configurations='databases')
    rows = [
        {
            'name': db.get('name'),
            'type': db.get('type'),
            'database': db.get('database'),
            'iam_auth': bool(db.get('iam_auth')),
        }
        for db in config.get('databases') or []
    ]
    return pd.DataFrame(rows, columns=['name', 'type', 'database', 'iam_auth'])


def list_tables(db_name: str, pattern: str | None = None) -> pd.DataFrame:
    """
    List the tables in a database.

    :param db_name: The name of the database as defined in the config file.
    :param pattern: Optional case-insensitive substring to filter table names by.
    :return: A DataFrame of table names, and row estimates where the database provides them.
    :raises ConfigError: If the database is not configured correctly.
    :raises QueryError: If the catalogue could not be read.
    """
    db_config = get_db_config(db_name)
    db_type = _require_supported_type(db_name, db_config)
    schema = db_config.get('schema') if db_type == 'snowflake' else db_config.get('database')

    # Parameters are bound rather than interpolated, so a pattern containing '%' or a quote
    # cannot change the shape of the query.
    if db_type == 'mysql':
        sql = """
            select table_name, table_rows, table_type
            from information_schema.tables
            where table_schema = :schema
              and (:pattern is null or lower(table_name) like lower(:pattern))
            order by table_name
        """
    else:
        sql = """
            select table_name, row_count as table_rows, table_type
            from information_schema.tables
            where table_schema = :schema
              and (:pattern is null or lower(table_name) like lower(:pattern))
            order by table_name
        """

    params = {'schema': schema, 'pattern': f'%{pattern}%' if pattern else None}
    return _read_with_params(db_name, db_type, sql, params)


def describe_table(db_name: str, table: str) -> pd.DataFrame:
    """
    Describe the columns of a table.

    :param db_name: The name of the database as defined in the config file.
    :param table: The table name.
    :return: A DataFrame with one row per column, giving its name, type, nullability and
        default.
    :raises ConfigError: If the database is not configured correctly.
    :raises QueryError: If the catalogue could not be read.
    """
    db_config = get_db_config(db_name)
    db_type = _require_supported_type(db_name, db_config)
    schema = db_config.get('schema') if db_type == 'snowflake' else db_config.get('database')

    sql = """
        select column_name, data_type, is_nullable, column_default
        from information_schema.columns
        where table_schema = :schema
          and lower(table_name) = lower(:table)
        order by ordinal_position
    """

    df = _read_with_params(db_name, db_type, sql, {'schema': schema, 'table': table})
    if df.empty:
        raise QueryError(
            f"Table '{table}' was not found in database '{db_name}'. "
            f"Use list_tables('{db_name}') to see what is available."
        )
    return df


def preview_table(db_name: str, table: str, limit: int = 10) -> pd.DataFrame:
    """
    Read the first few rows of a table.

    :param db_name: The name of the database as defined in the config file.
    :param table: The table name.
    :param limit: Maximum number of rows to return.
    :return: A DataFrame of sample rows.
    :raises ValueError: If the table name is not a plain identifier, or limit is not positive.
    :raises QueryError: If the rows could not be read.
    """
    if not re.fullmatch(r'[A-Za-z0-9_$.]+', table or ''):
        # Table names cannot be bound as parameters, so only accept plain identifiers
        # rather than interpolating arbitrary text into the query.
        raise ValueError(
            f"{table!r} is not a valid table name. Expected letters, digits, underscores, "
            "dots or dollar signs."
        )
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError(f'limit must be a positive integer, got {limit!r}.')

    return get_data(db_name, f'select * from {table} limit {limit}')


def _read_with_params(
    db_name: str,
    db_type: str,
    sql: str,
    params: dict[str, Any],
) -> pd.DataFrame:
    """
    Run a parameterised catalogue query against either database type.

    :param db_name: The name of the database as defined in the config file.
    :param db_type: Either 'mysql' or 'snowflake'.
    :param sql: The SQL to run, using :name style parameters.
    :param params: Values to bind.
    :return: A DataFrame of results, with column names lower-cased.
    :raises QueryError: If the query could not be run.
    """
    if db_type == 'snowflake':
        # Snowpark has no named-parameter binding, so fall back to a literal-safe
        # substitution of the values we control.
        rendered = sql
        for key, value in params.items():
            literal = 'null' if value is None else "'" + str(value).replace("'", "''") + "'"
            rendered = rendered.replace(f':{key}', literal)
        return read_snowflake(db_name, rendered)

    con = mysql_connect(db_name)
    try:
        df = pd.read_sql(text(sql), con, params=params)
        df.columns = df.columns.str.lower()
        return df
    except Exception as e:
        raise QueryError(f"Catalogue query against '{db_name}' failed: {e}") from e
    finally:
        con.close()
