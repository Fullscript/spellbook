import subprocess

import pandas as pd
import pytest

from spellbook import db_magic
from spellbook.exceptions import (
    AuthenticationError,
    ConfigError,
    ConnectionFailedError,
    DatabaseNotFoundError,
    QueryError,
    SpellbookError,
)


PASSWORD_DB = {
    'name': 'legacy_mysql',
    'type': 'mysql',
    'host': 'legacy.example.com',
    'port': 3306,
    'user': 'mysql_user_name',
    'password': 'mysql_password',
    'database': 'mysql_database',
}

IAM_DB = {
    'name': 'reporting_db',
    'type': 'mysql',
    'host': 'example-db.abc123.us-east-1.rds.amazonaws.com',
    'port': 3306,
    'user': 'iam_user',
    'iam_auth': True,
    'rds_db_name': 'example-rds-instance',
    'database': 'mysql_database',
}

# Real IAM tokens are URL shaped: the query string has to survive the trip into the
# connection string without being mistaken for part of the URL.
FAKE_TOKEN = (
    'example-db.abc123.us-east-1.rds.amazonaws.com:3306/'
    '?Action=connect&DBUser=iam_user&X-Amz-Signature=abc123'
)


@pytest.fixture
def engines(monkeypatch):
    """Capture the arguments mysql_connect passes to create_engine."""
    calls = []

    class FakeConnection:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    def fake_create_engine(connection_string, **kwargs):
        calls.append((connection_string, kwargs))
        return FakeEngine()

    monkeypatch.setattr(db_magic, 'create_engine', fake_create_engine)
    return calls


@pytest.fixture
def config(monkeypatch):
    """Point get_db_config at an in-test database list."""
    def use(*databases):
        by_name = {db['name']: db for db in databases}

        def get_db_config(name):
            if name not in by_name:
                raise DatabaseNotFoundError(f"Database configuration for '{name}' not found.")
            return by_name[name]

        monkeypatch.setattr(db_magic, 'get_db_config', get_db_config)
    return use


def fake_rx(stdout='', stderr='', returncode=0, expect=None, raises=None):
    """Build a stand-in for subprocess.run that mimics one `rx rds password` outcome."""
    def run(command, **kwargs):
        if expect is not None:
            assert command == expect
        if raises is not None:
            raise raises
        return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr=stderr)
    return run


# --- Password authentication stays exactly as it was -------------------------------------

def test_password_auth_uses_mysqlconnector(monkeypatch, config, engines):
    config(PASSWORD_DB)
    # Any attempt to shell out to rx on the password path is a backward compatibility bug.
    monkeypatch.setattr(subprocess, 'run', fake_rx(raises=AssertionError('rx must not run')))

    con = db_magic.mysql_connect('legacy_mysql')

    assert con is not None
    connection_string, kwargs = engines[0]
    assert connection_string == (
        'mysql+mysqlconnector://mysql_user_name:mysql_password'
        '@legacy.example.com:3306/mysql_database'
    )
    assert kwargs == {'connect_args': {}}


def test_password_auth_defaults_the_port(config, engines):
    config({key: value for key, value in PASSWORD_DB.items() if key != 'port'})

    db_magic.mysql_connect('legacy_mysql')

    assert ':3306/' in engines[0][0]


def test_iam_auth_false_behaves_like_password_auth(config, engines):
    config({**PASSWORD_DB, 'iam_auth': False})

    db_magic.mysql_connect('legacy_mysql')

    assert engines[0][0].startswith('mysql+mysqlconnector://')


# --- IAM authentication ------------------------------------------------------------------

def test_iam_auth_builds_a_pymysql_connection_string(monkeypatch, config, engines):
    config(IAM_DB)
    monkeypatch.setattr(subprocess, 'run', fake_rx(
        stdout=FAKE_TOKEN + '\n',
        expect=['rx', 'rds', 'password', 'example-rds-instance'],
    ))

    con = db_magic.mysql_connect('reporting_db')

    assert con is not None
    connection_string, kwargs = engines[0]
    assert connection_string.startswith('mysql+pymysql://iam_user:')
    assert connection_string.endswith(
        '@example-db.abc123.us-east-1.rds.amazonaws.com:3306/mysql_database'
    )
    # The token's own '?' and '&' must be escaped, or SQLAlchemy reads them as URL structure.
    assert '?Action=connect' not in connection_string
    assert '%3FAction%3Dconnect' in connection_string
    # TLS is mandatory for RDS IAM, so the ssl options must be truthy for pymysql to require it.
    assert kwargs['connect_args']['ssl']


