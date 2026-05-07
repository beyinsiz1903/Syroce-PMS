import React, { useEffect, useState } from "react";
import axios from "axios";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { useTranslation } from 'react-i18next';

const STATUS_OPTIONS = [
  "new",
  "contacted",
  "qualified",
  "lost",
  "won",
];

const statusLabel = {
  new: "Yeni",
  contacted: "Arandı",
  qualified: "Nitelikli",
  lost: "Kaybedildi",
  won: "Kazanıldı",
};

const STATUS_COLOR = {
  new: "bg-blue-500/10 text-blue-400 border-blue-500/30",
  contacted: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
  qualified: "bg-indigo-500/10 text-indigo-400 border-indigo-500/30",
  won: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  lost: "bg-slate-500/10 text-slate-400 border-slate-500/30",
};

const fmtDate = (iso) => {
  // NOT: useTranslation() çağrısı buradan kaldırıldı —
  // (a) `t` zaten kullanılmıyordu, (b) helper fonksiyon component değil,
  // bu yüzden hook'a izin yok (react-hooks/rules-of-hooks).
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};

const sanitizePhone = (phone) => {
  if (!phone) return '';
  return phone.replace(/\s+/g, '').replace(/[^\d+]/g, '');
};

const openLeadWhatsApp = (lead) => {
  if (!lead.phone) {
    toast.error('Telefon numarası yok');
    return;
  }
  
  const phone = sanitizePhone(lead.phone);
  const message = `Merhaba ${lead.full_name}, PMS Lite demo talebiniz hakkında bilgi vermek istiyorum...`;
  const url = `https://wa.me/${phone}?text=${encodeURIComponent(message)}`;
  window.open(url, '_blank');
};

const copyLeadSummary = async (lead) => {
  try {
    const text = `
Otel: ${lead.property_name || '-'}
İsim: ${lead.full_name || '-'}
Telefon: ${lead.phone || '-'}
Oda: ${lead.rooms_count || '-'}
Bölge: ${lead.location || '-'}
Durum: ${statusLabel[lead.status] || lead.status}
Not: ${lead.note || '-'}
    `.trim();
    
    await navigator.clipboard.writeText(text);
    toast.success('Lead bilgileri kopyalandı');
  } catch {
    toast.error('Kopyalanamadı');
  }
};

const copyLeadId = async (id) => {
  try {
    await navigator.clipboard.writeText(id);
    toast.success('Lead ID kopyalandı');
  } catch {
    toast.error('Kopyalanamadı');
  }
};

