import json

with open("frontend/test-results-business/22-calendar-conflict-dialo-f1c33-faces-BookingConflictDialog-desktop/trace_unzipped/1-trace.trace", "r") as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get("type") == "action":
                m = data.get("metadata", {})
                print(f"Action: {m.get('method')} on {m.get('apiName')}")
                if "error" in m:
                    print(f"  Error: {m['error']}")
            elif data.get("type") == "event" and data.get("method") == "console":
                m = data.get("metadata", {})
                print(f"Console: {m.get('type')} - {m.get('text')}")
        except:
            pass
