import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { TabsContent } from '@/components/ui/tabs';
import { Moon, Play, Clock, CheckCircle2, XCircle, AlertTriangle, RefreshCw, Calendar, FileText, ChevronDown, ChevronUp, DollarSign, Users, Building2, BarChart3, Eye, Loader2, Shield, Info, Timer, Settings2, Zap, RotateCcw, TrendingUp, CreditCard, ShieldCheck, Scale, Receipt, PieChart, ArrowUpDown, Banknote, AlertOctagon, Search } from 'lucide-react';

export default function ReportTab(props) {
  const { StatusBadge, categoryLabels, fetchFinancialReport, finLoading, financialReport, paymentMethodLabels, reportDates, setReportDates } = props;
  return (
    <TabsContent value="report" className="space-y-4 mt-4">
      <Card data-testid="financial-report-card">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Search className="w-4 h-4 text-indigo-500" />
            Tarih Aralığı Finansal Rapor
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row items-end gap-3 mb-4">
            <div className="flex-1">
              <label className="text-xs text-gray-600 mb-1 block">Başlangıç Tarihi</label>
              <input
                data-testid="report-start-date"
                type="date"
                value={reportDates.start}
                onChange={(e) => setReportDates((p) => ({ ...p, start: e.target.value }))}
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
            </div>
            <div className="flex-1">
              <label className="text-xs text-gray-600 mb-1 block">Bitiş Tarihi</label>
              <input
                data-testid="report-end-date"
                type="date"
                value={reportDates.end}
                onChange={(e) => setReportDates((p) => ({ ...p, end: e.target.value }))}
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
            </div>
            <Button
              data-testid="generate-report-btn"
              size="sm"
              onClick={() => fetchFinancialReport(reportDates.start, reportDates.end)}
              disabled={!reportDates.start || !reportDates.end || finLoading}
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
            >
              {finLoading ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <BarChart3 className="w-4 h-4 mr-1" />}
              Rapor Oluştur
            </Button>
          </div>

          {financialReport ? (
            <div className="space-y-4">
              {/* Summary */}
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                <div className="p-3 bg-emerald-50 rounded-lg">
                  <p className="text-lg font-bold text-emerald-700">{financialReport.summary?.total_revenue?.toFixed(2)} TL</p>
                  <p className="text-[11px] text-emerald-600">Toplam Gelir</p>
                </div>
                <div className="p-3 bg-blue-50 rounded-lg">
                  <p className="text-lg font-bold text-blue-700">{financialReport.summary?.total_tax?.toFixed(2)} TL</p>
                  <p className="text-[11px] text-blue-600">Toplam Vergi</p>
                </div>
                <div className="p-3 bg-indigo-50 rounded-lg">
                  <p className="text-lg font-bold text-indigo-700">{financialReport.summary?.total_with_tax?.toFixed(2)} TL</p>
                  <p className="text-[11px] text-indigo-600">Vergili Toplam</p>
                </div>
                <div className="p-3 bg-gray-50 rounded-lg">
                  <p className="text-lg font-bold text-gray-700">{financialReport.summary?.total_payments?.toFixed(2)} TL</p>
                  <p className="text-[11px] text-gray-600">Toplam Ödeme</p>
                </div>
                <div className="p-3 bg-amber-50 rounded-lg">
                  <p className="text-lg font-bold text-amber-700">{financialReport.summary?.net_position?.toFixed(2)} TL</p>
                  <p className="text-[11px] text-amber-600">Net Pozisyon</p>
                </div>
                <div className="p-3 bg-purple-50 rounded-lg">
                  <p className="text-lg font-bold text-purple-700">{financialReport.summary?.total_bookings || 0}</p>
                  <p className="text-[11px] text-purple-600">Toplam Rezervasyon</p>
                </div>
              </div>

              {/* Category Breakdown */}
              {Object.keys(financialReport.revenue_by_category || {}).length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">Kategori Bazlı Gelir</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2">
                        {Object.entries(financialReport.revenue_by_category).map(([cat, data]) => (
                          <div key={cat} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
                            <span className="text-sm font-medium text-gray-700">{categoryLabels[cat] || cat}</span>
                            <div className="text-right">
                              <span className="text-sm font-semibold">{data.amount.toFixed(2)} TL</span>
                              <span className="text-[11px] text-gray-400 ml-2">({data.count})</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">Ödeme Yöntem Dağılımı</CardTitle>
                    </CardHeader>
                    <CardContent>
                      {Object.keys(financialReport.payments_by_method || {}).length === 0 ? (
                        <p className="text-xs text-gray-400 py-4 text-center">Ödeme kaydedilmemiş</p>
                      ) : (
                        <div className="space-y-2">
                          {Object.entries(financialReport.payments_by_method).map(([method, data]) => (
                            <div key={method} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
                              <span className="text-sm font-medium text-gray-700">{paymentMethodLabels[method] || method}</span>
                              <div className="text-right">
                                <span className="text-sm font-semibold">{data.amount.toFixed(2)} TL</span>
                                <span className="text-[11px] text-gray-400 ml-2">({data.count})</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </div>
              )}

              {/* Daily Revenue Trend */}
              {(financialReport.revenue_by_date || []).length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <BarChart3 className="w-4 h-4 text-emerald-500" />
                      Günlük Gelir Trendi
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-xs text-gray-500 border-b">
                            <th className="text-left pb-2 pr-4">Tarih</th>
                            <th className="text-right pb-2 pr-4">Gelir</th>
                            <th className="text-right pb-2 pr-4">Vergi</th>
                            <th className="text-right pb-2">Kategoriler</th>
                          </tr>
                        </thead>
                        <tbody>
                          {financialReport.revenue_by_date.map((day) => (
                            <tr key={day.date} className="border-b border-gray-50 hover:bg-gray-50">
                              <td className="py-2 pr-4 font-medium">{day.date}</td>
                              <td className="py-2 pr-4 text-right font-semibold text-emerald-600">{day.total.toFixed(2)} TL</td>
                              <td className="py-2 pr-4 text-right text-gray-500">{day.tax.toFixed(2)} TL</td>
                              <td className="py-2 text-right">
                                <div className="flex flex-wrap justify-end gap-1">
                                  {Object.entries(day.categories || {}).map(([cat, d]) => (
                                    <Badge key={cat} className="bg-gray-100 text-gray-600 border-gray-200 border text-[10px]">
                                      {categoryLabels[cat] || cat}: {d.amount.toFixed(0)}
                                    </Badge>
                                  ))}
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Audit Runs in Range */}
              {(financialReport.audit_runs || []).length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Moon className="w-4 h-4 text-indigo-500" />
                      Donem Denetim Geçmişi ({financialReport.audit_runs.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-xs text-gray-500 border-b">
                            <th className="text-left pb-2 pr-4">Tarih</th>
                            <th className="text-left pb-2 pr-4">Durum</th>
                            <th className="text-right pb-2 pr-4">Gelir</th>
                            <th className="text-right pb-2 pr-4">Vergi</th>
                            <th className="text-right pb-2 pr-4">Oda</th>
                            <th className="text-right pb-2">Sure</th>
                          </tr>
                        </thead>
                        <tbody>
                          {financialReport.audit_runs.map((run) => (
                            <tr key={run.audit_id} className="border-b border-gray-50 hover:bg-gray-50">
                              <td className="py-2 pr-4 font-medium">{run.business_date}</td>
                              <td className="py-2 pr-4"><StatusBadge status={run.status} /></td>
                              <td className="py-2 pr-4 text-right font-semibold">{run.total_room_revenue?.toFixed(2)} TL</td>
                              <td className="py-2 pr-4 text-right text-gray-500">{run.total_tax_amount?.toFixed(2)} TL</td>
                              <td className="py-2 pr-4 text-right">{run.rooms_processed}</td>
                              <td className="py-2 text-right text-gray-400">{run.duration_ms ? `${run.duration_ms}ms` : "-"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          ) : (
            <div className="py-12 text-center">
              <BarChart3 className="w-10 h-10 mx-auto text-gray-300 mb-2" />
              <p className="text-sm text-gray-500">Tarih aralığı seçip "Rapor Oluştur" butonuna tıklayın</p>
            </div>
          )}
        </CardContent>
      </Card>
    </TabsContent>
  );
}
