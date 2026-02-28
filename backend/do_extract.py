"""
Extract PMS, Finance, and Reports routes from server.py into separate router files.
This script:
1. Parses server.py to find route handler functions
2. Groups them into PMS, Finance, Reports categories
3. Extracts them with associated model classes
4. Writes new router files
5. Produces a cleaned server.py
"""
import re
import sys

INFILE = '/app/backend/server.py'

with open(INFILE, 'r') as f:
    lines = f.readlines()

total = len(lines)

# ── Parse route blocks ──
route_pattern = re.compile(r'^@api_router\.(get|post|put|delete|patch)\("(/[^"]+)"')

def find_function_end(start_line):
    """Find end of a Python function starting from its def line."""
    i = start_line
    paren_depth = 0
    found_colon = False
    while i < total:
        for ch in lines[i]:
            if ch == '(':
                paren_depth += 1
            elif ch == ')':
                paren_depth -= 1
        if paren_depth <= 0 and ':' in lines[i]:
            found_colon = True
            break
        i += 1
    if not found_colon:
        return i + 1
    
    j = i + 1
    while j < total:
        line = lines[j]
        if line.strip() == '':
            j += 1
            continue
        if not line[0].isspace():
            break
        j += 1
    return j


# Parse all route blocks
route_blocks = []
i = 0
while i < total:
    m = route_pattern.match(lines[i])
    if m:
        block_start = i
        method = m.group(1)
        path = m.group(2)
        
        # Find function def line
        j = i + 1
        while j < total and not (lines[j].lstrip().startswith('async def ') or lines[j].lstrip().startswith('def ')):
            j += 1
        
        func_end = find_function_end(j)
        
        route_blocks.append({
            'start': block_start,
            'end': func_end,
            'method': method,
            'path': path,
        })
        i = func_end
    else:
        i += 1


# ── Parse class blocks ──
class_pattern = re.compile(r'^class (\w+)\(')
class_blocks = []
for i, line in enumerate(lines):
    m = class_pattern.match(line)
    if m:
        end = i + 1
        while end < total and (lines[end].startswith(' ') or lines[end].startswith('\t') or lines[end].strip() == ''):
            end += 1
        class_blocks.append({
            'start': i,
            'end': end,
            'name': m.group(1),
        })


# ── Group routes ──
def is_pms(p):
    return p.startswith('/pms/') or p.startswith('/rooms/') or p.startswith('/reservations/') or p.startswith('/bookings/')

def is_finance(p):
    return (p.startswith('/finance/') or p.startswith('/accounting/') or 
            p.startswith('/cashiering/') or p.startswith('/efatura/') or 
            p.startswith('/folio/') or p.startswith('/invoices'))

def is_reports(p):
    return p.startswith('/reports/') or p.startswith('/night-audit/')


groups = {'pms': [], 'finance': [], 'reports': []}
for block in route_blocks:
    path = block['path']
    if is_pms(path):
        groups['pms'].append(block)
    elif is_finance(path):
        groups['finance'].append(block)
    elif is_reports(path):
        groups['reports'].append(block)


# ── Deduplicate: keep first occurrence ──
def deduplicate_routes(blocks):
    seen = set()
    unique = []
    dupes = []
    for b in blocks:
        key = f"{b['method']}:{b['path']}"
        if key in seen:
            dupes.append(b)
        else:
            unique.append(b)
            seen.add(key)
    return unique, dupes


# ── Find model classes used by a group ──
def find_used_classes(route_blocks_list, all_classes):
    """Find model classes used by the route functions."""
    route_code = ''
    for b in route_blocks_list:
        route_code += ''.join(lines[b['start']:b['end']])
    
    used = []
    for cls in all_classes:
        if cls['start'] < 4500:  # Skip early imported/base classes
            continue
        if cls['name'] in route_code:
            used.append(cls)
    return used


# ── Build extraction plan ──
all_lines_to_remove = set()

