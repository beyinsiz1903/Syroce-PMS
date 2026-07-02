import re
with open("/Users/syroce/Documents/GitHub/SyrocePMS/backend/routers/mice.py", "r") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "[doc async for doc in cur]" in line:
        lines[i] = "    docs = await cur.to_list(length=None)\n    items = docs\n"
    elif "return {\"menus\": [doc async for doc in cur]}" in line:
        lines[i] = "    menus = await cur.to_list(length=None)\n    return {\"menus\": menus}\n"
    elif "return {\"accounts\": [d async for d in cur]}" in line:
        lines[i] = "    accounts = await cur.to_list(length=None)\n    return {\"accounts\": accounts}\n"
    elif "return {\"contacts\": [d async for d in cur]}" in line:
        lines[i] = "    contacts = await cur.to_list(length=None)\n    return {\"contacts\": contacts}\n"
    elif "return {\"resources\": [d async for d in cur]}" in line:
        lines[i] = "    resources = await cur.to_list(length=None)\n    return {\"resources\": resources}\n"
    elif "return {\"orders\": [d async for d in cur]}" in line:
        lines[i] = "    orders = await cur.to_list(length=None)\n    return {\"orders\": orders}\n"
    elif "orders = [d async for d in cur]" in line:
        lines[i] = "    orders = await cur.to_list(length=None)\n"

with open("/Users/syroce/Documents/GitHub/SyrocePMS/backend/routers/mice.py", "w") as f:
    f.writelines(lines)
