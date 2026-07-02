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

export default function HRAttendanceTab({ Users, attendanceMetrics, Clock, TrendingUp, outstandingEquipTotal, Package, expiringTrainTotal, GraduationCap, selectedStaffId, setSelectedStaffId, staffDropdown, clockIn, clockOut, navigate, recordsRange, attendanceRecords, fmtTime, topPerformers }) {
    const { t } = useTranslation();
    return (
        <TabsContent value="attendance" className="mt-4">
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-5">
              <KpiCard intent="info" icon={Users} label={t('cm.pages_HRComplete.toplam_calisan')} value={attendanceMetrics.total_active_staff ?? attendanceMetrics.staff_count} sub={`aktif personel${attendanceMetrics.staff_count ? ` • ${attendanceMetrics.staff_count} devam kayıtlı` : ''}`} />
              <KpiCard intent="success" icon={Clock} label={t('cm.pages_HRComplete.toplam_saat')} value={(attendanceMetrics.total_hours || 0).toFixed(1)} sub="son 30 gün" />
              <KpiCard intent="warning" icon={TrendingUp} label={t('cm.pages_HRComplete.ortalama_saat')} value={(attendanceMetrics.avg_hours_per_active_staff || attendanceMetrics.avg_hours_per_staff || 0).toFixed(1)} sub="personel başı (son 30 gün)" />
              <KpiCard intent={outstandingEquipTotal > 0 ? 'warning' : 'neutral'} icon={Package} label="Açık Zimmet" value={outstandingEquipTotal} sub="iade alınmamış" />
              <KpiCard intent={expiringTrainTotal > 0 ? 'warning' : 'neutral'} icon={GraduationCap} label="Süresi Dolan Eğitim" value={expiringTrainTotal} sub="önümüzdeki 60 gün" />
            </div>

            <Card>
              <CardHeader className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <CardTitle>{t('cm.pages_HRComplete.giris_cikis_kaydi')}</CardTitle>
                <div className="flex flex-wrap gap-2 items-center">
                  <Label className="text-xs">Personel</Label>
                  <select value={selectedStaffId} onChange={e => setSelectedStaffId(e.target.value)} className="rounded-md border border-input px-3 py-1.5 text-sm min-w-[200px]" data-testid="select-staff">
                    {staffDropdown.length === 0 && <option value="">— Personel yok —</option>}
                    {staffDropdown.map(s => <option key={s.id} value={s.id}>
                        {s.name} {s.department ? `(${s.department})` : ''}
                      </option>)}
                  </select>
                  <Button size="sm" onClick={clockIn} disabled={!selectedStaffId} data-testid="btn-clock-in">
                    <Clock className="w-4 h-4 mr-1.5" />{t('cm.pages_HRComplete.giris_yap')}
                  </Button>
                  <Button size="sm" variant="outline" onClick={clockOut} disabled={!selectedStaffId} data-testid="btn-clock-out">
                    <Clock className="w-4 h-4 mr-1.5" />{t('cm.pages_HRComplete.cikis_yap')}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {staffDropdown.length === 0 && <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                    {t('cm.pages_HRComplete.personel_listesi_bos_personel_eklemek_ic')}
                    <Button variant="link" size="sm" className="px-1.5" onClick={() => navigate('/staff-management')}>
                      {t('cm.pages_HRComplete.personel_yonetimi_28ee4')}
                    </Button>
                    {t('cm.pages_HRComplete.sayfasini_kullanin')}
                  </div>}
                <div className="rounded-md border bg-slate-50 p-3 text-xs text-slate-600">
                  {t('cm.pages_HRComplete.izlenen_aralik')} {recordsRange.start || '—'} → {recordsRange.end || '—'}
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-slate-500 border-b">
                        <th className="py-2">Personel</th>
                        <th>Departman</th>
                        <th>{t('cm.pages_HRComplete.gun')}</th>
                        <th>{t('cm.pages_HRComplete.giris')}</th>
                        <th>{t('cm.pages_HRComplete.cikis')}</th>
                        <th className="text-right">{t('cm.pages_HRComplete.saat')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {attendanceRecords.map(record => <tr key={record.id || record.clock_in} className="border-t border-slate-100">
                          <td className="py-2 font-medium">{record.staff_name || record.staff_id}</td>
                          <td className="capitalize text-slate-600">{record.department || '—'}</td>
                          <td className="text-slate-600">{record.date}</td>
                          <td>{fmtTime(record.clock_in)}</td>
                          <td>{record.clock_out ? fmtTime(record.clock_out) : '—'}</td>
                          <td className="text-right">{record.total_hours?.toFixed(2) ?? '—'}</td>
                        </tr>)}
                      {attendanceRecords.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-slate-500">{t('cm.pages_HRComplete.kayit_bulunamadi')}</td></tr>}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><Award className="w-4 h-4" />{t('cm.pages_HRComplete.en_yuksek_saat_top_3')}</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                {topPerformers.map(s => <div key={s.staff_id} className="flex items-center justify-between rounded border border-slate-100 bg-white px-3 py-2 text-sm">
                    <div>
                      <p className="font-semibold text-slate-800">{s.staff_name}</p>
                      <p className="text-xs text-slate-500 capitalize">{s.department}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-slate-400">{t('cm.pages_HRComplete.toplam_saat_f69c5')}</p>
                      <p className="text-lg font-bold text-slate-900">{s.total_hours?.toFixed(1)}</p>
                    </div>
                  </div>)}
                {topPerformers.length === 0 && <div className="text-center py-6 space-y-2">
                    <p className="text-sm text-slate-500">Yeterli devam verisi yok</p>
                    <Button variant="outline" size="sm" onClick={() => navigate('/staff-management')}>
                      <UserPlus className="w-4 h-4 mr-1.5" />{t('cm.pages_HRComplete.personel_ekle')}
                    </Button>
                  </div>}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
    );
}
