"""
Script to extract route handlers from server.py into separate router files.
Extracts PMS, Finance, and Reports routes.
"""
import re
import sys

def parse_server():
    with open('/app/backend/server.py', 'r') as f:
        lines = f.readlines()
    
    total = len(lines)
    route_pattern = re.compile(r'^@api_router\.(get|post|put|delete|patch)\("(/[^"]+)"')
    
    # Find all route blocks: decorator(s) + function + body
    route_blocks = []
    i = 0
    while i < total:
        m = route_pattern.match(lines[i])
        if m:
            block_start = i
            method = m.group(1)
            path = m.group(2)
            
            # Find function def (may have multiple decorators)
            j = i + 1
            while j < total and not (lines[j].startswith('async def ') or lines[j].startswith('def ')):
                j += 1
            
            # Find function end
            func_end = j + 1
            while func_end < total:
                line = lines[func_end]
                if line.strip() == '':
                    func_end += 1
                    continue
                # Check if this is a new top-level entity
                if not line.startswith(' ') and not line.startswith('\t'):
                    break
                func_end += 1
            
            # Trim trailing blank lines
            while func_end > j and lines[func_end - 1].strip() == '':
                func_end -= 1
            func_end += 1  # Include one blank line after
            
            route_blocks.append({
                'start': block_start,
                'end': min(func_end, total),
                'method': method,
                'path': path,
                'code': ''.join(lines[block_start:min(func_end, total)])
            })
            i = min(func_end, total)
        else:
            i += 1
    
    return lines, route_blocks


def find_class_blocks(lines):
    """Find all class definitions with their line ranges."""
    total = len(lines)
    class_pattern = re.compile(r'^class (\w+)\(')
    classes = []
    
    for i, line in enumerate(lines):
        m = class_pattern.match(line)
        if m:
            end = i + 1
            while end < total and (lines[end].startswith(' ') or lines[end].startswith('\t') or lines[end].strip() == ''):
                end += 1
            classes.append({
                'start': i,
                'end': end,
                'name': m.group(1),
                'code': ''.join(lines[i:end])
            })
    
    return classes


def group_routes(route_blocks):
    """Group routes by their target router."""
    groups = {
        'pms': [],
        'finance': [],
        'reports': [],
    }
    
    # Track seen routes to handle duplicates
    seen_pms = set()
    seen_finance = set()
    seen_reports = set()
    
    for block in route_blocks:
        path = block['path']
        method = block['method']
        key = f"{method}:{path}"
        
        if path.startswith('/pms/') or path.startswith('/rooms/') or path.startswith('/reservations/') or path.startswith('/bookings/'):
            if key not in seen_pms:
                groups['pms'].append(block)
                seen_pms.add(key)
            else:
                block['duplicate'] = True
                groups['pms'].append(block)
        elif (path.startswith('/finance/') or path.startswith('/accounting/') or 
              path.startswith('/cashiering/') or path.startswith('/efatura/') or 
              path.startswith('/folio/') or path.startswith('/invoices')):
            if key not in seen_finance:
                groups['finance'].append(block)
                seen_finance.add(key)
            else:
                block['duplicate'] = True
                groups['finance'].append(block)
        elif path.startswith('/reports/') or path.startswith('/night-audit/'):
            if key not in seen_reports:
                groups['reports'].append(block)
                seen_reports.add(key)
            else:
                block['duplicate'] = True
                groups['reports'].append(block)
    
    return groups


def find_model_classes_for_group(classes, route_blocks, all_lines):
    """Find model classes that are used by a group of routes."""
    # Get all class names referenced in route code
    route_code = '\n'.join(b['code'] for b in route_blocks if not b.get('duplicate'))
    
    used_classes = []
    for cls in classes:
        # Skip classes that are imported from models.schemas or models.enums
        if cls['start'] < 5000:  # Early classes are likely from imports
            continue
        # Check if class name appears in route code
        if cls['name'] in route_code:
            used_classes.append(cls)
    
    return used_classes


if __name__ == '__main__':
    lines, route_blocks = parse_server()
    classes = find_class_blocks(lines)
    groups = group_routes(route_blocks)
    
    print("=== EXTRACTION SUMMARY ===")
    for name, blocks in groups.items():
        unique = [b for b in blocks if not b.get('duplicate')]
        dupes = [b for b in blocks if b.get('duplicate')]
        total_lines = sum(b['end'] - b['start'] for b in blocks)
        print(f"\n{name}: {len(unique)} unique routes, {len(dupes)} duplicates, ~{total_lines} lines")
        
        # Find model classes
        model_classes = find_model_classes_for_group(classes, unique, lines)
        model_lines = sum(c['end'] - c['start'] for c in model_classes)
        print(f"  Model classes: {len(model_classes)} ({model_lines} lines)")
        for c in model_classes:
            print(f"    - {c['name']} (L{c['start']+1})")
    
    # Calculate total lines to remove
    all_blocks = []
    for blocks in groups.values():
        all_blocks.extend(blocks)
    
    # Also add model classes
    for name, blocks in groups.items():
        unique = [b for b in blocks if not b.get('duplicate')]
        model_classes = find_model_classes_for_group(classes, unique, lines)
        for c in model_classes:
            all_blocks.append(c)
    
    total_remove = sum(b['end'] - b['start'] for b in all_blocks)
    print(f"\n=== TOTAL: ~{total_remove} lines to remove from server.py ===")
    print(f"=== server.py will go from {len(lines)} to ~{len(lines) - total_remove} lines ===")
