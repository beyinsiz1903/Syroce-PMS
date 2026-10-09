import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import axios from "axios";
import { toast } from "sonner";
import {
  Building2, CalendarRange, ChartNoAxesCombined, Check, CheckCircle2, Clock,
  ExternalLink, Gift, Globe2, GraduationCap, Handshake, Headset, HeartPulse,
  CreditCard, Landmark, Loader2, Mail, Package, QrCode, Receipt, RefreshCw, ScanLine, Search,
  ShieldCheck, ShoppingBag, Sparkles, Users, Utensils, Wrench, XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const ICONS = { Building2, CalendarRange, ChartNoAxesCombined, Globe2, GraduationCap, Handshake, Headset, HeartPulse, Landmark, Mail, Package, QrCode, ScanLine, Sparkles, Users, Utensils, Wrench };
const CATEGORY_COPY = {
  all: { tr: "Tümü", en: "All" }, module: { tr: "Modüller", en: "Modules" },
  integration: { tr: "Entegrasyonlar", en: "Integrations" }, credit_pack: { tr: "Kredi Paketleri", en: "Credit Packs" },
};
const CATEGORY_STYLE = {
  module: "border-blue-200 bg-blue-50 text-blue-700",
  integration: "border-violet-200 bg-violet-50 text-violet-700",
  credit_pack: "border-emerald-200 bg-emerald-50 text-emerald-700",
};
const copy = (english, tr, en) => (english ? en : tr);

function ProductCard({ product, subscription, paymentReady, buying, english, onPurchase, onTrial, onQuote, onLaunch }) {
  const Icon = ICONS[product.icon] || Package;
  const name = english && product.name_en ? product.name_en : (product.name || "").replace(/mail\b/gi, "e-posta").replace("Omni Inbox", "Birleşik gelen kutusu");
  const description = english && product.description_en ? product.description_en : product.description;
  const features = english ? (product.features_en || []) : (product.features || []);
  const owned = Boolean(subscription);
  const recurring = product.billing_type === "subscription";
  const busy = buying === product.key;
  const [quantity, setQuantity] = useState(Math.max(1, Number(product.included_units || 1)));
  const unitLabels = { property: copy(english, "tesis", "property"), room: copy(english, "oda", "room"), employee: copy(english, "çalışan", "employee"), outlet: copy(english, "satış noktası", "outlet"), user: copy(english, "kullanıcı", "user"), pack: copy(english, "paket", "pack") };
  return (
    <article className={`group relative flex h-full flex-col overflow-hidden rounded-2xl border bg-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-lg ${product.popular ? "border-blue-300 ring-1 ring-blue-100" : "border-slate-200"}`}>
      {product.popular && <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-1.5 text-center text-[11px] font-semibold uppercase tracking-[0.14em] text-white">{copy(english, "Öne çıkan çözüm", "Featured solution")}</div>}
      <div className="flex flex-1 flex-col p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-slate-950 text-white shadow-sm"><Icon className="h-5 w-5" aria-hidden="true" /></div>
            <div className="min-w-0">
              <h3 className="text-base font-bold leading-tight text-slate-950">{name}</h3>
              <div className="mt-1 flex flex-wrap gap-1.5">
                <Badge variant="outline" className={CATEGORY_STYLE[product.category] || CATEGORY_STYLE.module}>{CATEGORY_COPY[product.category]?.[english ? "en" : "tr"] || product.category}</Badge>
                {product.badge && <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-700">{english && product.badge_en ? product.badge_en : product.badge}</Badge>}
              </div>
            </div>
          </div>
          {owned && <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600" aria-label={copy(english, "Aktif", "Active")} />}
        </div>
        <p className="mt-4 min-h-16 text-sm leading-6 text-slate-600">{description}</p>
        <ul className="mt-4 space-y-2">
          {features.slice(0, 4).map((feature, index) => <li key={`${product.key}-${index}`} className="flex items-start gap-2 text-sm text-slate-700"><Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" /><span>{feature}</span></li>)}
        </ul>
        <div className="mt-auto pt-6">
          <div className="mb-3 rounded-lg bg-slate-50 p-3 text-xs text-slate-600"><div className="flex justify-between"><span>{copy(english, "Fiyat ölçüsü", "Pricing unit")}</span><strong>{product.pricing_model === "pack" ? copy(english, "Paket başına", "Per pack") : product.included_units || 1} {product.pricing_model !== "pack" && (unitLabels[product.pricing_model] || product.pricing_model)}</strong></div><div className="mt-1 flex justify-between"><span>{copy(english, "Tahmini kurulum", "Estimated setup")}</span><strong>~{product.setup_minutes || 0} dk</strong></div><div className="mt-1 flex justify-between"><span>KDV</span><strong>%{product.tax_rate_pct ?? 20}</strong></div></div>
          <div className="border-t border-slate-100 pt-4">
            <div className="flex items-end justify-between gap-3">
              <div>
                <div className="flex items-baseline gap-1"><span className="text-2xl font-black tracking-tight text-slate-950">₺{Number(product.price_try || 0).toLocaleString(english ? "en-US" : "tr-TR")}</span><span className="text-xs font-medium text-slate-500">{recurring ? copy(english, "/ ay", "/ month") : copy(english, "tek sefer", "one-time")}</span></div>
                <p className="mt-1 text-[11px] text-slate-500">{english && product.price_note_en ? product.price_note_en : product.price_note?.replace(/checkout/gi, "ödeme adımı") || copy(english, "KDV ödeme adımında eklenir", "VAT is added at checkout")}</p>
              </div>
              {product.trial_days > 0 && !owned && <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100">{product.trial_days} {copy(english, "gün deneme", "day trial")}</Badge>}
            </div>
            {!owned && product.pricing_model !== "pack" && <label className="mt-3 block text-xs text-slate-600">{copy(english, "Fiyatlandırılacak adet", "Billable quantity")} ({unitLabels[product.pricing_model] || product.pricing_model})<Input className="mt-1" type="number" min="1" value={quantity} onChange={(event) => setQuantity(Math.max(1, Number(event.target.value) || 1))} /></label>}
            <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
              {owned ? <Button variant="outline" className="sm:col-span-2" onClick={() => onLaunch(product)} disabled={!product.route_path && !product.external}><ExternalLink className="mr-2 h-4 w-4" /> {copy(english, "Modülü aç", "Open module")}</Button> : <>
                {product.trial_days > 0 && <Button variant="outline" onClick={() => onTrial(product)} disabled={busy}><Gift className="mr-2 h-4 w-4" /> {copy(english, "Ücretsiz dene", "Start trial")}</Button>}
                <Button className={product.trial_days > 0 ? "" : "sm:col-span-2"} onClick={() => paymentReady ? onPurchase(product, quantity) : onQuote(product)} disabled={busy}>
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : paymentReady ? <><ShoppingBag className="mr-2 h-4 w-4" /> {copy(english, "Satın al", "Buy now")}</> : copy(english, "Teklif iste", "Request quote")}
                </Button>
              </>}
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}

const StoreSkeleton = () => <div className="h-[430px] animate-pulse rounded-2xl border border-slate-200 bg-white p-5"><div className="h-12 w-12 rounded-xl bg-slate-200" /><div className="mt-4 h-5 w-2/3 rounded bg-slate-200" /><div className="mt-4 h-3 w-full rounded bg-slate-100" /><div className="mt-2 h-3 w-5/6 rounded bg-slate-100" /></div>;

export default function ModuleStorePage() {
  const { i18n } = useTranslation();
  const english = (i18n.resolvedLanguage || i18n.language || "tr").startsWith("en");
  const navigate = useNavigate();
  const [products, setProducts] = useState([]);
  const [subscriptions, setSubscriptions] = useState([]);
  const [paymentReady, setPaymentReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [buying, setBuying] = useState(null);
  const [tab, setTab] = useState("store");
  const [category, setCategory] = useState("all");
  const [query, setQuery] = useState("");
  const [billing, setBilling] = useState({ invoices: [], payment_methods: [] });
  const [readiness, setReadiness] = useState({});

  const load = async () => {
    setLoading(true);
    try {
      const [catalog, owned] = await Promise.all([axios.get("/module-store/products"), axios.get("/module-store/my-subscriptions")]);
      setProducts(catalog.data.products || []);
      setPaymentReady(Boolean(catalog.data.payment_ready));
      setSubscriptions(owned.data.subscriptions || []);
    } catch (error) {
      console.error("Module store load failed", { status: error?.response?.status, type: error?.name });
      toast.error(copy(english, "Modül kataloğu yüklenemedi", "Module catalog could not be loaded"));
    } finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const subscriptionByProduct = useMemo(() => Object.fromEntries(subscriptions.map(item => [item.product_key, item])), [subscriptions]);
  const filteredProducts = useMemo(() => {
    const locale = english ? "en" : "tr";
    const normalized = query.trim().toLocaleLowerCase(locale);
    return products.filter(product => category === "all" || product.category === category).filter(product => !normalized || [product.name, product.name_en, product.description, product.description_en, ...(english ? (product.features_en || []) : (product.features || []))].join(" ").toLocaleLowerCase(locale).includes(normalized)).sort((a, b) => Number(b.popular || false) - Number(a.popular || false) || a.name.localeCompare(b.name, locale));
  }, [category, english, products, query]);

  const withBusy = async (product, action) => { setBuying(product.key); try { await action(); } finally { setBuying(null); } };
  const handlePurchase = (product, quantity = 1) => withBusy(product, async () => {
    try { const { data } = await axios.post("/module-store/purchase", { product_key: product.key, quantity }); if (!data.payment_page_url) throw new Error("missing_payment_url"); window.location.assign(data.payment_page_url); }
    catch (error) { toast.error(error?.response?.data?.detail || copy(english, "Satın alma başlatılamadı", "Purchase could not be started")); }
  });
  const handleTrial = product => withBusy(product, async () => {
    try { await axios.post("/module-store/start-trial", { product_key: product.key }); toast.success(copy(english, `${product.trial_days} günlük deneme etkinleştirildi`, `${product.trial_days}-day trial activated`)); await load(); }
    catch (error) { toast.error(error?.response?.data?.detail || copy(english, "Deneme başlatılamadı", "Trial could not be started")); }
  });
  const handleQuote = product => withBusy(product, async () => {
    try { const { data } = await axios.post("/module-store/request-quote", { product_key: product.key }); const shortId = data.request_id?.slice(0, 8); toast.success(copy(english, `Talebiniz satış kuyruğuna kaydedildi${shortId ? ` · No: ${shortId}` : ''}.`, `Your request was added to the sales queue${shortId ? ` · ID: ${shortId}` : ''}.`)); }
    catch (error) { toast.error(error?.response?.data?.detail || copy(english, "Teklif talebi gönderilemedi", "Quote request could not be sent")); }
  });
  const handleLaunch = product => {
    if (product.key === "af_sadakat") return navigate("/app/afsadakat");
    if (product.route_path) return navigate(product.route_path);
    toast.info(copy(english, "Modül bağlantısı hazırlanıyor", "Module link is being prepared"));
  };
  const loadBilling = async () => { try { const { data } = await axios.get("/module-store/billing"); setBilling(data || { invoices: [], payment_methods: [] }); } catch (error) { toast.error(error?.response?.data?.detail || copy(english, "Faturalama bilgileri yüklenemedi", "Billing could not be loaded")); } };
  const cancelSubscription = async subscription => { try { await axios.post(`/module-store/subscriptions/${subscription.id}/cancel`, { reason: "Otel yöneticisi tarafından dönem sonunda iptal" }); toast.success(copy(english, "Otomatik yenileme kapatıldı", "Automatic renewal disabled")); await load(); } catch (error) { toast.error(error?.response?.data?.detail || copy(english, "Abonelik iptal edilemedi", "Subscription could not be cancelled")); } };
  const removePaymentMethod = async method => { try { await axios.delete(`/module-store/payment-methods/${method.id}`); toast.success(copy(english, "Ödeme yöntemi kaldırıldı", "Payment method removed")); await loadBilling(); } catch (error) { toast.error(error?.response?.data?.detail || copy(english, "Ödeme yöntemi kaldırılamadı", "Payment method could not be removed")); } };
  const requestRefund = async invoice => { try { await axios.post("/module-store/orders/refund-request", { order_id: invoice.order_id, reason: "Otel yöneticisi tarafından faturalama ekranından talep edildi" }); toast.success(copy(english, "İade talebiniz incelemeye alındı", "Refund request submitted for review")); } catch (error) { toast.error(error?.response?.data?.detail || copy(english, "İade talebi gönderilemedi", "Refund request could not be submitted")); } };
  const loadReadiness = async subscription => { try { const { data } = await axios.get(`/module-store/subscriptions/${subscription.id}/readiness`); setReadiness(current => ({ ...current, [subscription.id]: data })); } catch (error) { toast.error(error?.response?.data?.detail || copy(english, "Kurulum planı yüklenemedi", "Setup plan could not be loaded")); } };
  const toggleReadinessStep = async (subscription, step) => { try { await axios.patch(`/module-store/subscriptions/${subscription.id}/readiness`, { step_key: step.key, completed: step.status !== "complete" }); await loadReadiness(subscription); } catch (error) { toast.error(error?.response?.data?.detail || copy(english, "Kurulum adımı güncellenemedi", "Setup step could not be updated")); } };

  return <main className="min-h-screen bg-slate-50/70 pb-12">
    <section className="border-b border-slate-200 bg-gradient-to-br from-slate-950 via-slate-900 to-blue-950 text-white">
      <div className="mx-auto grid max-w-[1500px] gap-8 px-4 py-10 sm:px-6 lg:grid-cols-[1fr_auto] lg:items-end lg:py-14">
        <div className="max-w-3xl">
          <Badge className="mb-4 border-white/15 bg-white/10 text-white hover:bg-white/10"><ShieldCheck className="mr-1.5 h-3.5 w-3.5" /> {copy(english, "Syroce ile hazır entegre", "Native Syroce integrations")}</Badge>
          <h1 className="text-3xl font-black tracking-tight sm:text-4xl">{copy(english, "Oteliniz büyüdükçe sisteminiz de büyüsün", "A platform that grows with your hotel")}</h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-300">{copy(english, "İhtiyacınız olan operasyon, finans, satış ve misafir deneyimi modüllerini seçin. Tek oturum, tek veri modeli ve PMS ile kesintisiz çalışma.", "Choose the operations, finance, sales and guest-experience modules you need. One login, one data model and seamless PMS workflows.")}</p>
        </div>
          <div className="grid grid-cols-3 gap-2 text-center">
          <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-3"><div className="text-xl font-bold">{products.length || "—"}</div><div className="text-[11px] text-slate-300">{copy(english, "hazır çözüm", "solutions")}</div></div>
          <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-3"><div className="text-xl font-bold">14</div><div className="text-[11px] text-slate-300">{copy(english, "gün deneme", "day trial")}</div></div>
          <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-3"><div className="text-xl font-bold">✓</div><div className="text-[11px] text-slate-300">{copy(english, "kurulum planı", "setup plan")}</div></div>
        </div>
      </div>
    </section>
    <div className="mx-auto max-w-[1500px] space-y-6 px-4 py-6 sm:px-6">
      {!paymentReady && <div className="flex items-start gap-3 rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-950 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-100"><ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-blue-600 dark:text-blue-300" /><div><strong>{copy(english, "Güvenli teklif akışı aktif. ", "Secure quote flow is active. ")}</strong>{copy(english, "Online ödeme bağlantısı devreye alınana kadar “Teklif iste” ile talebiniz kayıt altına alınır.", "Until online payment is enabled, Request quote records your request for the sales team.")}</div></div>}
      <Tabs value={tab} onValueChange={setTab}>
        <div className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm lg:flex-row lg:items-center lg:justify-between">
          <TabsList className="w-full lg:w-auto"><TabsTrigger value="store" className="flex-1 lg:flex-none">{copy(english, "Modül Pazarı", "Marketplace")}</TabsTrigger><TabsTrigger value="subs" className="flex-1 lg:flex-none">{copy(english, "Aboneliklerim", "My subscriptions")} {subscriptions.length > 0 && <Badge className="ml-2">{subscriptions.length}</Badge>}</TabsTrigger><TabsTrigger value="billing" onClick={() => void loadBilling()} className="flex-1 lg:flex-none">{copy(english, "Faturalama", "Billing")}</TabsTrigger></TabsList>
          <div className="flex flex-col gap-3 sm:flex-row"><div className="relative min-w-0 sm:w-72"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" /><Input value={query} onChange={event => setQuery(event.target.value)} className="pl-9" placeholder={copy(english, "Modül ara…", "Search modules…")} aria-label={copy(english, "Modül ara", "Search modules")} /></div><Button variant="outline" onClick={() => void load()} disabled={loading}><RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} /> {copy(english, "Yenile", "Refresh")}</Button></div>
        </div>
        <TabsContent value="store" className="mt-6 space-y-5">
          <div className="flex gap-2 overflow-x-auto pb-1">{Object.entries(CATEGORY_COPY).map(([key, labels]) => <Button key={key} size="sm" variant={category === key ? "default" : "outline"} onClick={() => setCategory(key)} className="shrink-0">{labels[english ? "en" : "tr"]}</Button>)}</div>
          {loading ? <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 9 }).map((_, index) => <StoreSkeleton key={index} />)}</div> : filteredProducts.length === 0 ? <Card><CardContent className="py-14 text-center text-slate-500">{copy(english, "Aramanızla eşleşen modül bulunamadı.", "No modules match your search.")}</CardContent></Card> : <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">{filteredProducts.map(product => <ProductCard key={product.key} product={product} subscription={subscriptionByProduct[product.key]} paymentReady={paymentReady} buying={buying} english={english} onPurchase={handlePurchase} onTrial={handleTrial} onQuote={handleQuote} onLaunch={handleLaunch} />)}</div>}
        </TabsContent>
        <TabsContent value="subs" className="mt-6">
          {subscriptions.length === 0 ? <Card><CardContent className="py-14 text-center"><Package className="mx-auto h-10 w-10 text-slate-300" /><h2 className="mt-4 font-semibold text-slate-900">{copy(english, "Henüz aktif aboneliğiniz yok", "No active subscriptions yet")}</h2><p className="mt-1 text-sm text-slate-500">{copy(english, "İhtiyacınız olan modülü pazardan seçerek başlayın.", "Choose a module from the marketplace to get started.")}</p></CardContent></Card> : <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">{subscriptions.map(subscription => {
            const product = products.find(item => item.key === subscription.product_key); const Icon = ICONS[product?.icon] || Package;
             const plan = readiness[subscription.id];
             return <Card key={subscription.id}><CardContent className="p-5"><div className="flex items-center justify-between gap-4"><div className="flex min-w-0 items-center gap-3"><div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-slate-950 text-white"><Icon className="h-5 w-5" /></div><div className="min-w-0"><div className="truncate font-semibold text-slate-950">{english && product?.name_en ? product.name_en : product?.name || subscription.product_key}</div><div className="mt-1 flex items-center gap-1 text-xs text-slate-500"><Clock className="h-3.5 w-3.5" />{subscription.end_date ? new Date(subscription.end_date).toLocaleDateString(english ? "en-US" : "tr-TR") : copy(english, "Süresiz", "No expiry")}</div></div></div><Button size="sm" variant="outline" onClick={() => handleLaunch(product || {})}>{copy(english, "Aç", "Open")}</Button></div><Button size="sm" variant="outline" className="mt-3 w-full" onClick={() => loadReadiness(subscription)}>{plan ? `${plan.completed_steps}/${plan.total_steps} ${copy(english, "kurulum adımı", "setup steps")}` : copy(english, "Kurulumu ve sağlığı kontrol et", "Check setup and health")}</Button>{plan && <div className="mt-3 space-y-2 rounded-lg bg-slate-50 p-3"><div className="flex justify-between text-xs"><strong>{copy(english, "Modül sağlığı", "Module health")}</strong><Badge variant="outline">{plan.health === "healthy" ? copy(english, "Hazır", "Healthy") : copy(english, "Kurulum gerekli", "Setup required")}</Badge></div>{plan.steps?.map(step => <button type="button" key={step.key} onClick={() => toggleReadinessStep(subscription, step)} className="flex w-full items-center gap-2 rounded-md bg-white p-2 text-left text-xs"><span className={`flex h-4 w-4 items-center justify-center rounded border ${step.status === "complete" ? "border-emerald-600 bg-emerald-600 text-white" : "border-slate-300"}`}>{step.status === "complete" && "✓"}</span>{step.key.replaceAll("_", " ")}</button>)}</div>}<div className="mt-4 flex items-center justify-between border-t pt-3 text-xs"><span>{subscription.cancel_at_period_end ? copy(english, "Dönem sonunda sona erecek", "Ends after current period") : subscription.auto_renew === false ? copy(english, "Otomatik yenileme kapalı", "Auto-renew off") : copy(english, "Otomatik yenileme açık", "Auto-renew on")}</span>{!subscription.cancel_at_period_end && subscription.end_date && <Button size="sm" variant="ghost" className="h-7 text-red-600" onClick={() => cancelSubscription(subscription)}><XCircle className="mr-1 h-3.5 w-3.5" />{copy(english, "İptal et", "Cancel")}</Button>}</div></CardContent></Card>;
          })}</div>}
        </TabsContent>
        <TabsContent value="billing" className="mt-6 space-y-4"><Card><CardContent className="p-5"><h2 className="flex items-center gap-2 font-semibold"><CreditCard className="h-5 w-5" />{copy(english, "Ödeme yöntemleri", "Payment methods")}</h2>{billing.payment_methods?.length ? billing.payment_methods.map(method => <div key={method.id} className="mt-3 flex items-center justify-between rounded-lg bg-slate-50 p-3 text-sm"><span>{method.card_family || "Kart"} •••• {method.last4 || "—"} {method.is_default && <Badge className="ml-2">{copy(english, "Varsayılan", "Default")}</Badge>}</span><Button size="sm" variant="ghost" className="text-red-600" onClick={() => removePaymentMethod(method)}>{copy(english, "Kaldır", "Remove")}</Button></div>) : <p className="mt-3 text-sm text-slate-500">{copy(english, "Kayıtlı ödeme yöntemi yok. İlk güvenli ödemeden sonra burada görünür.", "No saved payment method. It appears after the first secure payment.")}</p>}</CardContent></Card><Card><CardContent className="p-5"><h2 className="flex items-center gap-2 font-semibold"><Receipt className="h-5 w-5" />{copy(english, "Faturalar ve ödemeler", "Invoices and payments")}</h2><div className="mt-3 space-y-2">{billing.invoices?.map(invoice => <div key={invoice.order_id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-sm"><span>{invoice.product_name || invoice.product_key}<small className="ml-2 text-slate-500">{new Date(invoice.completed_at || invoice.created_at).toLocaleDateString(english ? "en-US" : "tr-TR")}</small></span><div className="flex items-center gap-2"><strong>₺{Number(invoice.total_try ?? invoice.price_try ?? 0).toLocaleString(english ? "en-US" : "tr-TR")}</strong><Button size="sm" variant="outline" onClick={() => requestRefund(invoice)}>{copy(english, "İade talebi", "Request refund")}</Button></div></div>)}{!billing.invoices?.length && <p className="text-sm text-slate-500">{copy(english, "Tamamlanmış ödeme yok.", "No completed payments.")}</p>}</div></CardContent></Card></TabsContent>
      </Tabs>
    </div>
  </main>;
}
