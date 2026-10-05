import re

with open("backend/routers/kbs.py", "r") as f:
    content = f.read()

# Fix 1: kbs_guest_list
content = re.sub(
    r'"birth_date": 1, "gender": 1',
    r'"birth_date": 1, "date_of_birth": 1, "gender": 1',
    content
)

content = re.sub(
    r'b\["birth_date"\] = g\.get\("birth_date", ""\)',
    r'b["birth_date"] = g.get("birth_date") or g.get("date_of_birth", "")',
    content
)

# Fix 2: enqueue_booking
content = re.sub(
    r'"birth_date": guest\.get\("birth_date", ""\),',
    r'"birth_date": guest.get("birth_date") or guest.get("date_of_birth", ""),',
    content
)

with open("backend/routers/kbs.py", "w") as f:
    f.write(content)
