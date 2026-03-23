import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { BarChart3, BedDouble, Users, CalendarCheck, UserCheck } from 'lucide-react';

const TenantStatsPanel = ({ tenantId }) => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!tenantId) return;
    setLoading(true);
    axios.get(`/admin/tenants/${tenantId}/stats`)
      .then((res) => setStats(res.data))
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, [tenantId]);

  if (loading) return <div className="text-xs text-gray-400 py-2">İstatistikler yükleniyor...</div>;
  if (!stats) return null;

  const items = [
    { label: 'Oda', value: stats.rooms, icon: BedDouble, color: 'text-blue-600 bg-blue-50' },
    { label: 'Kullanıcı', value: stats.users, icon: Users, color: 'text-indigo-600 bg-indigo-50' },
    { label: 'Misafir', value: stats.guests, icon: UserCheck, color: 'text-green-600 bg-green-50' },
    { label: 'Toplam Rez.', value: stats.total_bookings, icon: CalendarCheck, color: 'text-purple-600 bg-purple-50' },
    { label: 'Bu Ay Rez.', value: stats.bookings_this_month, icon: BarChart3, color: 'text-amber-600 bg-amber-50' },
    { label: 'Check-in', value: stats.checked_in, icon: UserCheck, color: 'text-emerald-600 bg-emerald-50' },
  ];

  return (
    <div className="grid grid-cols-3 md:grid-cols-6 gap-2 mt-3" data-testid={`tenant-stats-${tenantId}`}>
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <div key={item.label} className="border rounded-lg px-2.5 py-2 flex items-center gap-2 bg-white">
            <div className={`rounded p-1 ${item.color}`}>
              <Icon className="w-3.5 h-3.5" />
            </div>
            <div>
              <p className="text-sm font-bold text-gray-900">{item.value}</p>
              <p className="text-[10px] text-gray-400">{item.label}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default TenantStatsPanel;
