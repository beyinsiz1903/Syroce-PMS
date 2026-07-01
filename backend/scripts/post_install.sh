#!/bin/bash
# Post-install script for CI/CD
# Fixes litellm CVE-2026-49468 (auth bypass) plus the earlier CVE-2026-35029 /
# CVE-2026-35030, without breaking emergentintegrations.
# emergentintegrations==0.1.0 requires openai==1.99.9
# litellm>=1.83.0 requires openai>=2.30.0 (conflict)
# Solution: install litellm with --no-deps to avoid pulling incompatible openai version

set -e

echo "Installing litellm CVE fix (--no-deps)..."
python -m pip install "litellm>=1.84.0" --no-deps --quiet

echo "Verifying..."
python3 -c "
import litellm, openai
print(f'litellm: OK')
print(f'openai: {openai.__version__}')
print('All imports OK')
"

echo "Post-install complete."
