from snowflake.snowpark import Session
import os 
import json 
import pandas as pd
from sqlalchemy import create_engine
import random
import snowflake.connector

# Needs a very specific pip install
# pip install "snowflake-connector-python[pandas]"

def get_sf_creds(db_name):
    # Key value pairs of various snowflake databases
    dbs = {'snow_s':'staging_db',
        'snow_a':'analytics_db',
        'snow_f':'fivetran_database'}
    # Create a credentials dictionary
    creds = {
    'account': os.getenv('SNOWFLAKE_URL'),
    'user': os.getenv('SNOWFLAKE_USER'),
    'role': os.getenv('SNOWFLAKE_ROLE'),
    'password': os.getenv('SNOWFLAKE_PASSWORD'),
    'warehouse': 'COMPUTE_WH',
    'database': dbs[db_name]
    }
    return creds

def snowflake_connect(db_name):
    # Get the credentials dictionary
    creds = get_sf_creds(db_name)
    try:
        # Establish the connection
        con = snowflake.connector.connect(user=creds['user'], password = creds['password'], account=creds['account'], warehouse=creds['warehouse'], role=creds['role'], database=creds['database']) 
    except Exception as e:
        # Handle error
        print('An error was encountered creating the snowflake connection, ', e)        
    return con

def mysql_connect(db_name):
    # Key value pairs of various mysql databases
    hosts = {'fs_us': os.getenv('FS_US_URL'), 
             'fs_ca': os.getenv('FS_CA_URL')}
    dbs = {'fs_us':os.getenv('FS_US_DB'),
           'fs_ca':os.getenv('FS_CA_DB')}
    host=hosts[db_name]
    user=os.getenv('DB_USER')
    password=os.getenv('MYSQL_PASSWORD')
    database=dbs[db_name]
    # Create the connection string and engine sqlalchemy object
    connection_string = 'mysql+mysqlconnector://{user}:{password}@{host}:3306/{database}'.format(host=host, user=user, password=password,database=database)
    engine = create_engine(connection_string)
    # Establish the connection
    try:
        con=engine.connect()
    except Exception as e:
        print('An error was encountered creating the mysql connection, ', e)
    return con

def get_wizard():
    # Randomly source a wizard file
    random_file=random.choice(os.listdir('wizards'))
    try:
        # Open the file
        wizard = open('./wizards/{filen}'.format(filen=random_file)).read()
    except Exception as e:
        # Handle errors
        print('an error was encountered loading the wizard, ', e)
    return(wizard)

def read_mysql(db_name, query):
    # Create a blank dataframe to be overwritten
    df_extract = pd.DataFrame()
    try:
        # Establish the connection and get the dataframe
        con = mysql_connect(db_name)
        df_extract = pd.read_sql(query,con=con)
    except Exception as e:
        # Handle errors
        print('An error was encountered reading mysql, ', e)
    finally:
        # Close the connection
        con.close()
    # Cast all columns to lowercase
    df_extract.columns= df_extract.columns.str.lower()
    return df_extract

def execute_mysql(query, dbname):
    try:
        # Establish a connection and run the query
        con = mysql_connect(dbname)
        mycursor = con.connection.cursor()
        mycursor.execute(query)
    except Exception as e:
        # Handle errors
        print('An error was encountered executing mysql, ', e)
    finally:
        con.close()

def execute_snowflake(query):
    try:
        # Establish a connection and run the query
        con = snowflake_connect('snow_s')
        cur = con.cursor()
        cur.execute(query)
        print(get_wizard())
    except Exception as e:
        # Handle errors
        print('An error was encountered executing in snowflake, ', e)
    finally:
        # Close the connection
        con.close()

def read_snowflake(db_name, script):
    # Create a blank dataframe to be overwritten
    df_extract = pd.DataFrame()
    try:
        # Establish a connection and read the data
        con = snowflake_connect(db_name)
        cur = con.cursor()
        cur.execute(script)
        df_extract = cur.fetch_pandas_all()
    except Exception as e:
        # Handle errors
        print('An error was encountered reading snowflake, ', e)
    finally:
        # Close the connection
        con.close()        
    df_extract.columns= df_extract.columns.str.lower()
    return df_extract

def write_data(db_name, schema, df, tname):
    # Check if we are trying to write to staging
    if db_name !='snow_s':
        print('your can only write to the staging db')
    else:
        try:
            # Write the data
            session = Session.builder.configs(get_sf_creds(db_name)).create()
            print(get_wizard())
            snowparkDf=session.write_pandas(df=df, schema=schema, table_name=tname, auto_create_table=True, overwrite=True, 
                                        chunk_size=1000, on_error='continue', quote_identifiers=False)
        except Exception as e:
            # Handle errors
            print('An error was encountered writing to snowflake, ', e)

def get_data(db_name, script):
    # Call the correct database read function
    if db_name in ['snow_a', 'snow_f', 'snow_s']:
        df = read_snowflake(db_name, script)
        print(get_wizard())
    elif db_name in ['fs_us','fs_ca']:
        df = read_mysql(db_name, script)
        print(get_wizard())
    else:
        print('Valid database names are, fs_us, fs_ca, snow_a, snow_f and snow_s')
    return df

def run_sql(db_name, script):
    # Call the correct database run function
    if db_name in ['snow_a', 'snow_f', 'snow_s']:
        execute_snowflake(db_name, script)
        print(get_wizard())
    elif db_name in ['fs_us','fs_ca']:
        execute_mysql(db_name, script)
        print(get_wizard())
    else: 
        print('Valid database names are, fs_us, fs_ca, snow_a, snow_f and snow_s')