"""Physical-room filter for agency inventory queries.

The PMS keeps one virtual room per room type (``is_virtual=True``, room
numbers like ``V-SUP``, capacity 99) as an overbooking/unassigned holder. The
PMS room list hides them; agency search and booking must too, otherwise each
room type is oversold by one and a reservation can land in the holder room
with a party size no real room can take.
"""

PHYSICAL_ROOM_FILTER = {"is_virtual": {"$ne": True}}