def test_iam_auth_connection_string_round_trips_the_token(monkeypatch, config, engines):
    from sqlalchemy.engine import make_url

    config(IAM_DB)
    monkeypatch.setattr(subprocess, 'run', fake_rx(stdout=FAKE_TOKEN))

    db_magic.mysql_connect('reporting_db')

    url = make_url(engines[0][0])
    assert url.password == FAKE_TOKEN
    assert url.username == 'iam_user'
    assert url.database == 'mysql_database'


def test_iam_auth_falls_back_to_the_config_alias_for_the_rds_name(monkeypatch, config, engines):
    without_override = {key: value for key, value in IAM_DB.items() if key != 'rds_db_name'}
    config(without_override)
    monkeypatch.setattr(subprocess, 'run', fake_rx(
        stdout=FAKE_TOKEN,
        expect=['rx', 'rds', 'password', 'reporting_db'],
    ))

    assert db_magic.mysql_connect('reporting_db') is not None


def test_iam_auth_verifies_the_certificate_when_a_ca_bundle_is_given(monkeypatch, config, engines):
    config({**IAM_DB, 'ssl_ca': '/certs/rds-ca.pem'})
    monkeypatch.setattr(subprocess, 'run', fake_rx(stdout=FAKE_TOKEN))

    db_magic.mysql_connect('reporting_db')

    assert engines[0][1]['connect_args']['ssl'] == {'ca': '/certs/rds-ca.pem'}


def test_iam_auth_requires_tls_without_a_ca_bundle(monkeypatch, config, engines):
    config(IAM_DB)
    monkeypatch.setattr(subprocess, 'run', fake_rx(stdout=FAKE_TOKEN))

    db_magic.mysql_connect('reporting_db')

    assert engines[0][1]['connect_args']['ssl'] == {'check_hostname': False}


def test_iam_auth_fetches_a_fresh_token_per_connection(monkeypatch, config, engines):
    config(IAM_DB)
    tokens = iter(['token-one', 'token-two'])
    monkeypatch.setattr(
        subprocess, 'run',
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, stdout=next(tokens), stderr=''
        ),
    )

    db_magic.mysql_connect('reporting_db')
    db_magic.mysql_connect('reporting_db')

    assert 'token-one' in engines[0][0]
    assert 'token-two' in engines[1][0]


# --- Literal '%' must survive on the pymysql path ----------------------------------------
# pymysql substitutes whenever args is not None, so the empty parameter set pandas passes
# would turn `like '%x%'` into a format string. mysql-connector guards on `if params:`,
# so without this the IAM path would break queries the password path handles fine.

def test_iam_auth_uses_a_cursor_that_leaves_literal_percent_alone(monkeypatch, config, engines):
    config(IAM_DB)
    monkeypatch.setattr(subprocess, 'run', fake_rx(stdout=FAKE_TOKEN))

    db_magic.mysql_connect('reporting_db')

    cursor_class = engines[0][1]['connect_args']['cursorclass']
    import pymysql.cursors
    assert issubclass(cursor_class, pymysql.cursors.Cursor)


@pytest.fixture
def iam_cursor(monkeypatch):
    """An IAM cursor whose pymysql parent records the args it is handed."""
    import pymysql.cursors

    recorded = []
    monkeypatch.setattr(
        pymysql.cursors.Cursor, 'execute',
        lambda self, query, args=None: recorded.append(args),
    )
    return db_magic._iam_cursor_class()(None), recorded


@pytest.mark.parametrize('empty', [(), [], {}])
def test_empty_parameters_reach_pymysql_as_none(iam_cursor, empty):
    """An empty parameter set must arrive as None, or '%' gets read as a format character."""
    cursor, recorded = iam_cursor

    cursor.execute("select 1 from t where name like '%x%'", empty)

    assert recorded == [None]


