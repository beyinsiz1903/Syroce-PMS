"""
Housekeeping Intelligence
Oda dağılımı optimizasyonu ve geçmiş kayıtlara dayalı temizlik süresi tahmini.

NOT: Temizlik süresi tahmini, tamamlanmış housekeeping görevlerinin gerçek
started_at/completed_at sürelerinden hesaplanır. Geçmiş yoksa sahte/rastgele
süre üretilmez; fail-closed döner (data_available:false).
"""
from datetime import datetime


class HousekeepingAI:
    """Geçmiş veriye dayalı housekeeping optimizasyonu."""

    def __init__(self, db):
        self.db = db

    async def _avg_durations_by_type(self, tenant_id: str) -> dict[str, dict]:
        """Tamamlanmış görevlerden oda tipine göre ortalama temizlik süresi (dk).

        started_at/completed_at gerçek zaman damgalarından hesaplanır; sahte
        değer üretilmez. Dönüş: {room_type: {'avg': float, 'count': int}}.
        """
        agg: dict[str, dict] = {}
        async for task in self.db.housekeeping_tasks.find(
            {'tenant_id': tenant_id, 'status': 'completed'},
            {'_id': 0, 'room_type': 1, 'started_at': 1, 'completed_at': 1},
        ):
            room_type = task.get('room_type')
            started = task.get('started_at')
            completed = task.get('completed_at')
            if not room_type or not started or not completed:
                continue
            try:
                minutes = (
                    datetime.fromisoformat(completed) - datetime.fromisoformat(started)
                ).total_seconds() / 60
            except (ValueError, TypeError):
                continue
            if minutes <= 0:
                continue
            entry = agg.setdefault(room_type, {'sum': 0.0, 'count': 0})
            entry['sum'] += minutes
            entry['count'] += 1
        return {
            rt: {'avg': v['sum'] / v['count'], 'count': v['count']}
            for rt, v in agg.items()
        }

    async def optimize_room_assignment(self, tenant_id: str, staff_list: list[dict]) -> list[dict]:
        """Kirli odaları personele iş yükü dengeli dağıt.

        Tahmini süre: oda tipi için gerçek geçmiş ortalaması varsa onu kullanır
        (estimate_basis='historical'); yoksa SAHTE süre üretilmez —
        estimated_minutes=None, estimate_basis='unavailable'. Rastgele jitter yoktur.
        İş yükü dengelemesi için yalnızca dahili (raporlanmayan) bir ağırlık kullanılır.
        """
        dirty_rooms = await self.db.rooms.find(
            {'tenant_id': tenant_id, 'status': 'dirty'}, {'_id': 0}
        ).to_list(100)

        if not dirty_rooms or not staff_list:
            return []

        stats = await self._avg_durations_by_type(tenant_id)
        # Denge ağırlığı: geçmiş yoksa bilinen tiplerin ortalaması, o da yoksa nötr 1.
        known_avgs = [s['avg'] for s in stats.values()] if stats else []
        balance_weight = (sum(known_avgs) / len(known_avgs)) if known_avgs else 1

        assignments = []
        staff_workload = {s['id']: 0 for s in staff_list}

        for room in dirty_rooms:
            available_staff = sorted(staff_list, key=lambda s: staff_workload[s['id']])
            if not available_staff:
                continue
            assigned_staff = available_staff[0]
            room_type = room.get('room_type', 'Standard')
            rt_stat = stats.get(room_type)
            if rt_stat:
                estimated_time = int(round(rt_stat['avg']))
                basis = 'historical'
                weight = estimated_time
            else:
                estimated_time = None
                basis = 'unavailable'
                weight = balance_weight

            assignments.append({
                'room_id': room['id'],
                'room_number': room['room_number'],
                'staff_id': assigned_staff['id'],
                'staff_name': assigned_staff['name'],
                'estimated_minutes': estimated_time,
                'estimate_basis': basis,
            })
            staff_workload[assigned_staff['id']] += weight

        return assignments

    async def predict_cleaning_time(self, tenant_id: str, room_type: str, staff_id: str) -> dict:
        """Oda tipi için temizlik süresi tahmini — gerçek geçmişten.

        Tamamlanmış görev geçmişi yoksa fail-closed (data_available:false);
        sabit confidence veya uydurma süre döndürülmez.
        """
        stats = await self._avg_durations_by_type(tenant_id)
        rt_stat = stats.get(room_type)
        if not rt_stat:
            return {
                'room_type': room_type,
                'data_available': False,
                'predicted_minutes': None,
                'sample_size': 0,
                'message': 'Bu oda tipi için tamamlanmış temizlik geçmişi yok. Tahmin üretilemedi.',
            }
        return {
            'room_type': room_type,
            'data_available': True,
            'predicted_minutes': round(rt_stat['avg'], 1),
            'sample_size': rt_stat['count'],
        }


# Global
housekeeping_ai = None


def get_housekeeping_ai(db):
    global housekeeping_ai
    if housekeeping_ai is None:
        housekeeping_ai = HousekeepingAI(db)
    return housekeeping_ai
