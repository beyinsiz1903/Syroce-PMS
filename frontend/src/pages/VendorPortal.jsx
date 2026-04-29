import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast, Toaster } from "react-hot-toast";
import {
  Store,
  Package,
  ClipboardList,
  Plus,
  Edit2,
  Trash2,
  Truck,
  CheckCircle2,
  XCircle,
  LogOut,
  Loader2,
  Wallet,
  TrendingUp,
} from "lucide-react";

const VENDOR_TOKEN_KEY = "vendor_token";
const CATEGORIES = [
  { key: "banyo", label: "Banyo (Havlu, Şampuan, Terlik)" },
  { key: "yatak_tekstil", label: "Yatak & Tekstil" },
  { key: "temizlik", label: "Temizlik & Kimyasal" },
  { key: "mutfak_fb", label: "Mutfak & F&B" },
  { key: "kirtasiye", label: "Kırtasiye & Ofis" },
  { key: "diger", label: "Diğer" },
];

const STATUS_LABELS = {
  pending: { label: "Onay Bekliyor", color: "bg-yellow-100 text-yellow-800" },
  confirmed: { label: "Onaylandı", color: "bg-blue-100 text-blue-800" },
  shipped: { label: "Kargoda", color: "bg-purple-100 text-purple-800" },
  delivered: { label: "Teslim Edildi", color: "bg-green-100 text-green-800" },
  cancelled: { label: "İptal", color: "bg-red-100 text-red-800" },
};

const PAYMENT_LABELS = {
  cash_on_delivery: "Kapıda Ödeme",
  bank_transfer: "Havale / EFT",
};

const fmt = (n) =>
  new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" }).format(Number(n || 0));

// Scoped axios instance — never inherits hotel staff Authorization from
// axios.defaults. Always sends only the vendor token (or no auth header).
const vendorApi = axios.create();
vendorApi.interceptors.request.use((config) => {
  const token = localStorage.getItem(VENDOR_TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  } else if (config.headers) {
    delete config.headers.Authorization;
    delete config.headers.common?.Authorization;
  }
  return config;
});