def test_omitted_parameters_reach_pymysql_as_none(iam_cursor):
    cursor, recorded = iam_cursor

    cursor.execute("select 1 from t where name like '%x%'")

    assert recorded == [None]


def test_real_parameters_are_still_forwarded(iam_cursor):
    cursor, recorded = iam_cursor

    cursor.execute('select 1 from t where id = %s', (42,))

    assert recorded == [(42,)]


# --- Token retrieval ---------------------------------------------------------------------

def test_token_is_read_from_the_last_line_of_noisy_output(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', fake_rx(
        stdout='\x1b[32m⠿ Waiting for AWS authentication\x1b[0m\n\n' + FAKE_TOKEN + '\n',
    ))

    assert db_magic.get_rds_iam_token('example-rds-instance') == FAKE_TOKEN


def test_missing_rx_raises_a_clear_error(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', fake_rx(raises=FileNotFoundError('rx')))

    with pytest.raises(AuthenticationError, match="'rx' command is not installed"):
        db_magic.get_rds_iam_token('example-rds-instance')


def test_rx_timeout_raises_a_clear_error(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', fake_rx(
        raises=subprocess.TimeoutExpired(cmd='rx', timeout=120),
    ))

    with pytest.raises(AuthenticationError, match='did not finish within'):
        db_magic.get_rds_iam_token('example-rds-instance')


def test_rx_failure_surfaces_its_output(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', fake_rx(
        returncode=1, stderr='\x1b[;31m✘ database not found\x1b[;m',
    ))

    with pytest.raises(AuthenticationError) as error:
        db_magic.get_rds_iam_token('typo-db')

    message = str(error.value)
    assert 'exited with status 1' in message
    assert '✘ database not found' in message
    assert '\x1b' not in message  # colour codes stripped so the message stays readable
    assert 'typo-db' in message


def test_empty_rx_output_raises_rather_than_connecting_with_a_blank_password(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', fake_rx(stdout='   \n\n'))

    with pytest.raises(AuthenticationError, match='returned no token'):
        db_magic.get_rds_iam_token('example-rds-instance')


# --- Failures raise, and say which auth method failed ------------------------------------

def test_iam_failure_raises_and_names_the_auth_method(monkeypatch, config):
    config(IAM_DB)
    monkeypatch.setattr(subprocess, 'run', fake_rx(raises=FileNotFoundError('rx')))

    with pytest.raises(AuthenticationError, match='AWS RDS IAM authentication'):
        db_magic.mysql_connect('reporting_db')


def test_password_failure_raises_and_names_the_auth_method(monkeypatch, config):
    config(PASSWORD_DB)
    monkeypatch.setattr(db_magic, 'create_engine', lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError('driver missing')
    ))

    with pytest.raises(ConnectionFailedError) as error:
        db_magic.mysql_connect('legacy_mysql')

    message = str(error.value)
    assert 'password authentication' in message
    assert 'driver missing' in message
    assert 'legacy_mysql' in message


def test_missing_required_field_raises_config_error(config):
    config({key: value for key, value in PASSWORD_DB.items() if key != 'host'})

    with pytest.raises(ConfigError, match="missing the required 'host' field"):
        db_magic.mysql_connect('legacy_mysql')


# --- Required settings are validated per database, not across the whole config -----------
# Regression: validation ran over every block while parsing, so an unrelated Snowflake
# entry with an unset ${SNOW_PK_PASSPHRASE} made every MySQL query fail.

@pytest.fixture
def config_file(tmp_path, monkeypatch):
    """Write a real config file and make Spellbook load it."""
    import yaml

    def write(*databases):
        path = tmp_path / 'spellbook_config.yaml'
        path.write_text(yaml.safe_dump({'databases': list(databases)}))
        monkeypatch.setattr(
            db_magic, 'load_and_parse_config',
            lambda **kw: __import__('spellbook.utils', fromlist=['x'])
            .load_and_parse_config(config_file_path=str(path), **kw),
        )
    return write


