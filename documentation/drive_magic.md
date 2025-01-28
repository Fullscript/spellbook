## Different Authentication Methods

This package can use 2 different authentication methods:

- Service Account: The same method we currently use in `sheet_magic`
- OAuth: Method where the user has to allow the script to use their credentials

Both methods have their pros and cons:

- Service Account:
  - It's the easiest to use as one probably already has the setup ready.
  - It can only access folders shared with the service account email (similarly as it can only access sheets we share with it)
    - Because we're not managers of the data team's shared folders, we cannot share those folders with this account. This is a road block for now.
- OAuth:
  - The user has to grant access constantly (every time the scope changes or the authentication token expires)
  - This method can access any folder shared with you as the script will be using your identity (this includes shared folders where you're not the owner)

## OAuth Setup

Step-by-step:

  1 - Access this link and follow the [OAuth client ID credentials](https://developers.google.com/workspace/guides/create-credentials#oauth-client-id) process
  
  2 - Probably you'll be asked to setup the OAuth Consent Screen. At the second page of this part ("Scopes"), be sure to add all Google Drive API scopes.

  3 - In the "Client ID for Web Application" page, add `http://localhost:3000/` as an "Authorized redirect URIs"

  4 - From the same page, download the client secret as a JSON file.

  5 - Now the process is similar to what is done for `'GS_SERVICE_ACCOUNT'`. Copy the contents of the JSON file.

  6 - Go to the terminal and use `pbpaste | base64 | pbcopy` to paste, encode, and copy the contents again.

  7 - Store the encoded contents as an envvar called `'GS_CLIENT_SECRETS'`

## Initiate

```python
from spellbook import drive_magic as dm
```

## Usage examples

##### Getting service
```python
scopes = ['https://www.googleapis.com/auth/drive.metadata.readonly',
          'https://www.googleapis.com/auth/drive.file',
          'https://www.googleapis.com/auth/drive.readonly',
          'https://www.googleapis.com/auth/drive',
          'https://www.googleapis.com/auth/drive.file',
          'https://www.googleapis.com/auth/drive.appdata']

# service = dm.get_service(scopes=scopes, auth_type='service_account')
service = dm.get_service(scopes=scopes, auth_type='oauth')
del scopes
```

##### Listing contents of a folder
```python
folder_url = 'https://drive.google.com/drive/u/0/folders/1zgsK7EkEcYsvmiQ0InT04Bg5yBdG6b-D'
df_files = dm.list_folder_contents(service, folder_url)
```

##### Uploading a file
```python
dm.upload_file(service, folder_url, 'samples/01_sample_pdf.pdf')
```

##### Downloading a file
```python
temp_file_id = '1JAYgOUztUNYrx5qJispiEM-B2oXdLQzO'
dm.download_file(service, temp_file_id, '02_sample_picture_v2.jpeg')
```
##### Deleting / thrashing a file
```python
dm.delete_file(service, temp_file_id)
```