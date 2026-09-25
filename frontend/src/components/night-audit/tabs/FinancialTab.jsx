import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { TabsContent } from '@/components/ui/tabs';
import { Moon, Play, Clock, CheckCircle2, XCircle, AlertTriangle, RefreshCw, Calendar, FileText, ChevronDown, ChevronUp, DollarSign, Users, Building2, BarChart3, Eye, Loader2, Shield, Info, Timer, Settings2, Zap, RotateCcw, TrendingUp, CreditCard, ShieldCheck, Scale, Receipt, PieChart, ArrowUpDown, Banknote, AlertOctagon, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export default function FinancialTab(props) {
  const { t } = useTranslation();
  const { StatCard, categoryLabels, financialSummary, paymentMethodLabels, reportingDate } = props;
  const money = (value) => `${Number(value || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2 })} TL`;
  return (
    <TabsContent value="financial" className="space-y-4 mt-4">
      {financialSummary ? (
        <>
          <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900">
            <strong>Rapor iş günü:</strong> {financialSummary.business_date || financialSummary.date || reportingDate || '-'} · Son tamamlanan gece denetiminin finansal hareketleri
          </div>
          {/* Revenue & Payment Summary Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard
              icon={TrendingUp}
              label={t('cm.components_nightaudit_tabs_FinancialTab.toplam_gelir')}
              value={money(financialSummary.revenue?.total)}
              subValue={`${financialSummary.revenue?.charges_count || 0} masraf`}
              color="text-emerald-600"
            />
            <StatCard
              icon={Receipt}
              label={t('cm.components_nightaudit_tabs_FinancialTab.vergi_toplami')}
              value={money(financialSummary.tax?.total)}
              subValue={`KDV: ${money(financialSummary.tax?.breakdown?.vat)}`}
              color="text-blue-600"
            />
            <StatCard
              icon={CreditCard}
              label={t('cm.components_nightaudit_tabs_FinancialTab.toplam_odeme')}
              value={money(financialSummary.payments?.total)}
              subValue={`${financialSummary.payments?.payments_count || 0} ödeme`}
              color="text-indigo-600"
            />
            <StatCard
              icon={ArrowUpDown}
              label="Net Pozisyon"
              value={money(financialSummary.net_position)}
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
                  {t('cm.components_nightaudit_tabs_FinancialTab.gelir_dagilimi_kategori')}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {Object.keys(financialSummary.revenue?.by_category || {}).length === 0 ? (
                  <p className="text-xs text-gray-400 py-6 text-center">{t('cm.components_nightaudit_tabs_FinancialTab.bugun_icin_masraf_kaydedilmemis')}</p>
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
                            <span className="text-sm font-semibold text-gray-900">{money(data.amount)}</span>
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
                  {t('cm.components_nightaudit_tabs_FinancialTab.odeme_yontemleri')}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {Object.keys(financialSummary.payments?.by_method || {}).length === 0 ? (
                  <p className="text-xs text-gray-400 py-6 text-center">{t('cm.components_nightaudit_tabs_FinancialTab.bugun_icin_odeme_kaydedilmemis')}</p>
                ) : (
                  <div className="space-y-2">
                    {Object.entries(financialSummary.payments.by_method).map(([method, data]) => (
                      <div key={method} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
                        <div className="flex items-center gap-2">
                          <CreditCard className="w-3.5 h-3.5 text-indigo-400" />
                          <span className="text-sm font-medium text-gray-700">{paymentMethodLabels[method] || method}</span>
                          <span className="text-[11px] text-gray-400">({data.count})</span>
                        </div>
                        <span className="text-sm font-semibold text-gray-900">{money(data.amount)}</span>
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
                {t('cm.components_nightaudit_tabs_FinancialTab.acik_folyolar')}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="p-3 bg-gray-50 rounded-lg">
                  <p className="text-2xl font-bold text-gray-900">{financialSummary.open_folios?.count || 0}</p>
                  <p className="text-xs text-gray-500">{t('cm.components_nightaudit_tabs_FinancialTab.toplam_acik_folyo')}</p>
                </div>
                <div className="p-3 bg-gray-50 rounded-lg">
                  <p className="text-2xl font-bold text-gray-900">{money(financialSummary.open_folios?.balance?.total)}</p>
                  <p className="text-xs text-gray-500">{t('cm.components_nightaudit_tabs_FinancialTab.toplam_bakiye')}</p>
                </div>
                <div className="p-3 bg-amber-50 rounded-lg">
                  <p className="text-2xl font-bold text-amber-700">{money(financialSummary.open_folios?.balance?.receivable)}</p>
                  <p className="text-xs text-amber-600">Çıkışta tahsil edilecek</p>
                </div>
                <div className="p-3 bg-blue-50 rounded-lg">
                  <p className="text-2xl font-bold text-blue-700">{money(financialSummary.open_folios?.balance?.overpayment)}</p>
                  <p className="text-xs text-blue-600">Ön ödeme / kredi bakiyesi</p>
                </div>
              </div>

              {financialSummary.open_folios?.items && financialSummary.open_folios.items.length > 0 && (
                <div className="mt-4 pt-4 border-t">
                  <h4 className="text-sm font-medium text-gray-700 mb-3">Açık Folyo Detayları</h4>
                  <div className="overflow-x-auto rounded border">
                    <table className="w-full text-sm text-left">
                      <thead className="text-xs text-gray-500 bg-gray-50 uppercase border-b">
                        <tr>
                          <th className="px-3 py-2">Folyo No</th>
                          <th className="px-3 py-2">Oda</th>
                          <th className="px-3 py-2">Misafir</th>
                          <th className="px-3 py-2 text-right">Bakiye</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {financialSummary.open_folios.items.map((fol, idx) => (
                          <tr key={idx} className="hover:bg-gray-50">
                            <td className="px-3 py-2 font-medium text-blue-600">{fol.folio_number || '-'}</td>
                            <td className="px-3 py-2">{fol.room_no || '?'}</td>
                            <td className="px-3 py-2">{fol.guest_name || 'İsimsiz'}</td>
                            <td className={`px-3 py-2 text-right font-semibold ${fol.balance > 0 ? 'text-amber-600' : (fol.balance < 0 ? 'text-blue-600' : 'text-gray-500')}`}>
                              {money(fol.balance)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      ) : (
        <div className="flex items-center justify-center py-16 text-gray-400 text-sm">
          <Loader2 className="w-5 h-5 mr-2 animate-spin" /> {t('cm.components_nightaudit_tabs_FinancialTab.finansal_ozet_yukleniyor')}
        </div>
      )}
    </TabsContent>
  );
}
