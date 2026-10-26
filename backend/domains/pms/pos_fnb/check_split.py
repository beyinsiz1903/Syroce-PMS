"""Check split preview. An already paid source transaction is immutable."""

from fastapi import HTTPException

from .folio_lines import allocate
from .order_pricing import rounded


def split_number(value, fallback):
    try:
        return int(value)
    except (ValueError, TypeError):
        return fallback


def preview(transaction, split_type, split_count=2, details=None):
    total = rounded(transaction.get("total_amount"))
    if total < 0 or transaction.get("payment_type") == "refund":
        raise HTTPException(409, "İade hareketi bölünemez.")
    splits = []
    if split_type == "equal":
        if not isinstance(split_count, int) or not 1 <= split_count <= 100:
            raise HTTPException(422, "Bölme sayısı 1–100 olmalı.")
        splits = [{"split_number": i + 1, "amount": amount, "items": "Eşit pay"} for i, amount in enumerate(allocate(total, [1] * split_count))]
    elif split_type == "custom":
        if not isinstance(details, dict) or not details or len(details) > 100:
            raise HTTPException(422, "Özel bölme tutarlarını girin.")
        for index, (number, value) in enumerate(details.items(), 1):
            value = rounded(value)
            if value < 0:
                raise HTTPException(422, "Pay negatif olamaz.")
            splits.append({"split_number": split_number(number, index), "amount": float(value), "items": "Özel pay"})
    elif split_type == "by_item":
        items = transaction.get("order_items") or transaction.get("items") or []
        if not isinstance(details, dict) or not details or not items:
            raise HTTPException(422, "Ürün gruplarını seçin.")
        groups, seen = [], set()
        for group_index, (number, indices) in enumerate(details.items(), 1):
            if not isinstance(indices, list) or not indices:
                raise HTTPException(422, "Boş ürün grubu olamaz.")
            converted = []
            for raw_index in indices:
                # Form controls historically send decimal indices as strings.
                index = int(raw_index) if isinstance(raw_index, str) and raw_index.isdecimal() else raw_index
                if type(index) is not int or index < 0 or index >= len(items) or index in seen:
                    raise HTTPException(422, "Her ürün yalnız bir grupta olmalı; ürün sırası geçersiz.")
                seen.add(index)
                converted.append(index)
            weight = sum(
                rounded(items[i].get("total", items[i].get("total_price", rounded(items[i].get("unit_price", items[i].get("price"))) * rounded(items[i].get("quantity", 1)))))
                * (1 + rounded(items[i].get("tax_rate")))
                for i in converted
            )
            groups.append((split_number(number, group_index), converted, weight))
        if len(seen) != len(items):
            raise HTTPException(422, "Adisyondaki bütün ürünler gruplara dağıtılmalı.")
        amounts = allocate(total, [group[2] for group in groups])
        splits = [{"split_number": number, "amount": amount, "items": [items[i].get("item_name") or items[i].get("name") for i in indices]} for (number, indices, _), amount in zip(groups, amounts)]
    else:
        raise HTTPException(422, "Geçersiz bölme yöntemi.")
    actual = sum((rounded(row["amount"]) for row in splits), rounded(0))
    if actual != total:
        raise HTTPException(422, "Payların toplamı adisyon toplamına eşit olmalı.")
    return {
        "success": True,
        "preview_only": True,
        "original_transaction_id": transaction["id"],
        "original_amount": float(total),
        "split_type": split_type,
        "split_count": len(splits),
        "splits": splits,
        "total_validation": {"expected": float(total), "actual": float(actual), "delta": 0, "match": True},
        "notice": "Paylaştırma önizlemesidir; ödenmiş fiş veya muhasebe kaydı değiştirilmedi.",
    }
