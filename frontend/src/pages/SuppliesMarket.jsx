import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "react-hot-toast";
import {
  ShoppingCart,
  Package,
  Truck,
  CheckCircle2,
  XCircle,
  Loader2,
  Plus,
  Minus,
  Trash2,
  CreditCard,
  Banknote,
  Store,
  BarChart3,
  Sparkles,
  Tag,
  Clock,
  Wallet,
} from "lucide-react";
import Layout from "@/components/Layout";

const PAYMENT_LABELS = {
  cash_on_delivery: "Kapıda Ödeme",
  bank_transfer: "Havale / EFT",
  credit_card: "Kredi Kartı",
};

const STATUS_LABELS = {
  pending: { label: "Onay Bekliyor", color: "bg-yellow-100 text-yellow-800" },
  confirmed: { label: "Onaylandı", color: "bg-blue-100 text-blue-800" },
  shipped: { label: "Kargoda", color: "bg-indigo-100 text-indigo-800" },
  delivered: { label: "Teslim Edildi", color: "bg-green-100 text-green-800" },
  cancelled: { label: "İptal", color: "bg-red-100 text-red-800" },
};

const fmt = (n) =>
  new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" }).format(Number(n || 0));

export default function SuppliesMarket({ user, tenant, onLogout }) {
  const [tab, setTab] = useState("catalog");
  const [categories, setCategories] = useState([]);
  const [activeCategory, setActiveCategory] = useState("");
  const [products, setProducts] = useState([]);
  const [orders, setOrders] = useState([]);
  const [cart, setCart] = useState({}); // { product_id: { product, qty } }
  const [loading, setLoading] = useState(false);
  // Karşılaştır sekmesi state
  const [compareCategory, setCompareCategory] = useState("");
  const [compareQ, setCompareQ] = useState("");
  const [compareQty, setCompareQty] = useState(10);
  const [compareData, setCompareData] = useState(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [showCheckout, setShowCheckout] = useState(false);
  const [checkout, setCheckout] = useState({
    payment_method: "cash_on_delivery",
    shipping_address: "",
    contact_name: "",
    contact_phone: "",
    notes: "",
  });
  const [placing, setPlacing] = useState(false);

  const loadCategories = async () => {
    try {
      const { data } = await axios.get("/supplies-market/categories");
      setCategories(data || []);
    } catch (e) {
      console.error(e);
    }
  };

  const loadProducts = async (cat = "") => {
    setLoading(true);
    try {
      const { data } = await axios.get("/supplies-market/products", {
        params: cat ? { category: cat } : {},
      });
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
      const { data } = await axios.get("/supplies-market/orders/mine");
      setOrders(data || []);
    } catch (e) {
      toast.error("Siparişler yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCategories();
    loadProducts();
  }, []);

  useEffect(() => {
    if (tab === "orders") loadOrders();
  }, [tab]);

  const runCompare = async () => {
    if (!compareCategory && !compareQ) {
      toast.error("Kategori veya arama metni girin");
      return;
    }
    setCompareLoading(true);
    try {
      const params = { qty: compareQty || 1, limit: 20 };
      if (compareCategory) params.category = compareCategory;
      if (compareQ) params.q = compareQ;
      const { data } = await axios.get("/supplies-market/products/compare", { params });
      setCompareData(data);
      if (!data.options?.length) {
        toast("Bu kriterlerde uygun tedarikçi bulunamadı", { icon: "ℹ" });
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Karşılaştırma yapılamadı");
    } finally {
      setCompareLoading(false);
    }
  };

  const onCategory = (key) => {
    setActiveCategory(key);
    loadProducts(key);
  };

  const addToCart = (product, desiredQty = null) => {
    setCart((prev) => {
      const existing = prev[product.id];
      let qty;
      if (desiredQty != null) {
        // Karşılaştır'dan gelen sabit miktar — varsa üzerine yazar
        qty = Math.max(Math.max(1, product.moq || 1), parseInt(desiredQty) || 1);
      } else {
        qty = existing ? existing.qty + 1 : Math.max(1, product.moq || 1);
      }
      if (qty > (product.stock ?? 0)) {
        toast.error("Stok yetersiz");
        return prev;
      }
      return { ...prev, [product.id]: { product, qty } };
    });
  };

  const updateQty = (productId, delta) => {
    setCart((prev) => {
      const item = prev[productId];
      if (!item) return prev;
      const nextQty = item.qty + delta;
      if (nextQty <= 0) {
        const { [productId]: _, ...rest } = prev;
        return rest;
      }
      if (nextQty > (item.product.stock ?? 0)) {
        toast.error("Stok yetersiz");
        return prev;
      }
      return { ...prev, [productId]: { ...item, qty: nextQty } };
    });
  };

  const removeFromCart = (productId) => {
    setCart((prev) => {
      const { [productId]: _, ...rest } = prev;
      return rest;
    });
  };

  const cartItems = Object.values(cart);
  const cartTotal = useMemo(
    () => cartItems.reduce((sum, it) => sum + it.product.price_try * it.qty, 0),
    [cartItems],
  );

  // single-vendor-per-order rule
  const cartVendorIds = useMemo(
    () => Array.from(new Set(cartItems.map((it) => it.product.vendor_id))),
    [cartItems],
  );

  const placeOrder = async () => {
    if (cartItems.length === 0) return;
    if (cartVendorIds.length > 1) {
      toast.error("Tek siparişte yalnızca bir toptancıdan ürün eklenebilir");
      return;
    }
    if (!checkout.shipping_address || checkout.shipping_address.length < 10) {
      toast.error("Teslimat adresi en az 10 karakter olmalı");
      return;
    }
    if (!checkout.contact_name || !checkout.contact_phone) {
      toast.error("İletişim bilgileri zorunlu");
      return;
    }
    setPlacing(true);
    try {
      const payload = {
        ...checkout,
        lines: cartItems.map((it) => ({
          product_id: it.product.id,
          quantity: it.qty,
        })),
      };
      const { data } = await axios.post("/supplies-market/orders", payload);
      toast.success(`Sipariş oluşturuldu: ${data.order_no}`);
      setCart({});
      setShowCheckout(false);
      setCheckout({
        payment_method: "cash_on_delivery",
        shipping_address: "",
        contact_name: "",
        contact_phone: "",
        notes: "",
      });
      setTab("orders");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Sipariş oluşturulamadı");
    } finally {
      setPlacing(false);
    }
  };

  const confirmDelivery = async (orderId) => {
    try {
      await axios.post(`/supplies-market/orders/${orderId}/confirm-delivery`);
      toast.success("Teslim alındı olarak işaretlendi");
      loadOrders();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "İşlem başarısız");
    }
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="supplies_market">
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Store className="w-7 h-7 text-blue-600" /> Tedarik Pazarı
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Toptancılardan otel sarf malzemelerini doğrudan sipariş edin.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setTab("catalog")}
            className={`px-4 py-2 rounded-md text-sm font-medium ${
              tab === "catalog" ? "bg-blue-600 text-white" : "bg-gray-100 hover:bg-gray-200"
            }`}
          >
            <Package className="w-4 h-4 inline mr-1" /> Katalog
          </button>
          <button
            onClick={() => setTab("compare")}
            className={`px-4 py-2 rounded-md text-sm font-medium ${
              tab === "compare" ? "bg-blue-600 text-white" : "bg-gray-100 hover:bg-gray-200"
            }`}
          >
            <BarChart3 className="w-4 h-4 inline mr-1" /> Karşılaştır
          </button>
          <button
            onClick={() => setTab("orders")}
            className={`px-4 py-2 rounded-md text-sm font-medium ${
              tab === "orders" ? "bg-blue-600 text-white" : "bg-gray-100 hover:bg-gray-200"
            }`}
          >
            <Truck className="w-4 h-4 inline mr-1" /> Siparişlerim
          </button>
        </div>
      </div>

      {tab === "catalog" && (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Categories sidebar */}
          <aside className="lg:col-span-1">
            <div className="bg-white rounded-lg border p-3 sticky top-4">
              <h3 className="font-semibold text-sm mb-2 text-gray-700">Kategoriler</h3>
              <button
                onClick={() => onCategory("")}
                className={`block w-full text-left px-3 py-2 rounded text-sm ${
                  activeCategory === "" ? "bg-blue-50 text-blue-700" : "hover:bg-gray-50"
                }`}
              >
                Tümü
              </button>
              {categories.map((c) => (
                <button
                  key={c.key}
                  onClick={() => onCategory(c.key)}
                  className={`block w-full text-left px-3 py-2 rounded text-sm ${
                    activeCategory === c.key ? "bg-blue-50 text-blue-700" : "hover:bg-gray-50"
                  }`}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </aside>

          {/* Products grid */}
          <main className="lg:col-span-2">
            {loading ? (
              <div className="flex justify-center py-12">
                <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
              </div>
            ) : products.length === 0 ? (
              <div className="text-center py-12 text-gray-500 bg-white rounded-lg border">
                Bu kategoride ürün bulunamadı.
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {products.map((p) => (
                  <div key={p.id} className="bg-white rounded-lg border p-4 hover:shadow transition">
                    <div className="flex items-start justify-between mb-2">
                      <h4 className="font-semibold text-sm leading-tight pr-2">{p.name}</h4>
                      <span className="text-lg font-bold text-blue-600 whitespace-nowrap">
                        {fmt(p.price_try)}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 mb-2 line-clamp-2">{p.description}</p>
                    <div className="flex items-center justify-between text-xs text-gray-600 mb-3">
                      <span>{p.vendor_name}</span>
                      <span>
                        Stok: <b>{p.stock}</b> {p.unit}
                      </span>
                    </div>
                    <div className="text-xs text-gray-500 mb-3">
                      Min sipariş: {p.moq} {p.unit} · Paket: {p.pack_size}
                    </div>
                    <button
                      onClick={() => addToCart(p)}
                      disabled={p.stock <= 0}
                      className="w-full py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-md disabled:bg-gray-300"
                    >
                      <ShoppingCart className="w-4 h-4 inline mr-1" /> Sepete Ekle
                    </button>
                  </div>
                ))}
              </div>
            )}
          </main>

          {/* Cart */}
          <aside className="lg:col-span-1">
            <div className="bg-white rounded-lg border p-4 sticky top-4">
              <h3 className="font-semibold flex items-center gap-2 mb-3">
                <ShoppingCart className="w-5 h-5" /> Sepet ({cartItems.length})
              </h3>
              {cartItems.length === 0 ? (
                <p className="text-sm text-gray-500 py-6 text-center">Sepet boş</p>
              ) : (
                <>
                  {cartVendorIds.length > 1 && (
                    <div className="mb-3 p-2 text-xs bg-red-50 text-red-700 rounded">
                      ⚠ Tek siparişte yalnızca bir toptancıdan ürün eklenebilir.
                    </div>
                  )}
                  <div className="space-y-3 max-h-80 overflow-y-auto">
                    {cartItems.map((it) => (
                      <div key={it.product.id} className="border-b pb-2 last:border-0">
                        <div className="flex justify-between items-start gap-2 mb-1">
                          <span className="text-sm font-medium leading-tight">
                            {it.product.name}
                          </span>
                          <button
                            onClick={() => removeFromCart(it.product.id)}
                            className="text-red-500 hover:text-red-700"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                        <div className="flex items-center justify-between text-xs">
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => updateQty(it.product.id, -1)}
                              className="w-6 h-6 rounded bg-gray-100 hover:bg-gray-200"
                            >
                              <Minus className="w-3 h-3 mx-auto" />
                            </button>
                            <span className="w-8 text-center">{it.qty}</span>
                            <button
                              onClick={() => updateQty(it.product.id, +1)}
                              className="w-6 h-6 rounded bg-gray-100 hover:bg-gray-200"
                            >
                              <Plus className="w-3 h-3 mx-auto" />
                            </button>
                          </div>
                          <span className="font-semibold">
                            {fmt(it.product.price_try * it.qty)}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 pt-3 border-t">
                    <div className="flex justify-between mb-3">
                      <span className="text-sm">Toplam</span>
                      <span className="font-bold text-lg">{fmt(cartTotal)}</span>
                    </div>
                    <button
                      onClick={() => setShowCheckout(true)}
                      disabled={cartVendorIds.length > 1}
                      className="w-full py-2 bg-green-600 hover:bg-green-700 text-white rounded-md disabled:bg-gray-300"
                    >
                      Sipariş Ver
                    </button>
                  </div>
                </>
              )}
            </div>
          </aside>
        </div>
      )}

      {tab === "compare" && (
        <div className="space-y-4">
          <div className="bg-white rounded-lg border p-4">
            <h3 className="font-semibold mb-3 flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-blue-600" />
              Tedarikçi Fiyat Karşılaştırma
            </h3>
            <p className="text-xs text-gray-500 mb-3">
              Aynı ürün/kategoride birden fazla tedarikçinin fiyatını, teslim süresini ve
              vadesini yan yana görün. Sistem en avantajlı seçeneği önerir.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
              <select
                value={compareCategory}
                onChange={(e) => setCompareCategory(e.target.value)}
                className="border rounded p-2 text-sm"
              >
                <option value="">Tüm Kategoriler</option>
                {categories.map((c) => (
                  <option key={c.key} value={c.key}>{c.label}</option>
                ))}
              </select>
              <input
                placeholder="Ürün adı (ops.)"
                value={compareQ}
                onChange={(e) => setCompareQ(e.target.value)}
                className="border rounded p-2 text-sm"
              />
              <input
                type="number"
                min={1}
                placeholder="Adet"
                value={compareQty}
                onChange={(e) => setCompareQty(parseInt(e.target.value) || 1)}
                className="border rounded p-2 text-sm"
              />
              <button
                onClick={runCompare}
                disabled={compareLoading}
                className="bg-blue-600 hover:bg-blue-700 text-white rounded px-3 py-2 text-sm font-medium disabled:bg-gray-300"
              >
                {compareLoading ? <Loader2 className="w-4 h-4 animate-spin inline" /> : "Karşılaştır"}
              </button>
            </div>
          </div>

          {compareData && compareData.options?.length > 0 && (
            <div className="bg-white rounded-lg border overflow-hidden">
              <div className="p-3 bg-gray-50 border-b text-xs text-gray-600">
                {compareData.options.length} tedarikçi seçeneği · Adet: <b>{compareData.qty}</b>
                {compareData.best_pick_id && (
                  <span className="ml-3 inline-flex items-center gap-1 text-emerald-700 font-medium">
                    <Sparkles className="w-3.5 h-3.5" /> Akıllı seçim işaretlendi
                  </span>
                )}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                    <tr>
                      <th className="text-left p-3">Ürün / Tedarikçi</th>
                      <th className="text-right p-3">Birim Fiyat</th>
                      <th className="text-right p-3">Toplam ({compareData.qty})</th>
                      <th className="text-center p-3">Teslim</th>
                      <th className="text-center p-3">Vade</th>
                      <th className="text-left p-3">Avantaj</th>
                      <th className="p-3"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {compareData.options.map((o, idx) => {
                      const isBest = o.product_id === compareData.best_pick_id;
                      const isCheapest = idx === 0;
                      return (
                        <tr
                          key={o.product_id}
                          className={`border-t ${isBest ? "bg-emerald-50" : ""}`}
                        >
                          <td className="p-3">
                            <div className="font-medium">{o.product_name}</div>
                            <div className="text-xs text-gray-500">{o.vendor_name}</div>
                            {isBest && (
                              <span className="inline-flex items-center gap-1 mt-1 text-[10px] px-1.5 py-0.5 bg-emerald-600 text-white rounded">
                                <Sparkles className="w-3 h-3" /> AKILLI SEÇİM
                              </span>
                            )}
                            {isCheapest && !isBest && (
                              <span className="inline-flex items-center gap-1 mt-1 text-[10px] px-1.5 py-0.5 bg-blue-600 text-white rounded">
                                EN UCUZ
                              </span>
                            )}
                          </td>
                          <td className="p-3 text-right">
                            <div className="font-bold">{fmt(o.effective_price_try)}</div>
                            {o.savings_pct > 0 && (
                              <div className="text-[10px] text-emerald-600">
                                −%{o.savings_pct} (liste {fmt(o.base_price_try)})
                              </div>
                            )}
                          </td>
                          <td className="p-3 text-right font-semibold">{fmt(o.line_total_try)}</td>
                          <td className="p-3 text-center">
                            <span className="inline-flex items-center gap-1 text-xs">
                              <Clock className="w-3.5 h-3.5 text-gray-400" />
                              {o.lead_time_days > 0 ? `${o.lead_time_days} gün` : "—"}
                            </span>
                          </td>
                          <td className="p-3 text-center">
                            <span className="inline-flex items-center gap-1 text-xs">
                              <Wallet className="w-3.5 h-3.5 text-gray-400" />
                              {o.payment_terms_days > 0 ? `${o.payment_terms_days} gün` : "Peşin"}
                            </span>
                          </td>
                          <td className="p-3 text-xs space-y-1">
                            {o.applied_tier && (
                              <div className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded">
                                Kademe ≥{o.applied_tier.min_qty}
                              </div>
                            )}
                            {o.applied_promotion && (
                              <div className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-amber-50 text-amber-700 rounded">
                                <Tag className="w-3 h-3" />
                                {o.applied_promotion.title} (−%{o.applied_promotion.discount_pct})
                              </div>
                            )}
                          </td>
                          <td className="p-3 text-right">
                            <button
                              onClick={() => {
                                addToCart(
                                  {
                                    id: o.product_id,
                                    name: o.product_name,
                                    vendor_id: o.vendor_id,
                                    vendor_name: o.vendor_name,
                                    price_try: o.effective_price_try,
                                    stock: o.stock,
                                    moq: o.moq,
                                    unit: o.unit,
                                  },
                                  compareData.qty,
                                );
                                toast.success(
                                  `${o.product_name} × ${compareData.qty} sepete eklendi`,
                                );
                                setTab("catalog");
                              }}
                              className="text-xs px-2 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded"
                            >
                              Sepete Ekle
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {compareData && (compareData.options?.length || 0) === 0 && !compareLoading && (
            <div className="bg-white rounded-lg border text-center py-10 text-gray-500 text-sm">
              Bu kriterlerde uygun tedarikçi bulunamadı. Adedi azaltmayı veya kategoriyi
              değiştirmeyi deneyin.
            </div>
          )}
        </div>
      )}

      {tab === "orders" && (
        <div className="bg-white rounded-lg border">
          {loading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
            </div>
          ) : orders.length === 0 ? (
            <div className="text-center py-12 text-gray-500">Henüz sipariş yok</div>
          ) : (
            <div className="divide-y">
              {orders.map((o) => {
                const st = STATUS_LABELS[o.status] || STATUS_LABELS.pending;
                return (
                  <div key={o.id} className="p-4">
                    <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
                      <div>
                        <div className="font-semibold">{o.order_no}</div>
                        <div className="text-xs text-gray-500">
                          {o.vendor_name} · {new Date(o.created_at).toLocaleString("tr-TR")}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`px-2 py-1 rounded text-xs font-medium ${st.color}`}>
                          {st.label}
                        </span>
                        <span className="font-bold text-lg">{fmt(o.total)}</span>
                      </div>
                    </div>
                    <div className="text-xs text-gray-600 mb-2">
                      Ödeme: {PAYMENT_LABELS[o.payment_method] || o.payment_method}
                    </div>
                    <div className="text-xs text-gray-700 space-y-1 bg-gray-50 p-2 rounded">
                      {o.lines.map((l) => (
                        <div key={l.product_id} className="flex justify-between">
                          <span>
                            {l.product_name} × {l.quantity}
                          </span>
                          <span>{fmt(l.line_total)}</span>
                        </div>
                      ))}
                    </div>
                    {o.shipment && (
                      <div className="mt-2 text-xs bg-indigo-50 p-2 rounded">
                        <Truck className="w-3 h-3 inline mr-1" />
                        {o.shipment.carrier} — Takip: <b>{o.shipment.tracking_no}</b>
                        {o.shipment.note && <div className="text-gray-600 mt-1">{o.shipment.note}</div>}
                      </div>
                    )}
                    {o.status === "shipped" && (
                      <button
                        onClick={() => confirmDelivery(o.id)}
                        className="mt-3 px-3 py-1 text-xs bg-green-600 hover:bg-green-700 text-white rounded"
                      >
                        <CheckCircle2 className="w-3 h-3 inline mr-1" /> Teslim Aldım
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Checkout modal */}
      {showCheckout && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg p-6 max-w-lg w-full max-h-[90vh] overflow-y-auto">
            <h3 className="text-lg font-bold mb-4">Sipariş Bilgileri</h3>

            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium">Teslimat Adresi *</label>
                <textarea
                  value={checkout.shipping_address}
                  onChange={(e) =>
                    setCheckout({ ...checkout, shipping_address: e.target.value })
                  }
                  rows={3}
                  className="w-full border rounded p-2 text-sm"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium">İletişim Adı *</label>
                  <input
                    value={checkout.contact_name}
                    onChange={(e) =>
                      setCheckout({ ...checkout, contact_name: e.target.value })
                    }
                    className="w-full border rounded p-2 text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium">Telefon *</label>
                  <input
                    value={checkout.contact_phone}
                    onChange={(e) =>
                      setCheckout({ ...checkout, contact_phone: e.target.value })
                    }
                    className="w-full border rounded p-2 text-sm"
                  />
                </div>
              </div>
              <div>
                <label className="text-xs font-medium">Notlar</label>
                <textarea
                  value={checkout.notes}
                  onChange={(e) => setCheckout({ ...checkout, notes: e.target.value })}
                  rows={2}
                  className="w-full border rounded p-2 text-sm"
                />
              </div>

              <div>
                <label className="text-xs font-medium block mb-2">Ödeme Yöntemi *</label>
                <div className="space-y-2">
                  <label className="flex items-center gap-2 p-2 border rounded cursor-pointer hover:bg-gray-50">
                    <input
                      type="radio"
                      name="pay"
                      checked={checkout.payment_method === "cash_on_delivery"}
                      onChange={() =>
                        setCheckout({ ...checkout, payment_method: "cash_on_delivery" })
                      }
                    />
                    <Banknote className="w-4 h-4 text-green-600" />
                    <span className="text-sm">Kapıda Ödeme</span>
                  </label>
                  <label className="flex items-center gap-2 p-2 border rounded cursor-pointer hover:bg-gray-50">
                    <input
                      type="radio"
                      name="pay"
                      checked={checkout.payment_method === "bank_transfer"}
                      onChange={() =>
                        setCheckout({ ...checkout, payment_method: "bank_transfer" })
                      }
                    />
                    <Banknote className="w-4 h-4 text-blue-600" />
                    <span className="text-sm">Havale / EFT</span>
                  </label>
                  <label className="flex items-center gap-2 p-2 border rounded cursor-pointer hover:bg-gray-50">
                    <input
                      type="radio"
                      name="pay"
                      checked={checkout.payment_method === "credit_card"}
                      onChange={() =>
                        setCheckout({ ...checkout, payment_method: "credit_card" })
                      }
                    />
                    <CreditCard className="w-4 h-4 text-indigo-600" />
                    <span className="text-sm">Kredi Kartı</span>
                    <span className="text-xs text-gray-400 ml-auto">3D Secure</span>
                  </label>
                </div>
              </div>

              <div className="bg-gray-50 p-3 rounded flex justify-between font-semibold">
                <span>Toplam</span>
                <span>{fmt(cartTotal)}</span>
              </div>
            </div>

            <div className="flex gap-2 mt-5">
              <button
                onClick={() => setShowCheckout(false)}
                className="flex-1 py-2 bg-gray-100 hover:bg-gray-200 rounded"
              >
                İptal
              </button>
              <button
                onClick={placeOrder}
                disabled={placing}
                className="flex-1 py-2 bg-green-600 hover:bg-green-700 text-white rounded disabled:bg-gray-300"
              >
                {placing ? <Loader2 className="w-4 h-4 animate-spin inline" /> : "Onayla"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
    </Layout>
  );
}
