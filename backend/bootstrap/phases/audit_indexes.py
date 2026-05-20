"""R5 Index Audit — top 25 koleksiyon için kapsama eksiklerini gideren index'ler.

Audit (DB_NAME=syroce-pms, 2026-05-03) sonucunda kapsamayan 11 index tespit edildi:
- tenants.id, outbox_events(status,created_at), night_audit_runs(tenant,run_date),
  cm_imported_reservations(tenant,external_id), accounting_invoices(tenant_id),
  room_night_locks(tenant,date,room_id), ops_events(tenant,created_at),
  cp_failures(tenant,created_at), tenant_settings(tenant_id),
  kbs_reports(tenant,report_date), room_blocks(tenant,start_date,end_date)

Idempotent: zaten varsa sessizce geçer; oluşturulan adet döner.
"""
import logging

from core.database import _raw_db

logger = logging.getLogger(__name__)

_AUDIT_INDEXES: list[tuple[str, list[tuple[str, int]], str, dict]] = [
    ("tenants", [("id", 1)], "idx_tenant_id", {}),
    ("outbox_events", [("status", 1), ("created_at", 1)], "idx_outbox_status_created", {}),
    ("night_audit_runs", [("tenant_id", 1), ("run_date", -1)], "idx_night_audit_run_date", {}),
    ("cm_imported_reservations", [("tenant_id", 1), ("external_id", 1)], "idx_cm_imp_external", {}),
    ("accounting_invoices", [("tenant_id", 1)], "idx_acc_invoices_tenant", {}),
    # F8N (2026-05) — Field was "date" historically, but atomic_booking writes
    # "night_date". Renamed key + index name so this read-cover index actually
    # matches the documents. The unique guard lives in `ux_room_night`
    # (see core.atomic_booking.ensure_booking_indexes); this entry is purely a
    # secondary cover for time-window queries.
    ("room_night_locks", [("tenant_id", 1), ("night_date", 1), ("room_id", 1)], "idx_rnl_tenant_night_room", {}),
    ("ops_events", [("tenant_id", 1), ("created_at", -1)], "idx_ops_events_tenant_created", {}),
    ("cp_failures", [("tenant_id", 1), ("created_at", -1)], "idx_cp_failures_tenant_created", {}),
    ("tenant_settings", [("tenant_id", 1)], "idx_tenant_settings_tenant", {}),
    ("kbs_reports", [("tenant_id", 1), ("report_date", -1)], "idx_kbs_reports_tenant_date", {}),
    ("room_blocks", [("tenant_id", 1), ("start_date", 1), ("end_date", 1)], "idx_room_blocks_tenant_range", {}),
]


async def ensure_audit_indexes() -> int:
    """R5 audit derived index'leri idempotent oluşturur. Yeni oluşturulan adedi döner.

    create_index zaten varsa hata atmaz; gerçek "yeni" sayısı için pre/post
    index_information karşılaştırması yapılır (architect kalite önerisi).
    """
    created = 0
    for coll, keys, name, kwargs in _AUDIT_INDEXES:
        try:
            existing_before = await _raw_db[coll].index_information()
            await _raw_db[coll].create_index(keys, name=name, background=True, **kwargs)
            if name not in existing_before:
                created += 1
        except Exception as e:
            msg = str(e).lower()
            if "already exists" in msg or "indexoptionsconflict" in msg:
                continue
            logger.warning(f"R5 audit index {name} on {coll} failed: {e}")
    return created
