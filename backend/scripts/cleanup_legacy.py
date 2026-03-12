"""
Cleanup Script: Remove duplicate endpoints and auth shadows from legacy_routes.py.
Run from /app/backend: python3 scripts/cleanup_legacy.py
"""
import re

INPUT = "legacy_routes.py"
OUTPUT = "legacy_routes.py"  # overwrite in place

lines = open(INPUT).readlines()
total = len(lines)

# ── 1. Find all endpoint decorator positions (0-indexed) ──
endpoints = []
for i, line in enumerate(lines):
    m = re.match(r'@api_router\.(get|post|put|delete|patch)\(', line.strip())
    if m:
        endpoints.append(i)

def find_function_end(start_idx):
    """Given the decorator start line (0-indexed), find the last line of the function body."""
    i = start_idx + 1
    # Skip additional decorators
    while i < total and lines[i].strip().startswith('@'):
        i += 1
    # Skip the def/async def line
    if i < total and (lines[i].strip().startswith('def ') or lines[i].strip().startswith('async def ')):
        i += 1
    # Now find end of function body
    while i < total:
        stripped = lines[i].strip()
        if stripped.startswith('@api_router.'):
            return i - 1
        if stripped and not stripped.startswith('#') and lines[i][0] not in ' \t\n':
            if (stripped.startswith('def ') or stripped.startswith('async def ') or 
                stripped.startswith('class ') or stripped.startswith('# ===')): 
                return i - 1
        i += 1
    return total - 1

# ── 2. Lines to remove (0-indexed) ──
lines_to_remove = set()

# 2a. Cross-file duplicate endpoints (exist in domain routers already)
dupe_start_lines_1indexed = [
    19167, 19111,  # approvals (in analytics_router)
    18286, 18251, 18204,  # dashboard gm (in pos_router / analytics_router)
    20808,  # gm/team-performance (in analytics_router)
    3145, 3154,  # guest notification prefs (in experience_router)
    3742, 3735,  # marketplace products (in marketplace_router)
    6894, 6911,  # messaging templates 1st (in enterprise_live)
    17704, 17749,  # messaging templates 2nd (in enterprise_live)
    1428, 1459, 7516,  # multi-property dashboard (in enterprise_router)
    7484,  # multi-property properties (in enterprise_router)
    7202,  # pos daily-summary (in pos_router)
    17879,  # pos menu-items (in pos_router)
    7160,  # pos transactions (in pos_router)
    7671,  # multi-property transfer (in platform_scaling)
    24214,  # analytics/occupancy-trend intra-dup
    21903,  # rates/packages intra-dup
]

for start_1idx in dupe_start_lines_1indexed:
    start_0idx = start_1idx - 1
    if start_0idx in endpoints:
        end_0idx = find_function_end(start_0idx)
        # Include leading blank lines
        s = start_0idx
        while s > 0 and lines[s-1].strip() == '':
            s -= 1
        s += 1  # keep at least one blank line
        for j in range(s, end_0idx + 1):
            lines_to_remove.add(j)

# 2b. Auth shadow functions to remove (these are reimplemented from core/security & core/helpers)
# We'll remove specific line ranges for shadow functions
# First identify them by searching for their definition lines

shadow_ranges = []  # list of (start_0idx, end_0idx) tuples

def find_function_block(start_0idx):
    """Find the block of a top-level function definition starting at start_0idx."""
    i = start_0idx + 1
    while i < total:
        stripped = lines[i].strip()
        # Another top-level definition
        if stripped and lines[i][0] not in ' \t\n':
            if (stripped.startswith('def ') or stripped.startswith('async def ') or 
                stripped.startswith('class ') or stripped.startswith('@') or
                stripped.startswith('# ===') or stripped.startswith('MODULE_DEFAULTS') or
                stripped.startswith('FEATURES_BY_PLAN')):
                return i - 1
        i += 1
    return total - 1

