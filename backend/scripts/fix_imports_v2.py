"""
Fix all remaining import errors in extracted router files.
"""
import re
import os

BASE = "/app/backend"

# Fixes to apply: (filepath, old_text, new_text)
fixes = []

# 1. Add 'cached' import to all files that use it
cached_import = """
try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator
"""

cached_files = [
    "domains/ai/router.py",
    "domains/pms/night_audit_router.py",
    "domains/channel_manager/operations_router.py",
    "domains/pms/calendar_router.py",
    "domains/pms/misc_router.py",
]

for filepath in cached_files:
    full = os.path.join(BASE, filepath)
    if not os.path.exists(full):
        continue
    content = open(full).read()
    if 'from cache_manager import' not in content:
        # Insert after the logger line
        content = content.replace(
            'logger = logging.getLogger(__name__)',
            'logger = logging.getLogger(__name__)\n' + cached_import
        )
        open(full, 'w').write(content)
        print(f"  ✅ {filepath}: added cached import")

# 2. Add ConfigDict to pydantic imports
config_dict_files = [
    "domains/pms/frontdesk_router.py",
    "domains/pms/pos_fnb_router.py",
    "domains/guest/operations_router.py",
]

for filepath in config_dict_files:
    full = os.path.join(BASE, filepath)
    if not os.path.exists(full):
        continue
    content = open(full).read()
    if 'ConfigDict' not in content.split('from pydantic')[0] if 'from pydantic' in content else True:
        content = content.replace(
            'from pydantic import BaseModel, Field',
            'from pydantic import BaseModel, Field, ConfigDict'
        )
        open(full, 'w').write(content)
        print(f"  ✅ {filepath}: added ConfigDict")

# 3. Add EmailStr to admin router
admin_path = os.path.join(BASE, "domains/admin/router.py")
content = open(admin_path).read()
if 'EmailStr' not in content.split('\n')[0:20].__repr__():
    content = content.replace(
        'from pydantic import BaseModel, Field',
        'from pydantic import BaseModel, Field, EmailStr'
    )
    open(admin_path, 'w').write(content)
    print("  ✅ admin/router.py: added EmailStr")

# 4. Add File, UploadFile to housekeeping imports
hk_path = os.path.join(BASE, "domains/pms/housekeeping_router.py")
content = open(hk_path).read()
if 'File,' not in content.split('from fastapi')[0:200].__repr__():
    content = content.replace(
        'from fastapi import APIRouter, HTTPException, Depends, status, Body, Query',
        'from fastapi import APIRouter, HTTPException, Depends, status, Body, Query, File, UploadFile, Form'
    )
    open(hk_path, 'w').write(content)
    print("  ✅ housekeeping_router.py: added File/UploadFile")

# 5. Add RateType to revenue pricing
pricing_path = os.path.join(BASE, "domains/revenue/pricing_router.py")
content = open(pricing_path).read()
if 'RateType' not in content[:3000]:
    content = content.replace(
        'from models.enums import UserRole',
        'from models.enums import UserRole, RateType, MarketSegment'
    )
    open(pricing_path, 'w').write(content)
    print("  ✅ pricing_router.py: added RateType")

# 6. Add MaintenanceWorkOrder to maintenance router
maint_path = os.path.join(BASE, "domains/pms/maintenance_router.py")
content = open(maint_path).read()
content = content.replace(
    'from models.schemas import User',
    'from models.schemas import User, MaintenanceWorkOrder, SensorAlert'
)
open(maint_path, 'w').write(content)
print("  ✅ maintenance_router.py: added MaintenanceWorkOrder")

# 7. Fix model ordering issues - MessageType in messaging router
msg_path = os.path.join(BASE, "domains/guest/messaging/router.py")
content = open(msg_path).read()
# MessageType needs to be defined before SendMessageRequest
if 'class MessageType' in content:
    # It's already there but after SendMessageRequest - need to reorder
    # Find MessageType class definition and move it before SendMessageRequest
    lines = content.split('\n')
    msg_type_start = None
    msg_type_end = None
    send_msg_start = None
    for i, line in enumerate(lines):
        if 'class MessageType' in line:
            msg_type_start = i
        if msg_type_start is not None and msg_type_end is None:
            if i > msg_type_start and line.strip() and not line.startswith(' ') and not line.startswith('\t'):
                msg_type_end = i
        if 'class SendMessageRequest' in line:
            send_msg_start = i
    
    if msg_type_start and msg_type_end and send_msg_start and msg_type_start > send_msg_start:
        msg_type_block = '\n'.join(lines[msg_type_start:msg_type_end])
        # Remove from original position
        new_lines = lines[:msg_type_start] + lines[msg_type_end:]
        # Find SendMessageRequest again
        for i, line in enumerate(new_lines):
            if 'class SendMessageRequest' in line:
                new_lines.insert(i, msg_type_block + '\n')
                break
        content = '\n'.join(new_lines)
        open(msg_path, 'w').write(content)
        print("  ✅ messaging/router.py: reordered MessageType before SendMessageRequest")

# 8. Fix BudgetMonth ordering in dashboard router 
dash_path = os.path.join(BASE, "domains/pms/dashboard_router.py")
content = open(dash_path).read()
if 'class BudgetMonth' in content and 'class BudgetConfig' in content:
    lines = content.split('\n')
    budget_month_start = None
    budget_month_end = None
    budget_config_start = None
    
    for i, line in enumerate(lines):
        if 'class BudgetMonth' in line:
            budget_month_start = i
        if budget_month_start is not None and budget_month_end is None:
            if i > budget_month_start and line.strip() and not line.startswith(' ') and not line.startswith('\t'):
                budget_month_end = i
        if 'class BudgetConfig' in line:
            budget_config_start = i
    
    if budget_month_start and budget_month_end and budget_config_start and budget_month_start > budget_config_start:
        budget_month_block = '\n'.join(lines[budget_month_start:budget_month_end])
        new_lines = lines[:budget_month_start] + lines[budget_month_end:]
        for i, line in enumerate(new_lines):
            if 'class BudgetConfig' in line:
                new_lines.insert(i, budget_month_block + '\n')
                break
        content = '\n'.join(new_lines)
        open(dash_path, 'w').write(content)
        print("  ✅ dashboard_router.py: reordered BudgetMonth before BudgetConfig")

# 9. Fix LeadStage ordering in sales/crm_router
sales_path = os.path.join(BASE, "domains/sales/crm_router.py")
content = open(sales_path).read()
if 'class LeadStage' in content and 'class CreateLeadRequest' in content:
    lines = content.split('\n')
    lead_stage_start = None
    lead_stage_end = None
    create_lead_start = None
    
    for i, line in enumerate(lines):
        if 'class LeadStage' in line:
            lead_stage_start = i
        if lead_stage_start is not None and lead_stage_end is None:
            if i > lead_stage_start and line.strip() and not line.startswith(' ') and not line.startswith('\t'):
                lead_stage_end = i
        if 'class CreateLeadRequest' in line:
            create_lead_start = i
    
    if lead_stage_start and lead_stage_end and create_lead_start and lead_stage_start > create_lead_start:
        lead_stage_block = '\n'.join(lines[lead_stage_start:lead_stage_end])
        new_lines = lines[:lead_stage_start] + lines[lead_stage_end:]
        for i, line in enumerate(new_lines):
            if 'class CreateLeadRequest' in line:
                new_lines.insert(i, lead_stage_block + '\n')
                break
        content = '\n'.join(new_lines)
        open(sales_path, 'w').write(content)
        print("  ✅ crm_router.py: reordered LeadStage before CreateLeadRequest")

print("\nAll fixes applied!")