// ─── Login / Register ─────────────────────────────────────
function VendorAuth({ onAuthed }) {
  const [mode, setMode] = useState("login");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    email: "",
    password: "",
    company_name: "",
    contact_name: "",
    phone: "",
    tax_no: "",
    tax_office: "",
    iban: "",
    address: "",
    city: "",
  });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const url =
        mode === "login"
          ? "/supplies-market/vendor/login"
          : "/supplies-market/vendor/register";
      const payload =
        mode === "login"
          ? { email: form.email, password: form.password }
          : form;
      const { data } = await vendorApi.post(url, payload);
      localStorage.setItem(VENDOR_TOKEN_KEY, data.access_token);
      toast.success(mode === "login" ? "Giriş başarılı" : "Kayıt alındı, onay bekleniyor");
      onAuthed(data.vendor);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "İşlem başarısız");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden" style={{ background: 'linear-gradient(135deg, #1e1b4b 0%, #1e3a8a 50%, #0f172a 100%)' }}>
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-[10%] left-[8%] w-[380px] h-[380px] bg-blue-500 rounded-full mix-blend-screen filter blur-[80px] opacity-35" />
        <div className="absolute bottom-[5%] right-[10%] w-[460px] h-[460px] bg-purple-500 rounded-full mix-blend-screen filter blur-[90px] opacity-30" />
      </div>
      <div className="bg-white rounded-xl shadow-2xl p-8 max-w-md w-full relative z-10">
        <div className="text-center mb-6">
          <a href="/" title="Ana sayfaya dön" className="inline-block">
            <Store className="w-12 h-12 mx-auto text-blue-600 mb-2 hover:text-blue-700 transition" />
          </a>
          <h1 className="text-2xl font-bold">Toptancı Portalı</h1>
          <p className="text-sm text-gray-500">Syroce Tedarik Pazarı</p>
        </div>

        <div className="flex gap-2 mb-5">
          <button
            onClick={() => setMode("login")}
            className={`flex-1 py-2 rounded text-sm font-medium ${
              mode === "login" ? "bg-blue-600 text-white" : "bg-gray-100"
            }`}
          >
            Giriş
          </button>
          <button
            onClick={() => setMode("register")}
            className={`flex-1 py-2 rounded text-sm font-medium ${
              mode === "register" ? "bg-blue-600 text-white" : "bg-gray-100"
            }`}
          >
            Kayıt Ol
          </button>
        </div>

        <form onSubmit={submit} className="space-y-3">
          <input
            type="email"
            placeholder="E-posta"
            required
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            className="w-full border rounded p-2 text-sm"
          />
          <input
            type="password"
            placeholder="Şifre"
            required
            minLength={8}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            className="w-full border rounded p-2 text-sm"
          />

          {mode === "register" && (
            <>
              <input
                placeholder="Şirket Adı *"
                required
                value={form.company_name}
                onChange={(e) => setForm({ ...form, company_name: e.target.value })}
                className="w-full border rounded p-2 text-sm"
              />
              <input
                placeholder="Yetkili Kişi *"
                required
                value={form.contact_name}
                onChange={(e) => setForm({ ...form, contact_name: e.target.value })}
                className="w-full border rounded p-2 text-sm"
              />
              <input
                placeholder="Telefon *"
                required
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                className="w-full border rounded p-2 text-sm"
              />
              <div className="grid grid-cols-2 gap-2">
                <input
                  placeholder="Vergi No *"
                  required
                  value={form.tax_no}
                  onChange={(e) => setForm({ ...form, tax_no: e.target.value })}
                  className="border rounded p-2 text-sm"
                />
                <input
                  placeholder="Vergi Dairesi *"
                  required
                  value={form.tax_office}
                  onChange={(e) => setForm({ ...form, tax_office: e.target.value })}
                  className="border rounded p-2 text-sm"
                />
              </div>
              <input
                placeholder="IBAN *"
                required
                value={form.iban}
                onChange={(e) => setForm({ ...form, iban: e.target.value })}
                className="w-full border rounded p-2 text-sm"
              />
              <textarea
                placeholder="Adres *"
                required
                rows={2}
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
                className="w-full border rounded p-2 text-sm"
              />
              <input
                placeholder="Şehir *"
                required
                value={form.city}
                onChange={(e) => setForm({ ...form, city: e.target.value })}
                className="w-full border rounded p-2 text-sm"
              />
            </>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full py-2 bg-blue-600 hover:bg-blue-700 text-white rounded font-medium disabled:bg-gray-300"
          >
            {busy ? (
              <Loader2 className="w-4 h-4 animate-spin inline" />
            ) : mode === "login" ? (
              "Giriş Yap"
            ) : (
              "Kayıt Ol"
            )}
          </button>
        </form>

        {mode === "register" && (
          <p className="text-xs text-gray-500 mt-3 text-center">
            Kayıt sonrası Syroce ekibi onayı sonrası ürünleriniz yayına alınır.
          </p>
        )}
      </div>
    </div>
  );
}

