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

const PAYMENT_LABEL = {
  cash: 'Nakit',
  card: 'Kart',
  credit: 'Kredi Karti',
  room_charge: 'Oda Hesabi',
  folio: 'Folio',
  unknown: 'Belirsiz',
};

const fmt = (n) => Number(n || 0).toLocaleString('tr-TR', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const POSReports = ({ outletId }) => {
  const today = new Date().toISOString().slice(0, 10);
  const [date, setDate] = useState(today);
  const [report, setReport] = useState(null);
  const [voids, setVoids] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const params = { date };
      if (outletId) params.outlet_id = outletId;
      const [zRes, vRes] = await Promise.all([
        axios.get('/pos/z-report', { params }),
        axios.get('/pos/void-transactions', { params })
          .catch(() => ({ data: { void_transactions: [] } })),
      ]);
      setReport(zRes.data || null);
      const vlist = Array.isArray(vRes.data)
        ? vRes.data
        : (vRes.data.void_transactions || vRes.data.voided_transactions || []);
      setVoids(vlist);
    } catch (err) {
      console.error('Z raporu yuklenemedi:', err);
      toast.error('Rapor yuklenemedi');
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
              <BarChart3 className="w-5 h-5 text-orange-600" />
              Z Raporu / Gun Sonu
            </CardTitle>
            <div className="flex items-end gap-2">
              <div>
                <Label className="text-xs">Tarih</Label>
                <Input
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  className="w-40"
                />
              </div>
              <Button variant="outline" size="sm" onClick={load} disabled={loading}>
                <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                Yenile
              </Button>
              <Button size="sm" onClick={handlePrint} variant="outline">
                <Printer className="w-4 h-4 mr-2" />
                Yazdir
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {!report ? (
            <div className="text-center py-12 text-gray-500">
              <RefreshCw className="w-8 h-8 animate-spin text-orange-600 mx-auto mb-2" />
              <p>Yukleniyor...</p>
            </div>
          ) : (
            <Tabs defaultValue="summary">
              <TabsList>
                <TabsTrigger value="summary">Ozet</TabsTrigger>
                <TabsTrigger value="payment">Odeme Dagilimi</TabsTrigger>
                <TabsTrigger value="category">Kategori Dagilimi</TabsTrigger>
                <TabsTrigger value="voids">
                  Iptaller ({report.void_count ?? voids.length})
                </TabsTrigger>
              </TabsList>

              <TabsContent value="summary" className="mt-4 space-y-4">
                <div className="bg-gradient-to-r from-orange-50 to-amber-50 p-4 rounded-lg border border-orange-200">
                  <div className="flex items-center gap-2 mb-2">
                    <Receipt className="w-5 h-5 text-orange-600" />
                    <span className="font-semibold">{report.report_number || 'Z-?'}</span>
                    <Badge variant="outline" className="ml-auto">
                      <Calendar className="w-3 h-3 mr-1" />
                      {report.report_date}
                    </Badge>
                  </div>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <Card>
                    <CardContent className="p-4 text-center">
                      <DollarSign className="w-6 h-6 mx-auto text-green-600 mb-1" />
                      <p className="text-xs text-gray-600">Brut Satis</p>
                      <p className="text-2xl font-bold text-green-600">
                        {fmt(report.gross_sales)}
                      </p>
                      <p className="text-xs text-gray-400">TL</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="p-4 text-center">
                      <TrendingUp className="w-6 h-6 mx-auto text-blue-600 mb-1" />
                      <p className="text-xs text-gray-600">Net Satis</p>
                      <p className="text-2xl font-bold text-blue-600">
                        {fmt(report.net_sales)}
                      </p>
                      <p className="text-xs text-gray-400">TL</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="p-4 text-center">
                      <Receipt className="w-6 h-6 mx-auto text-purple-600 mb-1" />
                      <p className="text-xs text-gray-600">Islem Sayisi</p>
                      <p className="text-2xl font-bold text-purple-600">
                        {report.transaction_count || 0}
                      </p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="p-4 text-center">
                      <AlertCircle className="w-6 h-6 mx-auto text-red-600 mb-1" />
                      <p className="text-xs text-gray-600">Iptaller</p>
                      <p className="text-2xl font-bold text-red-600">
                        {report.void_count || 0}
                      </p>
                      {(report.refunds || 0) > 0 && (
                        <p className="text-xs text-red-500">{fmt(report.refunds)} TL</p>
                      )}
                    </CardContent>
                  </Card>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Card>
                    <CardContent className="p-3 flex items-center justify-between">
                      <span className="text-sm text-gray-600">Toplam KDV</span>
                      <span className="font-semibold">{fmt(report.tax_total)} TL</span>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="p-3 flex items-center justify-between">
                      <span className="text-sm text-gray-600">Indirim</span>
                      <span className="font-semibold text-orange-600">{fmt(report.discounts)} TL</span>
                    </CardContent>
                  </Card>
                </div>
              </TabsContent>

              <TabsContent value="payment" className="mt-4">
                <div className="space-y-2">
                  {Object.keys(report.payment_methods || {}).length === 0 ? (
                    <p className="text-center py-8 text-gray-500">Bu tarihte odeme yok</p>
                  ) : Object.entries(report.payment_methods || {}).map(([method, amount]) => {
                    const total = report.gross_sales || 1;
                    const pct = (amount / total) * 100;
                    return (
                      <div key={method} className="border rounded-lg p-3">
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex items-center gap-2">
                            <CreditCard className="w-4 h-4 text-gray-500" />
                            <span className="font-medium">{PAYMENT_LABEL[method] || method}</span>
                          </div>
                          <span className="font-bold">{fmt(amount)} TL</span>
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
                      .reduce((s, v) => s + v, 0) || 1;
                    const pct = (amount / total) * 100;
                    return (
                      <div key={cat} className="border rounded-lg p-3">
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-medium">{cat}</span>
                          <span className="font-bold">{fmt(amount)} TL</span>
                        </div>
                        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                          <div className="h-full bg-orange-500" style={{ width: `${pct}%` }} />
                        </div>
                        <p className="text-xs text-gray-500 mt-1">%{pct.toFixed(1)}</p>
                      </div>
                    );
                  })}
                </div>
              </TabsContent>

              <TabsContent value="voids" className="mt-4">
                {voids.length === 0 ? (
                  <div className="text-center py-8 text-gray-500">
                    <AlertCircle className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                    <p>Iptal edilmis islem yok</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {voids.map((v, idx) => (
                      <Card key={v.id || idx}>
                        <CardContent className="p-3 flex items-center justify-between">
                          <div>
                            <p className="font-medium">{v.id?.slice(0, 8) || `Islem ${idx + 1}`}</p>
                            <p className="text-xs text-gray-500">
                              {v.void_reason || v.reason || 'Sebep belirtilmemis'}
                            </p>
                          </div>
                          <div className="text-right">
                            <p className="font-bold text-red-600">
                              {fmt(v.total_amount || v.amount)} TL
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
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default POSReports;
