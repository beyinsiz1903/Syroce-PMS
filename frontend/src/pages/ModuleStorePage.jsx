import { useEffect, useState, useMemo } from "react";
import axios from "axios";
import { toast } from "sonner";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useNavigate } from "react-router-dom";
import {
  ShoppingBag, QrCode, ScanLine, Mail, Package, Sparkles,
  CheckCircle2, Clock, Loader2, RefreshCw, Gift, ExternalLink,
} from "lucide-react";

const ICONS = { QrCode, ScanLine, Mail, Package, Sparkles };
const CATEGORY_LABEL = {
  module: "Modül",
  integration: "Entegrasyon",
  credit_pack: "Kredi Paketi",
};
const CATEGORY_COLOR = {
  module: "bg-blue-100 text-blue-800 border-blue-200",
  integration: "bg-indigo-100 text-indigo-800 border-indigo-200",
  credit_pack: "bg-emerald-100 text-emerald-800 border-emerald-200",
};

function ProductCard({ product, owned, onPurchase, onStartTrial, onLaunch, buying }) {
  const Icon = ICONS[product.icon] || Package;
  const ownedSub = owned.find((s) => s.product_key === product.key);
  const hasTrial = !!product.trial_days;
  const isExternal = !!product.external;
  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-lg bg-slate-100 flex items-center justify-center">
              <Icon className="w-5 h-5 text-slate-700" />
            </div>
            <div>
              <CardTitle className="text-base">{product.name}</CardTitle>
              <Badge className={`mt-1 ${CATEGORY_COLOR[product.category] || ""}`}>
                {CATEGORY_LABEL[product.category] || product.category}
              </Badge>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col flex-1 gap-4">
        <p className="text-sm text-slate-600">{product.description}</p>
        {product.features?.length > 0 && (
          <ul className="space-y-1.5 text-sm">
            {product.features.map((f, i) => (
              <li key={i} className="flex items-start gap-2 text-slate-700">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
                <span>{f}</span>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-auto pt-3 border-t flex items-end justify-between">
          <div>
            <div className="text-2xl font-bold text-slate-900">
              {product.price_try.toLocaleString("tr-TR")} ₺
            </div>
            <div className="text-xs text-slate-500">
              {product.billing_type === "subscription"
                ? `${product.duration_days} günlük abonelik`
                : "Tek seferlik"}
            </div>
          </div>
          {ownedSub ? (
            <div className="flex items-center gap-2">
              <Badge className="bg-emerald-100 text-emerald-800 border-emerald-200">
                {ownedSub.trial ? "Deneme Aktif" : "Aktif"}
              </Badge>
              {isExternal && (
                <Button size="sm" variant="outline" onClick={() => onLaunch(product)}>
                  <ExternalLink className="w-3.5 h-3.5 mr-1" /> Aç
                </Button>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-1.5 items-end">
              {hasTrial && (
                <Button
                  onClick={() => onStartTrial(product)}
                  disabled={buying === product.key}
                  size="sm"
                  variant="outline"
                  className="border-violet-300 text-violet-700 hover:bg-violet-50"
                >
                  <Gift className="w-3.5 h-3.5 mr-1" />
                  {product.trial_days} Gün Ücretsiz Dene
                </Button>
              )}
              <Button
                onClick={() => onPurchase(product)}
                disabled={buying === product.key}
                size="sm"
              >
                {buying === product.key ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <>
                    <ShoppingBag className="w-4 h-4 mr-1" /> Satın Al
                  </>
                )}
              </Button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default function ModuleStorePage({ user, tenant, onLogout }) {
  const navigate = useNavigate();
  const [products, setProducts] = useState([]);
  const [subs, setSubs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [paymentReady, setPaymentReady] = useState(false);
  const [buying, setBuying] = useState(null);
  const [tab, setTab] = useState("store");

  const load = async () => {
    setLoading(true);
    try {
      const [p, s] = await Promise.all([
        axios.get("/module-store/products"),
        axios.get("/module-store/my-subscriptions"),
      ]);
      setProducts(p.data.products || []);
      setPaymentReady(!!p.data.payment_ready);
      setSubs(s.data.subscriptions || []);
    } catch (e) {
      console.error(e);
      toast.error("Veriler yüklenemedi");
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const handlePurchase = async (product) => {
    if (!paymentReady) {
      toast.warning(
        "Ödeme sistemi henüz aktif değil. Yöneticiniz iyzico bilgilerini girince satın alabilirsiniz."
      );
      return;
    }
    setBuying(product.key);
    try {
      const res = await axios.post("/module-store/purchase", {
        product_key: product.key,
      });
      if (res.data.payment_page_url) {
        window.location.href = res.data.payment_page_url;
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Satın alma başlatılamadı");
    }
    setBuying(null);
  };

  const handleStartTrial = async (product) => {
    setBuying(product.key);
    try {
      await axios.post("/module-store/start-trial", { product_key: product.key });
      toast.success(`${product.trial_days} günlük ücretsiz deneme başlatıldı`);
      await load();
      if (product.external) {
        // For external modules, jump straight to the launcher
        if (product.key === "af_sadakat") navigate("/app/afsadakat");
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Deneme başlatılamadı");
    }
    setBuying(null);
  };

  const handleLaunch = async (product) => {
    if (product.key === "af_sadakat") {
      navigate("/app/afsadakat");
    }
  };

  const grouped = useMemo(() => {
    const g = { module: [], integration: [], credit_pack: [] };
    for (const p of products) {
      const cat = g[p.category] ? p.category : "module";
      g[cat].push(p);
    }
    return g;
  }, [products]);

  if (loading) {
    return (
      <>
        <div className="min-h-[60vh] flex items-center justify-center">
          <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
        </div>
      </>
    );
  }

  return (
    <>
      <div className="max-w-7xl mx-auto p-4 sm:p-6 space-y-6">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
              <ShoppingBag className="w-6 h-6" /> Modül Pazarı
            </h1>
            <p className="text-sm text-slate-600">
              İhtiyacınız olan modül, entegrasyon ve kredi paketlerini buradan satın alın.
            </p>
          </div>
          <Button variant="outline" onClick={load}>
            <RefreshCw className="w-4 h-4 mr-1" /> Yenile
          </Button>
        </div>

        {!paymentReady && (
          <Card className="border-amber-200 bg-amber-50">
            <CardContent className="pt-4 text-sm text-amber-900">
              Ödeme sistemi (iyzico) henüz aktif edilmemiş. Bilgiler tanımlandığında
              satın alma butonları çalışacak.
            </CardContent>
          </Card>
        )}

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="store">Mağaza</TabsTrigger>
            <TabsTrigger value="subs">
              Aboneliklerim {subs.length > 0 && (
                <Badge className="ml-2 bg-slate-200 text-slate-800">{subs.length}</Badge>
              )}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="store" className="space-y-8 mt-6">
            {[
              { key: "module", title: "Modüller" },
              { key: "integration", title: "Entegrasyonlar" },
              { key: "credit_pack", title: "Kredi Paketleri" },
            ].map((sec) => grouped[sec.key].length > 0 && (
              <section key={sec.key}>
                <h2 className="text-lg font-semibold text-slate-900 mb-3">
                  {sec.title}
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {grouped[sec.key].map((p) => (
                    <ProductCard
                      key={p.key}
                      product={p}
                      owned={subs}
                      onPurchase={handlePurchase}
                      onStartTrial={handleStartTrial}
                      onLaunch={handleLaunch}
                      buying={buying}
                    />
                  ))}
                </div>
              </section>
            ))}
          </TabsContent>

          <TabsContent value="subs" className="mt-6">
            {subs.length === 0 ? (
              <Card>
                <CardContent className="pt-6 text-center text-slate-500">
                  Henüz aktif aboneliğiniz yok.
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-3">
                {subs.map((s) => {
                  const product = products.find((p) => p.key === s.product_key);
                  const Icon = ICONS[product?.icon] || Package;
                  const endDate = s.end_date
                    ? new Date(s.end_date).toLocaleDateString("tr-TR")
                    : "Süresiz";
                  return (
                    <Card key={s.id}>
                      <CardContent className="pt-5 flex items-center justify-between gap-4">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center">
                            <Icon className="w-5 h-5 text-slate-700" />
                          </div>
                          <div>
                            <div className="font-semibold text-slate-900">
                              {product?.name || s.product_key}
                            </div>
                            <div className="text-xs text-slate-500 flex items-center gap-1.5">
                              <Clock className="w-3 h-3" /> Bitiş: {endDate}
                            </div>
                          </div>
                        </div>
                        <Badge className="bg-emerald-100 text-emerald-800 border-emerald-200">
                          Aktif
                        </Badge>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </>
  );
}