def test_an_unrelated_database_does_not_block_the_one_you_asked_for(
    monkeypatch, config_file,
):
    monkeypatch.delenv('SNOW_PK_PASSPHRASE', raising=False)
    config_file(
        {'name': 'snow_s', 'type': 'snowflake', 'account': 'a', 'user': 'u', 'role': 'r',
         'warehouse': 'w', 'database': 'd',
         'private_key_passphrase': '${SNOW_PK_PASSPHRASE}'},
        IAM_DB,
    )

    db = db_magic.get_db_config('reporting_db')

    assert db['user'] == 'iam_user'
    assert '_unresolved_env' not in db, 'the internal marker must not leak to callers'


def test_an_optional_unset_setting_does_not_block_its_own_database(monkeypatch, config_file):
    """A Snowflake key with no passphrase is a valid setup, so it must not raise."""
    monkeypatch.delenv('SNOW_PK_PASSPHRASE', raising=False)
    config_file({
        'name': 'snow_s', 'type': 'snowflake', 'account': 'a', 'user': 'u', 'role': 'r',
        'warehouse': 'w', 'database': 'd', 'private_key_passphrase': '${SNOW_PK_PASSPHRASE}',
    })

    db = db_magic.get_db_config('snow_s')

    assert db['private_key_passphrase'] == ''


def test_a_required_setting_with_an_unset_variable_raises_and_names_it(
    monkeypatch, config_file,
):
    monkeypatch.delenv('DB_USER_NOT_SET', raising=False)
    config_file({
        'name': 'broken_db', 'type': 'mysql', 'host': 'h',
        'user': '${DB_USER_NOT_SET}', 'password': 'p', 'database': 'd',
    })

    with pytest.raises(ConfigError) as error:
        db_magic.get_db_config('broken_db')

    message = str(error.value)
    assert 'DB_USER_NOT_SET' in message
    assert 'broken_db' in message
    assert 'user' in message


@pytest.mark.parametrize('missing', ['host', 'user', 'database'])
def test_a_missing_required_mysql_setting_raises(config_file, missing):
    config_file({
        key: value for key, value in
        {'name': 'db', 'type': 'mysql', 'host': 'h', 'user': 'u',
         'password': 'p', 'database': 'd'}.items()
        if key != missing
    })

    with pytest.raises(ConfigError, match=f"required '{missing}'"):
        db_magic.get_db_config('db')


def test_password_is_required_without_iam_auth(config_file):
    config_file({'name': 'db', 'type': 'mysql', 'host': 'h', 'user': 'u', 'database': 'd'})

    with pytest.raises(ConfigError, match="required 'password'"):
        db_magic.get_db_config('db')


def test_password_is_not_required_with_iam_auth(config_file):
    config_file({'name': 'db', 'type': 'mysql', 'host': 'h', 'user': 'u',
                 'database': 'd', 'iam_auth': True})

    assert db_magic.get_db_config('db')['iam_auth'] is True


def test_every_spellbook_error_shares_one_base_class():
    for error in (
        ConfigError, DatabaseNotFoundError, AuthenticationError,
        ConnectionFailedError, QueryError,
    ):
        assert issubclass(error, SpellbookError)
    # DatabaseNotFoundError is a configuration problem, so it must be catchable as one.
    assert issubclass(DatabaseNotFoundError, ConfigError)


# --- Query failures surface, zero rows do not --------------------------------------------

@pytest.fixture
def mysql_results(monkeypatch):
    """Stub out the connection and pd.read_sql for read-path tests."""
    class FakeConnection:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    connection = FakeConnection()
    monkeypatch.setattr(db_magic, 'mysql_connect', lambda name: connection)
    return connection


def test_query_failure_raises_query_error(monkeypatch, mysql_results):
    monkeypatch.setattr(db_magic.pd, 'read_sql', lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("Table 'x' doesn't exist")
    ))

    with pytest.raises(QueryError, match="doesn't exist"):
        db_magic.read_mysql('legacy_mysql', 'select * from x')

    assert mysql_results.closed, 'the connection must be closed even when the query fails'


def test_zero_rows_is_an_empty_frame_not_an_error(monkeypatch, mysql_results):
    monkeypatch.setattr(db_magic.pd, 'read_sql', lambda *a, **k: pd.DataFrame(columns=['ID']))

    df = db_magic.read_mysql('legacy_mysql', 'select * from x where 1 = 0')

    assert df.empty
    assert list(df.columns) == ['id'], 'column names are lower-cased'


