# AWS Secrets Manager Provider

InfraFoundry can integrate with AWS Secrets Manager to retrieve and store secrets.

## Prerequisites

1.  **AWS Credentials**: The environment must be configured with AWS credentials.
    *   Standard AWS environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, etc.)
    *   Or `~/.aws/credentials` file.
    *   Or IAM Role if running on EC2/Lambda.
2.  **Permissions**: The IAM identity needs permissions for:
    *   `secretsmanager:GetSecretValue`
    *   `secretsmanager:PutSecretValue`
    *   `secretsmanager:CreateSecret` (if creating new secrets)

## Configuration

Inject the `AWSSecretsManagerProvider` into the `SecretManager`.

### Programmatic Usage

```python
from infrafoundry.core.secrets import SecretManager
from infrafoundry.core.secrets.providers.aws import AWSSecretsManagerProvider

# Initialize provider (uses default boto3 resolution or explicit params)
provider = AWSSecretsManagerProvider(region_name="us-east-1", profile_name="default")

manager = SecretManager(env_name="dev", provider=provider)

# Load a secret
# Maps to an AWS Secret named "prod/db/password"
secret = manager.decrypt_file("prod/db/password")
print(secret["password"])
```

### Data Mapping

*   **JSON Secrets**: AWS Secrets Manager secrets stored as JSON strings are parsed and returned as a dictionary.
*   **Plain String Secrets**: If a secret is a plain string (not JSON), it is returned as `{"value": "the-secret-string"}`.
*   **Binary Secrets**: Currently not supported.

## Saving Secrets

When saving secrets:
1.  The dictionary data is converted to a JSON string.
2.  `put_secret_value` is called to update existing secrets.
3.  If the secret does not exist, `create_secret` is called.

## Troubleshooting

*   **"ResourceNotFoundException"**: The secret name provided does not exist in the specified region.
*   **Auth Errors**: Verify AWS credentials and region are correctly configured.
