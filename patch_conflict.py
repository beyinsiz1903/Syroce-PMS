with open('backend/routers/cm_conflict_queue.py', 'r') as f:
    text = f.read()

text = text.replace('q = {**PENDING_QUERY, "tenant_id": current_user.tenant_id}', 'q = {**PENDING_QUERY}\n    if current_user.role != "super_admin":\n        q["tenant_id"] = current_user.tenant_id')

with open('backend/routers/cm_conflict_queue.py', 'w') as f:
    f.write(text)
