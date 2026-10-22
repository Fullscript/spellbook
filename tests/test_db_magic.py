import subprocess

import pytest

from spellbook import db_magic


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

    class FakeEngine:
        def connect(self):
            return 'connection'

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
        monkeypatch.setattr(db_magic, 'get_db_config', lambda name, **kwargs: by_name[name])
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

    assert con == 'connection'
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

    assert con == 'connection'
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

    assert db_magic.mysql_connect('reporting_db') == 'connection'


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

    with pytest.raises(RuntimeError, match="'rx' command is not installed"):
        db_magic.get_rds_iam_token('example-rds-instance')


def test_rx_timeout_raises_a_clear_error(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', fake_rx(
        raises=subprocess.TimeoutExpired(cmd='rx', timeout=120),
    ))

    with pytest.raises(RuntimeError, match='did not finish within'):
        db_magic.get_rds_iam_token('example-rds-instance')


def test_rx_failure_surfaces_its_output(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', fake_rx(
        returncode=1, stderr='\x1b[;31m✘ database not found\x1b[;m',
    ))

    with pytest.raises(RuntimeError) as error:
        db_magic.get_rds_iam_token('typo-db')

    message = str(error.value)
    assert 'exited with status 1' in message
    assert '✘ database not found' in message
    assert '\x1b' not in message  # colour codes stripped so the message stays readable
    assert 'typo-db' in message


def test_empty_rx_output_raises_rather_than_connecting_with_a_blank_password(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', fake_rx(stdout='   \n\n'))

    with pytest.raises(RuntimeError, match='returned no token'):
        db_magic.get_rds_iam_token('example-rds-instance')


def test_iam_failure_reports_which_auth_method_failed(monkeypatch, config, capsys):
    config(IAM_DB)
    monkeypatch.setattr(subprocess, 'run', fake_rx(raises=FileNotFoundError('rx')))

    assert db_magic.mysql_connect('reporting_db') is None

    output = capsys.readouterr().out
    assert 'AWS RDS IAM authentication' in output
    assert 'reporting_db' in output


def test_password_failure_reports_which_auth_method_failed(monkeypatch, config, capsys):
    config(PASSWORD_DB)
    monkeypatch.setattr(db_magic, 'create_engine', lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError('driver missing')
    ))

    assert db_magic.mysql_connect('legacy_mysql') is None

    output = capsys.readouterr().out
    assert 'password authentication' in output
    assert 'driver missing' in output
