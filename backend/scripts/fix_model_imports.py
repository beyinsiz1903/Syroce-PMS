"""
Fix missing model imports in extracted router files.
Reads inline models from legacy_routes.py and injects them into the correct router files.
"""
import re
import os

LEGACY_PATH = "/app/backend/legacy_routes.py"

# Read all inline models from legacy_routes.py
legacy_lines = open(LEGACY_PATH).readlines()
total = len(legacy_lines)

model_defs = {}
for i, line in enumerate(legacy_lines):
    m = re.match(r'^class (\w+)\(', line)
    if m:
        name = m.group(1)
        j = i + 1
        while j < total:
            if legacy_lines[j].strip() == '':
                j += 1
                continue
            if not legacy_lines[j][0].isspace():
                break
            j += 1
        code = ''.join(legacy_lines[i:j]).rstrip() + '\n'
        model_defs[name] = code

# Models already in models/schemas.py
schemas_lines = open('/app/backend/models/schemas.py').read()
schemas_models = set(re.findall(r'^class (\w+)\(', schemas_lines, re.MULTILINE))

# Models already in models/enums.py
enums_lines = open('/app/backend/models/enums.py').read()
enums_models = set(re.findall(r'^class (\w+)\(', enums_lines, re.MULTILINE))

# Router files to fix and their needed models
router_needs = {
    "domains/admin/router.py": [
        'TenantModulesUpdate', 'SubscriptionUpdateRequest', 'ChangePlanRequest',
        'UpdateHotelInfoRequest', 'CreateTeamMemberRequest', 'UpdateTeamMemberRoleRequest',
        'SLAConfig', 'DemoRequest', 'PmsLiteLeadStatus', 'PmsLiteLeadAdminUpdateRequest',
        'PmsLiteLeadContact', 'PmsLiteLeadHotel', 'PmsLiteLeadMetadata',
    ],
    "domains/pms/approvals_router.py": [
        'ApprovalType', 'ApprovalStatus', 'CreateApprovalRequest', 'ApprovalActionRequest',
        'BudgetMonth', 'BudgetConfig',
    ],
    "domains/pms/calendar_router.py": [
        'ChannelMixRequest',
    ],
    "domains/pms/dashboard_router.py": [
        'BudgetConfig', 'BudgetMonth',
    ],
    "domains/pms/frontdesk_router.py": [
        'PassportScanData', 'PassportScanRequest', 'WalkInBookingRequest',
        'GuestAlert', 'KeycardIssueRequest',
    ],
    "domains/pms/groups_router.py": [],
    "domains/pms/housekeeping_router.py": [
        'CleaningRequestStatusUpdate',
    ],
    "domains/pms/misc_router.py": [
        'PingTestRequest',
    ],
    "domains/pms/notification_router.py": [
        'NotificationPreferenceRequest', 'SystemAlertRequest',
    ],
    "domains/pms/pos_fnb_router.py": [
        'POSCategory', 'POSMenuItem', 'POSOrderItem', 'POSOrderItemRequest',
        'POSOrderCreateRequest', 'POSOrder', 'StockAdjustRequest', 'UpdateOrderStatusRequest',
        'TableLayout', 'KitchenOrderItem', 'Alert',
    ],
    "domains/revenue/pricing_router.py": [
        'RatePlanFilter', 'RatePlanCreate', 'PackageCreate',
        'DynamicRestrictionsRequest', 'DemandForecast', 'CompetitorRate',
        'RateOverrideRequest',
    ],
    "domains/guest/messaging/router.py": [
        'SendMessageRequest', 'SentMessage', 'MessageTemplate', 'MessageType',
        'InternalMessage', 'AutoMessageTrigger',
    ],
    "domains/guest/operations_router.py": [
        'GuestStayHistory', 'GuestPreference', 'GuestTag', 'GuestTagEnum',
        'RedeemPointsRequest', 'MinimumStockAlertRequest',
        'LinenInventoryItem', 'CleaningRequestCreate',
    ],
    "domains/sales/crm_router.py": [
        'CreateLeadRequest', 'UpdateLeadStageRequest', 'LeadStage',
        'PmsLiteLeadStatus', 'PmsLiteLeadContact', 'PmsLiteLeadHotel',
        'PmsLiteLeadMetadata', 'PmsLiteLeadCreateRequest', 'PmsLiteLeadAdminUpdateRequest',
    ],
    "domains/channel_manager/operations_router.py": [
        'PermissionCheckRequest',
    ],
}

