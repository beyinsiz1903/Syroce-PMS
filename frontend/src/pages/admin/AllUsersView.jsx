import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { Search, ChevronLeft, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ROLE_LABELS } from './tenantConstants';
import { useTranslation } from 'react-i18next';

const AllUsersView = ({ onBack, tenants }) => {
  const { t } = useTranslation();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const res = await axios.get('/admin/users');
        setUsers(res.data?.users || []);
      } catch {
        // silently fail
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const tenantMap = useMemo(() => {
    const m = {};
    (tenants || []).forEach((t) => { m[t.id] = t.property_name || t.name || '—'; });
    return m;
  }, [tenants]);

  const roleCounts = useMemo(() => {
    const c = {};
    users.forEach((u) => { c[u.role] = (c[u.role] || 0) + 1; });
    return c;
  }, [users]);

  const filtered = useMemo(() => {
    return users.filter((u) => {
      const nameMatch = !filter || (u.name || '').toLowerCase().includes(filter.toLowerCase()) || (u.email || '').toLowerCase().includes(filter.toLowerCase());
      const roleMatch = roleFilter === 'all' || u.role === roleFilter;
      return nameMatch && roleMatch;
    });
  }, [users, filter, roleFilter]);

  const roleColors = {
    super_admin: 'bg-red-100 text-red-700',
    admin: 'bg-indigo-100 text-indigo-700',
    front_desk: 'bg-green-100 text-green-700',
    housekeeping: 'bg-yellow-100 text-yellow-700',
    manager: 'bg-blue-100 text-blue-700',
    revenue: 'bg-indigo-100 text-indigo-700',
    finance: 'bg-emerald-100 text-emerald-700',
    sales: 'bg-amber-100 text-amber-700',
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onBack} data-testid="users-back-btn">
          <ChevronLeft className="w-4 h-4 mr-1" /> Geri
        </Button>
        <h2 className="text-lg font-bold text-gray-900">{t('cm.pages_admin_AllUsersView.tum_kullanicilar')}{users.length})</h2>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          className={`px-3 py-1.5 text-xs rounded-full border transition ${roleFilter === 'all' ? 'bg-gray-900 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
          onClick={() => setRoleFilter('all')}
        >{t('cm.pages_admin_AllUsersView.tumu')}{users.length})</button>
        {Object.entries(roleCounts).sort((a, b) => b[1] - a[1]).map(([role, count]) => (
          <button
            key={role}
            className={`px-3 py-1.5 text-xs rounded-full border transition ${roleFilter === role ? 'bg-gray-900 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
            onClick={() => setRoleFilter(roleFilter === role ? 'all' : role)}
          >{ROLE_LABELS[role] || role} ({count})</button>
        ))}
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          data-testid="users-search"
          type="text"
          placeholder="Ad veya e-posta ile ara..."
          className="w-full border rounded-lg pl-10 pr-3 py-2 text-sm"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-400 text-sm">{t('cm.pages_admin_AllUsersView.yukleniyor')}</div>
      ) : (
        <div className="bg-white border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500">{t('cm.pages_admin_AllUsersView.kullanici')}</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500">E-posta</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500">Otel</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500">Rol</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500">{t('cm.pages_admin_AllUsersView.durum')}</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {filtered.map((u) => (
                <tr key={u.id} className="hover:bg-gray-50/50">
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-full bg-gray-100 flex items-center justify-center text-xs font-bold text-gray-500">
                        {(u.name || '?')[0].toUpperCase()}
                      </div>
                      <span className="font-medium text-gray-900">{u.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-gray-500">{u.email}</td>
                  <td className="px-4 py-2.5 text-gray-500 text-xs">{tenantMap[u.tenant_id] || u.tenant_id?.substring(0, 8)}</td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${roleColors[u.role] || 'bg-gray-100 text-gray-600'}`}>
                      <ShieldCheck className="w-3 h-3" />
                      {ROLE_LABELS[u.role] || u.role}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`text-xs ${u.is_active !== false ? 'text-green-600' : 'text-red-500'}`}>
                      {u.is_active !== false ? 'Aktif' : 'Pasif'}
                    </span>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={5} className="text-center py-8 text-gray-400">{t('cm.pages_admin_AllUsersView.kullanici_bulunamadi')}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default AllUsersView;
