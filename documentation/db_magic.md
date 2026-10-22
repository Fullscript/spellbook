A magical wrapper to perform work with databases.


##### Key Features
* **Unified Interface**: Abstracts the complexities of connecting and interacting with Snowflake and MySQL databases.
* **Seamless Data Handling**: Fetch, manipulate, and write data with Pandas DataFrames.
* **Flexibility**: Supports secure credentials management via configuration files and environment variables.

```python
from spellbook import db_magic
```

### Error Handling

Every failure raises an exception. An empty DataFrame always means "the query matched no
rows" and never "something went wrong", so results can be trusted without extra checks.

```python
from spellbook import db_magic
from spellbook.exceptions import SpellbookError, QueryError, DatabaseNotFoundError

try:
    df = db_magic.get_data('reporting_db', 'select * from users limit 10')
except DatabaseNotFoundError:
    ...  # the name is not in spellbook_config.yaml
except QueryError:
    ...  # the database rejected the query
except SpellbookError:
    ...  # anything Spellbook raises
```

| Exception | Raised when |
| --- | --- |
| `SpellbookError` | Base class for all of the below |
| `ConfigError` | The config file is missing, malformed, or references an unset `${VAR}` |
| `DatabaseNotFoundError` | No database in the config matches the requested name |
| `AuthenticationError` | Credentials could not be obtained or were rejected |
| `ConnectionFailedError` | The database could not be reached |
| `QueryError` | The query was rejected or failed while running |

> **Upgrading from 2.x:** these functions used to print a message and return an empty
> DataFrame or `None` on failure. Code that inspected `df.empty` to detect *errors* now
> needs a `try`/`except`. Code that used `df.empty` to detect *zero rows* is unaffected.

### Quiet Mode

Spellbook prints a wizard for company on each query. It goes to stderr, never stdout, so it
cannot contaminate results. Set `SPELLBOOK_QUIET=1` to turn it off - recommended for
scripts, scheduled jobs and anything driven by an AI agent.

```bash
export SPELLBOOK_QUIET=1
```

### MySQL Authentication

MySQL connections support two authentication methods, chosen per database in `spellbook_config.yaml`.

**Password authentication** is the default and needs no changes to an existing config:

```yaml
- name: legacy_mysql
  type: mysql
  host: your_host
  port: 3306
  user: mysql_user_name
  password: ${MYSQL_PASSWORD}
  database: mysql_database
```

**AWS RDS IAM authentication** stores no password at all. Add `iam_auth: true` and Spellbook
calls `rx rds password <rds_db_name>` for a temporary token each time it connects, because the
tokens expire after about 15 minutes:

> **Internal use only.** `iam_auth` depends on the `rx` CLI, which is Fullscript internal
> tooling and is not publicly available. Password authentication is the only MySQL option
> outside Fullscript, and it remains fully supported.

```yaml
- name: reporting_db
  type: mysql
  host: ${MYSQL_HOST} # e.g. your-instance.abc123.us-east-1.rds.amazonaws.com
  port: 3306
  user: ${DB_USER}
  iam_auth: true
  rds_db_name: your_rds_instance_name # Optional, defaults to the value of `name`
  database: ${MYSQL_DATABASE}
```

| Field | Required | Notes |
| --- | --- | --- |
| `iam_auth` | No | `true` switches the database to IAM tokens. Omitting it keeps password authentication. |
| `user` | Yes | Your IAM database user. |
| `rds_db_name` | No | The remote database as named by `rx rds list`. Defaults to `name`, so set it whenever your config alias differs from the RDS name. |
| `ssl_ca` | No | Not needed in normal use; see below. |
| `password` | No | Ignored when `iam_auth` is true. |

Requirements for the IAM path:
* The `rx` CLI must be installed and on your `PATH`.
* You must be signed in to AWS. If a connection hangs or fails on authentication, run
  `rx rds password <rds_db_name>` in a terminal once to complete the AWS SSO prompt.
* IAM connections use the `pymysql` driver (installed with Spellbook). Password connections
  continue to use `mysql-connector`.

##### A note on TLS and `ssl_ca`

AWS requires TLS for IAM authentication, so Spellbook always negotiates an encrypted
connection. You do **not** need to set `ssl_ca` — leave it out and you get TLS without
verifying which server you reached, which is the normal setup.

