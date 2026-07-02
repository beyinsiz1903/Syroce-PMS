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

export default function HRRecruitmentTab({ jobItems, submitJob, jobForm, setJobForm, parseInt, creatingJob, openApplicants, decideJob, closeJob, applicantsDialog, setApplicantsDialog, submitApplicant, applicantForm, setApplicantForm, savingApplicant, setApplicantStatus }) {
    const { t } = useTranslation();
    return (
        <TabsContent value="recruitment" className="mt-4">
          <div className="space-y-4">
            {/* Akış açıklaması */}
            <div className="rounded-md border border-sky-200 bg-sky-50 p-3 text-sm flex items-start gap-2">
              <Info className="w-4 h-4 mt-0.5 text-sky-600 shrink-0" />
              <div className="text-slate-700 text-xs space-y-1">
                <p><strong>Bu modül dış yayınlama (LinkedIn/Kariyer.net) yapmaz.</strong> Departman müdürü personel ihtiyacını bildirir, HR yöneticisi onaylar, onaylı pozisyonlara aday eklenip süreç (görüşme/teklif/işe alım) takip edilir.</p>
                <p>Talep oluşturulduğunda HR yöneticilerine bildirim gider. Karar (onay/red) talep sahibine bildirim olarak döner.</p>
              </div>
            </div>

            {/* KPI özet */}
            <div className="grid gap-3 md:grid-cols-4">
              <KpiCard intent="warning" label="Onay Bekleyen Talep" value={jobItems.filter(j => j.status === 'pending_approval').length} />
              <KpiCard intent="success" label="Açık Pozisyon" value={jobItems.filter(j => j.status === 'active').length} />
              <KpiCard intent="info" label="Toplam İhtiyaç (kişi)" value={jobItems.filter(j => ['pending_approval', 'active'].includes(j.status)).reduce((sum, j) => sum + (j.headcount_needed || 1), 0)} />
              <KpiCard intent="neutral" label="Toplam Aday" value={jobItems.reduce((sum, j) => sum + (j.applicants_count || 0), 0)} />
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><Plus className="w-4 h-4" />Yeni Personel Talebi</CardTitle>
                <p className="text-xs text-slate-500 mt-1">
                  Departman müdürü olarak doldurun. Onay sonrası aday eklemeye açılır.
                </p>
              </CardHeader>
              <CardContent>
                <form onSubmit={submitJob} className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                  <div>
                    <Label className="text-xs">Pozisyon *</Label>
                    <Input required value={jobForm.title} onChange={e => setJobForm({
              ...jobForm,
              title: e.target.value
            })} placeholder="Resepsiyonist" />
                  </div>
                  <div>
                    <Label className="text-xs">Departman *</Label>
                    <Input required value={jobForm.department} onChange={e => setJobForm({
              ...jobForm,
              department: e.target.value
            })} placeholder="front_desk" />
                  </div>
                  <div>
                    <Label className="text-xs">İhtiyaç Sayısı (kişi)</Label>
                    <Input type="number" min="1" max="50" value={jobForm.headcount_needed} onChange={e => setJobForm({
              ...jobForm,
              headcount_needed: parseInt(e.target.value) || 1
            })} />
                  </div>
                  <div>
                    <Label className="text-xs">Aciliyet</Label>
                    <select value={jobForm.urgency} onChange={e => setJobForm({
              ...jobForm,
              urgency: e.target.value
            })} className="w-full rounded-md border border-input px-3 py-2 text-sm">
                      <option value="low">Düşük</option>
                      <option value="normal">Normal</option>
                      <option value="high">Yüksek</option>
                      <option value="critical">Kritik</option>
                    </select>
                  </div>
                  <div>
                    <Label className="text-xs">Çalışma Şekli</Label>
                    <select value={jobForm.employment_type} onChange={e => setJobForm({
              ...jobForm,
              employment_type: e.target.value
            })} className="w-full rounded-md border border-input px-3 py-2 text-sm">
                      <option value="full_time">Tam Zamanlı</option>
                      <option value="part_time">Yarı Zamanlı</option>
                      <option value="seasonal">Sezonluk</option>
                      <option value="contract">Sözleşmeli</option>
                      <option value="intern">Stajyer</option>
                    </select>
                  </div>
                  <div>
                    <Label className="text-xs">İhtiyaç Tarihi</Label>
                    <Input type="date" value={jobForm.needed_by} onChange={e => setJobForm({
              ...jobForm,
              needed_by: e.target.value
            })} />
                  </div>
                  <div>
                    <Label className="text-xs">Ücret Aralığı (öneri)</Label>
                    <Input value={jobForm.salary_range} onChange={e => setJobForm({
              ...jobForm,
              salary_range: e.target.value
            })} placeholder="22.000 – 30.000 TL" />
                  </div>
                  <div>
                    <Label className="text-xs">Lokasyon</Label>
                    <Input value={jobForm.location} onChange={e => setJobForm({
              ...jobForm,
              location: e.target.value
            })} />
                  </div>
                  <div className="md:col-span-2 lg:col-span-3">
                    <Label className="text-xs">Gerekçe (HR'a not)</Label>
                    <Textarea rows={2} value={jobForm.justification} onChange={e => setJobForm({
              ...jobForm,
              justification: e.target.value
            })} placeholder="Örn: yaz sezonu için ek personel; mevcut kadronun yetersizliği vb." />
                  </div>
                  <div className="md:col-span-2 lg:col-span-3">
                    <Label className="text-xs">Pozisyon Açıklaması</Label>
                    <Textarea rows={3} value={jobForm.description} onChange={e => setJobForm({
              ...jobForm,
              description: e.target.value
            })} placeholder="Sorumluluklar, beklentiler, gerekli niteliklere dair detaylar" />
                  </div>
                  <div className="md:col-span-2 lg:col-span-3 flex justify-end">
                    <Button type="submit" disabled={creatingJob}>
                      <Send className="w-4 h-4 mr-1.5" />
                      {creatingJob ? 'Gönderiliyor...' : 'Talep Oluştur (HR\'a Gönder)'}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>Talepler & Açık Pozisyonlar</CardTitle></CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-slate-500 border-b">
                        <th className="py-2">Pozisyon</th>
                        <th>Departman</th>
                        <th className="text-right">İhtiyaç</th>
                        <th>Aciliyet</th>
                        <th>İhtiyaç Tarihi</th>
                        <th>Talep Eden</th>
                        <th>Durum</th>
                        <th className="text-right">Aday</th>
                        <th className="text-right">İşlem</th>
                      </tr>
                    </thead>
                    <tbody>
                      {jobItems.map(job => <tr key={job.id} className="border-t border-slate-100 align-top">
                          <td className="py-2">
                            <div className="font-medium">{job.title}</div>
                            {job.justification && <div className="text-xs text-slate-400 max-w-xs truncate" title={job.justification}>
                                {job.justification}
                              </div>}
                          </td>
                          <td className="capitalize text-slate-600">{job.department}</td>
                          <td className="text-right">{job.headcount_needed || 1}</td>
                          <td>
                            {job.urgency === 'critical' && <StatusBadge intent="danger">Kritik</StatusBadge>}
                            {job.urgency === 'high' && <StatusBadge intent="warning">Yüksek</StatusBadge>}
                            {job.urgency === 'normal' && <span className="text-xs text-slate-500">Normal</span>}
                            {job.urgency === 'low' && <span className="text-xs text-slate-400">Düşük</span>}
                          </td>
                          <td className="text-slate-600 text-xs">{job.needed_by || '—'}</td>
                          <td className="text-slate-600 text-xs">{job.created_by_name || '—'}</td>
                          <td>
                            {job.status === 'pending_approval' && <StatusBadge intent="warning">Onay Bekliyor</StatusBadge>}
                            {job.status === 'active' && <StatusBadge intent="success">Açık</StatusBadge>}
                            {job.status === 'rejected' && <StatusBadge intent="danger">Reddedildi</StatusBadge>}
                            {job.status === 'closed' && <StatusBadge intent="neutral">Kapalı</StatusBadge>}
                          </td>
                          <td className="text-right">
                            <button type="button" onClick={() => openApplicants(job)} className="text-sky-600 hover:underline" disabled={job.status === 'pending_approval'}>
                              {job.applicants_count || 0}
                            </button>
                          </td>
                          <td className="text-right">
                            <div className="flex justify-end gap-1">
                              {job.status === 'pending_approval' && <>
                                  <Button size="sm" variant="outline" onClick={() => decideJob(job.id, 'approve')} title="HR yöneticisi olarak onayla">
                                    <ThumbsUp className="w-3.5 h-3.5 mr-1" />Onayla
                                  </Button>
                                  <Button size="sm" variant="outline" onClick={() => decideJob(job.id, 'reject')}>
                                    <ThumbsDown className="w-3.5 h-3.5 mr-1" />Reddet
                                  </Button>
                                </>}
                              {job.status === 'active' && <>
                                  <Button size="sm" variant="outline" onClick={() => openApplicants(job)}>
                                    <UserPlus className="w-3.5 h-3.5 mr-1" />Aday
                                  </Button>
                                  <Button size="sm" variant="outline" onClick={() => closeJob(job.id)}>
                                    <XCircle className="w-3.5 h-3.5" />
                                  </Button>
                                </>}
                            </div>
                          </td>
                        </tr>)}
                      {jobItems.length === 0 && <tr><td colSpan={9} className="py-10 text-center text-slate-500">
                          Henüz talep yok. Yukarıdaki formdan ilk personel talebini oluşturun.
                        </td></tr>}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Adaylar Modal */}
          <Dialog open={applicantsDialog.open} onOpenChange={o => !o && setApplicantsDialog({
    open: false,
    job: null,
    list: [],
    counts: {}
  })}>
            <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>
                  Adaylar — {applicantsDialog.job?.title}
                  <span className="text-xs text-slate-500 ml-2 font-normal">
                    ({applicantsDialog.job?.department})
                  </span>
                </DialogTitle>
              </DialogHeader>

              {/* Aday durum sayaçları */}
              <div className="flex flex-wrap gap-2 text-xs">
                {Object.entries(applicantsDialog.counts || {}).map(([k, v]) => <span key={k} className="rounded-full bg-slate-100 px-2 py-0.5">
                    {k}: <strong>{v}</strong>
                  </span>)}
              </div>

              {/* Yeni aday formu */}
              <form onSubmit={submitApplicant} className="grid gap-2 md:grid-cols-2 border-t pt-3 mt-2">
                <div className="md:col-span-2 text-sm font-medium flex items-center gap-2">
                  <UserPlus className="w-4 h-4" />Yeni Aday Ekle
                </div>
                <Input placeholder="Ad Soyad *" value={applicantForm.name} onChange={e => setApplicantForm({
          ...applicantForm,
          name: e.target.value
        })} />
                <Input placeholder="E-posta" type="email" value={applicantForm.email} onChange={e => setApplicantForm({
          ...applicantForm,
          email: e.target.value
        })} />
                <Input placeholder="Telefon" value={applicantForm.phone} onChange={e => setApplicantForm({
          ...applicantForm,
          phone: e.target.value
        })} />
                <Input placeholder="CV URL (opsiyonel)" value={applicantForm.cv_url} onChange={e => setApplicantForm({
          ...applicantForm,
          cv_url: e.target.value
        })} />
                <div className="md:col-span-2">
                  <Textarea rows={2} placeholder="Notlar (deneyim, görüşme izlenimi, vb.)" value={applicantForm.notes} onChange={e => setApplicantForm({
            ...applicantForm,
            notes: e.target.value
          })} />
                </div>
                <div className="md:col-span-2 flex justify-end">
                  <Button type="submit" size="sm" disabled={savingApplicant}>
                    <Plus className="w-3.5 h-3.5 mr-1" />
                    {savingApplicant ? 'Ekleniyor...' : 'Adayı Kaydet'}
                  </Button>
                </div>
              </form>

              {/* Aday listesi */}
              <div className="border-t pt-3">
                <div className="text-sm font-medium mb-2">Aday Listesi ({applicantsDialog.list.length})</div>
                <div className="space-y-2">
                  {applicantsDialog.list.map(a => <div key={a.id} className="rounded border border-slate-200 p-3">
                      <div className="flex items-start justify-between">
                        <div>
                          <div className="font-medium">{a.name}</div>
                          <div className="text-xs text-slate-500">
                            {a.email || '—'} • {a.phone || '—'}
                          </div>
                          {a.notes && <div className="text-xs text-slate-600 mt-1">{a.notes}</div>}
                          {a.cv_url && <a href={a.cv_url} target="_blank" rel="noreferrer" className="text-xs text-sky-600 hover:underline">
                              <ExternalLink className="w-3 h-3 inline mr-0.5" />CV
                            </a>}
                        </div>
                        <div className="flex flex-col items-end gap-1">
                          <select value={a.status || 'new'} onChange={e => setApplicantStatus(a.id, e.target.value)} className="text-xs rounded border border-input px-2 py-1">
                            <option value="new">Yeni</option>
                            <option value="screening">Eleme</option>
                            <option value="interview">Görüşme</option>
                            <option value="offer">Teklif</option>
                            <option value="hired">İşe Alındı</option>
                            <option value="rejected">Reddedildi</option>
                          </select>
                          <span className="text-[10px] text-slate-400">
                            {(a.created_at || '').slice(0, 10)}
                          </span>
                        </div>
                      </div>
                    </div>)}
                  {applicantsDialog.list.length === 0 && <p className="text-center text-sm text-slate-500 py-6">Henüz aday yok</p>}
                </div>
              </div>

              <DialogFooter>
                <Button variant="outline" onClick={() => setApplicantsDialog({
          open: false,
          job: null,
          list: [],
          counts: {}
        })}>
                  Kapat
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </TabsContent>
    );
}