// ─── Dashboard ────────────────────────────────────────────
function VendorDashboard({ vendor, onLogout }) {
  const [tab, setTab] = useState("products");
  const [products, setProducts] = useState([]);
  const [orders, setOrders] = useState([]);
  const [earnings, setEarnings] = useState(null);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(null);
  const [shipModal, setShipModal] = useState(null);
  const [shipForm, setShipForm] = useState({ carrier: "", tracking_no: "", note: "" });

  const loadProducts = async () => {
    setLoading(true);
    try {
      const { data } = await vendorApi.get("/supplies-market/vendor/products");
      setProducts(data || []);
    } catch (e) {
      toast.error("Ürünler yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  const loadOrders = async () => {
    setLoading(true);
    try {
      const { data } = await vendorApi.get("/supplies-market/vendor/orders");
      setOrders(data || []);
    } catch (e) {
      toast.error("Siparişler yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  const loadEarnings = async () => {
    setLoading(true);
    try {
      const { data } = await vendorApi.get("/supplies-market/vendor/earnings");
      setEarnings(data);
    } catch (e) {
      toast.error("Kazanç verileri yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (tab === "products") loadProducts();
    if (tab === "orders") loadOrders();
    if (tab === "earnings") loadEarnings();
  }, [tab]);

  const saveProduct = async (form) => {
    try {
      if (form.id) {
        await vendorApi.put(`/supplies-market/vendor/products/${form.id}`, form);
        toast.success("Ürün güncellendi");
      } else {
        await vendorApi.post("/supplies-market/vendor/products", form);
        toast.success("Ürün eklendi");
      }
      setEditing(null);
      loadProducts();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Kaydedilemedi");
    }
  };

  const deleteProduct = async (id) => {
    if (!confirm("Ürünü silmek istediğinize emin misiniz?")) return;
    try {
      await vendorApi.delete(`/supplies-market/vendor/products/${id}`);
      toast.success("Silindi");
      loadProducts();
    } catch (e) {
      toast.error("Silinemedi");
    }
  };

  const confirmOrder = async (id) => {
    try {
      await vendorApi.post(`/supplies-market/vendor/orders/${id}/confirm`);
      toast.success("Sipariş onaylandı");
      loadOrders();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "İşlem başarısız");
    }
  };

  const cancelOrder = async (id) => {
    if (!confirm("Sipariş iptal edilsin mi? Stok iade edilecek.")) return;
    try {
      await vendorApi.post(`/supplies-market/vendor/orders/${id}/cancel`);
      toast.success("Sipariş iptal edildi");
      loadOrders();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "İşlem başarısız");
    }
  };

  const submitShipment = async (e) => {
    e.preventDefault();
    try {
      await vendorApi.post(
        `/supplies-market/vendor/orders/${shipModal.id}/ship`,
        shipForm,
      );
      toast.success("Kargo bilgisi kaydedildi");
      setShipModal(null);
      setShipForm({ carrier: "", tracking_no: "", note: "" });
      loadOrders();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Kaydedilemedi");
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Store className="w-6 h-6 text-blue-600" />
            <div>
              <div className="font-bold text-sm">{vendor?.company_name || "Toptancı"}</div>
              <div className="text-xs text-gray-500">
                Durum:{" "}
                <span
                  className={`font-medium ${
                    vendor?.status === "approved"
                      ? "text-green-600"
                      : vendor?.status === "pending"
                        ? "text-yellow-600"
                        : "text-red-600"
                  }`}
                >
                  {vendor?.status === "approved"
                    ? "Onaylı"
                    : vendor?.status === "pending"
                      ? "Onay Bekliyor"
                      : "Askıda"}
                </span>{" "}
                · Komisyon: %{vendor?.commission_pct ?? 8}
              </div>
            </div>
          </div>
          <button
            onClick={onLogout}
            className="text-sm flex items-center gap-1 text-gray-600 hover:text-gray-900"
          >
            <LogOut className="w-4 h-4" /> Çıkış
          </button>
        </div>
      </header>

      <div className="max-w-6xl mx-auto p-4">
        {vendor?.status === "pending" && (
          <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded text-sm text-yellow-800">
            Hesabınız onay bekliyor. Onaylanana kadar ürünleriniz otellerin kataloğunda görünmez.
          </div>
        )}

        <div className="flex gap-2 mb-5">
          <button
            onClick={() => setTab("products")}
            className={`px-4 py-2 rounded font-medium text-sm ${
              tab === "products" ? "bg-blue-600 text-white" : "bg-white border"
            }`}
          >
            <Package className="w-4 h-4 inline mr-1" /> Ürünlerim
          </button>
          <button
            onClick={() => setTab("orders")}
            className={`px-4 py-2 rounded font-medium text-sm ${
              tab === "orders" ? "bg-blue-600 text-white" : "bg-white border"
            }`}
          >
            <ClipboardList className="w-4 h-4 inline mr-1" /> Siparişler
          </button>
          <button
            onClick={() => setTab("earnings")}
            className={`px-4 py-2 rounded font-medium text-sm ${
              tab === "earnings" ? "bg-blue-600 text-white" : "bg-white border"
            }`}
          >
            <Wallet className="w-4 h-4 inline mr-1" /> Kazançlarım
          </button>
        </div>

        {tab === "earnings" && (
          <EarningsPanel data={earnings} loading={loading} commissionPct={vendor?.commission_pct} />
        )}

        {tab === "products" && (
          <>
            <div className="flex justify-end mb-3">
              <button
                onClick={() =>
                  setEditing({
                    name: "",
                    description: "",
                    category: "banyo",
                    price_try: 0,
                    unit: "adet",
                    pack_size: 1,
                    moq: 1,
                    stock: 0,
                    is_active: true,
                    price_tiers: [],
                    promotions: [],
                    lead_time_days: 0,
                    payment_terms_days: 0,
                  })
                }
                className="px-3 py-2 bg-green-600 hover:bg-green-700 text-white rounded text-sm flex items-center gap-1"
              >
                <Plus className="w-4 h-4" /> Yeni Ürün
              </button>
            </div>

            {loading ? (
              <div className="text-center py-8">
                <Loader2 className="w-6 h-6 animate-spin inline text-blue-600" />
              </div>
            ) : (
              <div className="bg-white rounded-lg border overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                    <tr>
                      <th className="text-left p-3">Ürün</th>
                      <th className="text-left p-3">Kategori</th>
                      <th className="text-right p-3">Fiyat</th>
                      <th className="text-right p-3">Stok</th>
                      <th className="text-center p-3">Aktif</th>
                      <th className="p-3"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {products.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="text-center py-8 text-gray-500">
                          Henüz ürün yok
                        </td>
                      </tr>
                    ) : (
                      products.map((p) => (
                        <tr key={p.id} className="border-t">
                          <td className="p-3">
                            <div className="font-medium">{p.name}</div>
                            <div className="text-xs text-gray-500">
                              {p.unit} · paket {p.pack_size} · MOQ {p.moq}
                            </div>
                          </td>
                          <td className="p-3 text-xs">{p.category}</td>
                          <td className="p-3 text-right">{fmt(p.price_try)}</td>
                          <td className="p-3 text-right">{p.stock}</td>
                          <td className="p-3 text-center">
                            {p.is_active ? (
                              <CheckCircle2 className="w-4 h-4 text-green-600 inline" />
                            ) : (
                              <XCircle className="w-4 h-4 text-gray-400 inline" />
                            )}
                          </td>
                          <td className="p-3 text-right">
                            <button
                              onClick={() => setEditing(p)}
                              className="p-1 text-blue-600 hover:bg-blue-50 rounded"
                            >
                              <Edit2 className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => deleteProduct(p.id)}
                              className="p-1 text-red-600 hover:bg-red-50 rounded ml-1"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {tab === "orders" && (
          <div className="space-y-3">
            {loading ? (
              <div className="text-center py-8">
                <Loader2 className="w-6 h-6 animate-spin inline text-blue-600" />
              </div>
            ) : orders.length === 0 ? (
              <div className="text-center py-8 text-gray-500 bg-white border rounded">
                Sipariş yok
              </div>
            ) : (
              orders.map((o) => {
                const st = STATUS_LABELS[o.status] || STATUS_LABELS.pending;
                return (
                  <div key={o.id} className="bg-white border rounded p-4">
                    <div className="flex flex-wrap justify-between items-start gap-2 mb-2">
                      <div>
                        <div className="font-bold">{o.order_no}</div>
                        <div className="text-xs text-gray-500">
                          {o.hotel_name} · {new Date(o.created_at).toLocaleString("tr-TR")}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`px-2 py-1 rounded text-xs font-medium ${st.color}`}>
                          {st.label}
                        </span>
                        <div className="text-right">
                          <div className="font-bold">{fmt(o.total)}</div>
                          <div className="text-xs text-gray-500">
                            Net: {fmt(o.vendor_payout)}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="text-xs space-y-1 bg-gray-50 p-2 rounded mb-2">
                      {o.lines.map((l) => (
                        <div key={l.product_id} className="flex justify-between">
                          <span>
                            {l.product_name} × {l.quantity}
                          </span>
                          <span>{fmt(l.line_total)}</span>
                        </div>
                      ))}
                    </div>

                    <div className="text-xs text-gray-700 mb-2">
                      <b>Teslimat:</b> {o.shipping_address} —{" "}
                      <b>{o.contact_name}</b> ({o.contact_phone})
                      <br />
                      <b>Ödeme:</b> {PAYMENT_LABELS[o.payment_method] || o.payment_method}
                      {o.notes && (
                        <>
                          <br /> <b>Not:</b> {o.notes}
                        </>
                      )}
                    </div>

                    {o.shipment && (
                      <div className="text-xs bg-purple-50 p-2 rounded mb-2">
                        <Truck className="w-3 h-3 inline mr-1" />
                        {o.shipment.carrier} · Takip: <b>{o.shipment.tracking_no}</b>
                      </div>
                    )}

                    <div className="flex gap-2 flex-wrap">
                      {o.status === "pending" && (
                        <>
                          <button
                            onClick={() => confirmOrder(o.id)}
                            className="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded"
                          >
                            Onayla
                          </button>
                          <button
                            onClick={() => cancelOrder(o.id)}
                            className="px-3 py-1 text-xs bg-red-600 hover:bg-red-700 text-white rounded"
                          >
                            İptal
                          </button>
                        </>
                      )}
                      {o.status === "confirmed" && (
                        <>
                          <button
                            onClick={() => setShipModal(o)}
                            className="px-3 py-1 text-xs bg-purple-600 hover:bg-purple-700 text-white rounded"
                          >
                            <Truck className="w-3 h-3 inline mr-1" /> Kargoya Ver
                          </button>
                          <button
                            onClick={() => cancelOrder(o.id)}
                            className="px-3 py-1 text-xs bg-red-600 hover:bg-red-700 text-white rounded"
                          >
                            İptal
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>

      {editing && (
        <ProductModal
          product={editing}
          onClose={() => setEditing(null)}
          onSave={saveProduct}
        />
      )}

      {shipModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <form
            onSubmit={submitShipment}
            className="bg-white rounded-lg p-6 max-w-md w-full space-y-3"
          >
            <h3 className="text-lg font-bold">Kargo Bilgisi · {shipModal.order_no}</h3>
            <input
              required
              placeholder="Kargo Firması (örn. Aras Kargo)"
              value={shipForm.carrier}
              onChange={(e) => setShipForm({ ...shipForm, carrier: e.target.value })}
              className="w-full border rounded p-2 text-sm"
            />
            <input
              required
              placeholder="Takip Numarası"
              value={shipForm.tracking_no}
              onChange={(e) => setShipForm({ ...shipForm, tracking_no: e.target.value })}
              className="w-full border rounded p-2 text-sm"
            />
            <textarea
              placeholder="Not (opsiyonel)"
              rows={2}
              value={shipForm.note}
              onChange={(e) => setShipForm({ ...shipForm, note: e.target.value })}
              className="w-full border rounded p-2 text-sm"
            />
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setShipModal(null)}
                className="flex-1 py-2 bg-gray-100 rounded"
              >
                İptal
              </button>
              <button
                type="submit"
                className="flex-1 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded"
              >
                Kaydet
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

// ─── Earnings Panel ──────────────────────────────────────
function EarningsPanel({ data, loading, commissionPct }) {
  const fmt = (n) =>
    new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" }).format(Number(n || 0));

  if (loading || !data) {
    return (
      <div className="flex items-center justify-center py-12 text-gray-500">
        <Loader2 className="w-5 h-5 animate-spin mr-2" /> Yükleniyor…
      </div>
    );
  }

  const { all_time, last_30_days, pending, cancelled, monthly } = data;
  const maxNet = Math.max(1, ...monthly.map((m) => m.net));

  const Card = ({ icon: Icon, title, value, sub, color }) => (
    <div className="bg-white rounded-lg border p-4">
      <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
        <Icon className={`w-4 h-4 ${color}`} /> {title}
      </div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      {sub && <div className="text-xs text-gray-400 mt-1">{sub}</div>}
    </div>
  );

  return (
    <div className="space-y-4">
      {/* Üst özet kartları */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Card
          icon={Wallet}
          title="Net Kazancım (Tüm Zamanlar)"
          value={fmt(all_time.net)}
          sub={`${all_time.orders} tamamlanan sipariş`}
          color="text-green-600"
        />
        <Card
          icon={TrendingUp}
          title="Son 30 Gün Net"
          value={fmt(last_30_days.net)}
          sub={`${last_30_days.orders} sipariş`}
          color="text-blue-600"
        />
        <Card
          icon={XCircle}
          title="Toplam Komisyon Gideri"
          value={fmt(all_time.commission)}
          sub={commissionPct ? `Komisyon oranı: %${commissionPct}` : null}
          color="text-orange-600"
        />
        <Card
          icon={ClipboardList}
          title="Bekleyen Siparişler"
          value={fmt(pending.gross)}
          sub={`${pending.orders} sipariş onay bekliyor`}
          color="text-yellow-600"
        />
      </div>

      {/* Brüt / Komisyon / Net özet */}
      <div className="bg-white rounded-lg border p-4">
        <h3 className="text-sm font-semibold mb-3">Tüm Zamanlar Özeti</h3>
        <div className="grid grid-cols-3 gap-4 text-sm">
          <div>
            <div className="text-xs text-gray-500">Brüt Satış</div>
            <div className="font-semibold text-gray-900">{fmt(all_time.gross)}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Komisyon Gideri (-)</div>
            <div className="font-semibold text-orange-600">- {fmt(all_time.commission)}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Net Kazanç</div>
            <div className="font-semibold text-green-600">{fmt(all_time.net)}</div>
          </div>
        </div>
        {cancelled.orders > 0 && (
          <div className="mt-3 pt-3 border-t text-xs text-gray-500">
            İptal/iade: <span className="font-medium text-red-600">{cancelled.orders} sipariş</span> ·{" "}
            {fmt(cancelled.gross)}
          </div>
        )}
      </div>

      {/* Aylık trend */}
      <div className="bg-white rounded-lg border p-4">
        <h3 className="text-sm font-semibold mb-3">Aylık Net Kazanç (son 12 ay)</h3>
        {monthly.length === 0 ? (
          <div className="text-sm text-gray-400 py-6 text-center">
            Henüz tamamlanmış sipariş yok.
          </div>
        ) : (
          <div className="space-y-2">
            {monthly.map((m) => (
              <div key={m.month} className="flex items-center gap-3 text-xs">
                <div className="w-16 text-gray-600 font-mono">{m.month}</div>
                <div className="flex-1 bg-gray-100 rounded h-6 overflow-hidden relative">
                  <div
                    className="h-full bg-gradient-to-r from-green-400 to-green-600 rounded"
                    style={{ width: `${(m.net / maxNet) * 100}%` }}
                  />
                  <div className="absolute inset-0 flex items-center px-2 text-xs font-medium text-gray-800">
                    {fmt(m.net)} <span className="ml-2 text-gray-500">· komisyon {fmt(m.commission)}</span>
                  </div>
                </div>
                <div className="w-12 text-right text-gray-500">{m.orders}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="text-xs text-gray-400">
        * Net kazanç = Brüt satış − Platform komisyonu. Sadece onaylı/kargolanan/teslim edilmiş siparişler gelire dahil edilir.
      </div>
    </div>
  );
}

function ProductModal({ product, onClose, onSave }) {
  const [form, setForm] = useState({
    ...product,
    images: product.images || [],
    price_tiers: product.price_tiers || [],
    promotions: product.promotions || [],
    lead_time_days: product.lead_time_days ?? 0,
    payment_terms_days: product.payment_terms_days ?? 0,
  });
  const [uploading, setUploading] = useState(false);
  const submit = (e) => {
    e.preventDefault();
    const cleanTiers = (form.price_tiers || [])
      .map((t) => ({
        min_qty: parseInt(t.min_qty) || 1,
        price_try: parseFloat(t.price_try) || 0,
      }))
      .filter((t) => t.min_qty >= 1 && t.price_try > 0);
    const cleanPromos = (form.promotions || [])
      .map((p) => ({
        title: (p.title || "").trim(),
        discount_pct: parseFloat(p.discount_pct) || 0,
        min_qty: p.min_qty ? parseInt(p.min_qty) : null,
        valid_until: p.valid_until || null,
      }))
      .filter((p) => p.title && p.discount_pct > 0 && p.discount_pct <= 90);
    onSave({
      ...form,
      price_try: parseFloat(form.price_try) || 0,
      pack_size: parseInt(form.pack_size) || 1,
      moq: parseInt(form.moq) || 1,
      stock: parseInt(form.stock) || 0,
      lead_time_days: parseInt(form.lead_time_days) || 0,
      payment_terms_days: parseInt(form.payment_terms_days) || 0,
      price_tiers: cleanTiers,
      promotions: cleanPromos,
    });
  };

  const addTier = () =>
    setForm((p) => ({
      ...p,
      price_tiers: [...(p.price_tiers || []), { min_qty: "", price_try: "" }],
    }));
  const updateTier = (i, k, v) =>
    setForm((p) => {
      const tiers = [...(p.price_tiers || [])];
      tiers[i] = { ...tiers[i], [k]: v };
      return { ...p, price_tiers: tiers };
    });
  const removeTier = (i) =>
    setForm((p) => ({
      ...p,
      price_tiers: (p.price_tiers || []).filter((_, idx) => idx !== i),
    }));

  const addPromo = () =>
    setForm((p) => ({
      ...p,
      promotions: [
        ...(p.promotions || []),
        { title: "", discount_pct: "", min_qty: "", valid_until: "" },
      ],
    }));
  const updatePromo = (i, k, v) =>
    setForm((p) => {
      const promos = [...(p.promotions || [])];
      promos[i] = { ...promos[i], [k]: v };
      return { ...p, promotions: promos };
    });
  const removePromo = (i) =>
    setForm((p) => ({
      ...p,
      promotions: (p.promotions || []).filter((_, idx) => idx !== i),
    }));

  const handleFiles = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    setUploading(true);
    const uploaded = [];
    for (const f of files) {
      if (f.size > 5 * 1024 * 1024) {
        toast.error(`${f.name}: 5 MB üzerinde, atlandı`);
        continue;
      }
      try {
        const fd = new FormData();
        fd.append("file", f);
        const { data } = await vendorApi.post(
          "/supplies-market/vendor/products/upload-image",
          fd,
          { headers: { "Content-Type": "multipart/form-data" } },
        );
        if (data?.url) uploaded.push(data.url);
      } catch (err) {
        toast.error(`${f.name} yüklenemedi`);
      }
    }
    if (uploaded.length) {
      setForm((p) => ({ ...p, images: [...(p.images || []), ...uploaded] }));
      toast.success(`${uploaded.length} görsel yüklendi`);
    }
    setUploading(false);
    e.target.value = "";
  };

  const removeImage = (url) => {
    setForm((p) => ({ ...p, images: (p.images || []).filter((u) => u !== url) }));
  };
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <form onSubmit={submit} className="bg-white rounded-lg p-6 max-w-lg w-full space-y-3 max-h-[90vh] overflow-y-auto">
        <h3 className="text-lg font-bold">{form.id ? "Ürünü Düzenle" : "Yeni Ürün"}</h3>
        <input
          required
          placeholder="Ürün Adı"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          className="w-full border rounded p-2 text-sm"
        />
        <textarea
          placeholder="Açıklama"
          rows={2}
          value={form.description || ""}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          className="w-full border rounded p-2 text-sm"
        />
        <select
          value={form.category}
          onChange={(e) => setForm({ ...form, category: e.target.value })}
          className="w-full border rounded p-2 text-sm"
        >
          {CATEGORIES.map((c) => (
            <option key={c.key} value={c.key}>
              {c.label}
            </option>
          ))}
        </select>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs">
            Fiyat (TRY) *
            <input
              type="number"
              step="0.01"
              required
              value={form.price_try}
              onChange={(e) => setForm({ ...form, price_try: e.target.value })}
              className="w-full border rounded p-2 text-sm"
            />
          </label>
          <label className="text-xs">
            Birim
            <input
              value={form.unit}
              onChange={(e) => setForm({ ...form, unit: e.target.value })}
              className="w-full border rounded p-2 text-sm"
            />
          </label>
          <label className="text-xs">
            Paket Adedi
            <input
              type="number"
              min={1}
              value={form.pack_size}
              onChange={(e) => setForm({ ...form, pack_size: e.target.value })}
              className="w-full border rounded p-2 text-sm"
            />
          </label>
          <label className="text-xs">
            Min Sipariş
            <input
              type="number"
              min={1}
              value={form.moq}
              onChange={(e) => setForm({ ...form, moq: e.target.value })}
              className="w-full border rounded p-2 text-sm"
            />
          </label>
          <label className="text-xs col-span-2">
            Stok
            <input
              type="number"
              min={0}
              value={form.stock}
              onChange={(e) => setForm({ ...form, stock: e.target.value })}
              className="w-full border rounded p-2 text-sm"
            />
          </label>
          <label className="text-xs">
            Teslim Süresi (gün)
            <input
              type="number"
              min={0}
              max={365}
              value={form.lead_time_days}
              onChange={(e) => setForm({ ...form, lead_time_days: e.target.value })}
              className="w-full border rounded p-2 text-sm"
            />
          </label>
          <label className="text-xs">
            Vade (gün, 0=peşin)
            <input
              type="number"
              min={0}
              max={365}
              value={form.payment_terms_days}
              onChange={(e) => setForm({ ...form, payment_terms_days: e.target.value })}
              className="w-full border rounded p-2 text-sm"
            />
          </label>
        </div>

        {/* Kademeli Fiyat */}
        <div className="border rounded p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-700">
              Kademeli Fiyat (miktara göre indirim)
            </span>
            <button
              type="button"
              onClick={addTier}
              className="text-xs px-2 py-1 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded border border-blue-200"
            >
              + Kademe Ekle
            </button>
          </div>
          {(form.price_tiers || []).length === 0 && (
            <p className="text-xs text-gray-400">
              Örn: 50 adet → 90 TL · 100 adet → 80 TL. Boş bırakılırsa tek fiyat uygulanır.
            </p>
          )}
          {(form.price_tiers || []).map((t, i) => (
            <div key={i} className="grid grid-cols-[1fr_1fr_auto] gap-2 items-center">
              <input
                type="number"
                min={1}
                placeholder="Min adet"
                value={t.min_qty}
                onChange={(e) => updateTier(i, "min_qty", e.target.value)}
                className="border rounded p-1.5 text-sm"
              />
              <input
                type="number"
                step="0.01"
                min={0}
                placeholder="Birim fiyat (TRY)"
                value={t.price_try}
                onChange={(e) => updateTier(i, "price_try", e.target.value)}
                className="border rounded p-1.5 text-sm"
              />
              <button
                type="button"
                onClick={() => removeTier(i)}
                className="text-red-600 hover:text-red-700 text-xs px-2"
              >
                Sil
              </button>
            </div>
          ))}
        </div>

        {/* Promosyonlar */}
        <div className="border rounded p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-700">Promosyon / Kampanya</span>
            <button
              type="button"
              onClick={addPromo}
              className="text-xs px-2 py-1 bg-amber-50 hover:bg-amber-100 text-amber-700 rounded border border-amber-200"
            >
              + Promosyon Ekle
            </button>
          </div>
          {(form.promotions || []).length === 0 && (
            <p className="text-xs text-gray-400">
              Örn: "Ay sonu kampanyası" %10 indirim, min 30 adet, 30/06 tarihine kadar.
            </p>
          )}
          {(form.promotions || []).map((p, i) => (
            <div key={i} className="space-y-1.5 border-b pb-2 last:border-0">
              <input
                placeholder="Kampanya başlığı"
                value={p.title}
                onChange={(e) => updatePromo(i, "title", e.target.value)}
                className="w-full border rounded p-1.5 text-sm"
              />
              <div className="grid grid-cols-3 gap-2">
                <input
                  type="number"
                  step="0.5"
                  min={1}
                  max={90}
                  placeholder="İndirim %"
                  value={p.discount_pct}
                  onChange={(e) => updatePromo(i, "discount_pct", e.target.value)}
                  className="border rounded p-1.5 text-sm"
                />
                <input
                  type="number"
                  min={1}
                  placeholder="Min adet (ops.)"
                  value={p.min_qty || ""}
                  onChange={(e) => updatePromo(i, "min_qty", e.target.value)}
                  className="border rounded p-1.5 text-sm"
                />
                <input
                  type="date"
                  value={p.valid_until || ""}
                  onChange={(e) => updatePromo(i, "valid_until", e.target.value)}
                  className="border rounded p-1.5 text-sm"
                />
              </div>
              <button
                type="button"
                onClick={() => removePromo(i)}
                className="text-red-600 hover:text-red-700 text-xs"
              >
                Promosyonu Sil
              </button>
            </div>
          ))}
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-700">Ürün Görselleri</span>
            <label className="cursor-pointer text-xs px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded border border-blue-200">
              {uploading ? "Yükleniyor…" : "+ Görsel Ekle"}
              <input
                type="file"
                accept="image/*"
                multiple
                onChange={handleFiles}
                disabled={uploading}
                className="hidden"
              />
            </label>
          </div>
          {form.images?.length > 0 && (
            <div className="grid grid-cols-4 gap-2">
              {form.images.map((url) => (
                <div key={url} className="relative group aspect-square border rounded overflow-hidden bg-gray-50">
                  <img src={url} alt="ürün" className="w-full h-full object-cover" />
                  <button
                    type="button"
                    onClick={() => removeImage(url)}
                    className="absolute top-1 right-1 bg-red-600 text-white text-xs w-5 h-5 rounded-full opacity-0 group-hover:opacity-100 transition"
                    title="Kaldır"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="text-xs text-gray-400">JPG, PNG, WEBP · max 5 MB · birden fazla seçebilirsiniz</div>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.is_active}
            onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
          />
          Aktif (otellerin kataloğunda görünür)
        </label>
        <div className="flex gap-2 pt-2">
          <button type="button" onClick={onClose} className="flex-1 py-2 bg-gray-100 rounded">
            İptal
          </button>
          <button type="submit" className="flex-1 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded">
            Kaydet
          </button>
        </div>
      </form>
    </div>
  );
}

// ─── Root ─────────────────────────────────────────────────
export default function VendorPortal() {
  const [vendor, setVendor] = useState(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem(VENDOR_TOKEN_KEY);
    if (!token) {
      setChecking(false);
      return;
    }
    vendorApi
      .get("/supplies-market/vendor/me")
      .then(({ data }) => setVendor(data))
      .catch(() => {
        localStorage.removeItem(VENDOR_TOKEN_KEY);
      })
      .finally(() => setChecking(false));
  }, []);

  const logout = () => {
    localStorage.removeItem(VENDOR_TOKEN_KEY);
    setVendor(null);
  };

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <>
      <Toaster position="top-right" />
      {vendor ? (
        <VendorDashboard vendor={vendor} onLogout={logout} />
      ) : (
        <VendorAuth onAuthed={setVendor} />
      )}
    </>
  );
}
