with open("backend/routers/mice.py", "r") as f:
    content = f.read()

# Fix list comprehensions
content = content.replace('    items = [doc async for doc in cur]\n', '    docs = await cur.to_list(length=None)\n    items = docs\n')
content = content.replace('    return {"menus": [doc async for doc in cur]}\n', '    menus = await cur.to_list(length=None)\n    return {"menus": menus}\n')
content = content.replace('    return {"accounts": [d async for d in cur]}\n', '    accounts = await cur.to_list(length=None)\n    return {"accounts": accounts}\n')
content = content.replace('    return {"contacts": [d async for d in cur]}\n', '    contacts = await cur.to_list(length=None)\n    return {"contacts": contacts}\n')
content = content.replace('    return {"resources": [d async for d in cur]}\n', '    resources = await cur.to_list(length=None)\n    return {"resources": resources}\n')
content = content.replace('    return {"orders": [d async for d in cur]}\n', '    orders = await cur.to_list(length=None)\n    return {"orders": orders}\n')
content = content.replace('    orders = [d async for d in cur]\n', '    orders = await cur.to_list(length=None)\n')
content = content.replace('    return {"events": [d async for d in cur]}\n', '    events = await cur.to_list(length=None)\n    return {"events": events}\n')

# Fix dict comprehensions correctly
import re

# Match '    some_var = {m["id"]: m async for m in db.collection.find(...)}'
# We find everything from 'db.' to '})}' or 'session=session)}'
lines = content.split('\n')
for i, line in enumerate(lines):
    if "async for" in line and "{" in line and "}" in line and "find(" in line:
        if line.strip().startswith("spaces = {"):
            lines[i] = line.replace("spaces = {s[\"id\"]: s async for s in db.mice_spaces.find({\"tenant_id\": tenant_id, \"id\": {\"$in\": list(space_ids)}})}", 
                                    "    _l = await db.mice_spaces.find({\"tenant_id\": tenant_id, \"id\": {\"$in\": list(space_ids)}}).to_list(length=None)\n    spaces = {s[\"id\"]: s for s in _l}")
        elif line.strip().startswith("inventories = {"):
            lines[i] = line.replace("inventories = {i[\"id\"]: i async for i in db.mice_resources.find({\"tenant_id\": tenant_id, \"id\": {\"$in\": list(inv_ids)}}, session=session)}",
                                    "    _l = await db.mice_resources.find({\"tenant_id\": tenant_id, \"id\": {\"$in\": list(inv_ids)}}, session=session).to_list(length=None)\n    inventories = {i[\"id\"]: i for i in _l}")
        elif line.strip().startswith("spaces_by_id = {"):
            lines[i] = line.replace("spaces_by_id = {s[\"id\"]: s async for s in db.mice_spaces.find({\"tenant_id\": tenant_id})}",
                                    "    _l = await db.mice_spaces.find({\"tenant_id\": tenant_id}).to_list(length=None)\n    spaces_by_id = {s[\"id\"]: s for s in _l}")
            lines[i] = line.replace("spaces_by_id = {s[\"id\"]: s async for s in db.mice_spaces.find({\"tenant_id\": current_user.tenant_id})}",
                                    "    _l = await db.mice_spaces.find({\"tenant_id\": current_user.tenant_id}).to_list(length=None)\n    spaces_by_id = {s[\"id\"]: s for s in _l}")
        elif line.strip().startswith("menus = {"):
            lines[i] = line.replace("menus = {m[\"id\"]: m async for m in db.mice_menus.find({\"tenant_id\": current_user.tenant_id, \"id\": {\"$in\": menu_ids}})}",
                                    "    _l = await db.mice_menus.find({\"tenant_id\": current_user.tenant_id, \"id\": {\"$in\": menu_ids}}).to_list(length=None)\n    menus = {m[\"id\"]: m for m in _l}")

with open("backend/routers/mice.py", "w") as f:
    f.write("\n".join(lines))
