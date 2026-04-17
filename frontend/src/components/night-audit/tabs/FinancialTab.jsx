import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { TabsContent } from '@/components/ui/tabs';
import { Moon, Play, Clock, CheckCircle2, XCircle, AlertTriangle, RefreshCw, Calendar, FileText, ChevronDown, ChevronUp, DollarSign, Users, Building2, BarChart3, Eye, Loader2, Shield, Info, Timer, Settings2, Zap, RotateCcw, TrendingUp, CreditCard, ShieldCheck, Scale, Receipt, PieChart, ArrowUpDown, Banknote, AlertOctagon, Search } from 'lucide-react';

export default function FinancialTab(props) {
  const { StatCard, categoryLabels, financialSummary, paymentMethodLabels } = props;
  return (
    <TabsContent value="financial" className="space-y-4 mt-4">
      {financialSummary ? (
        <>
          {/* Revenue & Payment Summary Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard
              icon={TrendingUp}
              label="Toplam Gelir"
              value={`${financialSummary.revenue?.total?.toFixed(2) || "0.00"} TL`}
              subValue={`${financialSummary.revenue?.charges_count || 0} masraf`}
              color="text-emerald-600"
            />
            <StatCard
              icon={Receipt}
              label="Vergi Toplamı"
              value={`${financialSummary.tax?.total?.toFixed(2) || "0.00"} TL`}
              subValue={`KDV: ${financialSummary.tax?.breakdown?.vat?.toFixed(2) || "0"} TL`}
              color="text-blue-600"
            />
            <StatCard
              icon={CreditCard}
              label="Toplam Ödeme"
              value={`${financialSummary.payments?.total?.toFixed(2) || "0.00"} TL`}
              subValue={`${financialSummary.payments?.payments_count || 0} ödeme`}
              color="text-indigo-600"
            />
            <StatCard
              icon={ArrowUpDown}
              label="Net Pozisyon"
              value={`${financialSummary.net_position?.toFixed(2) || "0.00"} TL`}
              subValue={financialSummary.net_position > 0 ? "Alacak" : financialSummary.net_position < 0 ? "Fazla ödeme" : "Dengeli"}
              color={financialSummary.net_position > 0 ? "text-amber-600" : financialSummary.net_position < 0 ? "text-red-600" : "text-emerald-600"}
            />
          </div>

          {/* Revenue Breakdown */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card data-testid="revenue-breakdown-card">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <PieChart className="w-4 h-4 text-emerald-500" />
                  Gelir Dağılımı (Kategori)
                </CardTitle>
              </CardHeader>
              <CardContent>
                {Object.keys(financialSummary.revenue?.by_category || {}).length === 0 ? (
                  <p className="text-xs text-gray-400 py-6 text-center">Bugün için masraf kaydedilmemiş</p>
                ) : (
                  <div className="space-y-2">
                    {Object.entries(financialSummary.revenue.by_category).map(([cat, data]) => {
                      const pct = financialSummary.revenue.total > 0
                        ? ((data.amount / financialSummary.revenue.total) * 100).toFixed(1)
                        : 0;
                      return (
                        <div key={cat} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
                          <div className="flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full bg-emerald-500" />
                            <span className="text-sm font-medium text-gray-700">{categoryLabels[cat] || cat}</span>
                            <span className="text-[11px] text-gray-400">({data.count})</span>
                          </div>
                          <div className="text-right">
                            <span className="text-sm font-semibold text-gray-900">{data.amount.toFixed(2)} TL</span>
                            <span className="text-[11px] text-gray-400 ml-2">{pct}%</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card data-testid="payment-methods-card">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Banknote className="w-4 h-4 text-indigo-500" />
                  Ödeme Yöntemleri
                </CardTitle>
              </CardHeader>
              <CardContent>
                {Object.keys(financialSummary.payments?.by_method || {}).length === 0 ? (
                  <p className="text-xs text-gray-400 py-6 text-center">Bugün için ödeme kaydedilmemiş</p>
                ) : (
                  <div className="space-y-2">
                    {Object.entries(financialSummary.payments.by_method).map(([method, data]) => (
                      <div key={method} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
                        <div className="flex items-center gap-2">
                          <CreditCard className="w-3.5 h-3.5 text-indigo-400" />
                          <span className="text-sm font-medium text-gray-700">{paymentMethodLabels[method] || method}</span>
                          <span className="text-[11px] text-gray-400">({data.count})</span>
                        </div>
                        <span className="text-sm font-semibold text-gray-900">{data.amount.toFixed(2)} TL</span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Open Folios */}
          <Card data-testid="open-folios-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <FileText className="w-4 h-4 text-amber-500" />
                Açık Folyolar
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="p-3 bg-gray-50 rounded-lg">
                  <p className="text-2xl font-bold text-gray-900">{financialSummary.open_folios?.count || 0}</p>
                  <p className="text-xs text-gray-500">Toplam Açık Folyo</p>
                </div>
                <div className="p-3 bg-gray-50 rounded-lg">
                  <p className="text-2xl font-bold text-gray-900">{financialSummary.open_folios?.balance?.total?.toFixed(2) || "0.00"} TL</p>
                  <p className="text-xs text-gray-500">Toplam Bakiye</p>
                </div>
                <div className="p-3 bg-amber-50 rounded-lg">
                  <p className="text-2xl font-bold text-amber-700">{financialSummary.open_folios?.balance?.receivable?.toFixed(2) || "0.00"} TL</p>
                  <p className="text-xs text-amber-600">Alacak</p>
                </div>
                <div className="p-3 bg-blue-50 rounded-lg">
                  <p className="text-2xl font-bold text-blue-700">{financialSummary.open_folios?.balance?.overpayment?.toFixed(2) || "0.00"} TL</p>
                  <p className="text-xs text-blue-600">Fazla Ödeme</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </>
      ) : (
        <div className="flex items-center justify-center py-16 text-gray-400 text-sm">
          <Loader2 className="w-5 h-5 mr-2 animate-spin" /> Finansal ozet yükleniyor...
        </div>
      )}
    </TabsContent>
  );
}
