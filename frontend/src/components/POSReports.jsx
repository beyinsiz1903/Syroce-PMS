import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Label } from './ui/label';
import {
  Tabs, TabsContent, TabsList, TabsTrigger,
} from './ui/tabs';
import {
  BarChart3, RefreshCw, Printer, Calendar, Receipt,
  TrendingUp, CreditCard, DollarSign, AlertCircle,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useBusinessDate } from '@/hooks/useBusinessDate';
import { formatCurrency, cachedTenantCurrency } from '@/lib/currency';
import { formatBusinessDateForDisplay } from '@/lib/businessDateOriginCopy';

const PAYMENT_LABEL = {
  cash: 'Nakit',
  card: 'Kart',
  credit: 'Kredi Kartı',
  room_charge: 'Oda Hesabı',
  folio: 'Folyo',
  unknown: 'Belirsiz',
};

const money = (amount, currency) => formatCurrency(amount, currency || cachedTenantCurrency());
const CATEGORY_LABELS = {
  food: 'Ana Yemek', appetizer: 'Başlangıç', dessert: 'Tatlı',
  beverage: 'İçecek', alcohol: 'Alkollü', unknown: 'Diğer',
};
const percentage = (amount, total) => {
  const safeTotal = Number(total) || 0;
  if (safeTotal <= 0) return 0;
  return Math.max(0, Math.min(100, (Number(amount) || 0) / safeTotal * 100));
};

