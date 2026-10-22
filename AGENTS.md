# Working on Spellbook

Notes for anyone - person or coding agent - changing this package. This file covers the
things that are not obvious from reading the code.

## What this package is

A thin, friendly wrapper over Snowflake, MySQL, Google Sheets, Google Drive and some
statistics helpers, published publicly to PyPI as `fullscript.spellbook`.

**It is a public package.** Never commit Fullscript hostnames, database names, RDS instance
identifiers, usernames or internal URLs - not in code, examples, docs or tests. Use
placeholders (`${MYSQL_HOST}`, `your_rds_instance_name`) instead.

## Running the tests

```bash
pip install -e '.[test]'
pytest
```

Tests mock the database and `subprocess`, so they need no network and no credentials.
`tests/test_db_magic.py` covers connections and auth, `tests/test_utils.py` covers config
loading. Testing against a real database needs AWS SSO, which no automated run can do.

## Versioning

The version is **not** in a file. `setuptools_scm` derives it from git tags, so releasing
means tagging:

```bash
git tag 3.0.0 && git push origin main --tags
```

Pushing a tag triggers `.gitlab-ci.yml`, which publishes to both the internal registry and
public PyPI. Do not tag unless you intend to publish.

## Conventions worth keeping

**Errors raise, they do not return empty.** Every failure path raises a subclass of
`SpellbookError` from `spellbook/exceptions.py`. Returning `pd.DataFrame()` or `None` on
failure is the thing this package deliberately moved away from: a caller cannot tell
"matched no rows" from "never ran", which produces confidently wrong analysis. An empty
DataFrame must only ever mean zero rows.

**Decorative output goes to stderr, never stdout.** The wizard ASCII art is charm, not
data. `utils.show_wizard()` honours `SPELLBOOK_QUIET=1`; set that when calling Spellbook
from a script or agent. Use `logging` for diagnostics rather than `print`.

**Function signatures are `(db_name, query)`, in that order.** `execute_mysql` once took
`(query, dbname)`, which silently broke every `run_sql` call against MySQL. Keep the order
and the `db_name` spelling consistent across every function.

**Bind parameters in catalogue queries.** `list_tables` and `describe_table` pass values
through SQLAlchemy parameters so a `%` or a quote in user input cannot reshape the query.
`preview_table` cannot bind a table name, so it validates it against a strict identifier
pattern instead.

## Traps that have cost time before

**Validate the database being used, not the whole config.** The entire `databases` section
is re-parsed on every lookup, so any check that runs during parsing applies to databases the
caller never asked for. Release 3.0.0 raised on the first unset `${VAR}` anywhere in the
section, which meant an unrelated Snowflake entry with no key passphrase blocked every MySQL
query. `parse_env_variables` now substitutes permissively and records unresolved names under
`_unresolved_env`; `db_magic._validate_db_config` turns those into an error for the selected
database only, and only for settings in `REQUIRED_FIELDS`. Settings that are legitimately
empty - a Snowflake passphrase, `ssl_ca`, `port`, `schema` - must stay out of that list.

**Config file precedence.** `utils.find_config_file()` prefers `spellbook_config.yaml` in
the *current working directory* over the one in your home directory. Running anything from
this repository picks up the placeholder example config, not your real one. If a connection
fails with odd credentials, check which file was loaded.

**Two MySQL drivers.** Password auth uses `mysql+mysqlconnector`; AWS RDS IAM auth uses
`mysql+pymysql`, because only pymysql completes the IAM token handshake. They are not
interchangeable:

- pymysql substitutes parameters whenever `args is not None`, and pandas passes an empty
  tuple, so a literal `%` in `like '%value%'` is read as a format character and raises.
  mysql-connector guards on `if params:` instead. `db_magic._iam_cursor_class()` normalises
  empty parameters to `None` so both drivers behave the same. Do not remove it without a
  test that runs a `like '%...%'` query.
- An empty `ssl` dict makes TLS merely *preferred* in pymysql. The dict passed must be
  truthy for TLS to be required.

**RDS IAM specifics.** Tokens expire in about 15 minutes, so they are fetched per
connection and never cached. `rx rds password` takes the *RDS instance* name, which usually
differs from the config alias - hence the optional `rds_db_name` field. The token is URL
shaped and must be `quote_plus`-escaped into the connection string.

**`iam_auth` is internal only.** It shells out to `rx`, which is Fullscript internal
tooling, so the feature cannot work for public users of this package. Keep password auth
working and keep the docs honest about the limitation.

## Repository layout

| Path | Purpose |
| --- | --- |
| `spellbook/db_magic.py` | Snowflake and MySQL connections, queries, schema helpers |
| `spellbook/exceptions.py` | The `SpellbookError` hierarchy |
| `spellbook/utils.py` | Config loading, env substitution, wizards, SQL file loading |
| `spellbook/sheet_magic.py` | Google Sheets |
| `spellbook/drive_magic.py` | Google Drive |
| `spellbook/stats_magic.py` | Statistical tests |
| `spellbook_config.yaml` | **Example** config, published - placeholders only |
| `documentation/` | User-facing docs per module |
