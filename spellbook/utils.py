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
def load_and_parse_config(config_file_path='spellbook_config.yaml', configurations=None):
    """
    Load and parse the configuration
    :return: config variable
    """
    config = load_config(file_path=config_file_path)
    config = parse_env_variables(config, configurations=configurations)
    return config

# load wizard file from the wizard directory

def get_wizard():
    try:
        # Get a reference to the 'wizards' directory
        wizards_dir = importlib.resources.files('spellbook.wizards')

        # Convert the directory reference to a context-managed path
        with importlib.resources.as_file(wizards_dir) as wizards_path:
            # Get all text files in the directory
            wizard_files = [f.name for f in wizards_path.iterdir() if f.is_file() and f.name.endswith('.txt')]

        # Ensure there are wizard files available
        if not wizard_files:
            raise FileNotFoundError("No wizard files found in the directory.")

        # Choose a random file from the list
        random_file = random.choice(wizard_files)

        # Load the content of the randomly chosen file
        with importlib.resources.open_text('spellbook.wizards', random_file) as f:
            wizard = f.read()

        print(f"Loaded wizard file: {random_file}")
    except FileNotFoundError as e:
        print(e)
        wizard = None
    except Exception as e:
        print('An error was encountered loading the wizard:', e)
        wizard = None

    return wizard