const POSReports = ({ outletId }) => {
  const { t } = useTranslation();
  const businessDate = useBusinessDate();
  const [date, setDate] = useState(businessDate);
  const [report, setReport] = useState(null);
  const [voids, setVoids] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [voidError, setVoidError] = useState('');

  useEffect(() => { setDate(businessDate); }, [businessDate]);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      setVoidError('');
      const params = { date };
      if (outletId) params.outlet_id = outletId;
      const zRes = await axios.get('/pos/z-report', { params });
      setReport(zRes.data || null);
      try {
        const vRes = await axios.get('/pos/void-transactions', { params });
        const vlist = Array.isArray(vRes.data)
          ? vRes.data
          : (vRes.data.void_transactions || vRes.data.voided_transactions || []);
        setVoids(vlist);
      } catch (voidRequestError) {
        console.error('İptal kayıtları yüklenemedi:', voidRequestError);
        setVoids([]);
        setVoidError('İptal ayrıntıları yüklenemedi. Bu durum, iptal olmadığı anlamına gelmez.');
      }
    } catch (err) {
      console.error('Z raporu yüklenemedi:', err);
      setReport(null);
      setError('Rapor verileri yüklenemedi. Bağlantınızı kontrol edip yeniden deneyin.');
      toast.error('Rapor yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, [date, outletId]);

  useEffect(() => { load(); }, [load]);

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between flex-wrap gap-2">
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-amber-600" />
              Z Raporu / Gün Sonu
            </CardTitle>
            <div className="flex items-end gap-2">
              <div>
                <Label className="text-xs">{t('cm.components_POSReports.tarih')}</Label>
                <Input
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  className="w-40"
                />
              </div>
              <Button variant="outline" size="sm" onClick={load} disabled={loading}>
                <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                {t('cm.components_POSReports.yenile')}
              </Button>
              <Button size="sm" onClick={handlePrint} variant="outline" disabled={!report || loading}>
                <Printer className="w-4 h-4 mr-2" />
                {t('cm.components_POSReports.yazdir')}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading && !report ? (
            <div className="text-center py-12 text-gray-500">
              <RefreshCw className="w-8 h-8 animate-spin text-amber-600 mx-auto mb-2" />
              <p>{t('cm.components_POSReports.yukleniyor')}</p>
            </div>
          ) : error ? (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-10 text-center text-red-700" role="alert">
              <AlertCircle className="w-8 h-8 mx-auto mb-2" />
              <p className="font-medium">{error}</p>
              <Button variant="outline" size="sm" className="mt-4" onClick={load}>Yeniden dene</Button>
            </div>
          ) : report ? (
            <Tabs defaultValue="summary">
              <TabsList>
                <TabsTrigger value="summary">{t('cm.components_POSReports.ozet')}</TabsTrigger>
                <TabsTrigger value="payment">{t('cm.components_POSReports.odeme_dagilimi')}</TabsTrigger>
                <TabsTrigger value="category">Kategori Dağılımı</TabsTrigger>
                <TabsTrigger value="voids">
                  İptaller ({report.void_count ?? voids.length})
                </TabsTrigger>
              </TabsList>

              <TabsContent value="summary" className="mt-4 space-y-4">
                <div className="bg-gradient-to-r from-amber-50 to-amber-50 p-4 rounded-lg border border-amber-200">
                  <div className="flex items-center gap-2 mb-2">
                    <Receipt className="w-5 h-5 text-amber-600" />
                    <span className="font-semibold">{report.report_number || 'Z-?'}</span>
                    <Badge variant="outline" className="ml-auto">
                      <Calendar className="w-3 h-3 mr-1" />
                      {formatBusinessDateForDisplay(report.report_date)}
                    </Badge>
                  </div>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <Card>
                    <CardContent className="p-4 text-center">
                      <DollarSign className="w-6 h-6 mx-auto text-green-600 mb-1" />
                      <p className="text-xs text-gray-600">{t('cm.components_POSReports.brut_satis')}</p>
                      <p className="text-2xl font-bold text-green-600">
                        {money(report.gross_sales, report.currency)}
                      </p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="p-4 text-center">
                      <TrendingUp className="w-6 h-6 mx-auto text-blue-600 mb-1" />
                      <p className="text-xs text-gray-600">{t('cm.components_POSReports.net_satis')}</p>
                      <p className="text-2xl font-bold text-blue-600">
                        {money(report.net_sales, report.currency)}
                      </p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="p-4 text-center">
                      <Receipt className="w-6 h-6 mx-auto text-indigo-600 mb-1" />
                      <p className="text-xs text-gray-600">{t('cm.components_POSReports.islem_sayisi')}</p>
                      <p className="text-2xl font-bold text-indigo-600">
                        {report.transaction_count || 0}
                      </p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="p-4 text-center">
                      <AlertCircle className="w-6 h-6 mx-auto text-red-600 mb-1" />
                      <p className="text-xs text-gray-600">İptaller</p>
                      <p className="text-2xl font-bold text-red-600">
                        {report.void_count || 0}
                      </p>
                      {(report.refunds || 0) > 0 && (
                        <p className="text-xs text-red-500">{money(report.refunds, report.currency)}</p>
                      )}
                    </CardContent>
                  </Card>
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  <Card>
                    <CardContent className="p-3 flex items-center justify-between">
                      <span className="text-sm text-gray-600">{t('cm.components_POSReports.toplam_kdv')}</span>
                      <span className="font-semibold">{money(report.tax_total, report.currency)}</span>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="p-3 flex items-center justify-between">
                      <span className="text-sm text-gray-600">{t('cm.components_POSReports.indirim')}</span>
                      <span className="font-semibold text-amber-600">{money(report.discounts, report.currency)}</span>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="p-3 flex items-center justify-between">
                      <span className="text-sm text-gray-600">Servis bedeli</span>
                      <span className="font-semibold text-blue-700">{money(report.service_charges, report.currency)}</span>
                    </CardContent>
                  </Card>
                </div>
              </TabsContent>

              <TabsContent value="payment" className="mt-4">
                <div className="space-y-2">
                  {Object.keys(report.payment_methods || {}).length === 0 ? (
                    <p className="text-center py-8 text-gray-500">{t('cm.components_POSReports.bu_tarihte_odeme_yok')}</p>
                  ) : Object.entries(report.payment_methods || {}).map(([method, amount]) => {
                    const pct = percentage(amount, report.gross_sales);
                    return (
                      <div key={method} className="border rounded-lg p-3">
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex items-center gap-2">
                            <CreditCard className="w-4 h-4 text-gray-500" />
                            <span className="font-medium">{PAYMENT_LABEL[method] || method}</span>
                          </div>
                          <span className="font-bold">{money(amount, report.currency)}</span>
                        </div>
                        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                          <div className="h-full bg-blue-500" style={{ width: `${pct}%` }} />
                        </div>
                        <p className="text-xs text-gray-500 mt-1">%{pct.toFixed(1)}</p>
                      </div>
                    );
                  })}
                </div>
              </TabsContent>

              <TabsContent value="category" className="mt-4">
                <div className="space-y-2">
                  {Object.keys(report.category_sales || {}).length === 0 ? (
                    <p className="text-center py-8 text-gray-500">Kategori verisi yok</p>
                  ) : Object.entries(report.category_sales || {}).map(([cat, amount]) => {
                    const total = Object.values(report.category_sales || {})
                      .reduce((sum, value) => sum + (Number(value) || 0), 0);
                    const pct = percentage(amount, total);
                    return (
                      <div key={cat} className="border rounded-lg p-3">
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-medium">{CATEGORY_LABELS[cat] || cat}</span>
                          <span className="font-bold">{money(amount, report.currency)}</span>
                        </div>
                        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                          <div className="h-full bg-amber-500" style={{ width: `${pct}%` }} />
                        </div>
                        <p className="text-xs text-gray-500 mt-1">%{pct.toFixed(1)}</p>
                      </div>
                    );
                  })}
                </div>
              </TabsContent>

              <TabsContent value="voids" className="mt-4">
                {voidError ? (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-8 text-center text-amber-800" role="alert">
                    <AlertCircle className="w-8 h-8 mx-auto mb-2" />
                    <p className="font-medium">{voidError}</p>
                    <Button variant="outline" size="sm" className="mt-4" onClick={load}>Yeniden dene</Button>
                  </div>
                ) : voids.length === 0 ? (
                  <div className="text-center py-8 text-gray-500">
                    <AlertCircle className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                    <p>{t('cm.components_POSReports.iptal_edilmis_islem_yok')}</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {voids.map((v, idx) => (
                      <Card key={v.id || idx}>
                        <CardContent className="p-3 flex items-center justify-between">
                          <div>
                            <p className="font-medium">{v.id?.slice(0, 8) || `İşlem ${idx + 1}`}</p>
                            <p className="text-xs text-gray-500">
                              {v.void_reason || v.reason || 'Sebep belirtilmemiş'}
                            </p>
                          </div>
                          <div className="text-right">
                            <p className="font-bold text-red-600">
                              {money(v.total_amount || v.amount, v.currency || report.currency)}
                            </p>
                            <p className="text-xs text-gray-500">
                              {v.void_date || v.created_at?.slice(0, 10) || ''}
                            </p>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}
              </TabsContent>
            </Tabs>
          ) : (
            <div className="text-center py-12 text-gray-500">Bu tarih için rapor bulunamadı.</div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default POSReports;
