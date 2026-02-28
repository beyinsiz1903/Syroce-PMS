"""
Extract PMS, Finance, and Reports routes from server.py into separate router files.
Fixed version: properly handles triple-quoted strings in function bodies.
"""
import re

INFILE = '/app/backend/server.py'

with open(INFILE, 'r') as f:
    lines = f.readlines()

total = len(lines)

# ── Parse route blocks ──
route_pattern = re.compile(r'^@api_router\.(get|post|put|delete|patch)\("(/[^"]+)"')


def find_function_end(func_def_line):
    """Find end of a Python function. Handles triple-quoted strings."""
    # First, find end of function signature (matching parens + colon)
    i = func_def_line
    paren_depth = 0
    sig_end = i
    for idx in range(i, min(i + 30, total)):
        line = lines[idx]
        for ch in line:
            if ch == '(':
                paren_depth += 1
            elif ch == ')':
                paren_depth -= 1
        if paren_depth <= 0 and ':' in line and idx >= i:
            sig_end = idx
            break

    # Now scan function body until we find a non-indented, non-blank line
    # that is NOT inside a triple-quoted string
    j = sig_end + 1
    in_triple_single = False
    in_triple_double = False

    while j < total:
        line = lines[j]
        raw = line.rstrip('\n')

        # Track triple-quoted strings
        # Count occurrences of ''' and """ in this line
        triple_double_count = raw.count('"""')
        triple_single_count = raw.count("'''")

        if in_triple_double:
            if triple_double_count % 2 == 1:
                in_triple_double = False
            j += 1
            continue

        if in_triple_single:
            if triple_single_count % 2 == 1:
                in_triple_single = False
            j += 1
            continue

        # Not in triple quote - check for opening
        if triple_double_count % 2 == 1:
            in_triple_double = True
            j += 1
            continue

        if triple_single_count % 2 == 1:
            in_triple_single = True
            j += 1
            continue

        stripped = line.strip()
        if stripped == '':
            j += 1
            continue

        # Check if this line is at indent level 0
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

        # Find function def line (handle decorator chains)
        j = i + 1
        while j < total:
            ln = lines[j].lstrip()
            if ln.startswith('async def ') or ln.startswith('def '):
                break
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
class_pattern_re = re.compile(r'^class (\w+)\(')
class_blocks = []
for ci, line in enumerate(lines):
    m = class_pattern_re.match(line)
    if m and ci > 4500:  # Skip early imported classes
        end = ci + 1
        while end < total and (lines[end].startswith(' ') or lines[end].startswith('\t') or lines[end].strip() == ''):
            end += 1
        class_blocks.append({
            'start': ci,
            'end': end,
            'name': m.group(1),
        })


# ── Group routes ──
def is_pms(p):
    return (p.startswith('/pms/') or p.startswith('/rooms/') or
            p.startswith('/reservations/') or p.startswith('/bookings/'))


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
    unique, dupes = [], []
    for b in blocks:
        key = f"{b['method']}:{b['path']}"
        if key in seen:
            dupes.append(b)
        else:
            unique.append(b)
            seen.add(key)
    return unique, dupes


# ── Find model classes used by a group ──
def find_used_classes(route_list):
    code = ''
    for b in route_list:
        code += ''.join(lines[b['start']:b['end']])
    return [c for c in class_blocks if c['name'] in code]


# ── Build line removal set ──
all_lines_to_remove = set()

for group_name in ['pms', 'finance', 'reports']:
    unique, dupes = deduplicate_routes(groups[group_name])
    used_classes = find_used_classes(unique)

    for b in unique + dupes:
        for ln in range(b['start'], b['end']):
            all_lines_to_remove.add(ln)
    for c in used_classes:
        for ln in range(c['start'], c['end']):
            all_lines_to_remove.add(ln)

    # ── Write router file ──
    router_code_parts = []
    for c in used_classes:
        router_code_parts.append((c['start'], ''.join(lines[c['start']:c['end']])))
    for b in unique:
        router_code_parts.append((b['start'], ''.join(lines[b['start']:b['end']])))
    router_code_parts.sort(key=lambda x: x[0])

    outfile = f'/app/backend/routers/{group_name}.py'
    with open(outfile, 'w') as f:
        f.write(f'"""\n{group_name.upper()} Router - Extracted from server.py\n"""\n')
        f.write('import uuid\nimport io\nimport csv\n')
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

        for _pos, code in router_code_parts:
            replaced = code.replace('@api_router.', '@router.')
            f.write(replaced)
            if not replaced.endswith('\n'):
                f.write('\n')
            f.write('\n')

    u_count = len(unique)
    d_count = len(dupes)
    total_lines = sum(b['end'] - b['start'] for b in unique + dupes)
    cls_lines = sum(c['end'] - c['start'] for c in used_classes)
    print(f"{group_name}: {u_count} unique + {d_count} dupes = {u_count+d_count} routes, "
          f"~{total_lines+cls_lines} code lines → {outfile}")


# ── Write cleaned server.py ──
new_lines = [lines[i] for i in range(total) if i not in all_lines_to_remove]

# Collapse runs of >2 blank lines
cleaned = []
blanks = 0
for line in new_lines:
    if line.strip() == '':
        blanks += 1
        if blanks <= 2:
            cleaned.append(line)
    else:
        blanks = 0
        cleaned.append(line)

with open('/app/backend/server_new.py', 'w') as f:
    f.writelines(cleaned)

print(f"\nRemoved {len(all_lines_to_remove)} lines from server.py")
print(f"server.py: {total} → {len(cleaned)} lines")
print(f"Written to: /app/backend/server_new.py")
