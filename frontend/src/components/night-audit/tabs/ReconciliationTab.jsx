import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { TabsContent } from '@/components/ui/tabs';
import { Moon, Play, Clock, CheckCircle2, XCircle, AlertTriangle, RefreshCw, Calendar, FileText, ChevronDown, ChevronUp, DollarSign, Users, Building2, BarChart3, Eye, Loader2, Shield, Info, Timer, Settings2, Zap, RotateCcw, TrendingUp, CreditCard, ShieldCheck, Scale, Receipt, PieChart, ArrowUpDown, Banknote, AlertOctagon, Search } from 'lucide-react';

export default function ReconciliationTab(props) {
  const { StatCard, reconciliation, t } = props;
  return (
    <TabsContent value="reconciliation" className="space-y-4 mt-4">
      {reconciliation ? (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard
              icon={Receipt}
              label={t('cm.components_nightaudit_tabs_ReconciliationTab.masraf_toplami')}
              value={`${reconciliation.charges_total?.toFixed(2) || "0.00"} TL`}
              subValue={`${reconciliation.charges_count || 0} masraf`}
              color="text-blue-600"
            />
            <StatCard
              icon={CreditCard}
              label={t('common.paymentTotal')}
              value={`${reconciliation.payments_total?.toFixed(2) || "0.00"} TL`}
              subValue={`${reconciliation.payments_count || 0} ödeme`}
              color="text-emerald-600"
            />
            <StatCard
              icon={Scale}
              label="Fark"
              value={`${reconciliation.variance?.toFixed(2) || "0.00"} TL`}
              subValue={reconciliation.is_balanced ? "Dengeli" : "Dengesiz"}
              color={reconciliation.is_balanced ? "text-emerald-600" : "text-red-600"}
            />
            <StatCard
              icon={AlertOctagon}
              label={t('cm.components_nightaudit_tabs_ReconciliationTab.tutarsizlik')}
              value={reconciliation.discrepancy_count || 0}
              subValue={`${reconciliation.high_balance_count || 0} yüksek bakiye`}
              color={reconciliation.discrepancy_count > 0 ? "text-red-600" : "text-emerald-600"}
            />
          </div>

          {/* Discrepancies */}
          <Card data-testid="discrepancies-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-500" />
                {t('cm.components_nightaudit_tabs_ReconciliationTab.tutarsizliklar')}{reconciliation.discrepancy_count || 0})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {(reconciliation.discrepancies || []).length === 0 ? (
                <div className="py-8 text-center">
                  <CheckCircle2 className="w-8 h-8 mx-auto text-emerald-400 mb-2" />
                  <p className="text-sm text-gray-500">{t('cm.components_nightaudit_tabs_ReconciliationTab.tutarsizlik_bulunamadi_mutabakat_temiz')}</p>
                </div>
              ) : (
                <div className="space-y-2 max-h-80 overflow-y-auto">
                  {(reconciliation?.discrepancies || []).map((d, i) => (
                    <div key={i} className="flex items-start gap-3 p-3 bg-gray-50 border rounded-lg">
                      <div className={`rounded-lg p-1.5 flex-shrink-0 ${
                        d.severity === "error" ? "bg-red-100" : "bg-amber-100"
                      }`}>
                        {d.severity === "error" ? (
                          <XCircle className="w-4 h-4 text-red-600" />
                        ) : (
                          <AlertTriangle className="w-4 h-4 text-amber-600" />
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-gray-800">{d.message}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <Badge className={`text-[10px] ${
                            d.type === "duplicate_charge" ? "bg-amber-50 text-amber-700 border-amber-200"
                              : d.type === "rate_discrepancy" ? "bg-blue-50 text-blue-700 border-blue-200"
                              : d.type === "high_balance" ? "bg-red-50 text-red-700 border-red-200"
                              : "bg-gray-50 text-gray-600 border-gray-200"
                          } border`}>
                            {d.type === "duplicate_charge" ? "Tekrar Masraf"
                              : d.type === "rate_discrepancy" ? "Oran Tutarsızlığı"
                              : d.type === "high_balance" ? "Yüksek Bakiye"
                              : d.type === "orphan_charge" ? "Sahipsiz Masraf"
                              : d.type}
                          </Badge>
                          {d.amount && <span className="text-[11px] text-gray-400">{d.amount} TL</span>}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* High Balance Folios */}
          {(reconciliation.high_balance_folios || []).length > 0 && (
            <Card data-testid="high-balance-folios-card">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <AlertOctagon className="w-4 h-4 text-red-500" />
                  {t('cm.components_nightaudit_tabs_ReconciliationTab.yuksek_bakiyeli_folyolar')}{reconciliation.high_balance_count})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-1.5">
                  {reconciliation.high_balance_folios.map((f) => (
                    <div key={f.id} className="flex items-center justify-between p-2.5 bg-gray-50 rounded-lg text-sm">
                      <div className="flex items-center gap-2">
                        <FileText className="w-4 h-4 text-gray-400" />
                        <span className="font-medium text-gray-800">{f.folio_number || f.id?.substring(0, 8)}</span>
                      </div>
                      <span className={`font-bold ${f.balance > 0 ? "text-red-600" : "text-blue-600"}`}>
                        {f.balance?.toFixed(2)} TL
                      </span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      ) : (
        <div className="flex items-center justify-center py-16 text-gray-400 text-sm">
          <Loader2 className="w-5 h-5 mr-2 animate-spin" /> {t('cm.components_nightaudit_tabs_ReconciliationTab.mutabakat_yukleniyor')}
        </div>
      )}
    </TabsContent>
  );
}
