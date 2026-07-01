# Secrets Manager — Security Checklist

## IAM Permissions (AWS)
- [ ] IAM role/user has `secretsmanager:CreateSecret`
- [ ] IAM role/user has `secretsmanager:GetSecretValue`
- [ ] IAM role/user has `secretsmanager:PutSecretValue`
- [ ] IAM role/user has `secretsmanager:DeleteSecret`
- [ ] IAM role/user has `secretsmanager:DescribeSecret`
- [ ] IAM role/user has `secretsmanager:ListSecrets` (health check only)
- [ ] Resource policy restricts access to application role only
- [ ] No wildcard (`*`) permissions on secrets

## Environment Variables
- [ ] `SECRETS_PROVIDER` set to `aws_secrets_manager` in production
- [ ] `APP_ENV` set to `production`
- [ ] `AWS_REGION` configured correctly
- [ ] `ENABLE_LEGACY_SECRET_FALLBACK` set to `false` after full migration
- [ ] `SECRET_ACCESS_AUDIT_ENABLED` set to `true`
- [ ] `CM_CREDENTIAL_KEY` NOT set in production (not needed for AWS backend)
- [ ] No secret values in environment variables

## Secret Rotation
- [ ] Define rotation schedule (recommended: 90 days for provider credentials)
- [ ] Use `rotate_provider_credentials()` API for rotation
- [ ] After rotation, verify provider connection still works
- [ ] Monitor audit trail for rotation events
- [ ] Document emergency rotation procedure

## Incident Response
- [ ] If secret leaked: immediately rotate via `rotate_provider_credentials()`
- [ ] Check audit trail: `secret_access_audit` collection for unauthorized reads
- [ ] Review application logs for legacy fallback warnings (indicates unprotected access)
- [ ] If AWS credentials compromised: rotate IAM keys, rotate all secrets
- [ ] Contact provider (Exely/HotelRunner) if their API credentials were exposed

## API Security
- [ ] No credential values in API responses (verified by tests)
- [ ] `credentials_ref` field is opaque reference, not a secret
- [ ] Connection status endpoints exclude all sensitive fields
- [ ] Masking applied where field names must be shown

## Monitoring
- [ ] Alert on `result=failure` in audit trail
- [ ] Alert on legacy fallback usage after migration
- [ ] Monitor AWS Secrets Manager API call costs
- [ ] Review audit trail monthly for anomalous access patterns
- [ ] `GET /api/health/deep` includes secrets manager health
