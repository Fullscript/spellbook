import os
import re
import subprocess
from snowflake.snowpark import Session
from sqlalchemy import create_engine
import pandas as pd
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import base64
from urllib.parse import quote_plus
from spellbook.utils import load_and_parse_config, get_wizard, load_sql_file


# Needs a very specific pip install
# pip install "snowflake-connector-python[pandas]"

# How long to wait for `rx` to mint an RDS IAM token. The first call of the day can
# be slow because `rx` has to walk through AWS SSO before it reaches RDS.
RDS_TOKEN_TIMEOUT = 120

# `rx` colourises its progress output, which has to come off before we can read the token.
_ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

# Built on first use so that pymysql is only imported when an IAM connection is made.
_IAM_CURSOR_CLASS = None


def _strip_ansi(text):
    """
    Remove ANSI colour and cursor codes from CLI output.
    :param text: The raw text written by the CLI.
    :return: The same text with escape codes removed.
    """
    return _ANSI_ESCAPE.sub('', text or '')


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


def get_rds_iam_token(rds_db_name, timeout=RDS_TOKEN_TIMEOUT):
    """
    Generate a temporary AWS RDS IAM authentication token using the `rx` CLI.

    The token stands in for a stored password and expires after about 15 minutes, so it
    has to be fetched fresh for every connection rather than cached in the config file.

    :param rds_db_name: The remote database name, as listed by `rx rds list`.
    :param timeout: Seconds to wait for `rx` before giving up.
    :return: The token to use as the connection password.
    :raises RuntimeError: If `rx` is unavailable, times out, fails, or returns no token.
    """
    command = ['rx', 'rds', 'password', rds_db_name]
    printable = ' '.join(command)

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise RuntimeError(
            "AWS RDS IAM authentication failed: the 'rx' command is not installed or not on "
            "your PATH. Install the Fullscript developer tooling, or drop 'iam_auth' from the "
            "database configuration to go back to password authentication."
        ) from None
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"AWS RDS IAM authentication failed: '{printable}' did not finish within {timeout} "
            f"seconds. It is probably waiting on AWS SSO - run '{printable}' in a terminal once "
            "to sign in, then try again."
        ) from None

    if result.returncode != 0:
        detail = _strip_ansi(result.stderr or result.stdout or '').strip()
        raise RuntimeError(
            f"AWS RDS IAM authentication failed: '{printable}' exited with status "
            f"{result.returncode}. Check that '{rds_db_name}' appears in 'rx rds list' and that "
            f"you are signed in to AWS. Output from rx: {detail or '<none>'}"
        )

    # `rx` writes progress lines before the token, so the token is the last thing it prints.
    lines = [line.strip() for line in _strip_ansi(result.stdout).splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(
            f"AWS RDS IAM authentication failed: '{printable}' succeeded but returned no token."
        )

    return lines[-1]


def mysql_connect(db_name, **kwargs):
    """
    Create a MySQL connection using either AWS RDS IAM authentication or a stored password.

    Set `iam_auth: true` on the database in the config file to authenticate with a temporary
    IAM token from `rx rds password`. Without it, the `password` field is used as before.

    :param db_name: The name of the database as defined in the config file.
    :return: SQLAlchemy connection object, or None if the connection could not be made.
    """
    db_config = get_db_config(db_name, **kwargs)
    try:
        host = db_config['host']
        port = db_config.get('port', 3306)
        database = db_config['database']

        if db_config.get('iam_auth'):
            # RDS instance names rarely match the alias used in the config file, so allow an
            # override and fall back to the alias when the two happen to line up.
            token = get_rds_iam_token(db_config.get('rds_db_name', db_config['name']))
            # IAM tokens are URL shaped, so they have to be escaped inside the connection
            # string. AWS also requires TLS, and only pymysql completes the token handshake.
            ssl_ca = db_config.get('ssl_ca')
            connection_string = (
                f"mysql+pymysql://{quote_plus(db_config['user'])}:{quote_plus(token)}"
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

        engine = create_engine(connection_string, connect_args=connect_args)
        con = engine.connect()
        return con
    except Exception as e:
        auth_method = 'AWS RDS IAM' if db_config.get('iam_auth') else 'password'
        print(
            f"An error occurred creating the MySQL connection to '{db_name}' "
            f"using {auth_method} authentication: {e}"
        )
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
