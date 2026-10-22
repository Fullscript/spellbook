import importlib.resources
import logging
import os
import random
import re
import sys
import warnings
from typing import Any

import yaml

from spellbook.exceptions import ConfigError

logger = logging.getLogger('spellbook')

# Keys whose values should come from environment variables rather than the config file.
SENSITIVE_KEYS = {
    'account', 'user', 'password', 'private_key', 'private_key_passphrase', 'host',
}

_ENV_PLACEHOLDER = re.compile(r'\$\{(\w+)\}')

# The config is re-read on every call, so remember which hardcoded keys have already been
# reported. Without this the same advice repeats once per query.
_WARNED_HARDCODED: set[tuple[str, str]] = set()

CONFIG_FILENAME = 'spellbook_config.yaml'

# Decorative output (the wizards) is written to stderr so it never contaminates data on
# stdout, and can be turned off entirely. Automated callers should set SPELLBOOK_QUIET=1.
QUIET_ENV_VAR = 'SPELLBOOK_QUIET'


def is_quiet() -> bool:
    """
    Report whether decorative output is suppressed.

    :return: True when SPELLBOOK_QUIET is set to a truthy value.
    """
    return os.getenv(QUIET_ENV_VAR, '').strip().lower() in {'1', 'true', 'yes', 'on'}


def load_config(file_path: str) -> dict[str, Any]:
    """
    Load the configuration file.

    :param file_path: The path to the configuration file.
    :return: The parsed configuration.
    :raises ConfigError: If the file is missing or is not valid YAML.
    """
    try:
        with open(file_path, 'r') as file:
            config = yaml.safe_load(file)
    except FileNotFoundError:
        raise ConfigError(
            f"Configuration file not found at '{file_path}'. Create a '{CONFIG_FILENAME}' "
            "in your home directory or in the directory you are working from."
        ) from None
    except yaml.YAMLError as e:
        raise ConfigError(f"Configuration file '{file_path}' is not valid YAML: {e}") from e

    if not isinstance(config, dict):
        raise ConfigError(f"Configuration file '{file_path}' is empty or not a mapping.")

    return config


def parse_env_variables(config: dict[str, Any], configurations: str) -> dict[str, Any]:
    """
    Replace ${VAR} placeholders in a configuration block with environment variable values.

    An unset variable is an error rather than an empty string, because an empty username or
    host produces a confusing driver-level failure much later on.

    :param config: The configuration dictionary.
    :param configurations: The key of the configuration block to parse.
    :return: The configuration with placeholders substituted.
    :raises ConfigError: If the block is missing, or a referenced variable is not set.
    """
    if configurations not in config:
        raise ConfigError(
            f"Configuration file has no '{configurations}' section. "
            f"Found: {', '.join(sorted(config)) or '<nothing>'}."
        )

    for block in config[configurations]:
        name = block.get('name', '<unnamed>')
        for key, value in block.items():
            if not isinstance(value, str):
                continue

            matches = _ENV_PLACEHOLDER.findall(value)
            if not matches:
                if key in SENSITIVE_KEYS and (name, key) not in _WARNED_HARDCODED:
                    _WARNED_HARDCODED.add((name, key))
                    warnings.warn(
                        f"The key '{key}' is hardcoded in the configuration file for "
                        f"'{name}'. It is recommended to use environment variables for "
                        "sensitive information.",
                        stacklevel=2,
                    )
                continue

            for match in matches:
                env_value = os.getenv(match)
                if env_value is None or env_value == '':
                    raise ConfigError(
                        f"Environment variable '{match}' is referenced by '{key}' on "
                        f"'{name}' but is not set. Export it, or replace ${{{match}}} in "
                        f"{CONFIG_FILENAME} with a literal value."
                    )
                block[key] = block[key].replace(f'${{{match}}}', env_value)

    return config


def find_config_file(config_file_path: str | None = None) -> str:
    """
    Work out which configuration file will be used.

    A file in the current working directory takes precedence over the one in your home
    directory, which is worth knowing: running from a directory that happens to contain a
    `spellbook_config.yaml` will silently use that one instead.

    :param config_file_path: An explicit path, which is used as-is when given.
    :return: The path to the configuration file that will be loaded.
    """
    if config_file_path:
        return config_file_path
    if os.path.isfile(CONFIG_FILENAME):
        return os.path.abspath(CONFIG_FILENAME)
    return os.path.join(os.path.expanduser('~'), CONFIG_FILENAME)


def load_and_parse_config(
    config_file_path: str | None = None,
    configurations: str | None = None,
) -> dict[str, Any]:
    """
    Load the configuration file and substitute environment variables.

    :param config_file_path: An explicit path to the configuration file. Defaults to
        `spellbook_config.yaml` in the working directory, falling back to your home directory.
    :param configurations: The configuration block to parse, e.g. 'databases'.
    :return: The parsed configuration.
    :raises ConfigError: If the file cannot be read or a referenced variable is not set.
    """
    path = find_config_file(config_file_path)
    logger.debug('Loading Spellbook configuration from %s', path)

    config = load_config(file_path=path)
    if configurations is not None:
        config = parse_env_variables(config, configurations=configurations)
    return config


def get_wizard() -> str | None:
    """
    Load the text of a randomly chosen wizard.

    :return: The wizard text, or None if no wizard could be loaded.
    """
    try:
        wizards_dir = importlib.resources.files('spellbook.wizards')
        wizard_files = [
            f.name for f in wizards_dir.iterdir()
            if f.is_file() and f.name.endswith('.txt')
        ]
        if not wizard_files:
            logger.debug('No wizard files found in the wizards directory.')
            return None

        return (wizards_dir / random.choice(wizard_files)).read_text()
    except Exception as e:
        # A missing wizard is cosmetic, so it must never interrupt real work.
        logger.debug('Could not load a wizard: %s', e)
        return None


def show_wizard() -> None:
    """
    Print a wizard to stderr, unless decorative output is suppressed.

    Set SPELLBOOK_QUIET=1 to turn this off. Output goes to stderr so that it cannot be
    mistaken for query results on stdout.
    """
    if is_quiet():
        return

    wizard = get_wizard()
    if wizard:
        print(wizard, file=sys.stderr)


def load_sql_file(query_file: str) -> str:
    """
    Load the contents of a SQL file, or return the SQL string unchanged.

    :param query_file: Path to a .sql file, or a raw SQL query string.
    :return: The SQL query.
    :raises ValueError: If the path is not a .sql file, cannot be read, or the SQL is empty.
    """
    if isinstance(query_file, str) and os.path.exists(query_file):
        if not query_file.lower().endswith('.sql'):
            raise ValueError(f"The file {query_file} is not a valid SQL file.")

        try:
            with open(query_file, 'r', encoding='utf-8') as file:
                query_str = file.read()
        except Exception as e:
            raise ValueError(f"Error reading the file {query_file}: {e}") from e
    else:
        query_str = query_file

    if not query_str or not query_str.strip():
        raise ValueError("The SQL query is empty. Please provide valid SQL content.")

    return query_str
