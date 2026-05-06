import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "react-hot-toast";
import { Store, CheckCircle2, Ban, Loader2, RefreshCw, ShoppingBag } from "lucide-react";

import { confirmDialog, promptDialog } from '@/lib/dialogs';
const STATUS_BADGE = {
  pending: { label: "Onay Bekliyor", cls: "bg-yellow-100 text-yellow-800" },
  approved: { label: "Onaylı", cls: "bg-green-100 text-green-800" },
  suspended: { label: "Askıda", cls: "bg-red-100 text-red-800" },
};

const fmt = (n) =>
  new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" }).format(Number(n || 0));

export default function AdminVendors({ user, tenant, onLogout }) {
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
      toast.error("Tedarikçiler yüklenemedi");
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
      toast.error("Siparişler yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (tab === "vendors") loadVendors();
    else loadOrders();
  }, [tab]);

  const approve = async (id, commission) => {
    setBusyId(id);
    try {
      const url = commission != null
        ? `/supplies-market/admin/vendors/${id}/approve?commission_pct=${commission}`
        : `/supplies-market/admin/vendors/${id}/approve`;
      await axios.post(url);
      toast.success("Tedarikçi onaylandı");
      loadVendors();
    } catch (e) {
      toast.error("Onaylanamadı");
    } finally {
      setBusyId(null);
    }
  };

  const suspend = async (id) => {
    if (!await confirmDialog({ message: "Bu tedarikçinin hesabı askıya alınsın mı? Sipariş alamaz." })) return;
    setBusyId(id);
    try {
      await axios.post(`/supplies-market/admin/vendors/${id}/suspend`);
      toast.success("Hesap askıya alındı");
      loadVendors();
    } catch (e) {
      toast.error("İşlem başarısız");
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
    <>
      <div className="max-w-7xl mx-auto p-4 space-y-4">
        {/* Tabs */}
        <div className="flex items-center gap-2 border-b border-gray-200">
          <button
            onClick={() => setTab("vendors")}
            className={`px-4 py-2 text-sm font-medium flex items-center gap-2 border-b-2 transition ${
              tab === "vendors" ? "border-blue-600 text-blue-600" : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            <Store className="w-4 h-4" /> Tedarikçiler
          </button>
          <button
            onClick={() => setTab("orders")}
            className={`px-4 py-2 text-sm font-medium flex items-center gap-2 border-b-2 transition ${
              tab === "orders" ? "border-blue-600 text-blue-600" : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            <ShoppingBag className="w-4 h-4" /> Siparişler
          </button>
          <div className="ml-auto">
            <button
              onClick={() => (tab === "vendors" ? loadVendors() : loadOrders())}
              className="text-xs text-gray-500 hover:text-blue-600 flex items-center gap-1 px-2 py-1"
            >
              <RefreshCw className="w-3 h-3" /> Yenile
            </button>
          </div>
        </div>

        {tab === "vendors" && (
          <>
            {/* Status filter pills */}
            <div className="flex flex-wrap gap-2">
              {[
                { k: "all", label: "Tümü" },
                { k: "pending", label: "Onay Bekleyen" },
                { k: "approved", label: "Onaylı" },
                { k: "suspended", label: "Askıda" },
              ].map((o) => (
                <button
                  key={o.k}
                  onClick={() => setStatusFilter(o.k)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium border transition ${
                    statusFilter === o.k
                      ? "bg-blue-600 text-white border-blue-600"
                      : "bg-white text-gray-700 border-gray-200 hover:border-blue-400"
                  }`}
                >
                  {o.label} <span className="opacity-70">({counts[o.k]})</span>
                </button>
              ))}
            </div>

            {/* Vendors table */}
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
              {loading ? (
                <div className="flex items-center justify-center p-8 text-gray-500">
                  <Loader2 className="w-5 h-5 animate-spin mr-2" /> Yükleniyor…
                </div>
              ) : filteredVendors.length === 0 ? (
                <div className="p-8 text-center text-gray-500 text-sm">Bu durumda tedarikçi yok.</div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wider">
                    <tr>
                      <th className="text-left px-4 py-2">Firma / İletişim</th>
                      <th className="text-left px-4 py-2">Vergi</th>
                      <th className="text-left px-4 py-2">Şehir</th>
                      <th className="text-left px-4 py-2">Komisyon</th>
                      <th className="text-left px-4 py-2">Durum</th>
                      <th className="text-left px-4 py-2">Kayıt</th>
                      <th className="text-right px-4 py-2">İşlem</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredVendors.map((v) => {
                      const badge = STATUS_BADGE[v.status] || STATUS_BADGE.pending;
                      return (
                        <tr key={v.id} className="border-t border-gray-100 hover:bg-gray-50">
                          <td className="px-4 py-3">
                            <div className="font-medium text-gray-900">{v.company_name}</div>
                            <div className="text-xs text-gray-500">{v.contact_name} · {v.email}</div>
                            <div className="text-xs text-gray-400">{v.phone}</div>
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-600">
                            <div>{v.tax_no}</div>
                            <div className="text-gray-400">{v.tax_office}</div>
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-600">{v.city || "—"}</td>
                          <td className="px-4 py-3 text-xs">%{v.commission_pct}</td>
                          <td className="px-4 py-3">
                            <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${badge.cls}`}>
                              {badge.label}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-500">
                            {v.created_at ? new Date(v.created_at).toLocaleDateString("tr-TR") : "—"}
                          </td>
                          <td className="px-4 py-3 text-right space-x-1">
                            {v.status !== "approved" && (
                              <button
                                onClick={async () => {
                                  const c = await promptDialog({ message: "Komisyon oranı (% — varsayılan 8):", defaultValue: v.commission_pct || 8 });
                                  if (c === null) return;
                                  const num = parseFloat(c);
                                  approve(v.id, isNaN(num) ? null : num);
                                }}
                                disabled={busyId === v.id}
                                className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-green-600 hover:bg-green-700 text-white rounded disabled:opacity-50"
                              >
                                <CheckCircle2 className="w-3 h-3" /> Onayla
                              </button>
                            )}
                            {v.status !== "suspended" && (
                              <button
                                onClick={() => suspend(v.id)}
                                disabled={busyId === v.id}
                                className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-red-600 hover:bg-red-700 text-white rounded disabled:opacity-50"
                              >
                                <Ban className="w-3 h-3" /> Askıya Al
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}

        {tab === "orders" && (
          <>
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-center justify-between">
              <div>
                <div className="text-xs text-blue-700">Toplam Komisyon Geliri</div>
                <div className="text-2xl font-bold text-blue-900">{fmt(totalCommission)}</div>
              </div>
              <div className="text-xs text-blue-700">{orders.length} sipariş</div>
            </div>

            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
              {loading ? (
                <div className="flex items-center justify-center p-8 text-gray-500">
                  <Loader2 className="w-5 h-5 animate-spin mr-2" /> Yükleniyor…
                </div>
              ) : orders.length === 0 ? (
                <div className="p-8 text-center text-gray-500 text-sm">Henüz sipariş yok.</div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wider">
                    <tr>
                      <th className="text-left px-4 py-2">Sipariş</th>
                      <th className="text-left px-4 py-2">Tedarikçi</th>
                      <th className="text-left px-4 py-2">Otel</th>
                      <th className="text-right px-4 py-2">Tutar</th>
                      <th className="text-right px-4 py-2">Komisyon</th>
                      <th className="text-left px-4 py-2">Durum</th>
                      <th className="text-left px-4 py-2">Tarih</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orders.map((o) => (
                      <tr key={o.id} className="border-t border-gray-100 hover:bg-gray-50">
                        <td className="px-4 py-3 text-xs font-mono text-gray-600">{(o.id || "").slice(0, 8)}…</td>
                        <td className="px-4 py-3 text-xs">{o.vendor_name || o.vendor_id?.slice(0, 8)}</td>
                        <td className="px-4 py-3 text-xs">{o.tenant_name || o.tenant_id?.slice(0, 8)}</td>
                        <td className="px-4 py-3 text-right text-xs font-medium">{fmt(o.total_amount)}</td>
                        <td className="px-4 py-3 text-right text-xs text-blue-700 font-medium">{fmt(o.commission_amount)}</td>
                        <td className="px-4 py-3 text-xs">{o.status}</td>
                        <td className="px-4 py-3 text-xs text-gray-500">
                          {o.created_at ? new Date(o.created_at).toLocaleDateString("tr-TR") : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}
