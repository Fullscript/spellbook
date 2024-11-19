import os
import yaml
import re

def load_config(file_path='spelbook_config.yaml'):
    """
    Load the configuration file
    :param file_path:
    :return: config variable
    """
    with open(file_path, 'r') as file:
        config = yaml.safe_load(file)
    return config

def parse_env_variables(config):
    """
    Parse the environment variables in the configuration file
    :param config:
    :return:  config variable
    """
    pattern = re.compile(r'\$\{(\w+)\}')
    for db in config['databases']:
        for key, value in db.items():
            if isinstance(value, str):
                matches = pattern.findall(value)
                for match in matches:
                    env_value = os.getenv(match, '')
                    db[key] = db[key].replace(f'${{{match}}}', env_value)
    return config

# Load and parse the configuration
def load_and_parse_config():
    """
    Load and parse the configuration
    :return: config variable
    """
    config = load_config()
    config = parse_env_variables(config)
    return config
