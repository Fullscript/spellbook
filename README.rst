# Spellbook

Spellbook is a powerful and easy-to-use library by Fullscript that enables seamless connections to **Snowflake** and **MySQL** databases, making data handling simpler for developers and data scientists. With Spellbook, you can establish secure connections, run queries, and retrieve data effortlessly. Built with scalability and ease of use in mind, Spellbook allows companies to integrate their Python data workflows into Snowflake and MySQL environments with minimal setup.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Contributing](#contributing)
- [License](#license)

## Features

- **Effortless Database Connections**: Quickly connect to Snowflake and MySQL databases.
- **Query Execution**: Run queries with straightforward syntax.
- **Data Retrieval**: Retrieve and process data easily.
- **Scalability**: Designed for both small and large datasets.

## Installation

Spellbook requires Python 3.11 or higher. Use the following steps to install:

1. Pip install:

   ```bash
   pip install spellbookfs
   ```

## Configuration

To connect to Snowflake and MySQL, you'll need to provide the necessary connection credentials. Spellbook reads configurations from a `.env` file in the project root directory. Create a `.env` file with the following structure:

```plaintext
# Snowflake Configuration in your bash profile
SNOWFLAKE_ACCOUNT=your_snowflake_account
SNOWFLAKE_USER=your_snowflake_user
SNOWFLAKE_PASSWORD=your_snowflake_password
SNOWFLAKE_DATABASE=your_snowflake_database
SNOWFLAKE_SCHEMA=your_snowflake_schema

# MySQL Configuration in your bash profile
MYSQL_HOST=your_mysql_host
MYSQL_USER=your_mysql_user
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=your_mysql_database
```

## Usage

Once configured, you can use Spellbook to connect to and interact with Snowflake and MySQL databases.

### Connecting to Snowflake

```python
from spellbook import db_magic

```

### Connecting to MySQL

```python
from spellbook import db_magic

```

### Running Queries

Use the `execute_query` method to run SQL queries and retrieve results in a convenient format.

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