import hashlib
import json
import unicodedata


def normalize_string(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip()
    return unicodedata.normalize("NFC", s)

def compute_payload_fingerprint(lang: str, items: list) -> str:
    nl = lang.lower().strip()
    sorted_items = sorted(items, key=lambda x: x.service_code)

    canonical_items = []
    for it in sorted_items:
        c_item = {"service_code": it.service_code.strip()}
        if it.value:
            c_val = {}
            if it.value.quantity is not None:
                c_val["quantity"] = it.value.quantity
            if it.value.selected_options is not None:
                c_val["selected_options"] = sorted(it.value.selected_options)
            if it.value.date_value is not None:
                c_val["date_value"] = it.value.date_value
            if it.value.time_value is not None:
                c_val["time_value"] = it.value.time_value
            if it.value.datetime_value is not None:
                c_val["datetime_value"] = it.value.datetime_value
            if c_val:
                c_item["value"] = c_val
        n_note = normalize_string(it.note)
        if n_note:
            c_item["note"] = n_note
        canonical_items.append(c_item)

    payload = {"lang": nl, "items": canonical_items}
    compact_json = json.dumps(payload, separators=(',', ':'), sort_keys=True)
    return hashlib.sha256(compact_json.encode("utf-8")).hexdigest()

def generate_deterministic_description(input_type: str, validated_value: dict, guest_note: str | None, service_labels: dict | None, input_config: dict, lang: str, prop_lang: str) -> str:
    from domains.guest.qr_catalogue_service import process_lang
    # The description is reused as the staff-facing guest-request message.
    # Always lead with the human service label so one-tap requests never turn
    # into the context-free "Talep alındı." message.
    service_label = process_lang(service_labels, lang, prop_lang).strip()
    desc_lines = [service_label] if service_label else ["Misafir talebi"]

    if input_type == "quantity":
        qty = validated_value.get("quantity")
        if qty is not None:
            desc_lines.append(f"Miktar: {qty}")

    elif input_type in ("single_choice", "multi_choice"):
        selected = validated_value.get("selected_options", [])
        opts = input_config.get("options", [])

        labels_selected = []
        for code in selected:
            for opt in opts:
                if opt.get("code") == code:
                    labels_selected.append(process_lang(opt.get("labels"), lang, prop_lang))
                    break
        if labels_selected:
            desc_lines.append(f"Seçim: {', '.join(labels_selected)}")

    elif input_type == "date":
        d_str = validated_value.get("date_value")
        if d_str:
            desc_lines.append(f"Tarih: {d_str}")

    elif input_type == "time":
        t_str = validated_value.get("time_value")
        if t_str:
            desc_lines.append(f"Saat: {t_str}")

    elif input_type == "datetime":
        dt_str = validated_value.get("datetime_value")
        if dt_str:
            desc_lines.append(f"Tarih ve Saat: {dt_str[:16].replace('T', ' ')}")

    note = normalize_string(guest_note)
    if note:
        note = note.replace("<", "&lt;").replace(">", "&gt;")
        if len(note) > 1000:
            note = note[:1000] + "..."
        desc_lines.append(f"Not: {note}")

    return "\n".join(desc_lines)
