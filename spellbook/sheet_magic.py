import os
import pandas as pd
import pygsheets
import base64
from spellbook.utils import load_and_parse_config


class GSheetsHandler:
    """
    :param gsheet_url: The URL of the target Google Sheet workbook
    :param service_account_name: The name of the Google Sheets service account to be used for authorization
    """

    def __init__(self, gsheet_url, service_account_name):
        self._gsheet_url = gsheet_url
        self._service_account_name = service_account_name
        if os.path.isfile('spellbook_config.yaml'): 
            self._config_file = 'spellbook_config.yaml'
        else: 
            self._config_file = os.path.expanduser('~')+'/'+'spellbook_config.yaml'
        self._df_results = pd.DataFrame()
        self._gc = None
        self._sh = None

        # Initialize Google Sheets authorization
        self._authorize_google_sheets()

        # Open the Google Spreadsheet using the URL
        if self._gc:
            self._sh = self._gc.open_by_url(self._gsheet_url)

    def _authorize_google_sheets(self):
        """
        Private method to handle Google Sheets authorization using credentials from the configuration file.
        Loads the service account credentials, decodes them, and uses them for authorization.
        """
        try:
            # Load the configuration
            config = load_and_parse_config(config_file_path=self._config_file, configurations='google_accounts')
            gs_service_account = None

            # Find the Google Sheets service account details in the configuration
            google_accounts = config.get('google_accounts', [])
            for gs_account in google_accounts:
                if gs_account.get('name') == self._service_account_name:
                    gs_service_account = gs_account.get('service_account')
                    break

            if not gs_service_account:
                raise ValueError(f"Google Sheets service account '{self._service_account_name}' not found in configuration file.")

            # Decode and write credentials from configuration to a temporary file
            with open("credentials.json", "w") as credential_file:
                print(base64.b64decode(gs_service_account).decode(), file=credential_file)

            # Use the JSON file to authenticate on Google Sheets
            self._gc = pygsheets.authorize(service_file="credentials.json")
            os.remove("credentials.json")
        except FileNotFoundError:
            print("Config file not found. Please ensure 'spelbook_config.yaml' exists.")
        except ValueError as e:
            print(f'Error: {e}')
        except Exception as e:
            print(f'Could not load Google Sheets service account. Error: {e}')


    def delete_sheet(self, worksheet):
        """
        Deletes the specified worksheet from the Google Sheet.
        If the worksheet does not exist, an error message is printed.
        :param worksheet: The name or index of the worksheet to be deleted
        """
        try:
            if str(worksheet).isdigit():
                # Delete sheet by index
                self._sh.del_worksheet(self._sh[int(worksheet)])
            else:
                # Delete sheet by title
                self._sh.del_worksheet(self._sh.worksheet_by_title(worksheet))
            print('Tab deleted')
        except pygsheets.WorksheetNotFound as error:
            print(f'Error while deleting sheet: {error}')

    def create_sheet(self, worksheet):
        """
        Creates a new worksheet in the Google Sheet with the specified name.
        If a worksheet with the given name already exists, it will not create a duplicate.
        :param worksheet: The name of the new worksheet to create
        """
        try:
            self._sh.add_worksheet(str(worksheet))
        except Exception as error:
            print(f'Error while creating sheet: {error}')

    def get_sheet(self, worksheet):
        """
        Retrieves the specified worksheet object from the Google Sheet.
        The worksheet can be accessed either by its name or its index.
        If the worksheet does not exist, an error message is printed.
        :param worksheet: The name or index of the worksheet to retrieve
        :return: The worksheet object or None if not found
        """
        try:
            if str(worksheet).isdigit():
                return self._sh[int(worksheet)]
            else:
                return self._sh.worksheet_by_title(worksheet)
        except pygsheets.WorksheetNotFound:
            print(f'Sheet does not exist')
            return None

    def count_rows(self, worksheet, target_column=1, include_tailing_empty=False):
        """
        Counts the number of rows in the specified target column of a worksheet.
        :param worksheet: The name of the worksheet to read from
        :param target_column: The column number to count rows in
        :param include_tailing_empty: Whether to include empty trailing cells in the count
        :return: The count of rows in the specified column
        """
        wks = self.get_sheet(worksheet)
        if wks:
            return len(wks.get_col(col=target_column, returnas='matrix', include_tailing_empty=include_tailing_empty))
        return 0

    def clear_range(self, worksheet, clear_range_str=None):
        """
        Clears the specified range or the entire worksheet in the Google Sheet.
        :param worksheet: The name of the worksheet to clear
        :param clear_range_str: The range to be cleared (e.g., 'A1:B2'). If None, the entire worksheet will be cleared
        """
        wks = self.get_sheet(worksheet)
        if wks:
            if clear_range_str:
                clear_range = clear_range_str.split(':')
                wks.clear(clear_range[0], clear_range[1])
            else:
                wks.clear()

    def write_to_sheet(self, input_dataframe, worksheet, starting_pos='A1', extend=True, fit=False, nan='', clear_ws=True, clear_range_str=None):
        """
        Writes a pandas DataFrame to the specified worksheet in the Google Sheet.
        If the worksheet does not exist, it will be created.
        Optionally clears the worksheet or a specific range before writing.
        :param input_dataframe: The pandas DataFrame to be written to the worksheet
        :param worksheet: The worksheet to write to
        :param starting_pos: The starting cell position to write the DataFrame (e.g., 'A1')
        :param extend: Whether to extend the worksheet to fit the DataFrame if necessary
        :param fit: Whether to resize the worksheet to fit the entire DataFrame
        :param nan: The value to replace NaN entries with
        :param clear_ws: Whether to clear the worksheet before writing the DataFrame
        :param clear_range_str: The range to be cleared before writing if clear_ws is True
        """
        wks = self.get_sheet(worksheet)
        if not wks:
            print('Creating new sheet')
            self.create_sheet(worksheet)
            wks = self.get_sheet(worksheet)

        if clear_ws and wks:
            self.clear_range(worksheet=worksheet, clear_range_str=clear_range_str)

        if wks:
            wks.set_dataframe(df=input_dataframe, start=starting_pos, extend=extend, fit=fit, nan=nan)
            print('Write to sheet completed')

    def read_sheet(self, worksheet, target_range_str=None):
        """
        Reads data from the specified worksheet and returns it as a pandas DataFrame.
        If the target range is provided, only that specific range is read.
        :param worksheet: The name of the worksheet to read from
        :param target_range_str: The target range to read from (e.g., 'A1:B2'). If None, the entire worksheet will be read
        :return: A pandas DataFrame containing the data from the specified range or worksheet
        """
        wks = self.get_sheet(worksheet)
        if wks:
            if target_range_str:
                target_range = target_range_str.split(':')
                return wks.get_as_df(start=target_range[0], end=target_range[1])
            else:
                return wks.get_as_df()
        return pd.DataFrame()
