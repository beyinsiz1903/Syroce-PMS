import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Users, AlertTriangle, CheckCircle2, XCircle, FileSpreadsheet,
  RefreshCw, Phone, MessageCircle, Copy, Hash, Search,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { PageHeader } from "@/components/ui/page-header";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { useTranslation } from 'react-i18next';

const STATUS_OPTIONS = ["new", "contacted", "qualified", "lost", "won"];

const STATUS_META = {
  new:        { label: "Yeni",       intent: "info"    },
  contacted:  { label: "Arandı",     intent: "warning" },
  qualified:  { label: "Nitelikli",  intent: "info"    },
  won:        { label: "Kazanıldı",  intent: "success" },
  lost:       { label: "Kaybedildi", intent: "neutral" },
};

const SOURCE_META = {
  pms_lite_landing:     "PMS Lite",
  marketing_contact:    "İletişim",
  supplier_application: "Tedarikçi",
};

const fmtDate = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("tr-TR", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
};

const sanitizePhone = (phone) => {
  if (!phone) return "";
  return phone.replace(/\s+/g, "").replace(/[^\d+]/g, "");
};

const openLeadWhatsApp = (lead) => {
  if (!lead.phone) {
    toast.error("Telefon numarası yok");
    return;
  }
  const phone = sanitizePhone(lead.phone);
  const message = `Merhaba ${lead.full_name || ""}, PMS Lite demo talebiniz hakkında bilgi vermek istiyorum...`;
  window.open(`https://wa.me/${phone}?text=${encodeURIComponent(message)}`, "_blank");
};

const copyLeadSummary = async (lead) => {
  try {
    const meta = STATUS_META[lead.status] || { label: lead.status };
    const text = [
      `Otel: ${lead.property_name || "-"}`,
      `İsim: ${lead.full_name || "-"}`,
      `Telefon: ${lead.phone || "-"}`,
      `E-posta: ${lead.email || "-"}`,
      `Oda: ${lead.rooms_count || "-"}`,
      `Bölge: ${lead.location || "-"}`,
      `Durum: ${meta.label}`,
      `Not: ${lead.note || "-"}`,
    ].join("\n");
    await navigator.clipboard.writeText(text);
    toast.success("Lead bilgileri kopyalandı");
  } catch {
    toast.error("Kopyalanamadı");
  }
};

const copyLeadId = async (id) => {
  try {
    await navigator.clipboard.writeText(id);
    toast.success("Lead ID kopyalandı");
  } catch {
    toast.error("Kopyalanamadı");
  }
};

