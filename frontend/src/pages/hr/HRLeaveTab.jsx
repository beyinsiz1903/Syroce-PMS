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

export default function HRLeaveTab({ leaveCounts, loadLeaveBalances, staffPage, balanceLoading, leaveBalances, submitLeave, leaveForm, setLeaveForm, staffDropdown, LEAVE_TYPE_LABEL, creatingLeave, leavePage, STATUS_INTENT, STATUS_LABEL, decideLeave }) {
    const { t } = useTranslation();
    return (
        <TabsContent value="leave" className="mt-4">
          <div className="space-y-4">
            {/* Akış açıklaması */}
            <div className="rounded-md border border-sky-200 bg-sky-50 p-3 text-sm flex items-start gap-2">
              <Bell className="w-4 h-4 mt-0.5 text-sky-600 shrink-0" />
              <div className="text-slate-700 text-xs space-y-1">
                <p><strong>İzin akışı:</strong> Talep oluşturulduğunda HR yöneticilerine (admin/supervisor/finance rolleri) <strong>in-app bildirim</strong> düşer (bildirim zilinde görünür). Karar verildiğinde talep sahibine geri bildirim gider.</p>
                <p>Yıllık izin hakkı varsayılan <strong>14 gün</strong> (İş K. m.53). Personel kartında ya da <code>POST /hr/leave-balance</code> ile özelleştirilebilir. Onaylı talepler bakiyeden düşülür.</p>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              <KpiCard intent="warning" label={t('cm.pages_HRComplete.beklemede')} value={leaveCounts.pending} />
              <KpiCard intent="success" label="Onaylanan" value={leaveCounts.approved} />
              <KpiCard intent="danger" label="Reddedilen" value={leaveCounts.rejected} />
            </div>

            {/* İzin Bakiyeleri */}
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="flex items-center gap-2"><Calendar className="w-4 h-4" />Personel İzin Bakiyesi ({new Date().getFullYear()})</CardTitle>
                <Button size="sm" variant="outline" onClick={() => loadLeaveBalances(staffPage.items.map(s => s.id))} disabled={balanceLoading}>
                  <RefreshCw className={`w-3.5 h-3.5 mr-1 ${balanceLoading ? 'animate-spin' : ''}`} />Yenile
                </Button>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-slate-500 border-b">
                        <th className="py-2">Personel</th>
                        <th className="text-right">Yıllık Hak</th>
                        <th className="text-right">Devir</th>
                        <th className="text-right">Kullanılan</th>
                        <th className="text-right">Kalan</th>
                        <th className="text-right">Hastalık (kalan/hak)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {staffPage.items.map(s => {
                const b = leaveBalances[s.id];
                if (!b) return <tr key={s.id} className="border-t border-slate-100">
                            <td className="py-2">{s.name}</td>
                            <td colSpan={5} className="text-slate-400 text-xs text-center">Yükleniyor...</td>
                          </tr>;
                const remaining = b.annual?.remaining ?? 0;
                const intent = remaining <= 2 ? 'danger' : remaining <= 5 ? 'warning' : 'success';
                return <tr key={s.id} className="border-t border-slate-100">
                            <td className="py-2 font-medium">{s.name}</td>
                            <td className="text-right">{b.annual?.entitlement}</td>
                            <td className="text-right text-slate-500">{b.annual?.carry_over || 0}</td>
                            <td className="text-right">{b.annual?.used}</td>
                            <td className="text-right">
                              <StatusBadge intent={intent}>{remaining} gün</StatusBadge>
                            </td>
                            <td className="text-right text-slate-600">{b.sick?.remaining}/{b.sick?.entitlement}</td>
                          </tr>;
              })}
                      {staffPage.items.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-slate-500">Personel yok</td></tr>}
                    </tbody>
                  </table>
                {!staffPage.loading && staffPage.total > 0 && <PaginationBar page={staffPage.page} totalPages={staffPage.totalPages} total={staffPage.total} limit={staffPage.limit} onPageChange={staffPage.setPage} onLimitChange={staffPage.setLimit} />}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><Plus className="w-4 h-4" />{t('cm.pages_HRComplete.yeni_izin_talebi')}</CardTitle></CardHeader>
              <CardContent>
                <form onSubmit={submitLeave} className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                  <div>
                    <Label className="text-xs">Personel</Label>
                    <select value={leaveForm.staff_id} onChange={e => setLeaveForm({
              ...leaveForm,
              staff_id: e.target.value
            })} className="w-full rounded-md border border-input px-3 py-2 text-sm" data-testid="select-leave-staff">
                      <option value="">{t('cm.pages_HRComplete.secin')}</option>
                      {staffDropdown.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <Label className="text-xs">{t('cm.pages_HRComplete.izin_turu')}</Label>
                    <select value={leaveForm.leave_type} onChange={e => setLeaveForm({
              ...leaveForm,
              leave_type: e.target.value
            })} className="w-full rounded-md border border-input px-3 py-2 text-sm">
                      {Object.entries(LEAVE_TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <Label className="text-xs">{t('cm.pages_HRComplete.baslangic')}</Label>
                      <Input type="date" value={leaveForm.start_date} onChange={e => setLeaveForm({
                ...leaveForm,
                start_date: e.target.value
              })} />
                    </div>
                    <div>
                      <Label className="text-xs">{t('cm.pages_HRComplete.bitis')}</Label>
                      <Input type="date" value={leaveForm.end_date} onChange={e => setLeaveForm({
                ...leaveForm,
                end_date: e.target.value
              })} />
                    </div>
                  </div>
                  <div className="md:col-span-2 lg:col-span-3">
                    <Label className="text-xs">{t('cm.pages_HRComplete.aciklama')}</Label>
                    <Textarea rows={2} value={leaveForm.reason} onChange={e => setLeaveForm({
              ...leaveForm,
              reason: e.target.value
            })} placeholder={t('cm.pages_HRComplete.istege_bagli')} />
                  </div>
                  <div className="md:col-span-2 lg:col-span-3 flex justify-end">
                    <Button type="submit" disabled={creatingLeave} data-testid="btn-submit-leave">
                      <Plus className="w-4 h-4 mr-1.5" />
                      {creatingLeave ? 'Oluşturuluyor...' : 'Talep Oluştur'}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>{t('cm.pages_HRComplete.izin_talepleri')}</CardTitle></CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-slate-500 border-b">
                        <th className="py-2">Personel</th>
                        <th>{t('cm.pages_HRComplete.tur')}</th>
                        <th>{t('cm.pages_HRComplete.baslangic_677c8')}</th>
                        <th>{t('cm.pages_HRComplete.bitis_7cd21')}</th>
                        <th className="text-right">{t('cm.pages_HRComplete.gun_18b2f')}</th>
                        <th>{t('cm.pages_HRComplete.durum')}</th>
                        <th className="text-right">{t('cm.pages_HRComplete.islem')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {leavePage.loading ? <SkeletonRow cols={7} rows={3} /> : <>
                          {leavePage.items.map(item => <tr key={item.id} className="border-t border-slate-100">
                              <td className="py-2 font-medium">{item.staff_name}</td>
                          <td>{LEAVE_TYPE_LABEL[item.leave_type] || item.leave_type}</td>
                          <td>{item.start_date}</td>
                          <td>{item.end_date}</td>
                          <td className="text-right">{item.total_days}</td>
                          <td>
                            <StatusBadge intent={STATUS_INTENT[item.status]}>{STATUS_LABEL[item.status] || item.status}</StatusBadge>
                          </td>
                          <td className="text-right">
                            {item.status === 'pending' && <div className="flex justify-end gap-1 flex-wrap">
                                <Button size="sm" onClick={() => decideLeave(item.id, 'dept_approve')} data-testid={`btn-dept-approve-${item.id}`}>
                                  <CheckCircle2 className="w-3.5 h-3.5 mr-1" />Dept Onay
                                </Button>
                                <Button size="sm" variant="outline" onClick={() => decideLeave(item.id, 'reject')} data-testid={`btn-reject-${item.id}`}>
                                  <XCircle className="w-3.5 h-3.5 mr-1" />{t('cm.pages_HRComplete.reddet')}
                                </Button>
                              </div>}
                            {item.status === 'dept_approved' && <div className="flex justify-end gap-1 flex-wrap">
                                <Button size="sm" onClick={() => decideLeave(item.id, 'approve')} data-testid={`btn-hr-final-${item.id}`}>
                                  <CheckCircle2 className="w-3.5 h-3.5 mr-1" />HR Final Onay
                                </Button>
                                <Button size="sm" variant="outline" onClick={() => decideLeave(item.id, 'reject')} data-testid={`btn-hr-reject-${item.id}`}>
                                  <XCircle className="w-3.5 h-3.5 mr-1" />Reddet
                                </Button>
                              </div>}
                          </td>
                        </tr>)}
                          {leavePage.items.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-slate-500">{t('cm.pages_HRComplete.henuz_izin_talebi_yok')}</td></tr>}
                        </>}
                    </tbody>
                  </table>
                {!leavePage.loading && leavePage.total > 0 && <PaginationBar page={leavePage.page} totalPages={leavePage.totalPages} total={leavePage.total} limit={leavePage.limit} onPageChange={leavePage.setPage} onLimitChange={leavePage.setLimit} />}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
    );
}
