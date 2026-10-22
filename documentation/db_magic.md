A magical wrapper to perform work with databases.


##### Key Features
* **Unified Interface**: Abstracts the complexities of connecting and interacting with Snowflake and MySQL databases.
* **Seamless Data Handling**: Fetch, manipulate, and write data with Pandas DataFrames.
* **Flexibility**: Supports secure credentials management via configuration files and environment variables.

```python
from spellbook import db_magic
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
