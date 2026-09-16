import re

# 1. Patch CalendarGrid.jsx
with open("frontend/src/pages/calendar/CalendarGrid.jsx", "r") as f:
    content = f.read()

content = content.replace(
    "const covered = roomBookings.some(b => isActiveOn(b, dStr));",
    "const covered = roomBookings.some(b => isActiveOn(b, dStr) && b.status !== 'checked_out');"
)

with open("frontend/src/pages/calendar/CalendarGrid.jsx", "w") as f:
    f.write(content)

# 2. Patch ReservationCalendar.jsx
with open("frontend/src/pages/ReservationCalendar.jsx", "r") as f:
    content = f.read()

old_isRoom = r"b\.status !== 'cancelled' && b\.status !== 'no_show' &&\n\s*toDateStringUTC\(b\.check_in\) <= dStr"
new_isRoom = "b.status !== 'cancelled' && b.status !== 'no_show' && b.status !== 'checked_out' &&\n      toDateStringUTC(b.check_in) <= dStr"

content = re.sub(old_isRoom, new_isRoom, content)

with open("frontend/src/pages/ReservationCalendar.jsx", "w") as f:
    f.write(content)