# Find shadow functions by their start lines
shadow_definitions = {
    429: "hash_password",  # def hash_password
    434: "verify_password",  # def verify_password
    442: "create_excel_workbook",  # def create_excel_workbook
    485: "require_feature",  # def require_feature
    513: "require_super_admin",  # def require_super_admin
    527: "apply_row_colors",  # def apply_row_colors
    557: "excel_response",  # def excel_response
    570: "create_token",  # def create_token
    578: "get_current_user",  # async def get_current_user
    609: "_is_super_admin",  # def _is_super_admin
    616: "generate_qr_code",  # def generate_qr_code
    628: "generate_time_based_qr_token",  # def generate_time_based_qr_token
    639: "MODULE_DEFAULTS",  # MODULE_DEFAULTS dict
    685: "get_tenant_modules",  # def get_tenant_modules
    715: "require_module",  # def require_module
    762: "require_admin",  # async def require_admin
}

# Verify and collect shadow ranges
for line_1idx, name in shadow_definitions.items():
    line_0idx = line_1idx - 1
    if line_0idx < total:
        line_content = lines[line_0idx].strip()
        # Verify it matches
        if name in line_content or (name == "MODULE_DEFAULTS" and "MODULE_DEFAULTS" in line_content):
            end_0idx = find_function_block(line_0idx)
            shadow_ranges.append((line_0idx, end_0idx, name))
        else:
            print(f"  WARNING: Expected '{name}' at line {line_1idx}, found: {line_content[:60]}")

# Also remove the header comment lines for these sections
# "# ============= HELPER FUNCTIONS =============" at line 429
# "# ============= EXCEL EXPORT UTILITY FUNCTIONS =============" at line 440  
# "# ============= TENANT MODULE & ADMIN HELPERS =============" at line 637

for sr_start, sr_end, sr_name in shadow_ranges:
    # Include leading blank/comment lines that are section headers
    s = sr_start
    while s > 0 and (lines[s-1].strip() == '' or lines[s-1].strip().startswith('# ===')):
        s -= 1
    s += 1
    for j in range(s, sr_end + 1):
        lines_to_remove.add(j)

# Also handle the load_tenant_doc shadow (around lines 375-406)
# Check if it exists
for i, line in enumerate(lines):
    if 'async def load_tenant_doc' in line and i < 500:
        end_i = find_function_block(i)
        s = i
        while s > 0 and lines[s-1].strip() == '':
            s -= 1
        s += 1
        for j in range(s, end_i + 1):
            lines_to_remove.add(j)
        print(f"  Removing shadow load_tenant_doc at lines {s+1}-{end_i+1}")
        break

# ── 3. Write cleaned file ──
new_lines = []
for i, line in enumerate(lines):
    if i not in lines_to_remove:
        new_lines.append(line)

# Clean up excessive blank lines (more than 2 consecutive)
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

with open(OUTPUT, 'w') as f:
    f.writelines(final_lines)

# ── 4. Report ──
removed = total - len(final_lines)
print(f"\n{'='*60}")
print("CLEANUP COMPLETE")
print(f"  Original: {total} lines")
print(f"  Removed:  {removed} lines")
print(f"  Result:   {len(final_lines)} lines")
print(f"  Duplicate endpoints removed: {len(dupe_start_lines_1indexed)}")
print(f"  Shadow functions removed: {len(shadow_ranges)}")

# Verify no duplicate endpoints remain
new_endpoints = []
for i, line in enumerate(final_lines):
    m = re.match(r'@api_router\.(get|post|put|delete|patch)\(["\'](.+?)["\']', line.strip())
    if m:
        new_endpoints.append((m.group(1).upper(), m.group(2), i+1))

route_map = {}
for method, path, lineno in new_endpoints:
    key = f"{method} {path}"
    if key not in route_map:
        route_map[key] = []
    route_map[key].append(lineno)

remaining_dupes = {k: v for k, v in route_map.items() if len(v) > 1}
if remaining_dupes:
    print(f"\n  WARNING: {len(remaining_dupes)} intra-file duplicates still remain:")
    for k, v in remaining_dupes.items():
        print(f"    {k}: lines {v}")
else:
    print("\n  No intra-file duplicates remain.")

print(f"  Total endpoints remaining: {len(new_endpoints)}")
