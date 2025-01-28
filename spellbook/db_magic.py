import os
from snowflake.snowpark import Session
from sqlalchemy import create_engine
import pandas as pd
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import base64
from spellbook.utils import load_and_parse_config, get_wizard, load_sql_file


# Needs a very specific pip install
# pip install "snowflake-connector-python[pandas]"


def get_db_config(db_name):
    # load the configuration
    try:
        config = load_and_parse_config(configurations='databases')
    except FileNotFoundError:
        print("Config file not found. Please ensure 'spellbook_config.yaml' exists.")
        config = None

    for db in config['databases']:
        if db['name'] == db_name:
            return db
    raise ValueError(f"Database configuration for '{db_name}' not found.")


def snowflake_connect(db_name, **kwargs):
    """
    Create a Snowflake connection using credentials from the config file or environment variables.
    :param db_name: The name of the database as defined in the config file.
    :return: Snowpark session object.
    """
    db_config = get_db_config(db_name, **kwargs)  # Fetch database config from the config file

    # Determine authentication method
    use_private_key = db_config.get('private_key') or os.getenv('SNOW_PK')

    try:
        if use_private_key:
            # Private key authentication
            private_key = db_config.get('private_key')
            passphrase = db_config.get('private_key_passphrase')

            # Decode and load the private key
            p_key = serialization.load_pem_private_key(
                base64.b64decode(private_key),
                password=passphrase.encode('ascii') if passphrase else None,
                backend=default_backend()
            )
            pkb = p_key.private_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )

            session = Session.builder.configs({
                'account': db_config['account'],
                'user': db_config['user'],
                'private_key': pkb,
                'role': db_config['role'],
                'warehouse': db_config['warehouse'],
                'database': db_config['database'],
                'schema': db_config.get('schema', 'public')
            }).create()
        else:
            # Username/password authentication
            session = Session.builder.configs({
                'account': db_config['account'],
                'user': db_config['user'],
                'password': db_config.get('password'),
                'role': db_config['role'],
                'warehouse': db_config['warehouse'],
                'database': db_config['database'],
                'schema': db_config.get('schema', 'public')
            }).create()

        return session
    except Exception as e:
        print(f"An error occurred creating the Snowflake session: {e}")
        return None


def mysql_connect(db_name, **kwargs):
    db_config = get_db_config(db_name, **kwargs)
    try:
        connection_string = (
            f"mysql+mysqlconnector://{db_config['user']}:{db_config['password']}"
            f"@{db_config['host']}:{db_config.get('port', 3306)}/{db_config['database']}"
        )
        engine = create_engine(connection_string)
        con = engine.connect()
        return con
    except Exception as e:
        print(f"An error occurred creating the MySQL connection: {e}")
        return None


def read_mysql(db_name, query):
    """
    Read data from a MySQL database into a Pandas DataFrame.
    :param db_name: Name of the database as defined in the config file.
    :param query: SQL query to execute.
    :return:
    """
    con = mysql_connect(db_name)
    if con is None:
        return pd.DataFrame()
    try:
        df = pd.read_sql(
            load_sql_file(query),
            con)
        df.columns = df.columns.str.lower()
        return df
    except Exception as e:
        print(f"An error occurred reading from MySQL: {e}")
        return pd.DataFrame()
    finally:
        con.close()


def execute_mysql(query, dbname):
    """
    Execute a query on a MySQL database.
    :param query: SQL query to execute.
    :param dbname: Database name as defined in the config file.
    :return:
    """
    try:
        # Establish a connection and run the query
        con = mysql_connect(dbname)
        mycursor = con.connection.cursor()
        mycursor.execute(
            load_sql_file(query)
        )
    except Exception as e:
        # Handle errors
        print('An error was encountered executing mysql, ', e)
    finally:
        con.close()


def execute_snowflake(db_name, query):
    """
    Execute a query on Snowflake using Snowpark.
    :param query: SQL query to execute.
    :param db_name: Database name as defined in the config file.
    """
    try:
        # Establish session
        session = snowflake_connect(db_name)
        if not session:
            print("Failed to connect to Snowflake.")
            return

        # Execute query
        session.sql(
            load_sql_file(query)
        ).collect()
        print("Query executed successfully.")

    except Exception as e:
        print(f"An error occurred executing in Snowflake: {e}")

    finally:
        if session:
            session.close()


def read_snowflake(db_name, query):
    """
    Fetch data from Snowflake into a Pandas DataFrame using Snowpark.
    :param db_name: Database name as defined in the config file.
    :param query: SQL query to fetch data.
    :return: Pandas DataFrame.
    """
    try:
        # Establish session
        session = snowflake_connect(db_name)
        if not session:
            print("Failed to connect to Snowflake.")
            return pd.DataFrame()

        # Execute query and fetch data
        df = (session.sql(
                load_sql_file(query)
        ).to_pandas())
        df.columns = df.columns.str.lower()  # Normalize column names
        return df

    except Exception as e:
        print(f"An error occurred reading from Snowflake: {e}")
        return pd.DataFrame()

    finally:
        if session:
            session.close()


def write_data(db_name, schema, df, table_name, overwrite=True, chunk_size=1000, **kwargs):
    """
    Write a Pandas DataFrame to a Snowflake table using Snowpark.
    :param db_name: Database name as defined in the config file.
    :param schema: Schema where the table exists.
    :param df: Pandas DataFrame to write.
    :param table_name: Table name to write to.
    :param overwrite: Whether to overwrite the table if it exists.
    """
    try:
        # Establish session
        session = snowflake_connect(db_name)
        if not session:
            print("Failed to connect to Snowflake.")
            return

        # Write DataFrame to Snowflake
        session.write_pandas(
            df=df,
            schema=schema,
            table_name=table_name,
            auto_create_table=True,
            overwrite=overwrite,
            quote_identifiers=False,
            chunk_size=chunk_size,
            **kwargs
        )
        print(f"Data written successfully to {schema}.{table_name}.")

    except Exception as e:
        print(f"An error occurred writing to Snowflake: {e}")

    finally:
        if session:
            session.close()


def get_data(db_name, query, **kwargs):
    """
    Get data from a database
    :param db_name:  The name of the database as defined in the config file.
    :param query: SQL query to execute.
    :return: Returns a pandas dataframe
    """
    db_config = get_db_config(db_name, **kwargs)
    # Call the correct database read function
    if db_config['type'] == 'snowflake':
        print(get_wizard())
        df = read_snowflake(
            db_name,
            load_sql_file(query)
        )
    elif db_config['type'] == 'mysql':
        print(get_wizard())
        df = read_mysql(
            db_name,
            load_sql_file(query)
        )
    else:
        print('Valid database types are, snowflake and mysql')
    return df


def run_sql(db_name, query, **kwargs):
    """
    Run a SQL query on a database
    :param db_name:  The name of the database as defined in the config file.
    :param query:  SQL query to execute.
    :return: None
    """
    db_config = get_db_config(db_name, **kwargs)
    # Call the correct database run function
    if db_config['type'] == 'snowflake':
        print(get_wizard())
        execute_snowflake(
            db_name,
            load_sql_file(query)
        )
    elif db_config['type'] == 'mysql':
        print(get_wizard())
        execute_mysql(
            db_name,
            load_sql_file(query)
        )
    else:
        print('Valid database types are, snowflake and mysql')
