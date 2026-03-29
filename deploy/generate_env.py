#!/usr/bin/env python3
import subprocess, os, sys

target = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')

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

with open(target, 'w') as f:
    f.write(content)

print(f"DONE! .env dosyasi olusturuldu: {target}")
print("---")
print(content)
