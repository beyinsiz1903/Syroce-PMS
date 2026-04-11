"""Helpers to normalize PMS room availability into Booking-like structures.

This does not perform real Booking.com API calls yet. It only prepares
payloads that a future real integration can reuse.
"""
from typing import Dict, Any, List


def normalize_availability_response(
    rooms: List[Dict[str, Any]],
    check_in: str,
    check_out: str,
) -> List[Dict[str, Any]]:
    """Convert /pms/rooms/availability response into a compact per-room-type
    availability summary that would be suitable for Booking mapping.

    Input `rooms` is the list returned by /pms/rooms/availability, each item like:
    {
        'id': 'room-uuid',
        'room_number': '101',
        'room_type': 'Deluxe Double',
        'available': True/False,
        ...
    }

    Output is grouped per room_type:
    [
      {
        'room_type': 'Deluxe Double',
        'date_from': check_in,
        'date_to': check_out,
        'total_rooms': 10,
        'available_rooms': 7,
      },
      ...
    ]
    """
    by_type: Dict[str, Dict[str, Any]] = {}
    for room in rooms:
        rt = room.get('room_type') or 'Unknown'
        entry = by_type.setdefault(rt, {
            'room_type': rt,
            'date_from': check_in,
            'date_to': check_out,
            'total_rooms': 0,
            'available_rooms': 0,
        })
        entry['total_rooms'] += 1
        if room.get('available'):
            entry['available_rooms'] += 1

    return list(by_type.values())
