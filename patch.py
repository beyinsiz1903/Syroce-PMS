import re

with open("backend/routers/reservation_detail.py", "r") as f:
    content = f.read()

# 1. First lookup
old_lookup_1 = """    cari = await db.cari_accounts.find_one({"id": data.cari_account_id, "tenant_id": tid}, {"_id": 0})
    if not cari:
        raise HTTPException(status_code=404, detail="Cari hesap bulunamadı")"""

new_lookup_1 = """    cari = await db.cari_accounts.find_one({"id": data.cari_account_id, "tenant_id": tid}, {"_id": 0})
    is_city_ledger = False
    if not cari:
        cari = await db.city_ledger_accounts.find_one({"id": data.cari_account_id, "tenant_id": tid}, {"_id": 0})
        is_city_ledger = True
    if not cari:
        raise HTTPException(status_code=404, detail="Cari hesap bulunamadı")"""
content = content.replace(old_lookup_1, new_lookup_1)


# 2. Second lookup
old_lookup_2 = """        current_cari = await db.cari_accounts.find_one(
            {"id": data.cari_account_id, "tenant_id": tid},
            {"_id": 0},
            session=session,
        )
        if not current_cari:
            raise HTTPException(status_code=404, detail="Cari hesap bulunamadı")"""

new_lookup_2 = """        current_cari = await db.cari_accounts.find_one(
            {"id": data.cari_account_id, "tenant_id": tid},
            {"_id": 0},
            session=session,
        )
        if not current_cari:
            current_cari = await db.city_ledger_accounts.find_one(
                {"id": data.cari_account_id, "tenant_id": tid},
                {"_id": 0},
                session=session,
            )
        if not current_cari:
            raise HTTPException(status_code=404, detail="Cari hesap bulunamadı")"""
content = content.replace(old_lookup_2, new_lookup_2)

# 3. Transaction insertion
old_tx = """        transaction = {
            "id": transaction_id,
            "tenant_id": tid,
            "cari_account_id": data.cari_account_id,
            "booking_id": booking_id,
            "transaction_type": "charge",
            "amount": data.amount,
            "description": data.description or f"Rezervasyon {booking_id} - Cariye aktarım",
            "posted_by": current_user.name,
            "created_at": now,
        }
        await db.cari_transactions.insert_one({**transaction}, session=session)"""

new_tx = """        transaction = {
            "id": transaction_id,
            "tenant_id": tid,
            "booking_id": booking_id,
            "transaction_type": "charge",
            "amount": data.amount,
            "description": data.description or f"Rezervasyon {booking_id} - Cariye aktarım",
            "posted_by": current_user.name,
            "created_at": now,
        }
        if is_city_ledger:
            transaction["account_id"] = data.cari_account_id
            transaction["transaction_date"] = now
            await db.city_ledger_transactions.insert_one({**transaction}, session=session)
        else:
            transaction["cari_account_id"] = data.cari_account_id
            await db.cari_transactions.insert_one({**transaction}, session=session)"""
content = content.replace(old_tx, new_tx)

# 4. Balance update
old_bal = """        new_cari_balance = _cari_balance(current_cari) + data.amount
        await db.cari_accounts.update_one(
            {"id": data.cari_account_id, "tenant_id": tid},
            {
                "$set": {
                    "balance": new_cari_balance,
                    "current_balance": new_cari_balance,
                }
            },
            session=session,
        )"""

new_bal = """        if is_city_ledger:
            new_cari_balance = current_cari.get("current_balance", 0.0) + data.amount
            await db.city_ledger_accounts.update_one(
                {"id": data.cari_account_id, "tenant_id": tid},
                {"$set": {"current_balance": new_cari_balance}},
                session=session,
            )
        else:
            new_cari_balance = _cari_balance(current_cari) + data.amount
            await db.cari_accounts.update_one(
                {"id": data.cari_account_id, "tenant_id": tid},
                {
                    "$set": {
                        "balance": new_cari_balance,
                        "current_balance": new_cari_balance,
                    }
                },
                session=session,
            )"""
content = content.replace(old_bal, new_bal)

with open("backend/routers/reservation_detail.py", "w") as f:
    f.write(content)
