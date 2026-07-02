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

export default function HRPerformanceTab({ Award, performancePage, TrendingUp, perfAvg, submitPerformance, perfForm, setPerfForm, staffDropdown, onTemplateChange, perfTemplates, setCompetencyScore, creatingPerf }) {
    const { t } = useTranslation();
    return (
        <TabsContent value="performance" className="mt-4">
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2">
              <KpiCard intent="info" icon={Award} label={t('cm.pages_HRComplete.toplam_degerlendirme')} value={performancePage.total || 0} />
              <KpiCard intent="success" icon={TrendingUp} label="Ortalama Puan" value={(perfAvg || 0).toFixed(2)} sub="0–10 ölçek" />
            </div>

            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><Plus className="w-4 h-4" />{t('cm.pages_HRComplete.yeni_degerlendirme')}</CardTitle></CardHeader>
              <CardContent>
                <form onSubmit={submitPerformance} className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                  <div>
                    <Label className="text-xs">Personel</Label>
                    <select value={perfForm.staff_id} onChange={e => setPerfForm({
              ...perfForm,
              staff_id: e.target.value
            })} className="w-full rounded-md border border-input px-3 py-2 text-sm">
                      <option value="">{t('cm.pages_HRComplete.secin_4f7bd')}</option>
                      {staffDropdown.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <Label className="text-xs">Şablon (opsiyonel)</Label>
                    <select value={perfForm.template_id} onChange={e => onTemplateChange(e.target.value)} className="w-full rounded-md border border-input px-3 py-2 text-sm">
                      <option value="">— Şablon yok —</option>
                      {perfTemplates.map(tpl => <option key={tpl.id} value={tpl.id}>{tpl.name} ({tpl.competencies?.length || 0} yetkinlik)</option>)}
                    </select>
                  </div>
                  {perfForm.template_id && Object.keys(perfForm.competency_scores || {}).length > 0 && <div className="md:col-span-2 lg:col-span-3 rounded border border-slate-200 bg-slate-50 p-3">
                      <div className="text-xs font-semibold text-slate-700 mb-2">Yetkinlik Puanları (0–10)</div>
                      <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
                        {Object.entries(perfForm.competency_scores).map(([name, score]) => <div key={name}>
                            <Label className="text-xs">{name}</Label>
                            <Input type="number" min="0" max="10" step="0.1" value={score} onChange={e => setCompetencyScore(name, e.target.value)} />
                          </div>)}
                      </div>
                    </div>}
                  <div>
                    <Label className="text-xs">{t('cm.pages_HRComplete.donem')}</Label>
                    <Input value={perfForm.period} onChange={e => setPerfForm({
              ...perfForm,
              period: e.target.value
            })} placeholder="2026 Q1" />
                  </div>
                  <div>
                    <Label className="text-xs">Genel Puan (0–10)</Label>
                    <Input type="number" min="0" max="10" step="0.1" value={perfForm.overall_score} onChange={e => setPerfForm({
              ...perfForm,
              overall_score: e.target.value
            })} />
                  </div>
                  <div>
                    <Label className="text-xs">{t('cm.pages_HRComplete.guclu_yonler')}</Label>
                    <Textarea rows={2} value={perfForm.strengths} onChange={e => setPerfForm({
              ...perfForm,
              strengths: e.target.value
            })} />
                  </div>
                  <div>
                    <Label className="text-xs">{t('cm.pages_HRComplete.gelisim_alanlari')}</Label>
                    <Textarea rows={2} value={perfForm.improvement_areas} onChange={e => setPerfForm({
              ...perfForm,
              improvement_areas: e.target.value
            })} />
                  </div>
                  <div>
                    <Label className="text-xs">Hedefler</Label>
                    <Textarea rows={2} value={perfForm.goals} onChange={e => setPerfForm({
              ...perfForm,
              goals: e.target.value
            })} />
                  </div>
                  <div className="md:col-span-2 lg:col-span-3 flex justify-end">
                    <Button type="submit" disabled={creatingPerf}>
                      <Plus className="w-4 h-4 mr-1.5" />
                      {creatingPerf ? 'Kaydediliyor...' : 'Değerlendirme Kaydet'}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>{t('cm.pages_HRComplete.gecmis_degerlendirmeler')}</CardTitle></CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-slate-500 border-b">
                        <th className="py-2">Personel</th>
                        <th>{t('cm.pages_HRComplete.donem_625f5')}</th>
                        <th>{t('cm.pages_HRComplete.tarih')}</th>
                        <th className="text-right">Puan</th>
                        <th>{t('cm.pages_HRComplete.ozet')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {performancePage.loading ? <SkeletonRow cols={5} rows={3} /> : <>
                          {performancePage.items.map(item => <tr key={item.id} className="border-t border-slate-100 align-top">
                              <td className="py-2 font-medium">{item.staff_name}</td>
                          <td>{item.period || '—'}</td>
                          <td>{(item.reviewed_at || '').slice(0, 10)}</td>
                          <td className="text-right font-semibold">{item.overall_score}</td>
                          <td className="text-slate-600 max-w-md truncate">{item.strengths || item.goals || '—'}</td>
                        </tr>)}
                          {performancePage.items.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-slate-500">{t('cm.pages_HRComplete.henuz_degerlendirme_yok')}</td></tr>}
                        </>}
                    </tbody>
                  </table>
                {!performancePage.loading && performancePage.total > 0 && <PaginationBar page={performancePage.page} totalPages={performancePage.totalPages} total={performancePage.total} limit={performancePage.limit} onPageChange={performancePage.setPage} onLimitChange={performancePage.setLimit} />}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
    );
}
