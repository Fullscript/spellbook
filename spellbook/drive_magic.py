'''
What this script does:

https://www.thepythoncode.com/article/using-google-drive--api-in-python
https://developers.google.com/drive/api/v3/reference/files
'''

# importing packages
import os
import io
import pandas as pd
import base64
import pickle
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
from google.oauth2 import service_account
from spellbook.utils import load_and_parse_config

'''
Authentication Process
'''


def get_service(scopes, service_account_name, auth_type='service_account', **kwargs):
    """Gets Google Drive service
    Parameters
    ----------
    scopes : list
      List of strings representing the scopes one needs service for.
      Example: ['https://www.googleapis.com/auth/drive.metadata.readonly',
                'https://www.googleapis.com/auth/drive.file']
    auth_type : str
      Authorization type selected. It can be 'service_account' or 'oauth'

    Returns
    -------
    resource
      Google Drive service object
      :param scopes: The scopes needed for the service
      :param service_account_name: The name of the Google Sheets service account to be used for authorization
  """
    try:
        if auth_type == 'service_account':
            # option that uses the credential process we already have for sheets_magic
            # this method requires a folder to be shared with the service account email (as we do with our sheets)

            # Load the configuration
            config = load_and_parse_config(configurations='google_accounts', **kwargs)
            gs_service_account = None

            # Find the Google Sheets service account details in the configuration
            google_accounts = config.get('google_accounts', [])
            for gs_account in google_accounts:
                if gs_account.get('name') == service_account_name:
                    gs_service_account = gs_account.get('service_account')
                    break

            if not gs_service_account:
                raise ValueError(
                    f"Google Sheets service account '{service_account_name}' not found in configuration file.")

            # creates a credentials file using the info in the env var GS_SERVICE_ACCOUNT
            with open('credentials.json', 'w') as credential_file:
                print(base64.b64decode(os.environ['GS_SERVICE_ACCOUNT']).decode(), file=credential_file)

            # uses the file to create the scoped credentials
            credentials = service_account.Credentials.from_service_account_file('credentials.json')
            scoped_credentials = credentials.with_scopes(scopes)
            os.remove('credentials.json')

        elif auth_type == 'oauth':
            # This option will prompt the user to authorize the script to use their identity. This allows the script to read
            # and write to any folder the user has access to.
            # The file token.pickle stores the user's access and refresh tokens. It's automatically created at the first time
            # the user completes the authorization.
            # It's important to notice everytime a new scope is needed, the authorization needs to be run again.

            # initializing scoped_credentials
            scoped_credentials = None

            # if the token.pickle already exists, we can get credentials from it
            if os.path.exists('token.pickle'):
                with open('token.pickle', 'rb') as token:
                    scoped_credentials = pickle.load(token)

            # If the file doesn't exist or is expired, we need to run the authorization flow
            if not scoped_credentials or not scoped_credentials.valid:

                if scoped_credentials and scoped_credentials.expired and scoped_credentials.refresh_token:
                    # refresh the credentials
                    scoped_credentials.refresh(Request())
                else:
                    # run the authorization flow from the client secrets stored as a env var
                    with open('client_secrets.json', 'w') as credential_file:
                        print(base64.b64decode(os.environ['GS_CLIENT_SECRETS']).decode(), file=credential_file)

                    flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', scopes)
                    scoped_credentials = flow.run_local_server(port=3000)

                    os.remove('client_secrets.json')

                # save the credentials for the next run
                with open('token.pickle', 'wb') as token:
                    pickle.dump(scoped_credentials, token)

        # return the built service object.
        return build('drive', 'v3', credentials=scoped_credentials)
    except HttpError as error:
        print(f'An error occurred: {error}')
        return None


'''
Other functions
'''


def list_folder_contents(service, folder_url, max_results=1000, show_trashed=False):
    """Gets files in a specific folder
    Parameters
    ----------
    service : resource
      Google Drive resource object
    folder_url : str
      Folder URL
    max_results : int
      Number of results to be returned
    show_trashed : bool
      Flag whether files in the trash should be returned

    Returns
    -------
    pd.DataFrame
      Dataframe with file data
  """

    # get the folder id
    folder_id = folder_url.rsplit('/', 1)[-1]

    try:
        # get items from GDrive
        results = service.files().list(q=f"'{folder_id}' in parents and trashed = {str(show_trashed).lower()}",
                                       pageSize=max_results, orderBy='name',
                                       includeItemsFromAllDrives=True, supportsAllDrives=True,
                                       fields="nextPageToken, files(id, name, mimeType, size, parents, modifiedTime)").execute()
        items = results.get('files', [])

        # returns as a DF
        df_temp = pd.DataFrame(items)
        df_temp = df_temp.rename({'size': 'size_bytes'}, axis=1)
        return df_temp
    except HttpError as error:
        print(f'An error occurred: {error}')
        return None


def download_file(service, file_id, filepath):
    """Downloads a file from Google Drive
    Parameters
    ----------
    service : resource
      Google Drive resource object
    file_id : str
      ID of the file to be downloaded
    filepath : str
      File path where the downloaded file should be saved. (i.e.: 'samples/test_file.txt')

    Returns
    -------
    bool
      Flag whether the file was successfully downloaded or not
  """

    try:
        # pylint: disable=maybe-no-member
        request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
        file = io.BytesIO()
        downloader = MediaIoBaseDownload(file, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print(F'Download {int(status.progress() * 100)}.')

        with open(filepath, "wb") as f:
            f.write(file.getbuffer())

        return True

    except HttpError as error:
        print(F'An error occurred: {error}')
        return False


def upload_file(service, folder_url, filepath):
    """Gets files in a specific folder
    Parameters
    ----------
    service : resource
      Google Drive resource object
    folder_url : str
      Folder URL
    filepath : str
      Path of the file to be uploaded

    Returns
    -------
    str
      ID of the created file
  """

    # get the folder id
    folder_id = folder_url.rsplit('/', 1)[-1]

    # first, define file metadata, such as the name and the parent folder ID
    filename = os.path.basename(filepath)
    file_metadata = {
        "name": filename,
        "parents": [folder_id]
    }
    # upload
    try:
        media = MediaFileUpload(filepath, resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id',
                                      supportsAllDrives=True).execute()
        print(f'File created! - id: {file.get("id")}')
        return file.get("id")
    except HttpError as error:
        print(f'An error occurred: {error}')
        return None


def delete_file(service, file_id):
    """Permanently deletes a file owned by the user without moving it to the trash. If the file belongs to a shared drive
  the user must be an organizer on the parent. If the target is a folder, all descendants owned by the user are also
  deleted. In case the delete method is unsuccessful, tries to move the file to trash.
    Parameters
    ----------
    service : resource
      Google Drive resource object
    file_id : str
      ID of the file to be deleted

    Returns
    -------
    bool
      Flag whether the file was successfuly deleted or not
  """
    try:
        try:
            # delete method
            service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
            print('File deleted successfully!')
            return True
        except:
            # move to trash method
            body = {'trashed': True}
            service.files().update(fileId=file_id, body=body, supportsAllDrives=True).execute()
            print('Not able to delete the file. Moved to trash instead.')
            return True
    except HttpError as error:
        print(f'An error occurred: {error}')
        return False
