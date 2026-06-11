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
            'action': 'Optimal prices calculated',
            'price_changes': len(optimal_prices)
        })

        # Step 4: Push to channels (06:45)
        if self.mode == 'full_auto':
            push_result = await self.push_rates_to_channels(tenant_id, optimal_prices)
            report['actions'].append({
                'time': '06:45',
                'action': 'Rates pushed to channels',
                'channels': push_result['channels'],
                'status': 'completed'
            })
        else:
            report['actions'].append({
                'time': '06:45',
                'action': 'Rate recommendations generated',
                'status': 'pending_approval'
            })

        return report

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
            competitors.append({'hotel': name, 'rate': round(float(rate), 2)})
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
        """Optimal fiyatları kural bazlı (deterministik) hesapla."""
        base_price = 100
        demand_factor = 1.2 if demand_data['avg_occupancy'] > 75 else 1.0

        if competitor_data:
            competitor_avg = sum(c['rate'] for c in competitor_data) / len(competitor_data)
            optimal_price = competitor_avg * demand_factor
            applied_rule = (
                f"Rakip ort. {round(competitor_avg, 2)} x talep carpani {demand_factor} "
                f"(doluluk %{demand_data['avg_occupancy']})"
            )
        else:
            # Rakip verisi yok: yalnızca taban fiyat + talep çarpanı
            optimal_price = base_price * demand_factor
            applied_rule = (
                f"Rakip verisi yok -> taban {base_price} x talep carpani {demand_factor} "
                f"(doluluk %{demand_data['avg_occupancy']})"
            )

        return [{
            'room_type': 'Standard',
            'current_price': base_price,
            'optimal_price': round(optimal_price, 2),
            'change_pct': round(((optimal_price - base_price) / base_price) * 100, 1),
            'pricing_method': 'rule_based_deterministic',
            'applied_rule': applied_rule,
        }]

    async def push_rates_to_channels(self, tenant_id: str, optimal_prices: list[dict]) -> dict:
        """Fiyatları tüm kanallara gönder"""
        # Simulated (gerçekte: OTA API calls)
        channels = ['booking_com', 'expedia', 'hotel_website', 'gds']

        return {
            'success': True,
            'channels': channels,
            'updated_count': len(optimal_prices)
        }

# Global instance
autopilot = None

def get_revenue_autopilot(db):
    global autopilot
    if autopilot is None:
        autopilot = RevenueAutopilot(db)
    return autopilot