const AdminLeads = () => {
  const { t } = useTranslation();
  const [leads, setLeads] = useState([]);
  const [statusCounts, setStatusCounts] = useState({});
  const [followUpCount, setFollowUpCount] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [followUpOnly, setFollowUpOnly] = useState(false);
  const [updatingId, setUpdatingId] = useState(null);
  const [notes, setNotes] = useState({});

  const buildQs = () => {
    const params = new URLSearchParams();
    if (statusFilter) params.append("status", statusFilter);
    if (search) params.append("q", search);
    if (followUpOnly) params.append("follow_up", "1");
    return params;
  };

  const loadLeads = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`/admin/leads?${buildQs().toString()}`);
      setLeads(res.data?.leads || []);
      setStatusCounts(res.data?.status_counts || {});
      setFollowUpCount(res.data?.follow_up_count || 0);
      setTotal(res.data?.total ?? (res.data?.leads || []).length);
    } catch (e) {
      console.error(e);
      toast.error("Lead listesi yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const timer = setTimeout(loadLeads, search ? 350 : 0);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, search, followUpOnly]);

  const handleUpdate = async (leadId, newStatus) => {
    setUpdatingId(leadId);
    try {
      const payload = {};
      if (newStatus) payload.status = newStatus;
      if (notes[leadId] !== undefined) payload.note = notes[leadId];
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

  const handleCsvExport = async () => {
    try {
      const qs = buildQs().toString();
      const res = await fetch(`/api/admin/leads/export.csv${qs ? `?${qs}` : ""}`);
      if (!res.ok) {
        toast.error("CSV indirilemedi");
        return;
      }
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `pms-lite-leads_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success("CSV dışa aktarıldı");
    } catch (e) {
      console.error(e);
      toast.error("CSV indirilemedi");
    }
  };

  const kpis = useMemo(() => ({
    total,
    new: statusCounts.new || 0,
    won: statusCounts.won || 0,
    followUp: followUpCount,
  }), [total, statusCounts, followUpCount]);

  const hasActiveFilters = statusFilter || search || followUpOnly;

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-[1600px] mx-auto">
      <PageHeader
        icon={Users}
        title="PMS Lite Lead Listesi"
        subtitle={t('cm.pages_AdminLeads.pms_lite_tanitim_sayfasindan_gelen_demo_')}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleCsvExport} disabled={loading}>
              <FileSpreadsheet className="w-4 h-4 mr-1.5" aria-hidden="true" /> {t('cm.pages_AdminLeads.csv_indir')}
            </Button>
            <Button variant="outline" size="sm" onClick={loadLeads} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
              {t('cm.pages_AdminLeads.yenile')}
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard icon={Users}          label={t('cm.pages_AdminLeads.toplam_lead')}     value={kpis.total}    intent="default" />
        <KpiCard icon={AlertTriangle}  label="Takip Gerekli"   value={kpis.followUp} intent="warning"
          active={followUpOnly} onClick={() => setFollowUpOnly((v) => !v)} />
        <KpiCard icon={Users}          label={t('cm.pages_AdminLeads.yeni')}            value={kpis.new}      intent="info"
          active={statusFilter === "new"}
          onClick={() => setStatusFilter((v) => (v === "new" ? "" : "new"))} />
        <KpiCard icon={CheckCircle2}   label={t('cm.pages_AdminLeads.kazanildi')}       value={kpis.won}      intent="success"
          active={statusFilter === "won"}
          onClick={() => setStatusFilter((v) => (v === "won" ? "" : "won"))} />
      </div>

      <Card>
        <CardContent className="p-3 flex flex-col md:flex-row gap-3 md:items-center">
          <Select
            value={statusFilter || "all"}
            onValueChange={(val) => setStatusFilter(val === "all" ? "" : val)}
          >
            <SelectTrigger className="md:w-48">
              <SelectValue placeholder={t('cm.pages_AdminLeads.tum_durumlar')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('cm.pages_AdminLeads.tum_durumlar_7dd45')}</SelectItem>
              {STATUS_OPTIONS.map((s) => (
                <SelectItem key={s} value={s}>{STATUS_META[s].label}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <div className="relative flex-1 max-w-md w-full">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" aria-hidden="true" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('cm.pages_AdminLeads.isim_otel_telefon_e_posta')}
              className="pl-9"
              aria-label="Lead arama"
            />
          </div>

          <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer select-none">
            <Checkbox
              checked={followUpOnly}
              onCheckedChange={(v) => setFollowUpOnly(!!v)}
              aria-label={t('cm.pages_AdminLeads.yalnizca_takip_gerekenler')}
            />
            <span>Takip gerekli</span>
          </label>

          {hasActiveFilters && (
            <Button
              variant="ghost"
              size="sm"
              className="text-xs text-slate-500"
              onClick={() => { setStatusFilter(""); setSearch(""); setFollowUpOnly(false); }}
            >
              Filtreleri temizle
            </Button>
          )}
        </CardContent>
      </Card>

      <Card className="overflow-hidden">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center justify-between">
            <span>Leadler</span>
            <span className="text-xs text-slate-500">
              {leads.length} {t('cm.pages_AdminLeads.kayit')} {total !== leads.length ? `(toplam ${total})` : ""}
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="text-sm text-slate-500 text-center py-12">{t('cm.pages_AdminLeads.lead_listesi_yukleniyor')}</div>
          ) : leads.length === 0 ? (
            <div className="p-10 text-center text-slate-500 text-sm">
              <Users className="w-10 h-10 mx-auto text-slate-300 mb-2" aria-hidden="true" />
              <p className="font-medium text-slate-600">
                {hasActiveFilters ? "Eşleşen lead yok" : "Henüz PMS Lite lead kaydı yok"}
              </p>
              <p className="text-xs text-slate-400 mt-1">
                {hasActiveFilters
                  ? "Filtreleri değiştirerek tekrar deneyin."
                  : "Tanıtım sayfasından demo talebi gelince burada görünür."}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs border-t">
                <thead className="bg-slate-50 border-b sticky top-0 z-10">
                  <tr className="text-left whitespace-nowrap">
                    <th className="px-3 py-2 font-semibold text-slate-700">{t('cm.pages_AdminLeads.tarih')}</th>
                    <th className="px-3 py-2 font-semibold text-slate-700">Otel</th>
                    <th className="px-3 py-2 font-semibold text-slate-700">{t('cm.pages_AdminLeads.bolge')}</th>
                    <th className="px-3 py-2 font-semibold text-slate-700">{t('cm.pages_AdminLeads.oda')}</th>
                    <th className="px-3 py-2 font-semibold text-slate-700">{t('cm.pages_AdminLeads.isim')}</th>
                    <th className="px-3 py-2 font-semibold text-slate-700">Telefon</th>
                    <th className="px-3 py-2 font-semibold text-slate-700">{t('cm.pages_AdminLeads.durum')}</th>
                    <th className="px-3 py-2 font-semibold text-slate-700">{t('cm.pages_AdminLeads.son_islem')}</th>
                    <th className="px-3 py-2 font-semibold text-slate-700">Not</th>
                    <th className="px-3 py-2 font-semibold text-slate-700">Aksiyon</th>
                  </tr>
                </thead>
                <tbody>
                  {leads.map((lead) => {
                    const meta = STATUS_META[lead.status] || { label: lead.status, intent: "neutral" };
                    const lastOp = fmtDate(lead.last_contact_at || lead.status_changed_at);
                    return (
                      <tr key={lead.lead_id} className="border-b last:border-0 hover:bg-slate-50/60">
                        <td className="px-3 py-2 align-top whitespace-nowrap text-slate-600">{fmtDate(lead.created_at)}</td>
                        <td className="px-3 py-2 align-top font-medium text-slate-800">
                          {lead.property_name || "—"}
                          {lead.source && SOURCE_META[lead.source] && (
                            <span className="mt-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
                              {SOURCE_META[lead.source]}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 align-top text-slate-600">{lead.location || "—"}</td>
                        <td className="px-3 py-2 align-top text-slate-600">{lead.rooms_count ?? "—"}</td>
                        <td className="px-3 py-2 align-top text-slate-800">{lead.full_name || "—"}</td>
                        <td className="px-3 py-2 align-top text-slate-600 font-mono">{lead.phone || "—"}</td>
                        <td className="px-3 py-2 align-top">
                          <div className="flex items-center gap-1.5">
                            <StatusBadge intent={meta.intent}>{meta.label}</StatusBadge>
                            {lead.needs_follow_up && (
                              <span title="Takip gerekli">
                                <AlertTriangle className="w-3.5 h-3.5 text-amber-500" aria-label="takip gerekli" />
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-2 align-top text-slate-500 whitespace-nowrap">{lastOp}</td>
                        <td className="px-3 py-2 align-top w-56">
                          <div className="flex flex-col gap-1">
                            <Input
                              value={notes[lead.lead_id] ?? lead.note ?? ""}
                              onChange={(e) =>
                                setNotes((prev) => ({ ...prev, [lead.lead_id]: e.target.value }))
                              }
                              placeholder="Not ekle..."
                              className="h-8 text-xs"
                            />
                            {(notes[lead.lead_id] !== undefined && notes[lead.lead_id] !== (lead.note ?? "")) && (
                              <Button
                                variant="outline"
                                size="sm"
                                className="h-7 text-xs"
                                disabled={updatingId === lead.lead_id}
                                onClick={() => handleUpdate(lead.lead_id, null)}
                              >
                                {t('cm.pages_AdminLeads.notu_kaydet')}
                              </Button>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-2 align-top w-56">
                          <div className="flex flex-col gap-1.5">
                            <Select
                              value={lead.status}
                              onValueChange={(val) => handleUpdate(lead.lead_id, val)}
                              disabled={updatingId === lead.lead_id}
                            >
                              <SelectTrigger className="h-8 text-xs">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {STATUS_OPTIONS.map((s) => (
                                  <SelectItem key={s} value={s}>{STATUS_META[s].label}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <div className="flex flex-wrap gap-1">
                              <Button variant="outline" size="sm" className="h-7 text-xs px-2" asChild
                                disabled={!lead.phone}
                              >
                                <a href={lead.phone ? `tel:${sanitizePhone(lead.phone)}` : undefined}
                                   aria-label={t('cm.pages_AdminLeads.ara')}>
                                  <Phone className="w-3 h-3" aria-hidden="true" /> {t('cm.pages_AdminLeads.ara_43d45')}
                                </a>
                              </Button>
                              <Button variant="outline" size="sm" className="h-7 text-xs px-2"
                                onClick={() => openLeadWhatsApp(lead)}
                                disabled={!lead.phone}
                              >
                                <MessageCircle className="w-3 h-3" aria-hidden="true" /> WhatsApp
                              </Button>
                              <Button variant="ghost" size="sm" className="h-7 text-xs px-2"
                                onClick={() => copyLeadSummary(lead)}
                                aria-label={t('cm.pages_AdminLeads.lead_ozeti_kopyala')}
                              >
                                <Copy className="w-3 h-3" aria-hidden="true" />
                              </Button>
                              <Button variant="ghost" size="sm" className="h-7 text-xs px-2"
                                onClick={() => copyLeadId(lead.lead_id)}
                                aria-label="Lead ID kopyala"
                                title="Lead ID kopyala"
                              >
                                <Hash className="w-3 h-3" aria-hidden="true" />
                              </Button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default AdminLeads;
