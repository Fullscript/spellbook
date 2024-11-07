class gsheets_handler:
    """
  :param gsheet_url: url of the target GSheet workbook
  :param authorization_service_file: json authorization file (i.e.: '/Users/your_name/Desktop/pythonconnection_credentials.json')
  """
    os = __import__('os')
    pd = __import__('pandas')
    pygsheets = __import__('pygsheets')
    base64 = __import__('base64')

    # in this function we initialize all of the variables that are accessible to the rest of the function
    def __init__(self, gsheet_url):
        try:
            with open("credentials.json", "w") as credential_file:
                print(self.base64.b64decode(self.os.environ['GS_SERVICE_ACCOUNT']).decode(), file=credential_file)

            # Use the json file to authenticate on google sheets
            self._gc = self.pygsheets.authorize(service_file="credentials.json")
            self.os.remove("credentials.json")
        except:
            print('Could not load GS_SERVICE_ACCOUNT')
        self._gsheet_url = gsheet_url
        self._df_results = self.pd.DataFrame


        # open the google spreadsheet using the URL
        self._sh = self._gc.open_by_url(self._gsheet_url)

    def delete_sheet(self, worksheet):
        """
        Deletes the specified worksheet in the google document
        :param worksheet: sheet name or sheet index number
        """
        try:
            if str(worksheet).isdigit():
                # delete found sheet
                self._sh.del_worksheet(self._sh[worksheet])
                print('Tab deleted')
            else:
                # delete found sheet
                self._sh.del_worksheet(self._sh.worksheet_by_title(worksheet))
                print('Tab deleted')
        except self.pygsheets.WorksheetNotFound as error:
            print(f'Error while deleting sheet {error}')

    def create_sheet(self, worksheet):
        """
        Creates a sheet with the name passed in as a parameter
        :param worksheet: name of the sheet to create
        """
        try:
            self._sh.add_worksheet(str(worksheet))
        except self.pygsheets.WorksheetNotFound as error:
            print(f'Error while deleting sheet {error}')

    def get_sheet(self, worksheet):
        """
        Gets the specified sheet object
        :param worksheet: name of the worksheet to get
        """
        try:
            if str(worksheet).isdigit():
                return self._sh[worksheet]
            else:
                return self._sh.worksheet_by_title(worksheet)
        except self.pygsheets.WorksheetNotFound as error:
            print(f'Sheet does not exist')

    def count_rows(self, worksheet, target_column = 1, include_tailing_empty = False):
        """
        Counts the number rows in  the specified target column
        :param worksheet: name of the worksheet to read from
        :param target_column: target column number
        :param include_tailing_empty: if one wants to include (count) the empty cells tailing the data cells
        """
        # select the right sheet
        wks = self.get_sheet(worksheet)

        # get all values in the worksheet
        return len(wks.get_col(col=target_column,
                               returnas='matrix',
                               include_tailing_empty=include_tailing_empty))

    def clear_range(self, worksheet, clear_range_str = None):
        """
        Clears the specified worksheet
        :params worksheet: name of the worksheet to clear
        :param clear_range_str: To be used with clear_ws. Range that will be cleared. If '', the whole worksheet will be cleared.
        """
        # select the right sheet
        wks = self.get_sheet(worksheet)

        if clear_range_str:
            # clear specific range
            clear_range = clear_range_str.split(':')
            wks.clear(clear_range[0], clear_range[1])
        else:
            # clear the whole worksheet
            wks.clear()

    def write_to_sheet(self, input_dataframe, worksheet, starting_pos = 'A1', extend = True, fit = False, nan = '',
                       clear_ws = True,
                       clear_range_str = None):
        """
        Writes a pandas dataframe to a specified sheet, if the sheet does not exist, one will be created
        :param input_dataframe: Target dataframe to be written in the spreadsheet
        :param worksheet: worksheet to write to
        :param starting_pos: Target position to start writing the dataframe (format A1)
        :param extend: Add columns and rows to the worksheet if necessary, but won’t delete any rows or columns.
        :param fit: Resize the worksheet to fit all data inside if necessary. (Obs. Fit and Extend can't be True
              at the same time)
        :param nan: Value with which NaN values are replaced.
        :param clear_ws: Flag to clear worksheet before writing the dataframe
        :param clear_range_str: To be used with clear_ws. Range that will be cleared. If '', the whole worksheet
              will be cleared.
        """

        # fit and extend cannot be true at the same time
        if fit:
            extend = False

        # select the right sheet - if the sheet doesn't exist, creates one with worksheet_no_or_name as title
        wks = self.get_sheet(worksheet)
        if wks:
            pass
        else:
            print('creating new sheet')
            self.create_sheet(worksheet)
            wks = self.get_sheet(worksheet)

        # Clear the entire sheet
        if clear_ws:
            self.clear_range(worksheet=worksheet, clear_range_str=clear_range_str)

        # write dataframe
        wks.set_dataframe(df=input_dataframe, start=starting_pos, extend=extend, fit=fit, nan=nan)
        print('Write to sheet completed')

    def read_sheet(self, worksheet, target_range_str = None):
        """
        reads the specified worksheet and returns a pandas dataframe
        :param worksheet: name of the worksheet to read
        :param target_range: target range to be read, '' will read all available data in the target worksheet
        """

        # select the right sheet
        wks = self.get_sheet(worksheet)

        # get all values in the worksheet
        if target_range_str:
            target_range = target_range_str.split(':')
            return wks.get_as_df(start=target_range[0], end=target_range[1])
        else:
            return wks.get_as_df()
