### Key Features

1. **Sheet Management**:
  * Create, delete, or clear sheets with ease.
  * Access sheets by name or index.
2. **Data Handling**:
  * Read and write Pandas DataFrames.
  * Target specific ranges or clear entire sheets.
3. **Flexibility**:
  * Automatically create sheets if they don’t exist.
  * Handle trailing empty cells in row counting.
4. **Seamless Google Sheets Integration**:
  * Authenticate with Google Service Account credentials.
  * Perform operations with minimal setup.

# Setup

## Create a Google Service account
To use this feature, you must create a Google service account. Instructions on how to do this are available on the Google [IAM documentation](https://cloud.google.com/iam/docs/service-accounts-create#iam-service-accounts-create-console)

## Saving Your `GS_SERVICE_ACCOUNT` Environment Variable
How to save your 'GS_SERVICE_ACCOUNT' env-var to use this code

To use Google Service Account functionality with this code, you need to save your Google Service Account JSON as an encrypted string in an environment variable. Follow these steps:
1.Convert the JSON File Content to a Base64-Encoded String
  * Copy the content of your service account JSON file to your clipboard.
  * Open your terminal and run the following command to encode it:
  ```bash
   pbpaste | base64 | pbcopy
  ```
  * This command encrypts the JSON content using Base64 and places the encoded string back into your clipboard.
 
2.Save the Encoded String as an Environment Variable
  * Add the encoded string as an environment variable.
  * Use a name like GS_SERVICE_ACCOUNT for consistency.

For example, add the following line to your environment file (e.g., .env):
```bash
GS_SERVICE_ACCOUNT=your_base64_encoded_string
```
3.Why Base64 Encoding?
  * Base64 ensures the JSON content is securely represented as a single string, making it compatible with environment variables.

Once set up, your code will securely retrieve the service account details directly from the environment variable.

## Initialize

To begin using sheet_magic, initialize the handler with the URL of the Google Sheet you want to work with.

```python
from spellbook import sheet_magic

# Replace with your actual Google Sheet URL
sheet_url = 'https://docs.google.com/spreadsheets/d/your_sheet_id/edit'
working_sheet = sheet_magic.GSheetsHandler(gsheet_url=sheet_url, service_account_name='my_google_service_account')
```

<div style="border-left: 6px solid #f39c12; padding: 10px; background-color: #fcf8e3;">

⚠️ **Important Notice:** In order to use sheet_magic, you need to add the Google service account to the sheet you are working on

</div>

### Usage Examples

1. Create a New Sheet

Add a new sheet to your Google Sheets document.
```python
# Create a new sheet named 'test_sheet'
working_sheet.create_sheet(worksheet='test_sheet')
```

2. Delete an Existing Sheet

Delete a sheet by its name or index.
```python
# Delete a sheet by its name
working_sheet.delete_sheet(worksheet='test_sheet')

# Delete a sheet by its index
working_sheet.delete_sheet(worksheet=1)
```

3. Write Data to a Sheet

Write a Pandas DataFrame to a specified sheet. You can specify a starting position, and the sheet will be resized or extended as needed.

```python
import pandas as pd

# Sample DataFrame
data = {'Name': ['Alice', 'Bob'], 'Age': [25, 30]}
df_test = pd.DataFrame(data)

# Write DataFrame to a sheet by name
working_sheet.write_to_sheet(input_dataframe=df_test, worksheet='data_sheet')

# Write DataFrame to a sheet by index
working_sheet.write_to_sheet(input_dataframe=df_test, worksheet=2)
```

4. Count Rows in a Sheet

Count the number of rows in a specified column, with an option to include trailing empty cells.
```python
# Count rows in column 1 of the sheet 'data_sheet'
row_count = working_sheet.count_rows(worksheet='data_sheet')

# Count rows, including empty trailing cells
row_count_with_empty = working_sheet.count_rows(worksheet='data_sheet', include_tailing_empty=True)

print(f"Rows in column 1: {row_count}")
```

5. Clear a Range

Clear the contents of a specific range or the entire sheet.
```python
# Clear the entire sheet
working_sheet.clear_range(worksheet='data_sheet')

# Clear a specific range (e.g., B2:D4)
working_sheet.clear_range(worksheet='data_sheet', clear_range_str='B2:D4')
```

6. Read Data from a Sheet

Read data from a sheet into a Pandas DataFrame. Optionally, specify a target range.
```python
# Read all data from the sheet 'data_sheet'
df_read = working_sheet.read_sheet(worksheet='data_sheet')

# Read a specific range (e.g., B1:C4) from the sheet
df_read_partial = working_sheet.read_sheet(worksheet='data_sheet', target_range_str='B1:C4')

print(df_read.head())
```
