"""
Rule-Based Pricing Engine (Kural Bazlı Fiyatlandırma)
Deterministik fiyat önerisi: gerçek doluluk + hafta sonu + aciliyet kuralları.
Rakip fiyatları yalnızca gerçek competitor_rates koleksiyonundan okunur.
Rastgele (random) değer kullanılmaz; aynı girdi her zaman aynı çıktıyı verir.
"""

from datetime import UTC, datetime


class DynamicPricingEngine:
    """Kural bazlı (deterministik) fiyatlandırma motoru"""

    def __init__(self, db):
        self.db = db

    async def _resolve_base_price(self, tenant_id: str, room_type: str | None = None) -> float | None:
        """Taban fiyatı GERÇEK oda kayıtlarından türet (uydurma sabit yok).

        Önce verilen oda tipinin yapılandırılmış base_price ortalaması; yoksa
        çağıran mülk geneline düşebilir. Hiç gerçek fiyat yoksa None döner
        (fail-closed) — asla sabit bir sayı uydurulmaz.
        """
        query: dict = {"tenant_id": tenant_id, "base_price": {"$gt": 0}}
        if room_type:
            query["room_type"] = room_type
        prices = []
        rows = await self.db.rooms.find(query, {"_id": 0, "base_price": 1}).to_list(5000)
        for r in rows:
            bp = r.get("base_price")
            try:
                bp = float(bp)
            except (TypeError, ValueError):
                continue
            if bp > 0:
                prices.append(bp)
        if not prices:
            return None
        return round(sum(prices) / len(prices), 2)

    async def get_competitor_rates(self, tenant_id: str, date: str, room_type: str) -> dict:
        """Rakip otel fiyatlarını yalnızca gerçek competitor_rates koleksiyonundan getir.

        Kayıt yoksa available=False döner; uydurma/rastgele rakip fiyatı üretilmez.
        """
        docs = await self.db.competitor_rates.find(
            {
                "tenant_id": tenant_id,
                "date": date,
                "room_type": room_type,
            },
            {"_id": 0},
        ).to_list(50)

        competitors = {}
        for d in docs:
            name = d.get("competitor_name") or d.get("competitor")
            rate = d.get("rate")
            if name is None or rate is None:
                continue
            competitors[name] = round(float(rate), 2)

        if not competitors:
            return {
                "available": False,
                "competitors": {},
                "average": None,
                "min": None,
                "max": None,
            }

        values = list(competitors.values())
        avg_competitor = sum(values) / len(values)
        return {
            "available": True,
            "competitors": competitors,
            "average": round(avg_competitor, 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
        }

    async def calculate_demand_factors(self, tenant_id: str, target_date: str) -> dict:
        """Talep faktörlerini gerçek girdilerden deterministik hesapla."""
        # Parse target date with timezone
        if "T" in target_date:
            target = datetime.fromisoformat(target_date.replace("Z", "+00:00"))
        else:
            target = datetime.fromisoformat(target_date).replace(tzinfo=UTC)

        # Day of week factor
        day_of_week = target.weekday()
        weekend_factor = 1.3 if day_of_week >= 4 else 1.0  # Fri-Sun

        # Occupancy forecast (gerçek on-the-books)
        total_rooms = await self.db.rooms.count_documents({"tenant_id": tenant_id})
        booked = await self.db.bookings.count_documents(
            {"tenant_id": tenant_id, "check_in": {"$lte": target_date}, "check_out": {"$gt": target_date}, "status": {"$in": ["confirmed", "guaranteed", "checked_in"]}}
        )

        occupancy = (booked / total_rooms) if total_rooms > 0 else 0
        demand_factor = 1.4 if occupancy > 0.85 else 1.2 if occupancy > 0.7 else 1.0 if occupancy > 0.5 else 0.9

        # Days until arrival
        days_until = (target - datetime.now(UTC)).days
        urgency_factor = 1.3 if days_until <= 3 else 1.1 if days_until <= 7 else 1.0

        # Etkinlik faktörü: gerçek etkinlik verisi entegre edilene kadar nötr (1.0).
        event_factor = 1.0

        return {"weekend_factor": weekend_factor, "demand_factor": demand_factor, "urgency_factor": urgency_factor, "event_factor": event_factor, "occupancy_forecast": round(occupancy * 100, 2)}

    def _describe_rules(self, demand: dict) -> list[str]:
        """Uygulanan kuralları insan-okur biçimde açıkla."""
        rules = []
        occ = demand["occupancy_forecast"]
        df = demand["demand_factor"]
        if df > 1.0:
            rules.append(f"Doluluk %{occ} -> talep carpani x{df}")
        elif df < 1.0:
            rules.append(f"Dusuk doluluk %{occ} -> talep carpani x{df}")
        else:
            rules.append(f"Doluluk %{occ} -> talep carpani x{df}")
        if demand["weekend_factor"] > 1.0:
            rules.append(f"Hafta sonu -> x{demand['weekend_factor']}")
        if demand["urgency_factor"] > 1.0:
            rules.append(f"Yaklasan tarih -> aciliyet x{demand['urgency_factor']}")
        return rules

    async def recommend_price(self, tenant_id: str, room_type: str, target_date: str) -> dict:
        """Kural bazlı (deterministik) fiyat önerisi."""
        # Rakip verisi (yalnızca gerçek kayıtlardan)
        comp_data = await self.get_competitor_rates(tenant_id, target_date, room_type)

        # Talep faktörleri
        demand = await self.calculate_demand_factors(tenant_id, target_date)

        # Taban fiyat GERÇEK oda kayıtlarından — uydurma sabit yok.
        base_price = await self._resolve_base_price(tenant_id, room_type)
        base_note = None
        if base_price is None:
            # Oda tipi için fiyat yok -> mülk geneli gerçek ortalamaya düş.
            base_price = await self._resolve_base_price(tenant_id, None)
            if base_price is not None:
                base_note = f"Oda tipi '{room_type}' icin taban fiyat yok -> mulk geneli ortalama ({base_price}) kullanildi"
        if base_price is None:
            # Hic gercek taban fiyat yok -> fail-closed (oneri uretilemez).
            return {
                "room_type": room_type,
                "target_date": target_date,
                "recommended_price": None,
                "min_price": None,
                "max_price": None,
                "pricing_method": "base_price_unavailable",
                "applied_rules": ["Gercek oda taban fiyati yapilandirilmamis -> fiyat onerisi uretilemedi"],
                "competitor_data": comp_data,
                "demand_factors": demand,
                "current_price": None,
                "price_change_pct": None,
                "data_available": False,
            }

        # Önerilen fiyatı hesapla
        total_factor = demand["weekend_factor"] * demand["demand_factor"] * demand["urgency_factor"] * demand["event_factor"]

        recommended = base_price * total_factor

        applied_rules = self._describe_rules(demand)
        if base_note:
            applied_rules.insert(0, base_note)

        # Rakip ortalamasına göre ayarla (yalnızca gerçek rakip verisi varsa)
        competitor_avg = comp_data["average"] if comp_data.get("available") else None
        if competitor_avg is not None and abs(recommended - competitor_avg) > competitor_avg * 0.3:
            # Piyasadan %30'dan fazla sapma
            recommended = (recommended + competitor_avg) / 2
            applied_rules.append(f"Rakip ortalamasi {competitor_avg} -> piyasaya yaklastirildi (%30 sapma siniri)")
        elif competitor_avg is None:
            applied_rules.append("Rakip verisi yok -> rakip ayari uygulanmadi")

        min_price = recommended * 0.85
        max_price = recommended * 1.25

        return {
            "room_type": room_type,
            "target_date": target_date,
            "recommended_price": round(recommended, 2),
            "min_price": round(min_price, 2),
            "max_price": round(max_price, 2),
            "pricing_method": "rule_based_deterministic",
            "applied_rules": applied_rules,
            "competitor_data": comp_data,
            "demand_factors": demand,
            "current_price": base_price,
            "price_change_pct": round(((recommended - base_price) / base_price) * 100, 2),
            "data_available": True,
        }


# Global instance
pricing_engine = None


def get_pricing_engine(db):
    global pricing_engine
    if pricing_engine is None:
        pricing_engine = DynamicPricingEngine(db)
    return pricing_engine
