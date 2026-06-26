"""
Revenue Autopilot - Tam Otomatik Fiyat Yönetimi (Kural Bazlı)
Otomatik rakip takip, fiyat optimizasyonu, OTA push.
Rastgele değer kullanılmaz; rakip fiyatları yalnızca gerçek competitor_rates
koleksiyonundan, doluluk gerçek rezervasyon/oda verisinden hesaplanır.
"""
from datetime import UTC, datetime


class RevenueAutopilot:
    """Otonom revenue management sistemi"""

    def __init__(self, db):
        self.db = db
        self.mode = 'supervised'  # full_auto, supervised, advisory

    async def daily_optimization_cycle(self, tenant_id: str) -> dict:
        """Günlük optimizasyon döngüsü"""
        report = {
            'cycle_date': datetime.now(UTC).isoformat(),
            'mode': self.mode,
            'actions': []
        }

        # Step 1: Scrape competitor rates (06:00)
        competitor_data = await self.scrape_competitor_rates(tenant_id)
        report['actions'].append({
            'time': '06:00',
            'action': 'Competitor rates scraped',
            'competitors_checked': len(competitor_data)
        })

        # Step 2: Update demand forecast (06:15)
        demand_update = await self.update_demand_forecast(tenant_id)
        report['actions'].append({
            'time': '06:15',
            'action': 'Demand forecast updated',
            'avg_occupancy_30d': demand_update['avg_occupancy']
        })

        # Step 3: Calculate optimal prices (06:30)
        optimal_prices = await self.calculate_optimal_prices(tenant_id, competitor_data, demand_update)
        report['actions'].append({
            'time': '06:30',
            'action': 'Optimal prices calculated' if optimal_prices else 'Optimal price calculation skipped',
            'price_changes': len(optimal_prices),
            'data_available': bool(optimal_prices),
            'message': None if optimal_prices else 'Gercek taban fiyat (oda base_price) yok; fiyat onerisi uretilmedi.'
        })

        # Step 4: Push to channels (06:45)
        if self.mode == 'full_auto':
            # Otonom karar: her oda tipi/tarih icin RATE_UPDATED olayini outbox'a
            # yaz. Mevcut acente fan-out zinciri bu olayi anonim olarak aktif
            # acentelere ulastirir. Idempotency anahtari (tenant:event:entity:
            # payload_hash) sayesinde ayni gunun yeniden tetiklenmesi (duplicate
            # beat tick / Celery retry) cift kayit uretmez.
            rate_events_emitted = await self._emit_rate_updated_events(
                tenant_id, optimal_prices
            )
            report['actions'].append({
                'time': '06:30',
                'action': (
                    'RATE_UPDATED events emitted'
                    if rate_events_emitted else
                    'No RATE_UPDATED events (no priced room types)'
                ),
                'rate_events_emitted': rate_events_emitted,
            })

            push_result = await self.push_rates_to_channels(tenant_id, optimal_prices)
            report['actions'].append({
                'time': '06:45',
                'action': 'Rate push attempted',
                'channels': push_result['channels'],
                'status': 'completed' if push_result.get('success') else 'not_implemented'
            })
        else:
            report['actions'].append({
                'time': '06:45',
                'action': 'Rate recommendations generated',
                'status': 'pending_approval'
            })

        return report

    async def _emit_rate_updated_events(
        self, tenant_id: str, optimal_prices: list[dict]
    ) -> int:
        """Her oda tipi icin (bugunun tarihiyle) RATE_UPDATED olayini outbox'a yaz.

        Sadece ``full_auto`` modunda cagrilir. entity_id oda tipini icerir, boylece
        farkli oda tipleri ayri outbox kayitlari (ve ayri acente fan-out'lari) olur.
        Idempotency: enqueue_outbox_event'in varsayilan
        tenant+event+entity_id+payload_hash anahtari (ai_pricing.py ile ayni kalip)
        ayni hesabin tekrar gonderimini DuplicateKey ile yutar.
        """
        if not optimal_prices:
            return 0
        from core.outbox_service import RATE_UPDATED, enqueue_outbox_event

        target_date = datetime.now(UTC).strftime('%Y-%m-%d')
        count = 0
        for p in optimal_prices:
            room_type = p.get('room_type')
            recommended_rate = p.get('optimal_price')
            if not room_type or recommended_rate is None:
                continue
            await enqueue_outbox_event(
                self.db,
                tenant_id=tenant_id,
                event_type=RATE_UPDATED,
                entity_type='revenue_autopilot',
                entity_id=f"{tenant_id}:{target_date}:{room_type}",
                payload={
                    'date': target_date,
                    'room_type': room_type,
                    'recommended_rate': recommended_rate,
                    'strategy': 'autopilot',
                    'source': 'revenue_autopilot',
                },
            )
            count += 1
        return count

    async def scrape_competitor_rates(self, tenant_id: str) -> list[dict]:
        """Rakip fiyatlarını yalnızca gerçek competitor_rates koleksiyonundan oku.

        Kayıt yoksa boş liste döner; uydurma/rastgele rakip fiyatı üretilmez.
        """
        today = datetime.now(UTC).strftime('%Y-%m-%d')
        docs = await self.db.competitor_rates.find({
            'tenant_id': tenant_id,
            'date': today,
        }, {'_id': 0}).to_list(100)

        competitors = []
        for d in docs:
            name = d.get('competitor_name') or d.get('competitor')
            rate = d.get('rate')
            if name is None or rate is None:
                continue
            entry = {'hotel': name, 'rate': round(float(rate), 2)}
            # Rakip kaydi bir oda tipine eslenmisse onu tasi; per-room_type
            # fiyatlamada o tipe oncelikli, eslenmemisse genel ortalamaya duser.
            room_type = d.get('room_type')
            if room_type:
                entry['room_type'] = room_type
            competitors.append(entry)
        return competitors

    async def update_demand_forecast(self, tenant_id: str) -> dict:
        """Talep tahminini gerçek doluluk verisinden deterministik hesapla."""
        total_rooms = await self.db.rooms.count_documents({'tenant_id': tenant_id})
        occupied = await self.db.rooms.count_documents({
            'tenant_id': tenant_id,
            'status': 'occupied',
        })
        avg_occupancy = round((occupied / total_rooms) * 100, 1) if total_rooms > 0 else 0.0
        trend = 'increasing' if avg_occupancy >= 70 else 'stable' if avg_occupancy >= 40 else 'decreasing'
        return {
            'avg_occupancy': avg_occupancy,
            'trend': trend,
        }

    async def calculate_optimal_prices(self, tenant_id: str, competitor_data: list, demand_data: dict) -> list[dict]:
        """Optimal fiyatlari kural bazli (deterministik), oda tipi (room_type)
        bazinda hesapla.

        Odalar ``room_type`` alanina gore gruplanir; her tip icin ayri taban
        fiyat (o tipin gercek base_price ortalamasi) + ortak talep carpani +
        (varsa) o tipe eslenmis rakip ortalamasi ile optimal fiyat uretilir.
        Rakip verisi oda tipine eslenebiliyorsa o tipe, eslenemiyorsa genel
        rakip ortalamasina duser.

        Fail-closed: gercek taban fiyat (base_price > 0) olmayan oda tipleri icin
        oneri uretilmez; hicbir tipte gecerli taban fiyat yoksa bos liste doner.
        """
        rooms = await self.db.rooms.find(
            {'tenant_id': tenant_id, 'base_price': {'$gt': 0}},
            {'_id': 0, 'room_type': 1, 'base_price': 1},
        ).to_list(10000)

        # Oda tipine gore gercek taban fiyatlari topla (fail-closed: base_price>0).
        base_by_type: dict[str, list[float]] = {}
        for r in rooms:
            room_type = r.get('room_type')
            bp = r.get('base_price')
            if not room_type or bp is None:
                continue
            bp = float(bp)
            if bp <= 0:
                continue
            base_by_type.setdefault(room_type, []).append(bp)

        if not base_by_type:
            # Gercek taban fiyat yok -> fail-closed (oneri uretme)
            return []

        demand_factor = 1.2 if demand_data['avg_occupancy'] > 75 else 1.0

        # Rakip oranlarini oda tipine gore ayir + genel ortalama (fallback).
        comp_by_type: dict[str, list[float]] = {}
        all_comp_rates: list[float] = []
        for c in competitor_data:
            rate = c.get('rate')
            if rate is None:
                continue
            rate = float(rate)
            all_comp_rates.append(rate)
            room_type = c.get('room_type')
            if room_type:
                comp_by_type.setdefault(room_type, []).append(rate)
        global_comp_avg = (
            sum(all_comp_rates) / len(all_comp_rates) if all_comp_rates else None
        )

        results: list[dict] = []
        # Deterministik sira (oda tipi adina gore) — tekrar calismalarda ayni cikti.
        for room_type in sorted(base_by_type):
            prices = base_by_type[room_type]
            base_price = round(sum(prices) / len(prices), 2)

            type_rates = comp_by_type.get(room_type)
            if type_rates:
                competitor_avg = sum(type_rates) / len(type_rates)
                optimal_price = competitor_avg * demand_factor
                applied_rule = (
                    f"Oda tipi '{room_type}' rakip ort. {round(competitor_avg, 2)} "
                    f"x talep carpani {demand_factor} "
                    f"(doluluk %{demand_data['avg_occupancy']})"
                )
            elif global_comp_avg is not None:
                competitor_avg = global_comp_avg
                optimal_price = competitor_avg * demand_factor
                applied_rule = (
                    f"Oda tipi '{room_type}' (tipe ozel rakip yok) genel rakip ort. "
                    f"{round(competitor_avg, 2)} x talep carpani {demand_factor} "
                    f"(doluluk %{demand_data['avg_occupancy']})"
                )
            else:
                # Rakip verisi yok: yalnizca taban fiyat + talep carpani
                optimal_price = base_price * demand_factor
                applied_rule = (
                    f"Oda tipi '{room_type}' rakip verisi yok -> taban {base_price} "
                    f"x talep carpani {demand_factor} "
                    f"(doluluk %{demand_data['avg_occupancy']})"
                )

            results.append({
                'room_type': room_type,
                'current_price': base_price,
                'optimal_price': round(optimal_price, 2),
                'change_pct': round(((optimal_price - base_price) / base_price) * 100, 1),
                'pricing_method': 'rule_based_deterministic',
                'applied_rule': applied_rule,
            })

        return results

    async def push_rates_to_channels(self, tenant_id: str, optimal_prices: list[dict]) -> dict:
        """Fiyatlari kanallara gonder.

        Gercek OTA push entegrasyonu (booking.com/expedia/gds HTTP API) henuz
        uygulanmadi. Sahte 'success' uretmek yerine fail-closed don; cagiran
        akis bunu 'not_implemented' olarak raporlar.
        """
        return {
            'success': False,
            'data_available': False,
            'channels': [],
            'updated_count': 0,
            'message': 'Kanal fiyat push entegrasyonu henuz uygulanmadi; fiyat gonderilmedi.',
        }

# Global instance
autopilot = None

def get_revenue_autopilot(db):
    global autopilot
    if autopilot is None:
        autopilot = RevenueAutopilot(db)
    return autopilot
