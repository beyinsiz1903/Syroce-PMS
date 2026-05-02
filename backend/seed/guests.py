"""Seed section 4: guests (50 records, encrypted PII).

Writes ctx['guests'].
"""
import random
from datetime import timedelta

from seed._helpers import _encrypt_doc, _now, _uuid


async def seed_guests(db, ctx):
    tenant_id = ctx["tenant_id"]
    first_names_m = ["Ahmet", "Mehmet", "Ali", "Murat", "Emre", "Can", "Burak", "Serkan", "Oğuz", "Kerem",
                     "John", "Michael", "David", "James", "Robert", "William", "Thomas", "Daniel", "Hans", "Pierre"]
    first_names_f = ["Ayşe", "Fatma", "Elif", "Zeynep", "Selin", "Merve", "Deniz", "Ece", "İrem", "Başak",
                     "Emma", "Sophia", "Olivia", "Anna", "Maria", "Sophie", "Lisa", "Julia", "Elena", "Laura"]
    last_names = ["Yılmaz", "Kaya", "Demir", "Çelik", "Şahin", "Öztürk", "Aydın", "Arslan", "Doğan", "Kılıç",
                  "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Müller", "Dubois", "Rossi"]
    nationalities = ["TR", "TR", "TR", "TR", "DE", "GB", "US", "FR", "RU", "IT", "NL", "JP"]

    guests = []
    for i in range(50):
        if i % 2 == 0:
            first = random.choice(first_names_m)
        else:
            first = random.choice(first_names_f)
        last = random.choice(last_names)
        nat = random.choice(nationalities)

        guest = {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "name": f"{first} {last}",
            "email": f"{first.lower()}.{last.lower()}{i}@email.com",
            "phone": f"+{random.choice(['90','49','44','1','33','7','39'])}{random.randint(1000000000,9999999999)}",
            "id_number": f"{random.randint(10000000000,99999999999)}",
            "nationality": nat,
            "address": None,
            "vip_status": random.random() < 0.1,
            "loyalty_points": random.randint(0, 5000),
            "total_stays": random.randint(0, 15),
            "total_spend": round(random.uniform(0, 15000), 2),
            "notes": None,
            "created_at": (_now() - timedelta(days=random.randint(1, 365))).isoformat(),
        }
        guests.append(guest)

    guests = [_encrypt_doc(g, "guests") for g in guests]
    await db.guests.insert_many(guests)
    ctx["guests"] = guests
