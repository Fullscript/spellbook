# Spellbook

Spellbook is the ultimate tool to power ad-hoc analyses and support all your data and analytics needs at Fullscript. 
Designed with flexibility and functionality in mind, it’s a one-stop library for data scientists and developers.

With Spellbook, you can:
* Seamlessly connect to multiple databases, including Snowflake and MySQL, for secure querying and effortless data retrieval.
* Work with Google Sheets, making it easy to read, write, and update spreadsheets.
* Manage Google Drive, creating folders and saving files with ease. 
* Perform statistical analyses, helping you run A/B tests and extract actionable insights.

Spellbook is built to simplify your workflows and supercharge your data exploration, so you can focus on turning insights into action!

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
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
pip install spellbookfs
```

## Configuration
Effortlessly and securely manage your connections and configurations! Simply add database types and connection 
credentials to your [spelbook_config.yaml](spellbook_config.yaml) file, or include your Google service account details for seamless access to 
Google services. For added security, Spellbook supports storing credentials in environment variables 
or in a configuration file that references those variables, keeping your sensitive information safe and sound.

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