#!/usr/bin/env python3
"""
Generate a production .env file with strong random secrets.

SECURITY RULES:
- Generated secret values are NEVER printed to stdout.
- The output file is created with mode 0600 (owner read/write only).
- If the target file already exists the script refuses to overwrite it
  to prevent accidentally replacing a live production key.
"""
import subprocess
import os
import sys

target = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')

if os.path.exists(target):
    print(f"ERROR: {target} already exists. Delete it manually if you intend to regenerate secrets.", file=sys.stderr)
    sys.exit(1)

j = subprocess.check_output(['openssl', 'rand', '-base64', '48']).decode().strip()
c = subprocess.check_output(['openssl', 'rand', '-base64', '32']).decode().strip()
m = subprocess.check_output(['openssl', 'rand', '-base64', '32']).decode().strip()

content = f"""DB_NAME=syroce_production
JWT_SECRET={j}
CORS_ORIGINS=https://api.syroce.com
APP_ENV=production
SECRETS_PROVIDER=env
STRICT_TENANT_MODE=true
SECRET_ACCESS_AUDIT_ENABLED=true
CM_CREDENTIAL_KEY={c}
CM_MASTER_KEY_CURRENT={m}
CM_KEY_VERSION=v1
MESSAGING_MODE=sandbox
"""

# Write with a restrictive mode from the start (not world-readable even briefly)
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write(content)

# Double-check permissions (defense-in-depth; the O_EXCL open above already set them)
os.chmod(target, 0o600)

print(f"DONE! .env dosyasi olusturuldu: {target}")
print("Secrets generated successfully; values are not displayed for security.")
print("Store the generated file securely — it contains production credentials.")

