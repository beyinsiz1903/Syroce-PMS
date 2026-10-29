#!/bin/bash
# Post-install script for CI/CD
# Validates the security-fixed LiteLLM/OpenAI pair installed from
# requirements/integrations.txt.  Installing LiteLLM with --no-deps used to
# leave it next to OpenAI 1.x, which is incompatible at import time.

set -e

echo "Verifying..."
python3 -c "
import litellm, openai, pydantic_settings, msgpack, pymongo, dns, tornado
from importlib.metadata import version
from packaging.version import Version

assert Version(version('litellm')) == Version('1.100.4')
assert Version(openai.__version__) >= Version('2.20.0')
assert Version(version('msgpack')) >= Version('1.2.3')
assert Version(pymongo.version) >= Version('4.18.3')
assert Version(version('dnspython')) >= Version('2.9.0')
assert Version(tornado.version) >= Version('6.6.0')
print(f'litellm: OK')
print(f'openai: {openai.__version__}')
print('pydantic-settings: OK')
print('msgpack: OK')
print('pymongo/dnspython: OK')
print('tornado: OK')
print('All imports OK')
"

echo "Post-install complete."