# Also add needed schema/enum imports
schema_imports_needed = {
    "domains/pms/misc_router.py": [
        "Company", "CompanyCreate", "BookingCreate", "BookingExtended",
    ],
    "domains/pms/frontdesk_router.py": [
        "Booking", "BookingCreate", "BookingExtended",
    ],
    "domains/pms/groups_router.py": [
        "CreateGroupReservationRequest", "AssignGroupRoomsRequest",
        "CreateBlockReservationRequest", "UseBlockRoomRequest",
    ],
    "domains/pms/calendar_router.py": [
        "CreateRateCodeRequest", "GetCalendarTooltipRequest",
    ],
    "domains/pms/housekeeping_router.py": [
        "ReportIssueRequest", "UploadPhotoRequest",
    ],
    "domains/guest/messaging/router.py": [
        "SendWhatsAppRequest", "SendEmailRequest", "SendSMSRequest",
    ],
    "domains/guest/operations_router.py": [
        "LoyaltyProgramCreate", "LoyaltyTransactionCreate", "RoomServiceCreate",
    ],
    "domains/revenue/pricing_router.py": [],
    "domains/pms/pos_fnb_router.py": [
        "CreatePOSTransactionRequest", "OrderCreate",
    ],
}

enum_imports_needed = {
    "domains/pms/misc_router.py": ["RoomStatus", "BookingStatus", "CompanyStatus"],
    "domains/pms/frontdesk_router.py": ["RoomStatus", "BookingStatus", "FolioType", "ChannelType"],
    "domains/revenue/pricing_router.py": ["ChannelType"],
    "domains/revenue/analytics_router.py": ["ChannelType"],
    "domains/channel_manager/operations_router.py": ["ChannelType", "ChannelStatus", "ParityStatus"],
    "domains/sales/crm_router.py": ["CompanyStatus"],
}


def inject_models(filepath, model_names):
    """Inject inline model definitions after the imports section."""
    full_path = os.path.join("/app/backend", filepath)
    if not os.path.exists(full_path):
        print(f"  SKIP {filepath}: file not found")
        return
    
    content = open(full_path).read()
    
    # Collect models to inject
    models_to_add = []
    for name in model_names:
        if name in model_defs and f'class {name}(' not in content:
            models_to_add.append(model_defs[name])
    
    if not models_to_add:
        return
    
    # Find insertion point - after the last import line
    lines = content.split('\n')
    insert_after = 0
    for i, line in enumerate(lines):
        if line.startswith('from ') or line.startswith('import '):
            insert_after = i
        if line.startswith('router = '):
            insert_after = i
            break
    
    # Also add Enum import if needed
    enum_needed = False
    for model_code in models_to_add:
        if '(str, Enum)' in model_code or '(Enum)' in model_code:
            enum_needed = True
            break
    
    if enum_needed and 'from enum import Enum' not in content:
        models_to_add.insert(0, 'from enum import Enum')
    
    # Build injection block
    injection = '\n\n# ── Inline Models ──\n\n' + '\n\n'.join(models_to_add)
    
    # Insert after the router = line
    lines.insert(insert_after + 1, injection)
    
    with open(full_path, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"  ✅ {filepath}: injected {len(models_to_add)} models")


def add_schema_imports(filepath, model_names):
    """Add missing imports from models.schemas."""
    full_path = os.path.join("/app/backend", filepath)
    if not os.path.exists(full_path):
        return
    
    content = open(full_path).read()
    to_add = [n for n in model_names if n not in content]
    if not to_add:
        return
    
    # Find the models.schemas import line
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'from models.schemas import' in line:
            # Append the new models
            existing = line.rstrip()
            if existing.endswith(')'):
                existing = existing[:-1] + ', ' + ', '.join(to_add) + ')'
            else:
                existing = existing + ', ' + ', '.join(to_add)
            lines[i] = existing
            break
    else:
        # No existing import - add one
        for i, line in enumerate(lines):
            if line.startswith('from models.enums import'):
                lines.insert(i + 1, 'from models.schemas import ' + ', '.join(['User'] + to_add))
                break
    
    with open(full_path, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"  ✅ {filepath}: added schema imports {to_add}")


def add_enum_imports(filepath, enum_names):
    """Add missing imports from models.enums."""
    full_path = os.path.join("/app/backend", filepath)
    if not os.path.exists(full_path):
        return
    
    content = open(full_path).read()
    to_add = [n for n in enum_names if f'import {n}' not in content and f', {n}' not in content and f'{n},' not in content]
    if not to_add:
        return
    
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'from models.enums import' in line:
            existing = line.rstrip()
            existing = existing + ', ' + ', '.join(to_add)
            lines[i] = existing
            break
    else:
        for i, line in enumerate(lines):
            if line.startswith('from models.schemas import'):
                lines.insert(i, 'from models.enums import UserRole, ' + ', '.join(to_add))
                break
    
    with open(full_path, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"  ✅ {filepath}: added enum imports {to_add}")


# Execute fixes
print("=== Injecting inline models ===")
for filepath, model_names in router_needs.items():
    if model_names:
        inject_models(filepath, model_names)

print("\n=== Adding schema imports ===")
for filepath, model_names in schema_imports_needed.items():
    if model_names:
        add_schema_imports(filepath, model_names)

print("\n=== Adding enum imports ===")
for filepath, enum_names in enum_imports_needed.items():
    if enum_names:
        add_enum_imports(filepath, enum_names)

print("\nDone!")
