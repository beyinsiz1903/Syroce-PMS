import React, { useEffect, useMemo, useState, useCallback } from 'react';
import axios from 'axios';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input }  from '@/components/ui/input';
import { Label }  from '@/components/ui/label';
import { toast }  from 'sonner';
import {
  TrendingUp, TrendingDown, DollarSign, Percent,
  RefreshCw, Store, Award, ShoppingCart,
} from 'lucide-react';

/* ─── helpers ── */
const fmtDate = (d) => d.toISOString().slice(0, 10);
const fmt2    = (n) => Number(n || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtPct  = (n) => `${Number(n || 0).toFixed(1)}%`;

function SummaryCard({ icon: Icon, label, value, color }) {
  const c = {
    blue:    'from-blue-50  to-indigo-50  border-blue-200  text-blue-600',
    red:     'from-red-50   to-rose-50    border-red-200   text-red-600',
    green:   'from-emerald-50 to-green-50 border-emerald-200 text-emerald-600',
    gray:    'from-gray-50  to-slate-50   border-gray-200  text-gray-700',
  }[color] || 'from-gray-50 to-gray-50 border-gray-200 text-gray-700';
  return (
    <div className={`rounded-2xl border bg-gradient-to-br ${c} p-5 flex items-center gap-4 shadow-sm`}>
      <div className="w-10 h-10 rounded-xl bg-white/80 shadow-sm flex items-center justify-center shrink-0">
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-0.5">{label}</p>
        <p className="text-xl font-extrabold text-gray-900">{value}</p>
      </div>
    </div>
  );
}

function BarRow({ label, value, maxValue, color = 'indigo', suffix = '' }) {
  const pct = maxValue > 0 ? Math.min(100, (value / maxValue) * 100) : 0;
  const barColor = { indigo: 'bg-indigo-500', emerald: 'bg-emerald-500', amber: 'bg-amber-500' }[color] || 'bg-indigo-500';
  return (
    <div className="flex items-center gap-3">
      <span className="w-36 text-sm font-medium text-gray-700 truncate shrink-0">{label}</span>
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full ${barColor} rounded-full transition-all duration-500`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-20 text-right text-sm font-semibold text-gray-700 shrink-0">{suffix}{fmt2(value)}</span>
    </div>
  );
}

/* ─── main ── */
const FnBOutletDashboard = () => {
  const [outlets,       setOutlets]       = useState([]);
  const [selectedOutlet,setSelectedOutlet]= useState('all');
  const [startDate,     setStartDate]     = useState(() => fmtDate(new Date(new Date().getFullYear(), new Date().getMonth(), 1)));
  const [endDate,       setEndDate]       = useState(() => fmtDate(new Date()));
  const [loading,       setLoading]       = useState(false);
  const [menuData,      setMenuData]      = useState(null);

  const loadOutlets = useCallback(async () => {
    try {
      const res = await axios.get('/pos/outlets');
      setOutlets(res.data?.outlets || []);
    } catch { toast.error('Satış noktaları yüklenemedi'); }
  }, []);

  const loadSales = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/pos/menu-sales-breakdown', {
        params: {
          outlet_id:  selectedOutlet === 'all' ? undefined : selectedOutlet,
          start_date: startDate,
          end_date:   endDate,
        },
      });
      setMenuData(res.data);
    } catch { toast.error('F&B satışları yüklenemedi'); }
    finally  { setLoading(false); }
  }, [selectedOutlet, startDate, endDate]);

  useEffect(() => { loadOutlets(); loadSales(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const summary    = menuData?.summary;
  const byOutlet   = menuData?.by_outlet   || [];
  const topItems   = useMemo(() => (menuData?.menu_items || []).slice(0, 15), [menuData]);
  const byCategory = menuData?.by_category || [];

  return (
    <div className="space-y-5">
      {/* ── Filter bar ── */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
          <Store className="w-4 h-4 text-amber-500" />
          Outlet Satış Özeti
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 items-end">
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Başlangıç Tarihi</Label>
            <Input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
          </div>
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Bitiş Tarihi</Label>
            <Input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
          </div>
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Satış Noktası</Label>
            <Select value={selectedOutlet} onValueChange={setSelectedOutlet}>
              <SelectTrigger>
                <SelectValue placeholder="Tüm noktalar" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tüm noktalar</SelectItem>
                {outlets.map(o => <SelectItem key={o.id} value={o.id}>{o.outlet_name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <button
            onClick={loadSales}
            disabled={loading}
            className="flex items-center justify-center gap-2 h-10 px-5 rounded-xl bg-amber-500 hover:bg-amber-600 text-white font-semibold text-sm transition-colors disabled:opacity-60"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            {loading ? 'Yükleniyor…' : 'Yenile'}
          </button>
        </div>
      </div>

      {/* ── Summary cards ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {loading && !menuData ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-2xl border border-gray-200 bg-white p-5">
              <Skeleton className="h-4 w-24 mb-2" />
              <Skeleton className="h-7 w-32" />
            </div>
          ))
        ) : summary ? (
          <>
            <SummaryCard icon={DollarSign}  label="Toplam Ciro"   value={`₺${fmt2(summary.total_revenue)}`}     color="blue"  />
            <SummaryCard icon={TrendingDown} label="Toplam Maliyet" value={`₺${fmt2(summary.total_cost)}`}      color="red"   />
            <SummaryCard icon={TrendingUp}  label="Brüt Kâr"     value={`₺${fmt2(summary.gross_profit)}`}      color="green" />
            <SummaryCard icon={Percent}     label="Kâr Marjı"    value={fmtPct(summary.profit_margin)}          color="gray"  />
          </>
        ) : (
          <div className="col-span-4 rounded-2xl border-2 border-dashed border-gray-200 bg-white py-8 text-center">
            <DollarSign className="w-10 h-10 text-gray-300 mx-auto mb-2" />
            <p className="text-gray-400 text-sm">Seçilen dönem için satış verisi yok</p>
          </div>
        )}
      </div>

      {/* ── Outlet breakdown ── */}
      {selectedOutlet === 'all' && byOutlet.length > 0 && (
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <Store className="w-4 h-4 text-indigo-500" /> Satış Noktasına Göre Ciro
          </h3>
          <div className="space-y-2.5">
            {byOutlet.map(o => (
              <BarRow
                key={o.outlet_name}
                label={o.outlet_name}
                value={o.revenue}
                maxValue={summary?.total_revenue || 1}
                color="indigo"
                suffix="₺"
              />
            ))}
          </div>
        </div>
      )}

      {/* ── Category breakdown ── */}
      {byCategory.length > 0 && (
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <Award className="w-4 h-4 text-emerald-500" /> Kategoriye Göre Ciro
          </h3>
          <div className="space-y-2.5">
            {byCategory.map(c => (
              <BarRow
                key={c.category}
                label={c.category}
                value={c.revenue}
                maxValue={summary?.total_revenue || 1}
                color="emerald"
                suffix="₺"
              />
            ))}
          </div>
        </div>
      )}

      {/* ── Top items table ── */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
          <ShoppingCart className="w-4 h-4 text-amber-500" /> En Çok Satan Ürünler
        </h3>
        {loading && !menuData ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}
          </div>
        ) : topItems.length === 0 ? (
          <div className="py-10 text-center">
            <ShoppingCart className="w-10 h-10 text-gray-200 mx-auto mb-2" />
            <p className="text-sm text-gray-400">Seçilen dönem için satış verisi yok</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left pb-2 font-semibold text-gray-500 text-xs uppercase tracking-wide">Ürün</th>
                  <th className="text-right pb-2 font-semibold text-gray-500 text-xs uppercase tracking-wide">Adet</th>
                  <th className="text-right pb-2 font-semibold text-gray-500 text-xs uppercase tracking-wide">Ciro</th>
                  <th className="text-right pb-2 font-semibold text-gray-500 text-xs uppercase tracking-wide">Maliyet</th>
                  <th className="text-right pb-2 font-semibold text-gray-500 text-xs uppercase tracking-wide">Brüt Kâr</th>
                </tr>
              </thead>
              <tbody>
                {topItems.map((item, i) => (
                  <tr key={item.item_name} className={`border-b border-gray-50 ${i % 2 === 0 ? '' : 'bg-gray-50/50'}`}>
                    <td className="py-2.5 font-medium text-gray-900 truncate max-w-[180px]">{item.item_name}</td>
                    <td className="py-2.5 text-right text-gray-600">{item.quantity_sold}</td>
                    <td className="py-2.5 text-right font-semibold text-blue-600">₺{fmt2(item.total_revenue)}</td>
                    <td className="py-2.5 text-right text-red-500">₺{fmt2(item.total_cost)}</td>
                    <td className="py-2.5 text-right font-semibold text-emerald-600">₺{fmt2(item.gross_profit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default FnBOutletDashboard;