const AdminLeads = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [followUpOnly, setFollowUpOnly] = useState(false);
  const [updatingId, setUpdatingId] = useState(null);
  const [notes, setNotes] = useState({});

  const loadLeads = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.append("status", statusFilter);
      if (search) params.append("q", search);
      if (followUpOnly) params.append("follow_up", "1");
      const res = await axios.get(`/admin/leads?${params.toString()}`);
      setLeads(res.data?.leads || []);
    } catch (e) {
      console.error(e);
      toast.error("Lead listesi yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLeads();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [statusFilter, search, followUpOnly]);

  const handleUpdate = async (leadId, newStatus) => {
    setUpdatingId(leadId);
    try {
      const payload = {};
      if (newStatus) payload.status = newStatus;
      if (notes[leadId]) payload.note = notes[leadId];
      const res = await axios.patch(`/admin/leads/${leadId}`, payload);
      if (res.data?.ok) {
        toast.success("Lead güncellendi");
        loadLeads();
      } else {
        toast.error("Lead güncellenemedi");
      }
    } catch (e) {
      console.error(e);
      toast.error("Lead güncellenemedi");
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <>
      <div className="p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">PMS Lite Lead Listesi</h1>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center justify-between">
              <span>Filtreler</span>
              <Button
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={async () => {
                  try {
                    const params = new URLSearchParams();
                    if (statusFilter) params.append("status", statusFilter);
                    if (search) params.append("q", search);
                    if (followUpOnly) params.append("follow_up", "1");
                    const qs = params.toString();
                    const res = await fetch(`/api/admin/leads/export.csv${qs ? `?${qs}` : ""}`);
                    if (!res.ok) {
                      toast.error("CSV indirilemedi");
                      return;
                    }
                    const blob = await res.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = "pms-lite-leads.csv";
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    window.URL.revokeObjectURL(url);
                  } catch (e) {
                    console.error(e);
                    toast.error("CSV indirilemedi");
                  }
                }}
              >
                CSV indir
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid md:grid-cols-3 gap-3">
              <div>
                <Label>Status</Label>
                <Select
                  value={statusFilter}
                  onValueChange={(val) => setStatusFilter(val === "all" ? "" : val)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={t("common.all")} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">{t("common.all")}</SelectItem>
                    {STATUS_OPTIONS.map((s) => (
                      <SelectItem key={s} value={s}>
                        {statusLabel[s]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Arama</Label>
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="İsim, otel, telefon..."
                />
              </div>
              <div>
                <Label>&nbsp;</Label>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <input
                      id="follow-up"
                      type="checkbox"
                      checked={followUpOnly}
                      onChange={(e) => setFollowUpOnly(e.target.checked)}
                      className="rounded border-slate-600"
                    />
                    <label htmlFor="follow-up" className="text-xs text-slate-300">
                      Takip gerekli
                    </label>
                  </div>
                  <Button onClick={loadLeads} disabled={loading} className="ml-auto">
                    {loading ? t("common.loading") : "Listeyi Yenile"}
                  </Button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Leadler</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b text-xs text-gray-500">
                  <th className="px-2 py-1 text-left">Tarih</th>
                  <th className="px-2 py-1 text-left">Otel</th>
                  <th className="px-2 py-1 text-left">Bölge</th>
                  <th className="px-2 py-1 text-left">Oda</th>
                  <th className="px-2 py-1 text-left">İsim</th>
                  <th className="px-2 py-1 text-left">Telefon</th>
                  <th className="px-2 py-1 text-left">Status</th>
                  <th className="px-2 py-1 text-left">Son işlem</th>
                  <th className="px-2 py-1 text-left">Not</th>
                  <th className="px-2 py-1 text-left">Aksiyon</th>
                </tr>
              </thead>
              <tbody>
                {leads.length === 0 && (
                  <tr>
                    <td colSpan={9} className="px-2 py-4 text-center text-xs text-gray-500">
                      Henüz PMS Lite lead kaydı yok.
                    </td>
                  </tr>
                )}
                {leads.map((lead) => {
                  const created = fmtDate(lead.created_at);
                  const lastOp = fmtDate(lead.last_contact_at || lead.status_changed_at);
                  return (
                    <tr key={lead.lead_id} className="border-b last:border-0">
                      <td className="px-2 py-1 align-top whitespace-nowrap">{created}</td>
                      <td className="px-2 py-1 align-top">{lead.property_name}</td>
                      <td className="px-2 py-1 align-top">{lead.location}</td>
                      <td className="px-2 py-1 align-top">{lead.rooms_count}</td>
                      <td className="px-2 py-1 align-top">{lead.full_name}</td>
                      <td className="px-2 py-1 align-top">{lead.phone}</td>
                      <td className="px-2 py-1 align-top">
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] border ${
                            STATUS_COLOR[lead.status] ||
                            "bg-slate-500/10 text-slate-300 border-slate-500/30"
                          }`}
                        >
                          {statusLabel[lead.status] || lead.status}
                        </span>
                      </td>
                      <td className="px-2 py-1 align-top text-xs text-slate-300">{lastOp}</td>
                      <td className="px-2 py-1 align-top w-48">
                        <Input
                          value={notes[lead.lead_id] ?? lead.note ?? ""}
                          onChange={(e) =>
                            setNotes((prev) => ({ ...prev, [lead.lead_id]: e.target.value }))
                          }
                          className="text-xs"
                        />
                      </td>
                      <td className="px-2 py-1 align-top w-48">
                        <div className="flex flex-col gap-1">
                          <Select
                            onValueChange={(val) => handleUpdate(lead.lead_id, val)}
                            disabled={updatingId === lead.lead_id}
                          >
                            <SelectTrigger className="h-8 text-xs">
                              <SelectValue placeholder="Durum değiştir" />
                            </SelectTrigger>
                            <SelectContent>
                              {STATUS_OPTIONS.map((s) => (
                                <SelectItem key={s} value={s}>
                                  {statusLabel[s]}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-8 text-xs"
                            disabled={updatingId === lead.lead_id}
                            onClick={() => handleUpdate(lead.lead_id, null)}
                          >
                            Notu Kaydet
                          </Button>
                          <div className="flex gap-1 mt-1">
                            <Button variant="outline" size="xs" asChild>
                              <a href={`tel:${sanitizePhone(lead.phone)}`}>{t("common.search")}</a>
                            </Button>
                            <Button
                              variant="outline"
                              size="xs"
                              onClick={() => openLeadWhatsApp(lead)}
                            >
                              WhatsApp
                            </Button>
                            <Button
                              variant="ghost"
                              size="xs"
                              onClick={() => copyLeadSummary(lead)}
                            >
                              Kopyala
                            </Button>
                            <Button
                              variant="ghost"
                              size="xs"
                              onClick={() => copyLeadId(lead.lead_id || lead.id)}
                              title="Lead ID kopyala"
                            >
                              ID
                            </Button>
                          </div>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </div>
    </>
  );
};

export default AdminLeads;
