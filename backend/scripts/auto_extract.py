"""
Automated Domain Router Extraction Tool
Usage: python3 scripts/auto_extract.py <output_router_path> <tag> <prefix1> [prefix2] ...

Example:
  python3 scripts/auto_extract.py domains/ai/router.py "AI / ML" ai ai-concierge ml predictions
"""
import re
import sys
import os

LEGACY_PATH = "/app/backend/legacy_routes.py"

STANDARD_IMPORTS = '''"""
{docstring}
Extracted from legacy_routes.py — Phase B Domain Separation
"""
from fastapi import APIRouter, HTTPException, Depends, status, Body, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import ORJSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta, date
import os
import uuid
import random
import logging
import io

from core.database import db
from core.security import (
    get_current_user, security, JWT_SECRET, JWT_ALGORITHM,
    generate_qr_code, generate_time_based_qr_token,
)
from core.helpers import (
    create_audit_log, require_feature, require_module,
    require_super_admin_guard as require_super_admin, require_admin,
    get_tenant_modules, load_tenant_doc,
)
from models.schemas import User
from models.enums import UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["{tag}"])

'''


def read_lines():
    return open(LEGACY_PATH).readlines()


def find_endpoints(lines):
    eps = []
    for i, line in enumerate(lines):
        m = re.match(r'@api_router\.(get|post|put|delete|patch)\(["\'](.+?)["\']', line.strip())
        if m:
            eps.append((i, m.group(1).upper(), m.group(2)))
    return eps


def find_function_end(lines, start_idx):
    total = len(lines)
    i = start_idx + 1
    while i < total and lines[i].strip().startswith('@'):
        i += 1
    if i < total and (lines[i].strip().startswith('def ') or lines[i].strip().startswith('async def ')):
        i += 1
    while i < total:
        stripped = lines[i].strip()
        if stripped.startswith('@api_router.'):
            return i - 1
        if stripped and not stripped.startswith('#') and not lines[i][0] in ' \t\n':
            if (stripped.startswith('def ') or stripped.startswith('async def ') or
                stripped.startswith('class ') or stripped.startswith('# ===')):
                return i - 1
        i += 1
    return total - 1


def extract_batch(prefixes):
    lines = read_lines()
    eps = find_endpoints(lines)
    
    # Find matching endpoints
    to_extract = []  # (decorator_start, function_end, method, path)
    for idx, method, path in eps:
        first_seg = path.strip('/').split('/')[0]
        if first_seg in prefixes:
            end = find_function_end(lines, idx)
            to_extract.append((idx, end, method, path))
    
    if not to_extract:
        print("No matching endpoints found!")
        return None, set()
    
    # Build code blocks - extract each endpoint with any preceding comment
    code_blocks = []
    lines_to_remove = set()
    
    for dec_start, func_end, method, path in to_extract:
        # Look for preceding comments (section headers, endpoint comments)
        comment_start = dec_start
        while comment_start > 0:
            prev = lines[comment_start - 1].strip()
            if prev.startswith('#') or prev == '':
                comment_start -= 1
            else:
                break
        # Don't go past another endpoint's body
        comment_start = max(comment_start, 0)
        
        # Get the code block from decorator to function end
        block = ''.join(lines[dec_start:func_end + 1])
        # Replace api_router with router
        block = block.replace('@api_router.', '@router.')
        code_blocks.append(block)
        
        # Mark lines for removal (decorator to function end, plus trailing blanks)
        for j in range(dec_start, func_end + 1):
            lines_to_remove.add(j)
    
    # Also remove section header comments that precede extracted blocks
    # and are now orphaned
    sorted_ranges = sorted(to_extract, key=lambda x: x[0])
    for dec_start, func_end, _, _ in sorted_ranges:
        s = dec_start - 1
        while s >= 0 and (lines[s].strip().startswith('#') or lines[s].strip() == ''):
            # Only remove comments/blanks that are immediately before
            if lines[s].strip().startswith('# ==='):
                lines_to_remove.add(s)
            elif lines[s].strip() == '':
                lines_to_remove.add(s)
            elif lines[s].strip().startswith('#'):
                lines_to_remove.add(s)
            s -= 1
    
    return code_blocks, lines_to_remove


def remove_from_legacy(lines_to_remove):
    lines = read_lines()
    new_lines = []
    for i, line in enumerate(lines):
        if i not in lines_to_remove:
            new_lines.append(line)
    
    # Clean up excessive blank lines
    final_lines = []
    blank_count = 0
    for line in new_lines:
        if line.strip() == '':
            blank_count += 1
            if blank_count <= 2:
                final_lines.append(line)
        else:
            blank_count = 0
            final_lines.append(line)
    
    with open(LEGACY_PATH, 'w') as f:
        f.writelines(final_lines)
    
    return len(lines), len(final_lines)


def main():
    if len(sys.argv) < 4:
        print("Usage: python3 scripts/auto_extract.py <output_path> <tag> <prefix1> [prefix2] ...")
        sys.exit(1)
    
    output_path = os.path.join("/app/backend", sys.argv[1])
    tag = sys.argv[2]
    prefixes = sys.argv[3:]
    
    print(f"Extracting: prefixes={prefixes}")
    print(f"Output: {output_path}")
    print(f"Tag: {tag}")
    
    code_blocks, lines_to_remove = extract_batch(prefixes)
    
    if not code_blocks:
        sys.exit(1)
    
    # Create directory if needed
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Check if file exists - if so, append
    if os.path.exists(output_path):
        print(f"  File exists, appending {len(code_blocks)} endpoints")
        with open(output_path, 'a') as f:
            f.write('\n\n')
            f.write('\n\n'.join(code_blocks))
    else:
        # Generate docstring
        docstring = f"{tag} Domain Router"
        
        header = STANDARD_IMPORTS.format(docstring=docstring, tag=tag)
        
        with open(output_path, 'w') as f:
            f.write(header)
            f.write('\n\n'.join(code_blocks))
            f.write('\n')
    
    print(f"  Wrote {len(code_blocks)} endpoints to {output_path}")
    
    # Remove from legacy
    before, after = remove_from_legacy(lines_to_remove)
    
    print(f"  Legacy: {before} -> {after} lines ({before - after} removed)")
    
    # Verify no endpoint was lost
    lines = read_lines()
    remaining = find_endpoints(lines)
    print(f"  Remaining legacy endpoints: {len(remaining)}")


if __name__ == "__main__":
    main()
