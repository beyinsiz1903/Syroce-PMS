import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Store, CheckCircle2, Ban, Loader2, RefreshCw, ShoppingBag,
  Clock, ShieldAlert, ShieldCheck, Wallet, Package,
} from "lucide-react";

import { confirmDialog, promptDialog } from "@/lib/dialogs";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

const VENDOR_STATUS = {
  pending:   { label: "Onay Bekliyor", intent: "warning" },
  approved:  { label: "Onaylı",        intent: "success" },
  suspended: { label: "Askıda",        intent: "danger"  },
};

const ORDER_STATUS = {
  pending:    { label: "Bekliyor",   intent: "warning" },
  confirmed:  { label: "Onaylı",     intent: "info"    },
  shipped:    { label: "Kargoda",    intent: "info"    },
  delivered:  { label: "Teslim",     intent: "success" },
  cancelled:  { label: "İptal",      intent: "danger"  },
  rejected:   { label: "Reddedildi", intent: "danger"  },
};

const fmt = (n) =>
  new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" }).format(Number(n || 0));

export default function AdminVendors() {
  const [tab, setTab] = useState("vendors");
  const [vendors, setVendors] = useState([]);
  const [orders, setOrders] = useState([]);
  const [totalCommission, setTotalCommission] = useState(0);
  const [statusFilter, setStatusFilter] = useState("all");
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const loadVendors = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get("/supplies-market/admin/vendors");
      setVendors(data || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Tedarikçiler yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  const loadOrders = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get("/supplies-market/admin/orders");
      setOrders(data?.orders || []);
      setTotalCommission(data?.total_commission_try || 0);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Siparişler yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  const reload = () => (tab === "vendors" ? loadVendors() : loadOrders());

  useEffect(() => {
    if (tab === "vendors") loadVendors();
    else loadOrders();
  }, [tab]);

  const approve = async (id, currentPct) => {
    const c = await promptDialog({
      message: "Komisyon oranı (% — varsayılan 8):",
      defaultValue: String(currentPct ?? 8),
    });
    if (c === null) return;
    const num = parseFloat(c);
    setBusyId(id);
    try {
      const url = !isNaN(num)
        ? `/supplies-market/admin/vendors/${id}/approve?commission_pct=${num}`
        : `/supplies-market/admin/vendors/${id}/approve`;
      await axios.post(url);
      toast.success("Tedarikçi onaylandı");
      loadVendors();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Onaylanamadı");
    } finally {
      setBusyId(null);
    }
  };

  const suspend = async (id) => {
    if (!(await confirmDialog({ message: "Bu tedarikçinin hesabı askıya alınsın mı? Sipariş alamaz." }))) return;
    setBusyId(id);
    try {
      await axios.post(`/supplies-market/admin/vendors/${id}/suspend`);
      toast.success("Hesap askıya alındı");
      loadVendors();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "İşlem başarısız");
    } finally {
      setBusyId(null);
    }
  };

  const filteredVendors = statusFilter === "all"
    ? vendors
    : vendors.filter((v) => v.status === statusFilter);

  const counts = {
    all: vendors.length,
    pending: vendors.filter((v) => v.status === "pending").length,
    approved: vendors.filter((v) => v.status === "approved").length,
    suspended: vendors.filter((v) => v.status === "suspended").length,
  };

  return (
    <div className="max-w-7xl mx-auto p-4 md:p-6 space-y-4">
      <PageHeader
        icon={Store}
        title="Tedarikçi Pazarı Yönetimi"
        subtitle="Tedarikçi başvurularını onaylayın, siparişleri ve komisyon gelirini izleyin."
        actions={
          <Button variant="outline" size="sm" onClick={reload} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
            Yenile
          </Button>
        }
      />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="vendors" className="flex items-center gap-2">
            <Store className="w-4 h-4" aria-hidden="true" /> Tedarikçiler
          </TabsTrigger>
          <TabsTrigger value="orders" className="flex items-center gap-2">
            <ShoppingBag className="w-4 h-4" aria-hidden="true" /> Siparişler
          </TabsTrigger>
        </TabsList>

        {/* TEDARİKÇİLER */}
        <TabsContent value="vendors" className="space-y-4 mt-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard
              icon={Store}
              label="Tüm Tedarikçiler"
              value={counts.all}
              intent="default"
              active={statusFilter === "all"}
              onClick={() => setStatusFilter("all")}
            />
            <KpiCard
              icon={Clock}
              label="Onay Bekleyen"
              value={counts.pending}
              intent="warning"
              active={statusFilter === "pending"}
              onClick={() => setStatusFilter(statusFilter === "pending" ? "all" : "pending")}
            />
            <KpiCard
              icon={ShieldCheck}
              label="Onaylı"
              value={counts.approved}
              intent="success"
              active={statusFilter === "approved"}
              onClick={() => setStatusFilter(statusFilter === "approved" ? "all" : "approved")}
            />
            <KpiCard
              icon={ShieldAlert}
              label="Askıda"
              value={counts.suspended}
              intent="danger"
              active={statusFilter === "suspended"}
              onClick={() => setStatusFilter(statusFilter === "suspended" ? "all" : "suspended")}
            />
          </div>

          <Card>
            <CardContent className="p-0">
              {loading ? (
                <div className="flex items-center justify-center p-10 text-slate-500">
                  <Loader2 className="w-5 h-5 animate-spin mr-2" aria-hidden="true" /> Yükleniyor…
                </div>
              ) : filteredVendors.length === 0 ? (
                <div className="p-10 text-center text-slate-500 text-sm">
                  <Store className="w-10 h-10 mx-auto text-slate-300 mb-2" aria-hidden="true" />
                  <p className="font-medium text-slate-600">Bu durumda tedarikçi yok</p>
                  <p className="text-xs text-slate-400 mt-1">
                    {statusFilter === "pending"
                      ? "Yeni başvurular geldiğinde burada görünür."
                      : statusFilter === "approved"
                      ? "Henüz onaylanmış tedarikçi bulunmuyor."
                      : statusFilter === "suspended"
                      ? "Askıya alınmış tedarikçi yok."
                      : "Henüz tedarikçi başvurusu yok."}
                  </p>
                  {statusFilter !== "all" && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-3"
                      onClick={() => setStatusFilter("all")}
                    >
                      Tüm tedarikçileri göster
                    </Button>
                  )}
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 text-slate-600 text-xs uppercase tracking-wider">
                      <tr>
                        <th className="text-left px-4 py-2 font-semibold">Firma / İletişim</th>
                        <th className="text-left px-4 py-2 font-semibold">Vergi</th>
                        <th className="text-left px-4 py-2 font-semibold">Şehir</th>
                        <th className="text-left px-4 py-2 font-semibold">Komisyon</th>
                        <th className="text-left px-4 py-2 font-semibold">Durum</th>
                        <th className="text-left px-4 py-2 font-semibold">Kayıt</th>
                        <th className="text-right px-4 py-2 font-semibold">İşlem</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredVendors.map((v) => {
                        const meta = VENDOR_STATUS[v.status] || VENDOR_STATUS.pending;
                        return (
                          <tr key={v.id} className="border-t border-slate-100 hover:bg-slate-50/60">
                            <td className="px-4 py-3">
                              <div className="font-medium text-slate-900">{v.company_name}</div>
                              <div className="text-xs text-slate-500">
                                {v.contact_name}{v.contact_name && v.email ? " · " : ""}{v.email}
                              </div>
                              {v.phone && <div className="text-xs text-slate-400">{v.phone}</div>}
                            </td>
                            <td className="px-4 py-3 text-xs text-slate-600">
                              <div>{v.tax_no || "—"}</div>
                              {v.tax_office && <div className="text-slate-400">{v.tax_office}</div>}
                            </td>
                            <td className="px-4 py-3 text-xs text-slate-600">{v.city || "—"}</td>
                            <td className="px-4 py-3 text-xs text-slate-700">%{v.commission_pct ?? 0}</td>
                            <td className="px-4 py-3">
                              <StatusBadge intent={meta.intent}>{meta.label}</StatusBadge>
                            </td>
                            <td className="px-4 py-3 text-xs text-slate-500">
                              {v.created_at ? new Date(v.created_at).toLocaleDateString("tr-TR") : "—"}
                            </td>
                            <td className="px-4 py-3 text-right">
                              <div className="inline-flex items-center gap-1.5">
                                {v.status !== "approved" && (
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    className="h-7 text-xs"
                                    onClick={() => approve(v.id, v.commission_pct)}
                                    disabled={busyId === v.id}
                                  >
                                    <CheckCircle2 className="w-3.5 h-3.5 mr-1 text-emerald-600" aria-hidden="true" />
                                    Onayla
                                  </Button>
                                )}
                                {v.status !== "suspended" && (
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    className="h-7 text-xs"
                                    onClick={() => suspend(v.id)}
                                    disabled={busyId === v.id}
                                  >
                                    <Ban className="w-3.5 h-3.5 mr-1 text-rose-600" aria-hidden="true" />
                                    Askıya Al
                                  </Button>
                                )}
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
        </TabsContent>

        {/* SİPARİŞLER */}
        <TabsContent value="orders" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <KpiCard
              icon={Wallet}
              label="Toplam Komisyon Geliri"
              value={fmt(totalCommission)}
              intent="success"
            />
            <KpiCard
              icon={Package}
              label="Toplam Sipariş"
              value={orders.length}
              intent="info"
            />
          </div>

          <Card>
            <CardContent className="p-0">
              {loading ? (
                <div className="flex items-center justify-center p-10 text-slate-500">
                  <Loader2 className="w-5 h-5 animate-spin mr-2" aria-hidden="true" /> Yükleniyor…
                </div>
              ) : orders.length === 0 ? (
                <div className="p-10 text-center text-slate-500 text-sm">
                  <ShoppingBag className="w-10 h-10 mx-auto text-slate-300 mb-2" aria-hidden="true" />
                  <p className="font-medium text-slate-600">Henüz sipariş yok</p>
                  <p className="text-xs text-slate-400 mt-1">
                    Oteller tedarikçilerden ürün satın aldığında siparişler burada görünür.
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 text-slate-600 text-xs uppercase tracking-wider">
                      <tr>
                        <th className="text-left px-4 py-2 font-semibold">Sipariş</th>
                        <th className="text-left px-4 py-2 font-semibold">Tedarikçi</th>
                        <th className="text-left px-4 py-2 font-semibold">Otel</th>
                        <th className="text-right px-4 py-2 font-semibold">Tutar</th>
                        <th className="text-right px-4 py-2 font-semibold">Komisyon</th>
                        <th className="text-left px-4 py-2 font-semibold">Durum</th>
                        <th className="text-left px-4 py-2 font-semibold">Tarih</th>
                      </tr>
                    </thead>
                    <tbody>
                      {orders.map((o) => {
                        const meta = ORDER_STATUS[o.status] || { label: o.status || "—", intent: "neutral" };
                        return (
                          <tr key={o.id} className="border-t border-slate-100 hover:bg-slate-50/60">
                            <td className="px-4 py-3 text-xs font-mono text-slate-600">
                              {(o.id || "").slice(0, 8)}…
                            </td>
                            <td className="px-4 py-3 text-xs">{o.vendor_name || (o.vendor_id || "").slice(0, 8) || "—"}</td>
                            <td className="px-4 py-3 text-xs">{o.tenant_name || (o.tenant_id || "").slice(0, 8) || "—"}</td>
                            <td className="px-4 py-3 text-right text-xs font-medium text-slate-800">
                              {fmt(o.total_amount)}
                            </td>
                            <td className="px-4 py-3 text-right text-xs font-medium text-emerald-700">
                              {fmt(o.commission_amount)}
                            </td>
                            <td className="px-4 py-3">
                              <StatusBadge intent={meta.intent}>{meta.label}</StatusBadge>
                            </td>
                            <td className="px-4 py-3 text-xs text-slate-500">
                              {o.created_at ? new Date(o.created_at).toLocaleDateString("tr-TR") : "—"}
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
        </TabsContent>
      </Tabs>
    </div>
  );
}
