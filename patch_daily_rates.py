import re

file_path = 'backend/routers/reservation_detail.py'
with open(file_path, 'r') as f:
    content = f.read()

pattern = r'(await ensure_reservation_mutable\(db, tid, booking\))'
replacement = r'''\1

        if booking.get("is_complimentary"):
            for rate in data.rates:
                rate.rate = 0.0'''
content = re.sub(pattern, replacement, content)

with open(file_path, 'w') as f:
    f.write(content)
