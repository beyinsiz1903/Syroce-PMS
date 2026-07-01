"""Seed section 7: housekeeping tasks (active for dirty/cleaning + history).

Reads ctx['rooms'] (already mutated by bookings.py). Writes ctx['tasks'].
"""

import random
from datetime import timedelta

from seed._helpers import _now, _uuid


async def seed_housekeeping(db, ctx):
    tenant_id = ctx["tenant_id"]
    rooms = ctx["rooms"]

    task_types = ["cleaning", "inspection", "deep_cleaning", "turndown"]
    priorities = ["low", "normal", "high", "urgent"]
    hk_staff = ["Maria H.", "Ana K.", "Carlos M.", "Elif Y.", "Fatma D."]
    tasks = []

    # Tasks for dirty/cleaning rooms
    for room in rooms:
        if room["status"] in ("dirty", "cleaning"):
            tasks.append(
                {
                    "id": _uuid(),
                    "tenant_id": tenant_id,
                    "room_id": room["id"],
                    "task_type": "cleaning",
                    "assigned_to": random.choice(hk_staff),
                    "status": "in_progress" if room["status"] == "cleaning" else "pending",
                    "priority": random.choice(["normal", "high"]),
                    "notes": None,
                    "started_at": _now().isoformat() if room["status"] == "cleaning" else None,
                    "completed_at": None,
                    "created_at": _now().isoformat(),
                }
            )

    # Additional random completed tasks (history)
    for _ in range(15):
        room = random.choice(rooms)
        completed_at = _now() - timedelta(hours=random.randint(1, 72))
        tasks.append(
            {
                "id": _uuid(),
                "tenant_id": tenant_id,
                "room_id": room["id"],
                "task_type": random.choice(task_types),
                "assigned_to": random.choice(hk_staff),
                "status": "completed",
                "priority": random.choice(priorities),
                "notes": random.choice([None, "Extra towels placed", "Minibar restocked", "Guest requested late checkout"]),
                "started_at": (completed_at - timedelta(minutes=random.randint(15, 60))).isoformat(),
                "completed_at": completed_at.isoformat(),
                "created_at": (completed_at - timedelta(minutes=random.randint(60, 180))).isoformat(),
            }
        )

    if tasks:
        await db.housekeeping_tasks.insert_many(tasks)
    ctx["tasks"] = tasks
