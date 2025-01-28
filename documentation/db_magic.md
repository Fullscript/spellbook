A magical wrapper to perform work with databases.


##### Key Features
* **Unified Interface**: Abstracts the complexities of connecting and interacting with Snowflake and MySQL databases.
* **Seamless Data Handling**: Fetch, manipulate, and write data with Pandas DataFrames.
* **Flexibility**: Supports secure credentials management via configuration files and environment variables.

```python
from spellbook import db_magic
```

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