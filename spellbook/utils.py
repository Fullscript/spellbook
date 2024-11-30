import os
import yaml
import re
import warnings


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
