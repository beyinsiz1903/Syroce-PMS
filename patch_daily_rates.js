const fs = require('fs');
const file = 'backend/routers/reservation_detail.py';
let content = fs.readFileSync(file, 'utf8');

const oldCode = `    existing_rates = {
        str(row.get("date") or "")[:10]: row
        async for row in db.daily_rates.find(
            {"booking_id": booking_id, "tenant_id": tid},
            {"_id": 0, "date": 1, "rate": 1},
        )
    }
    for rate_entry in data.rates:`;

const newCode = `    existing_rates = {
        str(row.get("date") or "")[:10]: row
        async for row in db.daily_rates.find(
            {"booking_id": booking_id, "tenant_id": tid},
            {"_id": 0, "date": 1, "rate": 1},
        )
    }

    # Bug Fix: If daily_rates are missing in DB, they were generated on-the-fly for the frontend.
    # We must recreate them here to allow the frontend to submit the locked unchanged rates without triggering a 409.
    if not existing_rates and booking.get("check_in") and booking.get("check_out"):
        ci = _reservation_calendar_date(booking["check_in"])
        co = _reservation_calendar_date(booking["check_out"])
        if ci is not None and co is not None:
            nights = max((co - ci).days, 1)
            nightly_rate = round(booking.get("total_amount", 0) / nights, 2) if nights > 0 else 0
            current = ci
            for _ in range(nights):
                d_str = str(current)[:10]
                existing_rates[d_str] = {"date": current.isoformat(), "rate": nightly_rate}
                current = current + timedelta(days=1)

    for rate_entry in data.rates:`;

if (content.includes(oldCode)) {
    content = content.replace(oldCode, newCode);
    fs.writeFileSync(file, content);
    console.log("Patched reservation_detail.py successfully.");
} else {
    console.log("Could not find the target code in reservation_detail.py.");
}
