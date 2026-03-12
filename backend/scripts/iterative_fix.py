"""
Iterative import fixer - keeps fixing NameErrors until all routers load.
"""
import re
import os
import sys
import importlib

BASE = "/app/backend"

# Build a map of ALL class/constant definitions from legacy_routes.py and models/
def build_definitions_map():
    defs = {}
    
    # From legacy_routes.py
    lines = open(os.path.join(BASE, 'legacy_routes.py')).readlines()
    total = len(lines)
    for i, line in enumerate(lines):
        m = re.match(r'^class (\w+)[\(:]', line)
        if m:
            name = m.group(1)
            j = i + 1
            while j < total:
                if lines[j].strip() == '':
                    j += 1
                    continue
                if not lines[j][0].isspace():
                    break
                j += 1
            defs[name] = ''.join(lines[i:j]).rstrip()
    
    # Check for constant dicts
    for i, line in enumerate(lines):
        m = re.match(r'^([A-Z_]+)\s*=\s*\{', line)
        if m:
            name = m.group(1)
            j = i + 1
            brace_count = line.count('{') - line.count('}')
            while j < total and brace_count > 0:
                brace_count += lines[j].count('{') - lines[j].count('}')
                j += 1
            defs[name] = ''.join(lines[i:j]).rstrip()
    
    return defs

# Map of names available from models modules
def get_schemas_models():
    content = open(os.path.join(BASE, 'models/schemas.py')).read()
    return set(re.findall(r'^class (\w+)', content, re.MULTILINE))

def get_enums_models():
    content = open(os.path.join(BASE, 'models/enums.py')).read()
    return set(re.findall(r'^class (\w+)', content, re.MULTILINE))

# FastAPI / Pydantic known imports
FASTAPI_NAMES = {'APIRouter', 'HTTPException', 'Depends', 'status', 'Body', 'Query', 
                 'File', 'UploadFile', 'Form', 'Header', 'Request', 'Response',
                 'BackgroundTasks', 'Path'}
PYDANTIC_NAMES = {'BaseModel', 'Field', 'ConfigDict', 'EmailStr', 'conint', 'constr',
                  'field_validator', 'model_validator', 'validator'}

defs_map = build_definitions_map()
schema_models = get_schemas_models()
enum_models = get_enums_models()

routers_to_fix = [
    'domains.guest.messaging.router',
    'domains.revenue.pricing_router',
    'domains.admin.router',
    'domains.pms.maintenance_router',
    'domains.guest.operations_router',
    'domains.channel_manager.operations_router',
]

MAX_ITERATIONS = 20

for router_mod in routers_to_fix:
    filepath = os.path.join(BASE, router_mod.replace('.', '/') + '.py')
    iteration = 0
    
    while iteration < MAX_ITERATIONS:
        iteration += 1
        # Clear cached module
        for key in list(sys.modules.keys()):
            if key.startswith('domains.'):
                del sys.modules[key]
        
        try:
            mod = importlib.import_module(router_mod)
            router = getattr(mod, 'router')
            print(f"  ✅ {router_mod}: {len(router.routes)} routes (fixed in {iteration-1} iterations)")
            break
        except NameError as e:
            missing = str(e).split("'")[1]
            content = open(filepath).read()
            
            # Check where to get the missing name from
            if missing in FASTAPI_NAMES:
                # Add to fastapi import
                for line in content.split('\n'):
                    if line.startswith('from fastapi import'):
                        if missing not in line:
                            content = content.replace(line, line + f', {missing}')
                        break
                open(filepath, 'w').write(content)
                print(f"    {router_mod}: +{missing} from fastapi")
                
            elif missing in PYDANTIC_NAMES:
                for line in content.split('\n'):
                    if line.startswith('from pydantic import'):
                        if missing not in line:
                            content = content.replace(line, line + f', {missing}')
                        break
                open(filepath, 'w').write(content)
                print(f"    {router_mod}: +{missing} from pydantic")
                
            elif missing in schema_models:
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if 'from models.schemas import' in line:
                        lines[i] = line.rstrip() + f', {missing}'
                        break
                open(filepath, 'w').write('\n'.join(lines))
                print(f"    {router_mod}: +{missing} from models.schemas")
                
            elif missing in enum_models:
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if 'from models.enums import' in line:
                        lines[i] = line.rstrip() + f', {missing}'
                        break
                open(filepath, 'w').write('\n'.join(lines))
                print(f"    {router_mod}: +{missing} from models.enums")
                
            elif missing in defs_map:
                # Inline model from legacy - inject it
                model_code = defs_map[missing]
                lines = content.split('\n')
                # Find the router = APIRouter line
                insert_at = 0
                for i, line in enumerate(lines):
                    if 'router = APIRouter(' in line:
                        insert_at = i
                        break
                # Check if Enum import needed
                if '(str, Enum)' in model_code or '(Enum)' in model_code:
                    if 'from enum import' not in content:
                        for i, line in enumerate(lines):
                            if line.startswith('from pydantic'):
                                lines.insert(i, 'from enum import Enum')
                                insert_at += 1
                                break
                
                lines.insert(insert_at, '\n' + model_code + '\n')
                open(filepath, 'w').write('\n'.join(lines))
                print(f"    {router_mod}: +inline model {missing}")
            else:
                print(f"    {router_mod}: ❌ Cannot find '{missing}' anywhere!")
                break
                
        except Exception as e:
            print(f"  ❌ {router_mod}: {type(e).__name__}: {e}")
            break
    else:
        print(f"  ⚠️ {router_mod}: Max iterations reached!")

print("\nDone!")
