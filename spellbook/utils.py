import os
import yaml
import re
import warnings
import random
import importlib.resources

def load_config(file_path):
    """
    Load the configuration file
    :param file_path: The path to the configuration file
    :return: config variable
    """
    with open(file_path, 'r') as file:
        config = yaml.safe_load(file)
    return config


def parse_env_variables(config, configurations):
    """
    Parse the environment variables in the configuration file
    :param configurations:  The key of the configuration block
    :param config: The configuration dictionary
    :return:  config variable
    """
    sensitive_keys = {'account', 'user', 'password', 'private_key', 'private_key_passphrase', 'host'}
    pattern = re.compile(r'\$\{(\w+)\}')

    for block in config[configurations]:
        for key, value in block.items():
            if isinstance(value, str):
                matches = pattern.findall(value)
                if not matches:  # If the value is not referencing an environment variable
                    if key in sensitive_keys:
                        warnings.warn(
                            f"The key '{key}' is hardcoded in the configuration file. "
                            "It is recommended to use environment variables for sensitive information."
                        )
                else:
                    # Replace environment variable placeholders with their values
                    for match in matches:
                        env_value = os.getenv(match, '')
                        block[key] = block[key].replace(f'${{{match}}}', env_value)
    return config


# Load and parse the configuration
# def load_and_parse_config(config_file_path='spellbook_config.yaml', configurations=None):
def load_and_parse_config(config_file_path=os.path.expanduser('~')+'/'+'spellbook_config.yaml', configurations=None):
    """
    Load and parse the configuration
    :return: config variable
    """

    # Use the home folder version but if a local file exists it overwrites the home folder version
    if os.path.isfile('spellbook_config.yaml'): 
        config_file_path='spellbook_config.yaml'
    else: 
        pass

    config = load_config(file_path=config_file_path)
    config = parse_env_variables(config, configurations=configurations)
    return config

# load wizard file from the wizard directory

def get_wizard():
    try:
        # Get a reference to the 'wizards' directory
        wizards_dir = importlib.resources.files('spellbook.wizards')

        # List all text files in the directory
        wizard_files = [f.name for f in wizards_dir.iterdir() if f.is_file() and f.name.endswith('.txt')]

        # Ensure there are wizard files available
        if not wizard_files:
            raise FileNotFoundError("No wizard files found in the directory.")

        # Choose a random file from the list
        random_file = random.choice(wizard_files)

        # Load the content of the randomly chosen file
        with importlib.resources.open_text('spellbook.wizards', random_file) as f:
            wizard = f.read()

    except FileNotFoundError as e:
        print(e)
        wizard = None
    except Exception as e:
        print('An error was encountered loading the wizard:', e)
        wizard = None

    return wizard


def load_sql_file(query_file):
    """
    Load the contents of a SQL file or return the SQL string directly.

    :param query_file: str, path to the SQL file or raw SQL query string
    :return: str, SQL query
    :raises ValueError: if the file path is invalid or not a .sql file
    """
    if isinstance(query_file, str) and os.path.exists(query_file):
        # Ensure it's a .sql file
        if not query_file.lower().endswith('.sql'):
            raise ValueError(f"The file {query_file} is not a valid SQL file.")

        # Use a context manager to read the file safely
        try:
            with open(query_file, 'r', encoding='utf-8') as file:
                query_str = file.read()
        except Exception as e:
            raise ValueError(f"Error reading the file {query_file}: {e}")
    else:
        # Assume it's a raw SQL query string
        query_str = query_file

    # Check for empty SQL content
    if not query_str.strip():
        raise ValueError("The SQL query is empty. Please provide valid SQL content.")

    return query_str