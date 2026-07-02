import { useTranslation } from 'react-i18next';
import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Clock, Calendar, DollarSign, Briefcase, UserPlus, Download, Users, FileSpreadsheet, RefreshCw, Plus, CheckCircle2, XCircle, TrendingUp, ExternalLink, FileDown, Award, Info, AlertCircle, Bell, FileText, ClipboardList, Send, ThumbsUp, ThumbsDown, Timer, Check, X, Package, GraduationCap } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { promptDialog, confirmDialog } from '@/lib/dialogs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { formatCurrency } from '@/lib/currency';
import PaginationBar from '@/components/PaginationBar';
import SkeletonRow from '@/components/SkeletonRow';
import { useHRPagination } from '@/hooks/useHRPagination';

export default function HRPayrollTab({ exportMonth, setExportMonth, handlePayrollPreview, handlePayrollSaveDraft, savingDraft, handlePayrollExport, exporting, taxRates, payrollRuns, selectedRun, fmtCurrency, loadRunDetail, handlePayrollFinalize, finalizing, handleRevisionOpen, revising, handleRunXlsx, runRevisions, payrollPreview, Users, DollarSign }) {
    const { t } = useTranslation();
    return (
        <TabsContent value="payroll" className="mt-4">
          <div className="space-y-4">
            <Card>
              <CardHeader className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2"><DollarSign className="w-4 h-4" />{t('cm.pages_HRComplete.bordro_islemleri')}</CardTitle>
                  <p className="text-xs text-slate-500 mt-1">
                    {t('cm.pages_HRComplete.devam_kayitlarindan_otomatik_hesap_tr_is')}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Label className="text-xs">{t('cm.pages_HRComplete.ay')}</Label>
                  <Input type="month" value={exportMonth} onChange={e => setExportMonth(e.target.value)} className="w-40" data-testid="input-payroll-month" />
                  <Button variant="outline" size="sm" onClick={handlePayrollPreview} data-testid="btn-payroll-preview">
                    <RefreshCw className="w-4 h-4 mr-1.5" />{t('cm.pages_HRComplete.onizle')}
                  </Button>
                  <Button size="sm" onClick={handlePayrollSaveDraft} disabled={savingDraft} data-testid="btn-payroll-save-draft" className="bg-slate-900 text-white hover:bg-slate-800">
                    <FileText className="w-4 h-4 mr-1.5" />
                    {savingDraft ? 'Kaydediliyor...' : 'Taslak Kaydet'}
                  </Button>
                  <Button variant="outline" size="sm" onClick={handlePayrollExport} disabled={exporting} data-testid="btn-payroll-csv">
                    <FileDown className="w-4 h-4 mr-1.5" />
                    {exporting ? 'İndiriliyor...' : 'CSV İndir'}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Task #264: Dry-run + draft/locked/revisions akış rehberi */}
                <div className="rounded-md border border-sky-200 bg-sky-50 p-3 text-sm">
                  <div className="flex items-start gap-2">
                    <Info className="w-4 h-4 mt-0.5 text-sky-600 shrink-0" />
                    <div className="space-y-2">
                      <p className="font-medium text-sky-900">Bordro yaşam döngüsü (önbordro / muhasebe ihracı)</p>
                      <ol className="list-decimal pl-5 space-y-1 text-slate-700 text-xs">
                        <li><strong>Önizle</strong>: Devam kayıtlarından dry-run hesap. Hiçbir muhasebe etkisi YOKTUR.</li>
                        <li><strong>Taslak Kaydet</strong>: Bu ayın hesabı `payroll_runs` koleksiyonuna <em>draft</em> olarak kaydedilir; aynı gün tekrar bastığınızda mevcut taslak güncellenir.</li>
                        <li><strong>Kilitle</strong>: Taslak satır bazında dondurulur (<em>locked</em>, immutable). Yalnızca HR Admin / Finance / Süper Admin.</li>
                        <li><strong>Revizyon Aç</strong>: Kilitli bordro değişmez; yeni bir taslak ile düzeltme akışı başlar (audit zinciri korunur).</li>
                        <li><strong>CSV / XLSX</strong>: Muhasebe ihracı; XLSX kalem (avans, prim, yemek, yol, kesinti, mesai) detayı içerir.</li>
                      </ol>
                      <p className="text-xs text-amber-700">
                        <AlertCircle className="w-3 h-3 inline mr-1" />
                        {(() => {
                  const r = taxRates?.rates || {
                    sgk_employee: 14,
                    unemployment: 1,
                    income_tax: 15,
                    stamp_tax: 0.759
                  };
                  const fmt = n => Number(n).toLocaleString('tr-TR', {
                    maximumFractionDigits: 3
                  });
                  return `Kesintiler: %${fmt(r.sgk_employee)} SGK + %${fmt(r.unemployment)} işsizlik + %${fmt(r.income_tax)} gelir vergisi (matrah − SGK) + %${fmt(r.stamp_tax)} damga.`;
                })()}
                        {' '}Asgari ücret muafiyeti / AGİ / özel kesintiler için muhasebenizle doğrulayın.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Runs listesi */}
                {payrollRuns.length > 0 && <div className="rounded-md border bg-white">
                    <div className="px-3 py-2 border-b bg-slate-50 text-xs font-semibold text-slate-700">
                      {exportMonth} ayı bordro çalışmaları ({payrollRuns.length})
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left text-slate-500 border-b text-xs">
                            <th className="py-2 px-3">Durum</th>
                            <th className="px-3">Run ID</th>
                            <th className="px-3 text-right">Personel</th>
                            <th className="px-3 text-right">Brüt</th>
                            <th className="px-3 text-right">Net</th>
                            <th className="px-3">Güncellendi</th>
                            <th className="px-3 text-right">İşlem</th>
                          </tr>
                        </thead>
                        <tbody>
                          {payrollRuns.map(r => <tr key={r.id} className={`border-t border-slate-100 ${selectedRun?.id === r.id ? 'bg-slate-50' : ''}`}>
                              <td className="py-2 px-3">
                                <StatusBadge intent={r.status === 'locked' ? 'success' : 'warning'}>
                                  {r.status === 'locked' ? 'Kilitli' : 'Taslak'}
                                </StatusBadge>
                              </td>
                              <td className="px-3 font-mono text-xs text-slate-600">{r.id.slice(0, 8)}…</td>
                              <td className="px-3 text-right">{r.summary?.staff_count ?? '—'}</td>
                              <td className="px-3 text-right">{r.summary ? fmtCurrency(r.summary.total_gross) : '—'}</td>
                              <td className="px-3 text-right">{r.summary ? fmtCurrency(r.summary.total_net) : '—'}</td>
                              <td className="px-3 text-xs text-slate-500">{(r.updated_at || r.created_at || '').slice(0, 16).replace('T', ' ')}</td>
                              <td className="px-3 text-right">
                                <Button size="sm" variant="outline" onClick={() => loadRunDetail(r.id)} data-testid={`btn-run-detail-${r.id.slice(0, 8)}`}>
                                  Aç
                                </Button>
                              </td>
                            </tr>)}
                        </tbody>
                      </table>
                    </div>
                  </div>}

                {/* Seçili run detayı */}
                {selectedRun && <div className="rounded-md border bg-white">
                    <div className="px-3 py-2 border-b bg-slate-50 flex flex-wrap items-center justify-between gap-2">
                      <div className="text-xs">
                        <span className="font-semibold text-slate-700">Run </span>
                        <span className="font-mono">{selectedRun.id.slice(0, 8)}…</span>
                        <span className="ml-2">
                          <StatusBadge intent={selectedRun.status === 'locked' ? 'success' : 'warning'}>
                            {selectedRun.status === 'locked' ? 'Kilitli' : 'Taslak'}
                          </StatusBadge>
                        </span>
                        {selectedRun.parent_run_id && <span className="ml-2 text-slate-500">
                            (revizyon — üst: <span className="font-mono">{selectedRun.parent_run_id.slice(0, 8)}…</span>)
                          </span>}
                      </div>
                      <div className="flex items-center gap-2">
                        {selectedRun.status === 'draft' && <Button size="sm" onClick={() => handlePayrollFinalize(selectedRun.id)} disabled={finalizing} className="bg-slate-900 text-white hover:bg-slate-800" data-testid="btn-payroll-finalize">
                            <CheckCircle2 className="w-4 h-4 mr-1.5" />
                            {finalizing ? 'Kilitleniyor...' : 'Kilitle'}
                          </Button>}
                        {selectedRun.status === 'locked' && <Button size="sm" variant="outline" onClick={() => handleRevisionOpen(selectedRun.id)} disabled={revising} data-testid="btn-payroll-revision">
                            <RefreshCw className="w-4 h-4 mr-1.5" />
                            {revising ? 'Açılıyor...' : 'Revizyon Aç'}
                          </Button>}
                        <Button size="sm" variant="outline" onClick={() => handleRunXlsx(selectedRun.id)} data-testid="btn-payroll-xlsx">
                          <FileDown className="w-4 h-4 mr-1.5" />XLSX İndir
                        </Button>
                      </div>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left text-slate-500 border-b text-xs">
                            <th className="py-2 px-3">Personel</th>
                            <th className="px-3">Departman</th>
                            <th className="px-3 text-right">Saat</th>
                            <th className="px-3 text-right">Mesai</th>
                            <th className="px-3 text-right">Brüt</th>
                            <th className="px-3 text-right">Ek Kazanç</th>
                            <th className="px-3 text-right">Ek Kesinti</th>
                            <th className="px-3 text-right">Net</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(selectedRun.rows || []).map(row => <tr key={row.staff_id} className="border-t border-slate-100">
                              <td className="py-2 px-3 font-medium">{row.staff_name}</td>
                              <td className="px-3 capitalize text-slate-600">{row.department}</td>
                              <td className="px-3 text-right">{Number(row.total_hours || 0).toFixed(1)}</td>
                              <td className="px-3 text-right text-amber-700">{Number(row.overtime_hours || 0).toFixed(1)}</td>
                              <td className="px-3 text-right">{fmtCurrency(row.gross_pay)}</td>
                              <td className="px-3 text-right text-emerald-700">{fmtCurrency(row.extra_earnings || 0)}</td>
                              <td className="px-3 text-right text-rose-700">{fmtCurrency(row.extra_deductions || 0)}</td>
                              <td className="px-3 text-right font-semibold">{fmtCurrency(row.net_salary)}</td>
                            </tr>)}
                          {(!selectedRun.rows || selectedRun.rows.length === 0) && <tr><td colSpan={8} className="py-6 text-center text-slate-500">Bu run'da satır yok</td></tr>}
                        </tbody>
                      </table>
                    </div>
                    {runRevisions.length > 0 && <div className="border-t bg-slate-50 px-3 py-2 text-xs">
                        <div className="font-semibold text-slate-700 mb-1">Revizyon geçmişi ({runRevisions.length})</div>
                        <ul className="space-y-1">
                          {runRevisions.map(rev => <li key={rev.id} className="flex flex-wrap items-center gap-2 text-slate-600">
                              <span className="text-slate-400">{(rev.created_at || '').slice(0, 16).replace('T', ' ')}</span>
                              <span className="font-mono">{rev.new_run_id?.slice(0, 8)}…</span>
                              <span>—</span>
                              <span>{rev.reason}</span>
                              <span className="text-slate-400">
                                (brüt {fmtCurrency(rev.diff?.gross_before)} → {fmtCurrency(rev.diff?.gross_after)})
                              </span>
                            </li>)}
                        </ul>
                      </div>}
                  </div>}

                {payrollPreview ? <>
                    <div className="grid gap-3 md:grid-cols-3">
                      <KpiCard intent="info" icon={Users} label="Personel" value={payrollPreview.staff_count} />
                      <KpiCard intent="success" icon={DollarSign} label={t('cm.pages_HRComplete.toplam_brut')} value={fmtCurrency(payrollPreview.total_gross_pay)} />
                      <KpiCard intent="warning" icon={DollarSign} label={t('cm.pages_HRComplete.toplam_net')} value={fmtCurrency(payrollPreview.total_net_pay)} />
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left text-slate-500 border-b">
                            <th className="py-2">Personel</th>
                            <th>Departman</th>
                            <th className="text-right">{t('cm.pages_HRComplete.saat_2460e')}</th>
                            <th className="text-right">Mesai</th>
                            <th className="text-right">{t('cm.pages_HRComplete.brut')}</th>
                            <th className="text-right">{t('cm.pages_HRComplete.sgk_issiz')}</th>
                            <th className="text-right">Vergi</th>
                            <th className="text-right">Net</th>
                          </tr>
                        </thead>
                        <tbody>
                          {payrollPreview.payroll?.map(row => <tr key={row.staff_id} className="border-t border-slate-100">
                              <td className="py-2 font-medium">{row.staff_name}</td>
                              <td className="capitalize text-slate-600">{row.department}</td>
                              <td className="text-right">{row.total_hours.toFixed(1)}</td>
                              <td className="text-right text-amber-700">{row.overtime_hours.toFixed(1)}</td>
                              <td className="text-right">{fmtCurrency(row.gross_pay)}</td>
                              <td className="text-right text-slate-600">{fmtCurrency(row.sgk_employee + row.unemployment)}</td>
                              <td className="text-right text-slate-600">{fmtCurrency(row.income_tax + row.stamp_tax)}</td>
                              <td className="text-right font-semibold">{fmtCurrency(row.net_salary)}</td>
                            </tr>)}
                          {(!payrollPreview.payroll || payrollPreview.payroll.length === 0) && <tr><td colSpan={8} className="py-6 text-center text-slate-500">{t('cm.pages_HRComplete.bu_ayda_devam_kaydi_yok')}</td></tr>}
                        </tbody>
                      </table>
                    </div>
                  </> : <div className="rounded-md border bg-slate-50 p-4 text-sm text-slate-600">
                    {t('cm.pages_HRComplete.bordro_onizlemek_icin_ay_secin_ve')} <strong>{t('cm.pages_HRComplete.onizle_d9316')}</strong>{t('cm.pages_HRComplete.ye_basin_kalici_kayit_icin')} <strong>{t('cm.pages_HRComplete.bordroyu_kaydet')}</strong>{t('cm.pages_HRComplete.disa_aktarmak_icin')} <strong>{t('cm.pages_HRComplete.csv_indir')}</strong>.
                  </div>}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
    );
}
