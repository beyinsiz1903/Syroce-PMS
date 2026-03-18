import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Badge } from '@/components/ui/badge';
import { Loader2, Shield, Banknote, RefreshCw } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function DepositTracking({ user, tenant, onLogout }) {
  const [deposits, setDeposits] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadDeposits = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/api/pms/deposits/all`);
      setDeposits(res.data.deposits || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

  useEffect(() => { loadDeposits(); }, [loadDeposits]);

  const totalActive = deposits.filter(d => d.status === 'received').reduce((s, d) => s + (d.amount || 0), 0);
  const totalRefunded = deposits.filter(d => d.status === 'refunded').reduce((s, d) => s + (d.amount || 0), 0);
  const totalAll = deposits.reduce((s, d) => s + (d.amount || 0), 0);

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="deposits">
      <div className="p-6 space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Depozito Takibi</h1>
          <p className="text-sm text-gray-500 mt-1">Tum depozitolari goruntuleyin ve yonetin</p>
        </div>

        {/* Summary */}
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 text-center">
            <div className="text-xs text-blue-600 font-medium uppercase">Toplam</div>
            <div className="text-2xl font-bold text-blue-800 mt-1">{totalAll.toLocaleString('tr-TR')} TL</div>
          </div>
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-5 text-center">
            <div className="text-xs text-emerald-600 font-medium uppercase">Aktif</div>
            <div className="text-2xl font-bold text-emerald-800 mt-1">{totalActive.toLocaleString('tr-TR')} TL</div>
          </div>
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 text-center">
            <div className="text-xs text-amber-600 font-medium uppercase">Iade Edilen</div>
            <div className="text-2xl font-bold text-amber-800 mt-1">{totalRefunded.toLocaleString('tr-TR')} TL</div>
          </div>
        </div>

        {/* Deposits Table */}
        {loading ? (
          <div className="flex items-center justify-center py-16"><Loader2 className="w-8 h-8 animate-spin text-gray-400" /></div>
        ) : deposits.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <Shield className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p className="text-lg font-medium">Henuz depozito yok</p>
          </div>
        ) : (
          <div className="border rounded-xl overflow-hidden bg-white" data-testid="deposits-table">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="text-left py-3 px-4 font-semibold text-xs text-gray-500 uppercase">Misafir</th>
                  <th className="text-left py-3 px-4 font-semibold text-xs text-gray-500 uppercase">Oda</th>
                  <th className="text-left py-3 px-4 font-semibold text-xs text-gray-500 uppercase">Yontem</th>
                  <th className="text-right py-3 px-4 font-semibold text-xs text-gray-500 uppercase">Tutar</th>
                  <th className="text-left py-3 px-4 font-semibold text-xs text-gray-500 uppercase">Durum</th>
                  <th className="text-left py-3 px-4 font-semibold text-xs text-gray-500 uppercase">Tarih</th>
                  <th className="text-left py-3 px-4 font-semibold text-xs text-gray-500 uppercase">Kaydeden</th>
                </tr>
              </thead>
              <tbody>
                {deposits.map((d, i) => (
                  <tr key={d.id || i} className="border-t hover:bg-gray-50">
                    <td className="py-3 px-4 font-medium text-gray-800">{d.guest_name || '-'}</td>
                    <td className="py-3 px-4">{d.room_number || '-'}</td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1.5">
                        <Banknote className="w-3.5 h-3.5 text-gray-400" />
                        {d.method === 'cash' ? 'Nakit' : d.method === 'card' ? 'Kart' : 'Havale'}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-right font-bold text-gray-800">{(d.amount || 0).toLocaleString('tr-TR')} TL</td>
                    <td className="py-3 px-4">
                      <Badge className={`text-xs ${
                        d.status === 'refunded' ? 'bg-red-100 text-red-700' :
                        d.status === 'partially_refunded' ? 'bg-amber-100 text-amber-700' :
                        'bg-emerald-100 text-emerald-700'
                      }`}>
                        {d.status === 'refunded' ? 'Iade' : d.status === 'partially_refunded' ? 'Kismi Iade' : 'Aktif'}
                      </Badge>
                    </td>
                    <td className="py-3 px-4 text-xs text-gray-500">{(d.created_at || '').toString().slice(0, 16).replace('T', ' ')}</td>
                    <td className="py-3 px-4 text-xs text-gray-500">{d.recorded_by || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Layout>
  );
}
