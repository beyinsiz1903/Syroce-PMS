# Security Hardening Backlog — Tenant-Pin Standardı

Son güncelleme: v106 round-9 kapanışı.

## Amaç

`update_one`/`delete_one`/`find_one_and_update` çağrılarında **tenant_id** filtresinin
her zaman bulunması (tenant izolasyonu için defense-in-depth standardı).

Round-8/9'da doğrudan IDOR riski olan 9 yer yamandı (housekeeping, departments,
pms_rooms, reports, cross_property, b2b_api). Bu dosya kalan ~100 yeri risk
sınıfına göre listeliyor — hiçbiri **bilinen exploit** değil; hepsi
defense-in-depth için kademeli olarak temizlenmeli.

---

## Risk Sınıflandırma Kuralı

| Sınıf | Tanım | Aciliyet |
|-------|-------|----------|
| **P0** | Kullanıcı girdisinden (path/body param) doğrudan tenant koleksiyonuna yazım, tenant_id filtresi YOK. | Bir sonraki turda kapatılmalı. |
| **P1** | Önce tenant-scoped `find_one` yapılıyor, sonra `_id` ile yazım. Mevcut akışta güvenli ama tenant pin yoksa regression riski yüksek. | Sonraki sprintte ele alınmalı. |
| **P2** | `current_user.id` veya benzeri self-scoped yazım (kullanıcı sadece kendini değiştiriyor). | Düşük öncelik. |
| **P3** | Background worker / migration / seed / arşiv işi. Dış saldırı yüzeyi yok. | Sadece kayıt amaçlı. |

---

## P0 — Doğrudan Kullanıcı Girdisi (öncelikli)

| Dosya:Satır | Kollek. | Notlar |
|-------------|---------|--------|
| `backend/domains/guest/checkin_router.py:68` | bookings | `request.booking_id` doğrudan |
| `backend/domains/guest/operations_router.py:476,709,721,1255` | bookings/rooms/guests | Path/body param |
| `backend/domains/guest/router.py:80,140` | guests | `guest_id` path param |
| `backend/domains/admin/router.py:411,793,1284` | users | `user_id` path param (admin route ama yine de) |
| `backend/domains/ai/router.py:2211,2241,2268` | guests | `guest_id` body param |
| `backend/domains/pms/enterprise_router.py:611,681` | tasks | `task_id` path param |
| `backend/domains/pms/misc_router.py:592,605` | payments/folios | `payment_id`/`folio_id` path |
| `backend/domains/pms/mobile/mobile_ops_service.py:29,34,52,54,55` | bookings/rooms | Service layer |
| `backend/domains/pms/mobile_router.py:1069` | rooms (update_many) | `room_ids` listesi |
| `backend/domains/revenue/analytics_router.py:1367,1396` | rooms | `room_id` body param |
| `backend/routers/finance/accounting.py:1167,1377` | folios/invoices | `folio_id`/`invoice_id` body |
| `backend/routers/finance/cashiering.py:144` | bookings | |
| `backend/routers/finance/dashboards.py:488` | folios | |
| `backend/routers/finance/folio.py:493,545,604,608,648,...` | folios | Folio operasyonları (6 yer) |
| `backend/routers/finance/konaklama_vergisi.py:566` | folios | |
| `backend/routers/pms_reservations.py:317` | bookings | |

## P1 — _id-pinned Sonrası Yazım (defense-in-depth)

`find_one({"tenant_id": ..., "id": ...})` ile önce kontrol var, sonra `_id` ile yazım.
Mevcut akışta güvenli ama refactor sırasında regression riski yüksek.

- `backend/routers/b2b_api.py:1406,1673,2192` (guests/bookings)
- `backend/scripts/migrate_exely_vault.py:64,84` (exely_connections)
- `backend/domains/pms/frontdesk_service.py:81,118,122,126,179,...` (~8 yer)
- `backend/domains/pms/frontdesk_service_v2.py:178,188,192,304,333,...` (~17 yer — **en büyük yüzey**)
- `backend/domains/pms/night_audit/service.py:271,298,308`
- `backend/domains/pms/groups_router.py:351`
- `backend/domains/pms/pos_fnb/pos_fnb_service_v2.py:242`
- `backend/domains/guest/experience_router.py:1973,2002`
- `backend/modules/guest_journey/guest_journey_service.py:45`
- `backend/modules/platform_scaling/multi_property_platform.py:164`
- `backend/modules/platform_scaling/revenue_autopricing.py:234`

## P2 — Self-scoped (düşük öncelik)

- `backend/routers/auth.py:186,796,815,880,946`
- `backend/routers/security_2fa.py:83,126,207,261`
- `backend/domains/pms/misc_router.py:1138`

## P3 — Background / Migration (kayıt amaçlı)

- `backend/celery_tasks.py:307,335`
- `backend/auto_seed.py:627,636,820`
- `backend/data_archival.py:81`
- `backend/core/atomic_checkin_checkout.py:11` (kod sembolü, gerçek yazım değil)
- `backend/scripts/migrate_hotel_id_username.py:92,124`
- `backend/domains/channel_manager/providers/exely/auto_import.py:418`

---

## Yanlış Pozitifler

Aşağıdaki yerler raporda görünüyor ama aslında tenant_id ile zaten korunuyorlar
(çok satırlı filter regex'i tarafından yanlış işaretlendi):

- `backend/routers/reservation_detail.py:1412,1414` — `{"id": ..., "tenant_id": tid}` mevcut
- `backend/routers/hotel_services.py:171` — koşullu filter, tenant_id var

---

## Tarama Komutu

```bash
python3 - <<'PY'
import re, pathlib
TENANT_COLLECTIONS = {
    "bookings","reservations","guests","rooms","folios","payments","users",
    "invoices","spa_services","spa_therapists","spa_appointments","mice_events",
    "loyalty_members","loyalty_transactions","tasks","alerts","exely_connections",
    "hotelrunner_connections","afsadakat_members","afsadakat_transactions",
}
for p in pathlib.Path("backend").rglob("*.py"):
    if "/tests/" in str(p) or "/load_tests/" in str(p): continue
    text = p.read_text(errors="ignore")
    for m in re.finditer(r'(\w+)\.(update_one|delete_one|update_many|delete_many|find_one_and_update|find_one_and_delete)\s*\(\s*(\{[^}]*\})', text):
        var, op, filt = m.group(1), m.group(2), m.group(3)
        if "tenant_id" in filt: continue
        coll_pat = re.search(rf'{re.escape(var)}\s*=\s*[\w\.]+\[\s*"(\w+)"\s*\]', text)
        coll = coll_pat.group(1) if coll_pat else var
        if coll in TENANT_COLLECTIONS:
            print(f"{p}:{text[:m.start()].count(chr(10))+1}  {coll}.{op}  {filt[:80]}")
PY
```

## Düzeltme Şablonu

```python
# Önce
await db.<collection>.update_one(
    {"id": some_id},
    {"$set": {...}},
)

# Sonra (P0/P1 için)
await db.<collection>.update_one(
    {"id": some_id, "tenant_id": current_user.tenant_id},
    {"$set": {...}},
)
```

Service layer (current_user yoksa) için `tenant_id` parametresini fonksiyon
imzasına ekleyip caller'dan geçirin.
