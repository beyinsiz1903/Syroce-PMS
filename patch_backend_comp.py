import re

file_path = 'backend/modules/reservations/services/update_reservation_service.py'
with open(file_path, 'r') as f:
    content = f.read()

# Inside `update` method, before doing the update, we can check if the booking is complimentary.
# If `existing_booking.get("is_complimentary")` is True, we pop `total_amount` from `update_data`.

pattern = r'(update_data = \{\n\s*k: v\n\s*for k, v in booking_data\.items\(\)\n\s*if k in ALLOWED_UPDATE_FIELDS\n\s*and k not in existing_booking\.get\("locked_fields", \[\]\)\n\s*\})'
replacement = r'''\1

            # If the reservation is complimentary, protect its pricing from being overwritten by clients
            if existing_booking.get("is_complimentary"):
                update_data.pop("total_amount", None)
'''
content = re.sub(pattern, replacement, content)

with open(file_path, 'w') as f:
    f.write(content)
