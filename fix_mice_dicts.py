import re
with open("/Users/syroce/Documents/GitHub/SyrocePMS/backend/routers/mice.py", "r") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "spaces_by_id = {s[\"id\"]: s async for s in db.mice_spaces.find" in line:
        # Extract the db.mice_spaces.find(...) part
        match = re.search(r'db\.mice_spaces\.find\((.*?)\)', line)
        if match:
            find_args = match.group(1)
            new_lines = f"    _spaces_list = await db.mice_spaces.find({find_args}).to_list(length=None)\n    spaces_by_id = {{s['id']: s for s in _spaces_list}}\n"
            lines[i] = new_lines
    elif "spaces = {s[\"id\"]: s async for s in db.mice_spaces.find" in line:
        match = re.search(r'db\.mice_spaces\.find\((.*?)\)', line)
        if match:
            find_args = match.group(1)
            new_lines = f"    _spaces_list = await db.mice_spaces.find({find_args}).to_list(length=None)\n    spaces = {{s['id']: s for s in _spaces_list}}\n"
            lines[i] = new_lines
    elif "inventories = {i[\"id\"]: i async for i in db.mice_resources.find" in line:
        match = re.search(r'db\.mice_resources\.find\((.*?)\)', line)
        if match:
            find_args = match.group(1)
            new_lines = f"    _inv_list = await db.mice_resources.find({find_args}).to_list(length=None)\n    inventories = {{i['id']: i for i in _inv_list}}\n"
            lines[i] = new_lines
    elif "menus = {m[\"id\"]: m async for m in db.mice_menus.find" in line:
        match = re.search(r'db\.mice_menus\.find\((.*?)\)', line)
        if match:
            find_args = match.group(1)
            new_lines = f"    _menu_list = await db.mice_menus.find({find_args}).to_list(length=None)\n    menus = {{m['id']: m for m in _menu_list}}\n"
            lines[i] = new_lines

with open("/Users/syroce/Documents/GitHub/SyrocePMS/backend/routers/mice.py", "w") as f:
    f.writelines(lines)
