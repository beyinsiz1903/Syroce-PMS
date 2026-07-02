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

export default function HROvertimeTab({ Timer, overtimeCounts, CheckCircle2, XCircle, severanceCap, updateSeveranceCap, savingSeverance, taxRates, updateTaxRates, savingTaxRates, taxRatesForm, setTaxRatesForm, overtimeItems, STATUS_INTENT, STATUS_LABEL, decideOvertime }) {
    const { t } = useTranslation();
    return (
        <TabsContent value="overtime" className="mt-4">
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-3">
              <KpiCard intent="warning" icon={Timer} label="Bekleyen Talep" value={overtimeCounts.pending || 0} sub="onay bekliyor" />
              <KpiCard intent="success" icon={CheckCircle2} label="Onaylanan" value={overtimeCounts.approved || 0} sub="bu yıl" />
              <KpiCard intent="danger" icon={XCircle} label="Reddedilen" value={overtimeCounts.rejected || 0} />
            </div>

            {severanceCap && <Card className="border-slate-200">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center justify-between">
                    <span className="flex items-center gap-2 text-base">
                      <Timer className="w-4 h-4" />Kıdem Tazminatı Tavanı (Tenant Ayarı)
                    </span>
                    <Button size="sm" variant="outline" onClick={updateSeveranceCap} disabled={savingSeverance}>
                      {savingSeverance ? 'Kaydediliyor…' : 'Tavanı Güncelle'}
                    </Button>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-3 md:grid-cols-3 text-sm">
                    <div className="rounded border border-slate-200 p-3">
                      <div className="text-xs text-slate-500">Günlük Brüt Tavan</div>
                      <div className="text-lg font-semibold mt-1">
                        ₺{Number(severanceCap.daily_cap || 0).toLocaleString('tr-TR', {
                minimumFractionDigits: 2
              })}
                      </div>
                      {severanceCap.is_default && <div className="text-[11px] text-amber-600 mt-1">Default değer kullanılıyor</div>}
                    </div>
                    <div className="rounded border border-slate-200 p-3">
                      <div className="text-xs text-slate-500">30 Günlük Tavan (yaklaşık)</div>
                      <div className="text-lg font-semibold mt-1">
                        ₺{Number(severanceCap.monthly_cap_estimate || 0).toLocaleString('tr-TR', {
                minimumFractionDigits: 2
              })}
                      </div>
                    </div>
                    <div className="rounded border border-slate-200 p-3">
                      <div className="text-xs text-slate-500">Son Güncelleme</div>
                      <div className="text-sm mt-1">
                        {severanceCap.updated_at ? severanceCap.updated_at.slice(0, 10) : 'Hiç güncellenmemiş'}
                      </div>
                    </div>
                  </div>
                  <div className="text-[11px] text-slate-500 mt-3">
                    {severanceCap.note}
                  </div>
                </CardContent>
              </Card>}

            {taxRates && <Card className="border-slate-200">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center justify-between">
                    <span className="flex items-center gap-2 text-base">
                      <AlertCircle className="w-4 h-4" />Vergi Oranlarını Güncelle (Bordro Kesintileri)
                    </span>
                    {taxRates.can_edit && <Button size="sm" variant="outline" onClick={updateTaxRates} disabled={savingTaxRates}>
                        {savingTaxRates ? 'Kaydediliyor…' : 'Oranları Kaydet'}
                      </Button>}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-3 md:grid-cols-4 text-sm">
                    {[{
            key: 'sgk_employee',
            label: 'SGK İşçi Payı'
          }, {
            key: 'unemployment',
            label: 'İşsizlik Sigortası'
          }, {
            key: 'income_tax',
            label: 'Gelir Vergisi'
          }, {
            key: 'stamp_tax',
            label: 'Damga Vergisi'
          }].map(({
            key,
            label
          }) => {
            const isCustom = taxRatesForm && Number(taxRatesForm[key]) !== Number(taxRates.defaults?.[key]);
            return <div key={key} className="rounded border border-slate-200 p-3">
                          <div className="text-xs text-slate-500">{label}</div>
                          <div className="flex items-center gap-1 mt-1">
                            <Input type="number" step="0.001" min="0" max="100" className="h-9" value={taxRatesForm ? taxRatesForm[key] ?? '' : ''} disabled={!taxRates.can_edit} onChange={e => setTaxRatesForm(f => ({
                  ...(f || {}),
                  [key]: e.target.value
                }))} />
                            <span className="text-slate-500">%</span>
                          </div>
                          <div className="text-[11px] mt-1">
                            {isCustom ? <span className="text-sky-600">
                                Tenant'a özel (varsayılan %{Number(taxRates.defaults?.[key]).toLocaleString('tr-TR', {
                    maximumFractionDigits: 3
                  })})
                              </span> : <span className="text-amber-600">Varsayılan değer</span>}
                          </div>
                        </div>;
          })}
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-2 mt-3">
                    <div className="text-[11px] text-slate-500">
                      {taxRates.note}
                    </div>
                    <div className="text-[11px] text-slate-500">
                      Son güncelleme: {taxRates.updated_at ? taxRates.updated_at.slice(0, 10) : 'Hiç güncellenmemiş'}
                    </div>
                  </div>
                </CardContent>
              </Card>}

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span className="flex items-center gap-2"><Timer className="w-4 h-4" />Mesai Talepleri</span>
                  <span className="text-xs text-slate-500 font-normal">İş K. m.41/3 — yıllık 270 saat üst sınırı otomatik kontrol edilir</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-slate-500 border-b">
                        <th className="py-2">Personel</th>
                        <th>Tarih</th>
                        <th className="text-right">Saat</th>
                        <th>Sebep</th>
                        <th>Durum</th>
                        <th>İstek</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {overtimeItems.map(req => <tr key={req.id} className="border-t border-slate-100 align-top">
                          <td className="py-2 font-medium">{req.staff_name}</td>
                          <td>{req.work_date}</td>
                          <td className="text-right">{req.hours}h</td>
                          <td className="text-slate-600 text-xs max-w-xs">{req.reason}</td>
                          <td>
                            <StatusBadge intent={STATUS_INTENT[req.status] || 'neutral'}>
                              {STATUS_LABEL[req.status] || req.status}
                            </StatusBadge>
                            {req.decision_note && <div className="text-[10px] text-slate-500 mt-1 max-w-[160px] truncate" title={req.decision_note}>
                                {req.decision_note}
                              </div>}
                          </td>
                          <td className="text-xs text-slate-500">{(req.requested_at || '').slice(0, 10)}</td>
                          <td className="text-right">
                            {req.status === 'pending' && <div className="flex justify-end gap-1 flex-wrap">
                                <Button size="sm" onClick={() => decideOvertime(req, 'dept_approve')} data-testid={`ot-dept-${req.id}`}>
                                  <Check className="w-3.5 h-3.5 mr-1" />Dept Onay
                                </Button>
                                <Button size="sm" variant="outline" onClick={() => decideOvertime(req, 'reject')} data-testid={`ot-reject-${req.id}`}>
                                  <X className="w-3.5 h-3.5 mr-1 text-rose-600" />Reddet
                                </Button>
                              </div>}
                            {req.status === 'dept_approved' && <div className="flex justify-end gap-1 flex-wrap">
                                <Button size="sm" onClick={() => decideOvertime(req, 'approve')} data-testid={`ot-hr-final-${req.id}`}>
                                  <Check className="w-3.5 h-3.5 mr-1" />HR Final (Bordro)
                                </Button>
                                <Button size="sm" variant="outline" onClick={() => decideOvertime(req, 'reject')} data-testid={`ot-hr-reject-${req.id}`}>
                                  <X className="w-3.5 h-3.5 mr-1 text-rose-600" />Reddet
                                </Button>
                              </div>}
                          </td>
                        </tr>)}
                      {overtimeItems.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-slate-500">
                          Mesai talebi yok — personel uygulamadan talep gönderdiğinde burada görünür
                        </td></tr>}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
    );
}
