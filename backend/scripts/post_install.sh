#!/bin/bash
# Post-install script for CI/CD
# Validates the security-fixed LiteLLM/OpenAI pair installed from
# requirements/integrations.txt.  Installing LiteLLM with --no-deps used to
# leave it next to OpenAI 1.x, which is incompatible at import time.

set -e

echo "Verifying..."
python3 -c "
import litellm, openai, pydantic_settings
from importlib.metadata import version
from packaging.version import Version

assert Version(version('litellm')) >= Version('1.84.10')
assert Version(openai.__version__) >= Version('2.20.0')
print(f'litellm: OK')
print(f'openai: {openai.__version__}')
print('pydantic-settings: OK')
print('All imports OK')
"

echo "Post-install complete."