for group_name in ['pms', 'finance', 'reports']:
    unique, dupes = deduplicate_routes(groups[group_name])
    used_classes = find_used_classes(unique, class_blocks)
    
    # Mark all route lines (unique + dupes) for removal
    for b in unique + dupes:
        for ln in range(b['start'], b['end']):
            all_lines_to_remove.add(ln)
    
    # Mark class lines for removal  
    for c in used_classes:
        for ln in range(c['start'], c['end']):
            all_lines_to_remove.add(ln)
    
    # Write router file
    print(f"\n{'='*60}")
    print(f"Group: {group_name}")
    print(f"  Unique routes: {len(unique)}")
    print(f"  Duplicate routes (to remove): {len(dupes)}")
    print(f"  Model classes: {len(used_classes)}")
    
    # Collect code for the router file
    router_code_parts = []
    
    # Add model classes first
    for c in sorted(used_classes, key=lambda x: x['start']):
        router_code_parts.append(('class', c['start'], ''.join(lines[c['start']:c['end']])))
    
    # Add unique route functions
    for b in sorted(unique, key=lambda x: x['start']):
        router_code_parts.append(('route', b['start'], ''.join(lines[b['start']:b['end']])))
    
    # Sort by original position
    router_code_parts.sort(key=lambda x: x[1])
    
    # Write to file
    outfile = f'/app/backend/routers/{group_name}.py'
    with open(outfile, 'w') as f:
        # Write header
        f.write(f'"""\n{group_name.upper()} Router - Extracted from server.py\n"""\n')
        f.write('import uuid\n')
        f.write('import io\n')
        f.write('import csv\n')
        f.write('from datetime import datetime, timezone, timedelta, date\n')
        f.write('from typing import List, Optional, Dict, Any\n')
        f.write('from enum import Enum\n\n')
        f.write('from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form, Request\n')
        f.write('from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials\n')
        f.write('from fastapi.responses import FileResponse\n')
        f.write('from pydantic import BaseModel, Field\n\n')
        f.write('from core.database import db\n')
        f.write('from core.security import get_current_user\n')
        f.write('from core.helpers import (\n')
        f.write('    require_module, create_audit_log, load_tenant_doc,\n')
        f.write('    require_admin, require_feature, get_tenant_modules,\n')
        f.write(')\n')
        f.write('from models.enums import (\n')
        f.write('    UserRole, RoomStatus, BookingStatus, PaymentStatus,\n')
        f.write('    PaymentMethod, ChargeType, InvoiceStatus, FolioType,\n')
        f.write('    FolioStatus, ChargeCategory, FolioOperationType, PaymentType,\n')
        f.write(')\n')
        f.write('from models.schemas import (\n')
        f.write('    User, Room, RoomCreate, Guest, GuestCreate,\n')
        f.write('    Booking, BookingCreate, BookingExtended,\n')
        f.write('    Folio, FolioCreate, FolioCharge, ChargeCreate,\n')
        f.write('    Payment, PaymentCreate, FolioOperation, FolioOperationCreate,\n')
        f.write('    Invoice, InvoiceCreate, InvoiceItem,\n')
        f.write('    RateOverrideLog, RoomMoveHistory, RoomServiceCreate, RoomService,\n')
        f.write('    RatePlan, Package, AuditLog, RateOverride,\n')
        f.write('    CityTaxRule, Expense, CashFlow, BankAccount,\n')
        f.write('    CreditLimit, CityLedgerTransaction,\n')
        f.write('    Company, CompanyCreate,\n')
        f.write('    _ensure_hotel_context,\n')
        f.write(')\n\n')
        f.write('try:\n')
        f.write('    from cache_manager import cached\n')
        f.write('except ImportError:\n')
        f.write('    def cached(ttl=300, key_prefix=""):\n')
        f.write('        def decorator(func):\n')
        f.write('            return func\n')
        f.write('        return decorator\n\n')
        f.write(f'router = APIRouter(prefix="/api", tags=["{group_name}"])\n')
        f.write('security = HTTPBearer()\n\n')
        
        # Write the code parts, replacing api_router with router
        for kind, pos, code in router_code_parts:
            replaced = code.replace('@api_router.', '@router.')
            f.write(replaced)
            if not replaced.endswith('\n'):
                f.write('\n')
            f.write('\n')
    
    print(f"  Written to: {outfile}")


# ── Write cleaned server.py ──
print(f"\n{'='*60}")
print(f"Total lines to remove: {len(all_lines_to_remove)}")
print(f"Original server.py: {total} lines")
print(f"New server.py: ~{total - len(all_lines_to_remove)} lines")

# Write new server.py
new_lines = []
i = 0
while i < total:
    if i in all_lines_to_remove:
        # Skip this line, but track contiguous blocks
        # Add a single blank line marker to preserve structure
        start_skip = i
        while i < total and i in all_lines_to_remove:
            i += 1
        # Don't add anything - just skip the removed code
    else:
        new_lines.append(lines[i])
        i += 1

# Clean up multiple consecutive blank lines (more than 2)
cleaned_lines = []
blank_count = 0
for line in new_lines:
    if line.strip() == '':
        blank_count += 1
        if blank_count <= 2:
            cleaned_lines.append(line)
    else:
        blank_count = 0
        cleaned_lines.append(line)

with open('/app/backend/server_new.py', 'w') as f:
    f.writelines(cleaned_lines)

print(f"Written cleaned server.py to: /app/backend/server_new.py ({len(cleaned_lines)} lines)")
print("\nDone! Review the files before replacing server.py.")
