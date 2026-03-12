"""
Batch Endpoint Extraction Tool
Extracts endpoint groups from legacy_routes.py into domain router files.
"""
import re
import sys

INPUT = "/app/backend/legacy_routes.py"

lines = open(INPUT).readlines()
total = len(lines)

# ── Find all endpoint positions ──
def find_endpoints():
    eps = []
    for i, line in enumerate(lines):
        m = re.match(r'@api_router\.(get|post|put|delete|patch)\(["\'](.+?)["\']', line.strip())
        if m:
            eps.append((i, m.group(1).upper(), m.group(2)))
    return eps

def find_function_end(start_idx):
    """Find the last line of an endpoint function starting at start_idx."""
    i = start_idx + 1
    while i < total and lines[i].strip().startswith('@'):
        i += 1
    if i < total and (lines[i].strip().startswith('def ') or lines[i].strip().startswith('async def ')):
        i += 1
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

def extract_endpoints_by_prefixes(prefixes):
    """Extract all endpoints matching given path prefixes."""
    eps = find_endpoints()
    matching = []
    for idx, method, path in eps:
        first_seg = path.strip('/').split('/')[0]
        if first_seg in prefixes:
            end = find_function_end(idx)
            # Include leading comments/blank lines
            start = idx
            while start > 0 and (lines[start-1].strip().startswith('#') or lines[start-1].strip() == ''):
                if lines[start-1].strip().startswith('# ==='):
                    start -= 1
                    break
                start -= 1
            start = max(start, 0)
            matching.append({
                'start': start,
                'end': end,
                'method': method,
                'path': path,
                'code': ''.join(lines[start:end+1])
            })
    return matching

def generate_router_code(endpoints, router_prefix_tag):
    """Generate a complete router file from extracted endpoints."""
    # Collect all code blocks
    code_blocks = []
    for ep in endpoints:
        code = ep['code']
        # Replace @api_router with @router
        code = code.replace('@api_router.', '@router.')
        code_blocks.append(code.strip())
    
    return code_blocks


if __name__ == "__main__":
    # Just report what would be extracted
    prefixes = sys.argv[1:] if len(sys.argv) > 1 else ['ai']
    matching = extract_endpoints_by_prefixes(prefixes)
    print(f"Prefixes: {prefixes}")
    print(f"Matched: {len(matching)} endpoints")
    total_lines_extracted = sum(ep['end'] - ep['start'] + 1 for ep in matching)
    print(f"Total lines: {total_lines_extracted}")
    for ep in matching:
        print(f"  {ep['method']:6s} {ep['path']:50s} lines {ep['start']+1}-{ep['end']+1}")
