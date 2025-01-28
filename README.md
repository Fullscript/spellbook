# Spellbook

Helping data scientists and engineers save time by making it simple to connect to databases, work with spreadsheets, 
manage files, and run analyses. With Spellbook, they can focus on finding insights and solving problems instead of 
dealing with complicated tools.

With Spellbook, you can:
* Seamlessly connect to Snowflake and MySQL databases, for secure querying and effortless data retrieval.
* Work with Google Sheets, making it easy to read, write, and update spreadsheets.
* Manage Google Drive, creating folders and saving files with ease. 
* Perform statistical analyses, helping you run A/B tests and extract actionable insights.

Spellbook is built to simplify your workflows and supercharge your data exploration, so you can focus on turning insights into action!

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

## Features

- Effortless Database Connections and query execution
- Read/ Write to Google worksheets
- Manage Google Drive
- Perform statistical analyses

For feature methods and examples, please refer to the [Wiki Page](https://git.fullscript.io/data/spellbook/-/wikis/home).


## Installation

Spellbook requires Python 3.11 or higher. Use the following steps to install:
> Note: At the time relase, Snowpark does not support versions of Python higher than 3.11

1. Pip install:

```bash
pip install git+https://git.fullscript.io/data/spellbook.git
```

## Configuration
Effortlessly and securely manage your connections and configurations! Simply add database types and connection 
credentials to your [spellbook_config.yaml](spellbook_config.yaml) file, or include your Google service account details for seamless access to 
Google services. For added security, Spellbook supports storing credentials in environment variables 
or in a configuration file that references those variables, keeping your sensitive information safe and sound.

You must have a `spellbook_config.yaml` file in your root directory or in your project directory.
An example of the `spellbook_config.yaml` file is shown below:

```yaml
databases:
  # Snowflake Database Connection
  - name: alias_of_your_connection
    type: snowflake
    account: your_account
    user: snowflake_user_name # Optional for private key auth
    password: snowflake_password # Optional, used if private key is not present
    private_key: snowflake_pk # Base64-encoded private key
    private_key_passphrase: snowflake_pk_phrase # Optional
    role: snowflake_role
    warehouse: snowflake_warehouse
    database: snowflake_database
    schema: snowflake_schema

google_accounts:
  # Google Sheets Service Account 1
  - name: google_sheets_service_account_1
    service_account: "your_base64_encoded_service_account_credentials_here"  # Add your Base64-encoded service account JSON here
```

## Documentation
For detailed documentation on how to use Spellbook, please refer to the [Documentation](documentation) folder in the repository.  
**Functionality:**
- [Database Magic](documentation/db_magic.md)
- [Drive Magic](documentation/drive_magic.md)
- [Sheet Magic](documentation/sheet_magic.md)
- [Stat Magic](documentation/stat_magic.md)

## Contributing

We welcome contributions! Please follow these steps:

1. Fork this repository.
2. Create a new branch: `git checkout -b feature-name`.
3. Commit your changes: `git commit -m 'Add some feature'`.
4. Push to the branch: `git push origin feature-name`.
5. Open a pull request.

## License

Spellbook is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.

---