Set `ssl_ca` only if you also want the server certificate verified. If you do:
* Point it at the [AWS RDS CA bundle](https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem).
  Your operating system's bundle will not work, because RDS certificates do not chain to a
  publicly trusted root; using it fails with `CERTIFICATE_VERIFY_FAILED`.
* Use the instance's own RDS endpoint as `host`. Verification also checks the hostname, so a
  CNAME that points at the instance is likely to be rejected even with the right bundle.

### Methods Overview


##### get_data(db_name, query)

Fetches data from a specified database and returns it as a Pandas DataFrame. This method abstracts the connection and retrieval process for both Snowflake and MySQL databases, allowing you to focus on the SQL query.

Parameters:
* `db_name` (str): The database name defined in the configuration file.
* `query` (str): The SQL query to execute.

Returns:
* A Pandas DataFrame containing the result of the query.

```python
# Fetch data from Snowflake
# Option 1:
query = "SELECT * FROM my_table LIMIT 10;"
df = db_magic.get_data("snowflake_db", query)

# Option 2:
df = db_magic.get_data("snowflake_db", 'my_sql_query.sql')

# Option 3:
df = db_magic.get_data("snowflake_db", 'user/project/my_query.sql')


# Fetch data from MySQL
query = "SELECT * FROM users WHERE is_active = 1;"
df = db_magic.get_data("mysql_db", query)

# Display results
print(df.head())
```

##### write_data(db_name, schema, df, table_name, overwrite=True, chunk_size=1000, **kwargs)

Writes a Pandas DataFrame to a table in Snowflake. It supports creating tables automatically and overwriting existing tables.

Parameters:
* `db_name` (str): The database name defined in the configuration file.
* `schema` (str): The schema where the table is located.
* `df` (Pandas DataFrame): The data to write.
* `table_name` (str): The name of the destination table.
* `overwrite` (bool): Whether to overwrite the table if it exists (default: True).
* `chunk_size` (int): Number of rows to write per chunk (default: 1000).

```python
import pandas as pd

# Create a sample DataFrame
data = {"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"]}
df = pd.DataFrame(data)

# Write data to Snowflake
db_magic.write_data("snowflake_db", "my_schema", df, "my_table", overwrite=True)
```

##### run_sql(db_name, query)

Executes a SQL query directly on a specified database without returning results. Ideal for operations like creating tables, updating rows, or running stored procedures.

Parameters:
* `db_name` (str): The database name defined in the configuration file.
* `query` (str): The SQL query to execute.

Returns:
* `None`

```python

# Execute SQL in Snowflake
create_table_query = """
CREATE TABLE my_table (
    id INT,
    name STRING
);
"""
db_magic.run_sql("snowflake_db", create_table_query)

# Execute SQL in MySQL
update_query = "UPDATE users SET is_active = 1 WHERE last_login > '2024-01-01';"
db_magic.run_sql("mysql_db", update_query)

print("SQL executed successfully!")
```

### Exploring a database

These helpers answer "what is in here?" without hand-writing `information_schema` queries.
They are useful interactively, and they are what an AI agent needs before it can write a
sensible query.

##### list_databases()

Lists the databases in your configuration file, with no credentials included.

```python
db_magic.list_databases()
#            name     type        database  iam_auth
# 0  reporting_db    mysql  mysql_database      True
```

##### list_tables(db_name, pattern=None)

Lists the tables in a database, optionally filtered by a case-insensitive substring.

```python
db_magic.list_tables("mysql_db")
db_magic.list_tables("mysql_db", pattern="order")
```

The pattern is passed as a bound parameter, so `%` and quotes in it are treated as literal
text rather than changing the query.

##### describe_table(db_name, table)

Returns one row per column, with its type, nullability and default. Raises `QueryError` if
the table does not exist.

```python
db_magic.describe_table("mysql_db", "users")
#   column_name data_type is_nullable column_default
# 0          id    bigint          NO           None
# 1        name   varchar         YES           None
```

##### preview_table(db_name, table, limit=10)

Reads the first few rows of a table.

```python
db_magic.preview_table("mysql_db", "users", limit=5)
```

`table` must be a plain identifier - letters, digits, underscores, dots or dollar signs -
because a table name cannot be passed as a bound parameter.