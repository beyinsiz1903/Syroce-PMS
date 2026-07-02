import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { DollarSign, Calendar, TrendingUp, Utensils, RefreshCw } from 'lucide-react';
import { BarChart, Bar, Cell, ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { COLORS, formatCurrency, KPICard, CustomTooltip, SectionHeader } from './ReportHelpers';
import { useTranslation } from 'react-i18next';
const CATEGORY_LABELS = {
  room: 'Konaklama',
  food: 'Yiyecek',
  beverage: 'İçecek',
  minibar: 'Minibar',
  spa: 'Spa',
  laundry: 'Çamaşır',
  phone: 'Telefon',
  internet: 'İnternet',
  parking: 'Otopark',
  city_tax: 'Şehir Vergisi',
  service_charge: 'Servis Bedeli',
  other: 'Diğer'
};
const fmt = n => Number(n || 0).toLocaleString('tr-TR', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
});
const isoDaysAgo = n => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
};
const isoToday = () => new Date().toISOString().slice(0, 10);
const CategoryRevenueCard = () => {
  const {
    t
  } = useTranslation();
  const [from, setFrom] = useState(isoDaysAgo(30));
  const [to, setTo] = useState(isoToday());
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await axios.get(`/folio/reports/revenue-by-category`, {
        params: {
          date_from: from,
          date_to: to
        }
      });
      setData(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || 'Yüklenemedi');
      setData(null);
    }
    setLoading(false);
  }, [from, to]);
  useEffect(() => {
    load();
  }, [load]);
  const rows = data?.rows || [];
  const totals = data?.totals;
  return <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm flex items-center justify-between">
          <span>{t('cm.pages_reports_RevenueSection.kategori_bazli_gelir')}</span>
          <div className="flex items-end gap-2">
            <div>
              <Label className="text-[10px] text-gray-500">{t('cm.pages_reports_RevenueSection.baslangic')}</Label>
              <Input type="date" value={from} onChange={e => setFrom(e.target.value)} className="h-8 text-xs w-36" />
            </div>
            <div>
              <Label className="text-[10px] text-gray-500">{t('cm.pages_reports_RevenueSection.bitis')}</Label>
              <Input type="date" value={to} onChange={e => setTo(e.target.value)} className="h-8 text-xs w-36" />
            </div>
            <Button size="sm" variant="outline" onClick={load} disabled={loading} className="h-8">
              <RefreshCw className={`w-3 h-3 mr-1 ${loading ? 'animate-spin' : ''}`} />
              {t('cm.pages_reports_RevenueSection.yenile')}
            </Button>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {error && <div className="text-xs text-red-600 mb-2">{error}</div>}
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left p-2">Kategori</th>
                <th className="text-right p-2">Adet</th>
                <th className="text-right p-2">{t('cm.pages_reports_RevenueSection.ara_toplam')}</th>
                <th className="text-right p-2">{t('cm.pages_reports_RevenueSection.indirim')}</th>
                <th className="text-right p-2">Net</th>
                <th className="text-right p-2">KDV</th>
                <th className="text-right p-2">{t('cm.pages_reports_RevenueSection.sehir_vergisi')}</th>
                <th className="text-right p-2">{t('cm.pages_reports_RevenueSection.toplam')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? <tr><td colSpan={8} className="text-center p-6 text-gray-400">{t('cm.pages_reports_RevenueSection.bu_tarih_araliginda_islem_yok')}</td></tr> : rows.map(r => <tr key={r.category} className="border-t">
                  <td className="p-2 font-medium">{CATEGORY_LABELS[r.category] || r.category}</td>
                  <td className="p-2 text-right">{r.count}</td>
                  <td className="p-2 text-right">{fmt(r.subtotal)}</td>
                  <td className="p-2 text-right text-amber-700">{r.discount > 0 ? `−${fmt(r.discount)}` : '0,00'}</td>
                  <td className="p-2 text-right">{fmt(r.net)}</td>
                  <td className="p-2 text-right">{fmt(r.vat)}</td>
                  <td className="p-2 text-right">{fmt(r.city_tax)}</td>
                  <td className="p-2 text-right font-semibold">{fmt(r.total)} ₺</td>
                </tr>)}
            </tbody>
            {totals && rows.length > 0 && <tfoot className="bg-gray-100 font-semibold">
                <tr>
                  <td className="p-2">TOPLAM</td>
                  <td className="p-2 text-right">{totals.count}</td>
                  <td className="p-2 text-right">{fmt(totals.subtotal)}</td>
                  <td className="p-2 text-right text-amber-700">{totals.discount > 0 ? `−${fmt(totals.discount)}` : '0,00'}</td>
                  <td className="p-2 text-right">{fmt(totals.net)}</td>
                  <td className="p-2 text-right">{fmt(totals.vat)}</td>
                  <td className="p-2 text-right">{fmt(totals.city_tax)}</td>
                  <td className="p-2 text-right">{fmt(totals.total)} ₺</td>
                </tr>
              </tfoot>}
          </table>
        </div>
      </CardContent>
    </Card>;
};
const RevenueSection = ({
  data,
  s,
  pc,
  roomTypeData
}) => {
  const {
    t
  } = useTranslation();
  return <div className="space-y-6" data-testid="section-revenue">
    <SectionHeader title="Gelir Raporu" description={t('cm.pages_reports_RevenueSection.detayli_gelir_analizi_ve_trendler')} />
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <KPICard title={t('cm.pages_reports_RevenueSection.bugunku_gelir')} value={s.today_revenue} icon={DollarSign} color="green" />
      <KPICard title={t('cm.pages_reports_RevenueSection.haftalik_gelir')} value={pc.week_revenue} icon={Calendar} color="blue" />
      <KPICard title={t('cm.pages_reports_RevenueSection.aylik_gelir')} value={pc.month_revenue} prevValue={pc.prev_month_revenue} icon={TrendingUp} color="purple" />
      <KPICard title="F&B Geliri" value={s.fnb_revenue} icon={Utensils} color="amber" />
    </div>
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-sm">{t('cm.pages_reports_RevenueSection.30_gunluk_gelir_trendi')}</CardTitle></CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={data?.revenue_trend || []}>
            <defs><linearGradient id="rvFull" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#059669" stopOpacity={0.2} /><stop offset="95%" stopColor="#059669" stopOpacity={0} /></linearGradient></defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="label" tick={{
              fontSize: 10
            }} interval={2} />
            <YAxis tick={{
              fontSize: 10
            }} tickFormatter={v => (v / 1000).toFixed(0) + 'K'} />
            <Tooltip content={<CustomTooltip formatter={formatCurrency} />} />
            <Legend wrapperStyle={{
              fontSize: 11
            }} />
            <Area type="monotone" dataKey="revenue" name="Gelir" stroke="#059669" fill="url(#rvFull)" strokeWidth={2} />
            <Line type="monotone" dataKey="revenue" name="Trend" stroke="#D97706" strokeWidth={2} dot={false} strokeDasharray="5 5" />
          </ComposedChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
    <CategoryRevenueCard />
    {roomTypeData.length > 0 && <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">{t('cm.pages_reports_RevenueSection.oda_tipi_bazli_gelir')}</CardTitle></CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={roomTypeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="name" tick={{
              fontSize: 10
            }} />
              <YAxis tick={{
              fontSize: 10
            }} tickFormatter={v => (v / 1000).toFixed(0) + 'K'} />
              <Tooltip content={<CustomTooltip formatter={formatCurrency} />} />
              <Bar dataKey="revenue" name="Gelir" radius={[4, 4, 0, 0]}>{roomTypeData.map((_, i) => <Cell key={_.id || i} fill={COLORS[i % COLORS.length]} />)}</Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>}
  </div>;
};
export default RevenueSection;