def test_unsupported_db_type_raises_config_error(config):
    config({'name': 'weird', 'type': 'postgres'})

    with pytest.raises(ConfigError, match='Valid types are'):
        db_magic.get_data('weird', 'select 1')


# --- run_sql dispatches with the arguments in the right order ----------------------------
# Regression test: run_sql used to call execute_mysql(db_name, sql) against a signature of
# (query, dbname), so every MySQL run_sql call failed before reaching the database.

def test_run_sql_passes_db_name_and_query_in_that_order(monkeypatch, config):
    config(PASSWORD_DB)
    seen = {}
    monkeypatch.setattr(db_magic, 'execute_mysql',
                        lambda db_name, query: seen.update(db=db_name, sql=query))

    db_magic.run_sql('legacy_mysql', 'delete from t where id = 1')

    assert seen == {'db': 'legacy_mysql', 'sql': 'delete from t where id = 1'}


def test_execute_mysql_takes_db_name_first(monkeypatch, config, mysql_results):
    """The signature must match every other function: (db_name, query)."""
    executed = []
    mysql_results.execute = lambda statement: executed.append(str(statement))
    mysql_results.commit = lambda: None

    db_magic.execute_mysql('legacy_mysql', 'delete from t')

    assert executed == ['delete from t']


def test_get_data_dispatches_to_mysql(monkeypatch, config):
    config(PASSWORD_DB)
    monkeypatch.setattr(db_magic, 'read_mysql',
                        lambda db_name, query: pd.DataFrame({'n': [1]}))

    assert db_magic.get_data('legacy_mysql', 'select 1').iloc[0, 0] == 1


# --- Schema helpers ----------------------------------------------------------------------

def test_preview_table_rejects_names_that_are_not_identifiers(config):
    config(PASSWORD_DB)

    with pytest.raises(ValueError, match='not a valid table name'):
        db_magic.preview_table('legacy_mysql', 'users; drop table users')


@pytest.mark.parametrize('limit', [0, -1, 'ten', 1.5, True])
def test_preview_table_rejects_a_bad_limit(config, limit):
    config(PASSWORD_DB)

    with pytest.raises(ValueError, match='positive integer'):
        db_magic.preview_table('legacy_mysql', 'users', limit=limit)


def test_preview_table_builds_a_limited_select(monkeypatch, config):
    config(PASSWORD_DB)
    seen = {}
    monkeypatch.setattr(db_magic, 'get_data',
                        lambda db_name, query: seen.update(db=db_name, sql=query))

    db_magic.preview_table('legacy_mysql', 'users', limit=5)

    assert seen['sql'] == 'select * from users limit 5'


def test_list_tables_binds_the_pattern_rather_than_interpolating_it(monkeypatch, config):
    config(PASSWORD_DB)
    seen = {}

    def fake_read(db_name, db_type, sql, params):
        seen.update(sql=sql, params=params)
        return pd.DataFrame()

    monkeypatch.setattr(db_magic, '_read_with_params', fake_read)
    db_magic.list_tables('legacy_mysql', pattern="o'brien%")

    # The value travels as a bound parameter, so quotes and '%' cannot alter the query.
    assert seen['params']['pattern'] == "%o'brien%%"
    assert "o'brien" not in seen['sql']
    assert seen['params']['schema'] == 'mysql_database'


def test_list_tables_without_a_pattern_binds_null(monkeypatch, config):
    config(PASSWORD_DB)
    seen = {}
    monkeypatch.setattr(db_magic, '_read_with_params',
                        lambda d, t, sql, params: seen.update(params=params) or pd.DataFrame())

    db_magic.list_tables('legacy_mysql')

    assert seen['params']['pattern'] is None


def test_describe_table_raises_when_the_table_is_unknown(monkeypatch, config):
    config(PASSWORD_DB)
    monkeypatch.setattr(db_magic, '_read_with_params',
                        lambda *a, **k: pd.DataFrame())

    with pytest.raises(QueryError, match='was not found'):
        db_magic.describe_table('legacy_mysql', 'nope')
