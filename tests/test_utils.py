import os

import pytest
import yaml

from spellbook import utils
from spellbook.exceptions import ConfigError


CONFIG = {
    'databases': [
        {
            'name': 'reporting_db',
            'type': 'mysql',
            'host': '${MYSQL_HOST}',
            'user': '${DB_USER}',
            'database': 'fixed_value',
            'port': 3306,
            'iam_auth': True,
        }
    ]
}


@pytest.fixture
def config_file(tmp_path):
    """Write a config file and return its path."""
    def write(contents, name='spellbook_config.yaml'):
        path = tmp_path / name
        path.write_text(contents if isinstance(contents, str) else yaml.safe_dump(contents))
        return str(path)
    return write


@pytest.fixture(autouse=True)
def forget_hardcoded_warnings():
    """The hardcoded-key warning is remembered per process, so reset it between tests."""
    utils._WARNED_HARDCODED.clear()


# --- Unresolved environment variables are an error ---------------------------------------
# Previously ${VAR} for an unset variable became '', which surfaced much later as a
# confusing driver error, e.g. an empty username being rejected by the server.

def test_unset_environment_variable_raises(monkeypatch, config_file):
    monkeypatch.delenv('DB_USER', raising=False)
    monkeypatch.setenv('MYSQL_HOST', 'db.example.com')
    path = config_file(CONFIG)

    with pytest.raises(ConfigError) as error:
        utils.load_and_parse_config(config_file_path=path, configurations='databases')

    message = str(error.value)
    assert 'DB_USER' in message
    assert 'reporting_db' in message, 'the error should name the database involved'
    assert 'user' in message


def test_empty_environment_variable_raises(monkeypatch, config_file):
    monkeypatch.setenv('MYSQL_HOST', 'db.example.com')
    monkeypatch.setenv('DB_USER', '')
    path = config_file(CONFIG)

    with pytest.raises(ConfigError, match='DB_USER'):
        utils.load_and_parse_config(config_file_path=path, configurations='databases')


def test_placeholders_are_substituted_when_set(monkeypatch, config_file):
    monkeypatch.setenv('MYSQL_HOST', 'db.example.com')
    monkeypatch.setenv('DB_USER', 'iam_user')
    path = config_file(CONFIG)

    config = utils.load_and_parse_config(config_file_path=path, configurations='databases')

    db = config['databases'][0]
    assert db['host'] == 'db.example.com'
    assert db['user'] == 'iam_user'
    assert db['iam_auth'] is True, 'non-string values must pass through untouched'
    assert db['port'] == 3306


# --- Config file problems ----------------------------------------------------------------

def test_missing_file_raises_config_error(tmp_path):
    with pytest.raises(ConfigError, match='not found'):
        utils.load_config(str(tmp_path / 'absent.yaml'))


def test_malformed_yaml_raises_config_error(config_file):
    path = config_file('databases: [oops\n  bad indent')

    with pytest.raises(ConfigError, match='not valid YAML'):
        utils.load_config(path)


def test_empty_file_raises_config_error(config_file):
    path = config_file('')

    with pytest.raises(ConfigError, match='empty or not a mapping'):
        utils.load_config(path)


def test_missing_section_raises_config_error(config_file):
    path = config_file({'google_accounts': []})

    with pytest.raises(ConfigError, match="no 'databases' section"):
        utils.load_and_parse_config(config_file_path=path, configurations='databases')


# --- Hardcoded sensitive values warn once, not once per call -----------------------------

def test_hardcoded_sensitive_key_warns_once(config_file):
    path = config_file({'databases': [
        {'name': 'legacy', 'type': 'mysql', 'host': 'db.example.com'}
    ]})

    with pytest.warns(UserWarning, match="'host' is hardcoded"):
        utils.load_and_parse_config(config_file_path=path, configurations='databases')

    # A second load must stay silent, or the advice repeats on every query.
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        utils.load_and_parse_config(config_file_path=path, configurations='databases')


# --- Config file discovery ---------------------------------------------------------------

def test_explicit_path_wins(config_file):
    path = config_file(CONFIG, name='custom.yaml')

    assert utils.find_config_file(path) == path


def test_working_directory_shadows_the_home_directory(tmp_path, monkeypatch):
    """A config in the working directory silently takes precedence - worth asserting."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'spellbook_config.yaml').write_text('databases: []')

    found = utils.find_config_file()

    assert found == str(tmp_path / 'spellbook_config.yaml')


def test_falls_back_to_the_home_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no config file here

    found = utils.find_config_file()

    assert found == os.path.join(os.path.expanduser('~'), 'spellbook_config.yaml')


# --- Quiet mode --------------------------------------------------------------------------

@pytest.mark.parametrize('value', ['1', 'true', 'TRUE', 'yes', 'on'])
def test_quiet_is_detected(monkeypatch, value):
    monkeypatch.setenv('SPELLBOOK_QUIET', value)

    assert utils.is_quiet() is True


@pytest.mark.parametrize('value', ['', '0', 'false', 'no'])
def test_quiet_is_off_by_default(monkeypatch, value):
    monkeypatch.setenv('SPELLBOOK_QUIET', value)

    assert utils.is_quiet() is False


def test_show_wizard_prints_to_stderr_not_stdout(monkeypatch, capsys):
    monkeypatch.delenv('SPELLBOOK_QUIET', raising=False)
    monkeypatch.setattr(utils, 'get_wizard', lambda: 'a wizard appears')

    utils.show_wizard()

    captured = capsys.readouterr()
    assert captured.out == '', 'decorative output must never touch stdout'
    assert 'a wizard appears' in captured.err


def test_show_wizard_is_silent_when_quiet(monkeypatch, capsys):
    monkeypatch.setenv('SPELLBOOK_QUIET', '1')
    monkeypatch.setattr(utils, 'get_wizard', lambda: 'a wizard appears')

    utils.show_wizard()

    captured = capsys.readouterr()
    assert captured.out == ''
    assert captured.err == ''


def test_a_broken_wizard_never_interrupts_work(monkeypatch, capsys):
    monkeypatch.delenv('SPELLBOOK_QUIET', raising=False)
    monkeypatch.setattr(utils, 'get_wizard', lambda: None)

    utils.show_wizard()  # must not raise

    assert capsys.readouterr().err == ''


# --- load_sql_file -----------------------------------------------------------------------

def test_raw_sql_is_returned_unchanged():
    assert utils.load_sql_file('select 1') == 'select 1'


def test_sql_file_is_read(tmp_path):
    path = tmp_path / 'query.sql'
    path.write_text('select 42')

    assert utils.load_sql_file(str(path)) == 'select 42'


def test_non_sql_file_is_rejected(tmp_path):
    path = tmp_path / 'query.txt'
    path.write_text('select 42')

    with pytest.raises(ValueError, match='not a valid SQL file'):
        utils.load_sql_file(str(path))


@pytest.mark.parametrize('empty', ['', '   ', '\n\t'])
def test_empty_sql_is_rejected(empty):
    with pytest.raises(ValueError, match='empty'):
        utils.load_sql_file(empty)
