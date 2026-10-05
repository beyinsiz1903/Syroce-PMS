import re

with open("backend/routers/reservation_detail.py", "r") as f:
    content = f.read()

# Fix get_reservation_detail to resolve additional guests
new_query = """        # Also check for additional guests
        ag_links = await db.booking_guests.find({"booking_id": booking_id, "tenant_id": tid}, {"guest_id": 1}).to_list(100)
        ag_ids = [l["guest_id"] for l in ag_links if "guest_id" in l]
        if ag_ids:
            async for ag in db.guests.find({"id": {"$in": ag_ids}, "tenant_id": tid}, {"_id": 0}):
                guests_list.append(ag)"""

old_query = r"        # Also check for additional guests\n        async for ag in db\.booking_guests\.find\(\{\"booking_id\": booking_id, \"tenant_id\": tid\}, \{\"_id\": 0\}\):\n            guests_list\.append\(ag\)"

content = re.sub(old_query, new_query, content)

with open("backend/routers/reservation_detail.py", "w") as f:
    f.write(content)
