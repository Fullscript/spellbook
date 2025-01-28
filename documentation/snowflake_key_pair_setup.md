A step-by-step guide to establishing a connection to Snowflake using Snowpark for Python with key-pair authentication.

### 1. Generate Key Pair:
* **Private Key**: Create an unencrypted private key using OpenSSL:
```bash
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out rsa_key.p8 -nocrypt
```
> Note: If you want a passphrase for additional security, remove the `-nocrypt` flag.

* **Public Key**: Derive the public key from the private key:
```bash
openssl rsa -in rsa_key.p8 -pubout -out rsa_key.pub
```

### 2. Assign Public Key to Snowflake User (will require admin access):
* In Snowflake, associate the generated public key with your user account:
```sql
ALTER USER <username> SET rsa_public_key='<contents_of_rsa_key.pub>';
```

* Replace `<username>` with your actual Snowflake username and `<contents_of_rsa_key.pub>` with the content of your public key file.


### 3. Base64 Encode the Private Key:
Since private keys are typically multi-line strings, encoding them in Base64 ensures they can be stored as single-line environment variables.
```bash
openssl base64 -in rsa_key.p8 -out rsa_key_base64.txt
```
This command reads your rsa_key.p8 file and outputs a Base64-encoded version to rsa_key_base64.txt.

### 4. Set the Environment Variable:
Once you have the Base64-encoded key, set it as an environment variable.
```bash
export PRIVATE_KEY_BASE64='your_base64_encoded_key_here'
```