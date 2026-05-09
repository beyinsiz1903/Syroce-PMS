import { useEffect, useMemo, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Building2, BedDouble, DollarSign, Users, CheckCircle2,
  Circle, ChevronLeft, ChevronRight, SkipForward, Loader2,
  PartyPopper, ArrowRight, RefreshCw, AlertCircle,
} from "lucide-react";

// 5 görünür wizard adımı; her biri backend'in 13 adımından bir veya
// daha fazlasıyla eşleşir. UI ilerlemesi BURADAKİ 5 adıma göre hesaplanır
// (P0: 9/13 ile 5 görünür kart kafa karışıklığını çözer).
const STEP_DEFS = [
  { id: "hotel", labelKey: "onboarding.steps.hotel", labelFallback: "Otel Bilgileri", icon: Building2, related: ["hotel_info_completed"] },
  { id: "rooms", labelKey: "onboarding.steps.rooms", labelFallback: "Odalar", icon: BedDouble, related: ["rooms_configured"] },
  { id: "rates", labelKey: "onboarding.steps.rates", labelFallback: "Fiyatlar", icon: DollarSign, related: ["rates_configured"] },
  { id: "team", labelKey: "onboarding.steps.team", labelFallback: "Ekip", icon: Users, related: ["team_members_added"] },
  { id: "done", labelKey: "onboarding.steps.done", labelFallback: "Tamamlandı", icon: PartyPopper, related: [] },
];

const PROPERTY_TYPES = [
  { v: "hotel", l: "Otel" },
  { v: "boutique", l: "Butik Otel" },
  { v: "resort", l: "Tatil Köyü" },
  { v: "apart", l: "Apart" },
  { v: "hostel", l: "Hostel" },
  { v: "villa", l: "Villa" },
  { v: "pansiyon", l: "Pansiyon" },
];

const CURRENCIES = ["TRY", "USD", "EUR", "GBP", "RUB"];
const LANGUAGES = [
  { v: "tr", l: "Türkçe" },
  { v: "en", l: "English" },
  { v: "ru", l: "Русский" },
  { v: "de", l: "Deutsch" },
  { v: "ar", l: "العربية" },
];

const TIMEZONES = [
  "Europe/Istanbul", "Europe/Berlin", "Europe/London", "Asia/Dubai",
  "Europe/Moscow", "Asia/Riyadh", "America/New_York",
];

export default function OnboardingWizard({ user, tenant, onLogout }) {
  void onLogout;
  const navigate = useNavigate();
  const { t } = useTranslation?.() || { t: (_, def) => def };
  const [stepIdx, setStepIdx] = useState(0);
  const [progress, setProgress] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const [hotelForm, setHotelForm] = useState({
    property_name: tenant?.property_name || "",
    property_type: tenant?.property_type || "hotel",
    star_rating: tenant?.star_rating || "",
    opening_year: tenant?.opening_year || "",
    contact_phone: tenant?.contact_phone || "",
    contact_email: tenant?.contact_email || "",
    address: tenant?.address || "",
    location: tenant?.location || "",
    city: tenant?.city || "",
    district: tenant?.district || "",
    neighborhood: tenant?.neighborhood || "",
    street: tenant?.street || "",
    building_no: tenant?.building_no || "",
    postal_code: tenant?.postal_code || "",
    total_rooms: tenant?.total_rooms || "",
    currency: tenant?.currency || "TRY",
    timezone: tenant?.timezone || "Europe/Istanbul",
    default_language: tenant?.default_language || "tr",
    tax_number: tenant?.tax_number || "",
    mersis_no: tenant?.mersis_no || "",
    tga_code: tenant?.tga_code || "",
    vat_rate: tenant?.vat_rate ?? 8,
    accommodation_tax_exempt: tenant?.accommodation_tax_exempt || false,
  });

  // P0 #3 + UX: backend response'u is_tenant_admin döner; client-side
  // kontrol artık super_admin'e kısıtlı değil — admin/owner da true.
  const isTenantAdmin = useMemo(() => {
    if (progress?.is_tenant_admin !== undefined) return !!progress.is_tenant_admin;
    const role = (user?.role || "").toLowerCase();
    const roles = Array.isArray(user?.roles) ? user.roles.map(r => (r || "").toLowerCase()) : [];
    const ADMIN = ["super_admin", "platform_admin", "admin", "owner"];
    return ADMIN.includes(role) || roles.some(r => ADMIN.includes(r));
  }, [progress, user]);

  const refresh = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await axios.get("/onboarding/progress");
      setProgress(r.data);
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || "Bilinmeyen hata";
      setError(msg);
      toast.error("İlerleme okunamadı: " + msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const stepStatus = useMemo(() => {
    const map = {};
    (progress?.steps || []).forEach((s) => { map[s.step_id] = s.completed; });
    return map;
  }, [progress]);

  const isStepDone = (def) =>
    def.related.length > 0 && def.related.every(k => !!stepStatus[k]);

  // P0: UI 5 görünür adımdan kendi yüzdesini hesaplar (backend 9/13 ≠ UI 5 adım).
  const visibleDone = STEP_DEFS.filter(d => d.related.length > 0 && isStepDone(d)).length;
  const visibleTotal = STEP_DEFS.filter(d => d.related.length > 0).length;
  const visiblePct = visibleTotal > 0 ? Math.round((visibleDone / visibleTotal) * 100) : 0;
  // Backend ham progress (informational/tooltip için)
  const backendDone = progress?.completed ?? 0;
  const backendTotal = progress?.total ?? 0;
  const backendPct = progress?.progress_pct ?? 0;

  const currentDef = STEP_DEFS[stepIdx];

  const validateHotelForm = () => {
    if (!hotelForm.property_name?.trim()) {
      toast.error("Mülk adı zorunlu");
      return false;
    }
    if (!hotelForm.total_rooms || parseInt(hotelForm.total_rooms, 10) < 1) {
      toast.error("Toplam oda sayısı zorunlu (en az 1)");
      return false;
    }
    if (hotelForm.contact_phone && !/^\+?[0-9 ()\-]{10,20}$/.test(hotelForm.contact_phone.trim())) {
      toast.error("Telefon formatı geçersiz (örn. +905551234567)");
      return false;
    }
    return true;
  };

  const saveHotelInfo = async () => {
    if (!validateHotelForm()) return;
    setSaving(true);
    try {
      const payload = { ...hotelForm };
      payload.total_rooms = parseInt(payload.total_rooms, 10);
      if (payload.star_rating === "" || payload.star_rating == null) delete payload.star_rating;
      else payload.star_rating = parseInt(payload.star_rating, 10);
      if (payload.opening_year === "" || payload.opening_year == null) delete payload.opening_year;
      else payload.opening_year = parseInt(payload.opening_year, 10);
      if (payload.vat_rate === "" || payload.vat_rate == null) delete payload.vat_rate;
      else payload.vat_rate = parseFloat(payload.vat_rate);
      // boş stringleri at
      Object.keys(payload).forEach(k => {
        if (payload[k] === "" || payload[k] === null) delete payload[k];
      });
      await axios.patch("/onboarding/hotel-info", payload);
      toast.success("Otel bilgileri kaydedildi");
      await refresh();
      setStepIdx(1);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Kaydedilemedi");
    } finally {
      setSaving(false);
    }
  };

  const handleSkip = async () => {
    if (!isTenantAdmin) {
      toast.error("Bu işlem için yönetici yetkisi gerekli");
      return;
    }
    try {
      await axios.post("/onboarding/dismiss");
      toast.info("Sihirbaz kapatıldı. Menüden istediğiniz zaman geri açabilirsiniz.");
      navigate("/app/dashboard");
    } catch {
      navigate("/app/dashboard");
    }
  };

  const handleFinish = async () => {
    if (isTenantAdmin) {
      try { await axios.post("/onboarding/dismiss"); } catch { /* ignore */ }
    }
    navigate("/app/dashboard");
  };

  if (loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
      </div>
    );
  }

  if (error && !progress) {
    return (
      <div className="max-w-2xl mx-auto p-6">
        <Card className="p-6 text-center">
          <AlertCircle className="w-10 h-10 text-rose-500 mx-auto mb-3" />
          <div className="font-semibold text-slate-900 mb-1">İlerleme yüklenemedi</div>
          <div className="text-sm text-slate-500 mb-4">{error}</div>
          <Button onClick={refresh} variant="outline">
            <RefreshCw className="w-4 h-4 mr-1.5" /> Tekrar Dene
          </Button>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-4 sm:p-6 space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            {t("onboarding.welcome", "Hoş geldiniz")}
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            Sistemi 5 adımda kullanıma hazırlayın. Her adımı atlayabilir,
            menüden tekrar geri dönebilirsiniz.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={refresh} disabled={loading || saving}>
          <RefreshCw className="w-4 h-4 mr-1.5" /> Yenile
        </Button>
      </div>

      {/* Overall progress (UI'nın 5 görünür adımına göre) */}
      <Card>
        <CardContent className="pt-6 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-slate-700">
              Kurulum ilerlemesi
            </span>
            <Badge variant="outline" className="font-mono">
              {visibleDone}/{visibleTotal} · {visiblePct}%
            </Badge>
          </div>
          <Progress value={visiblePct} className="h-2" />
          <div className="text-xs text-slate-500">
            Detay: backend {backendDone}/{backendTotal} ({backendPct}%) — kanal yöneticisi,
            fatura, gece denetimi gibi ileri özellikler kullanılmaya başlandıkça otomatik tamamlanır.
          </div>
        </CardContent>
      </Card>

      {/* Step strip — mobile responsive (3 sütun) → sm 5 sütun */}
      <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
        {STEP_DEFS.map((def, i) => {
          const Icon = def.icon;
          const done = isStepDone(def);
          const active = i === stepIdx;
          return (
            <button
              key={def.id}
              type="button"
              onClick={() => setStepIdx(i)}
              aria-current={active ? "step" : undefined}
              aria-pressed={active}
              className={`text-left rounded-lg border px-3 py-2 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
                active
                  ? "border-indigo-500 bg-indigo-50 ring-2 ring-indigo-200"
                  : "border-slate-200 hover:border-slate-300"
              }`}
            >
              <div className="flex items-center gap-2">
                {done ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                ) : (
                  <Circle className="w-4 h-4 text-slate-400" />
                )}
                <span className="text-xs font-medium text-slate-700">
                  {i + 1}. {t(def.labelKey, def.labelFallback)}
                </span>
              </div>
              <Icon className={`w-5 h-5 mt-1 ${active ? "text-indigo-600" : "text-slate-400"}`} />
            </button>
          );
        })}
      </div>

      {/* Step body */}
      {currentDef.id === "hotel" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Building2 className="w-5 h-5 text-indigo-600" /> Otel Bilgileri
            </CardTitle>
            <CardDescription>
              Kurulum için gerekli temel bilgiler. <span className="text-amber-700">Toplam oda sayısı kapasiteyi gösterir; odaları ayrıca 2. adımda toplu olarak oluşturursunuz.</span>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <Label htmlFor="property_name">Mülk Adı *</Label>
                <Input id="property_name" value={hotelForm.property_name}
                  onChange={(e) => setHotelForm(f => ({ ...f, property_name: e.target.value }))}
                  placeholder="Örn. Syroce Park Otel" />
              </div>
              <div>
                <Label>Mülk Tipi *</Label>
                <Select value={hotelForm.property_type} onValueChange={v => setHotelForm(f => ({ ...f, property_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{PROPERTY_TYPES.map(p => <SelectItem key={p.v} value={p.v}>{p.l}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div>
                <Label htmlFor="star_rating">Yıldız (1–5)</Label>
                <Input id="star_rating" type="number" min="1" max="5" value={hotelForm.star_rating}
                  onChange={e => setHotelForm(f => ({ ...f, star_rating: e.target.value }))} />
              </div>
              <div>
                <Label htmlFor="opening_year">Açılış Yılı</Label>
                <Input id="opening_year" type="number" min="1900" max={new Date().getFullYear() + 5}
                  value={hotelForm.opening_year}
                  onChange={e => setHotelForm(f => ({ ...f, opening_year: e.target.value }))} />
              </div>
              <div>
                <Label htmlFor="total_rooms">Oda Sayısı *</Label>
                <Input id="total_rooms" type="number" min="1" value={hotelForm.total_rooms}
                  onChange={e => setHotelForm(f => ({ ...f, total_rooms: e.target.value }))}
                  placeholder="50" />
              </div>
              <div>
                <Label>Para Birimi</Label>
                <Select value={hotelForm.currency} onValueChange={v => setHotelForm(f => ({ ...f, currency: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{CURRENCIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <Label>Zaman Dilimi</Label>
                <Select value={hotelForm.timezone} onValueChange={v => setHotelForm(f => ({ ...f, timezone: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{TIMEZONES.map(z => <SelectItem key={z} value={z}>{z}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div>
                <Label>Varsayılan Dil</Label>
                <Select value={hotelForm.default_language} onValueChange={v => setHotelForm(f => ({ ...f, default_language: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{LANGUAGES.map(l => <SelectItem key={l.v} value={l.v}>{l.l}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="vat_rate">KDV (%)</Label>
                <Input id="vat_rate" type="number" min="0" max="100" step="0.1"
                  value={hotelForm.vat_rate}
                  onChange={e => setHotelForm(f => ({ ...f, vat_rate: e.target.value }))} />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <Label htmlFor="contact_phone">Telefon</Label>
                <Input id="contact_phone" value={hotelForm.contact_phone}
                  onChange={e => setHotelForm(f => ({ ...f, contact_phone: e.target.value }))}
                  placeholder="+905551234567" />
              </div>
              <div>
                <Label htmlFor="contact_email">E-posta</Label>
                <Input id="contact_email" type="email" value={hotelForm.contact_email}
                  onChange={e => setHotelForm(f => ({ ...f, contact_email: e.target.value }))}
                  placeholder="info@hotel.com" />
              </div>
            </div>

            {/* Yapılandırılmış adres (KBS / e-fatura için gerekli) */}
            <div>
              <div className="text-sm font-semibold text-slate-700 mb-2">Adres (KBS / e-fatura için)</div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div>
                  <Label htmlFor="city">İl</Label>
                  <Input id="city" value={hotelForm.city}
                    onChange={e => setHotelForm(f => ({ ...f, city: e.target.value }))} placeholder="Antalya" />
                </div>
                <div>
                  <Label htmlFor="district">İlçe</Label>
                  <Input id="district" value={hotelForm.district}
                    onChange={e => setHotelForm(f => ({ ...f, district: e.target.value }))} placeholder="Muratpaşa" />
                </div>
                <div>
                  <Label htmlFor="neighborhood">Mahalle</Label>
                  <Input id="neighborhood" value={hotelForm.neighborhood}
                    onChange={e => setHotelForm(f => ({ ...f, neighborhood: e.target.value }))} />
                </div>
                <div>
                  <Label htmlFor="postal_code">Posta Kodu</Label>
                  <Input id="postal_code" value={hotelForm.postal_code}
                    onChange={e => setHotelForm(f => ({ ...f, postal_code: e.target.value }))} placeholder="07100" />
                </div>
                <div className="col-span-2">
                  <Label htmlFor="street">Cadde / Sokak</Label>
                  <Input id="street" value={hotelForm.street}
                    onChange={e => setHotelForm(f => ({ ...f, street: e.target.value }))} />
                </div>
                <div>
                  <Label htmlFor="building_no">Bina No</Label>
                  <Input id="building_no" value={hotelForm.building_no}
                    onChange={e => setHotelForm(f => ({ ...f, building_no: e.target.value }))} placeholder="12/A" />
                </div>
                <div>
                  <Label htmlFor="location">Bölge / Etiket</Label>
                  <Input id="location" value={hotelForm.location}
                    onChange={e => setHotelForm(f => ({ ...f, location: e.target.value }))} placeholder="Lara" />
                </div>
              </div>
            </div>

            {/* TR yasal kodlar */}
            <div>
              <div className="text-sm font-semibold text-slate-700 mb-2">Yasal Kodlar (Türkiye)</div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div>
                  <Label htmlFor="tax_number">VKN / TCKN</Label>
                  <Input id="tax_number" value={hotelForm.tax_number}
                    onChange={e => setHotelForm(f => ({ ...f, tax_number: e.target.value }))} />
                </div>
                <div>
                  <Label htmlFor="mersis_no">MERSİS No</Label>
                  <Input id="mersis_no" value={hotelForm.mersis_no}
                    onChange={e => setHotelForm(f => ({ ...f, mersis_no: e.target.value }))} />
                </div>
                <div>
                  <Label htmlFor="tga_code">TGA Tesis Kodu</Label>
                  <Input id="tga_code" value={hotelForm.tga_code}
                    onChange={e => setHotelForm(f => ({ ...f, tga_code: e.target.value }))} />
                </div>
                <div className="flex items-end gap-2 pb-1">
                  <input id="acc_tax_exempt" type="checkbox" className="w-4 h-4"
                    checked={!!hotelForm.accommodation_tax_exempt}
                    onChange={e => setHotelForm(f => ({ ...f, accommodation_tax_exempt: e.target.checked }))} />
                  <Label htmlFor="acc_tax_exempt" className="text-xs">Konaklama vergisi muafiyeti</Label>
                </div>
              </div>
            </div>

            {!isTenantAdmin && (
              <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
                Bu formu yalnızca otel yöneticisi kaydedebilir. Mevcut rolünüzle değişiklikleri kaydetme yetkiniz yok.
              </div>
            )}

            <Button onClick={saveHotelInfo} disabled={saving || !isTenantAdmin} size="lg" className="w-full">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : (
                <>Kaydet ve Devam Et <ArrowRight className="w-4 h-4 ml-1" /></>
              )}
            </Button>
          </CardContent>
        </Card>
      )}

      {currentDef.id === "rooms" && (
        <ActionStep
          icon={BedDouble}
          title="Odalarınızı tanımlayın"
          description={
            isTenantAdmin
              ? "Toplu eklemeden önce oda numaraları önizlenir ve onayınız istenir."
              : "Oda oluşturma yetkisi yöneticilere aittir. Lütfen otel yöneticisi ile iletişime geçin."
          }
          done={!!stepStatus.rooms_configured}
          primary={{
            label: isTenantAdmin ? "Toplu Oda Ekle (önizlemeli)" : "Yetki Gerekli",
            disabled: !isTenantAdmin,
            action: () => {
              if (!isTenantAdmin) return;
              // P1 #5 cross-tenant fallback fix: tenant id yoksa hiç set etme.
              if (tenant?.id) {
                window.localStorage.setItem(
                  `pms_open_dialog_once:${tenant.id}`, "bulk-rooms"
                );
              }
              navigate("/app/pms#rooms");
            },
          }}
        />
      )}

      {currentDef.id === "rates" && (
        <ActionStep
          icon={DollarSign}
          title="Fiyat planı tanımlayın"
          description="En az bir rate plan eklediğinizde bu adım otomatik tamamlanır."
          done={!!stepStatus.rates_configured}
          primary={{
            label: "Tarife Yönetimi",
            action: () => navigate("/unified-rate-manager"),
          }}
        />
      )}

      {currentDef.id === "team" && (
        <ActionStep
          icon={Users}
          title="Ekip üyelerini davet edin"
          description="Resepsiyon, kat hizmetleri vb. için ek kullanıcı ekleyin. İkinci kullanıcı eklendiğinde adım otomatik tamamlanır."
          done={!!stepStatus.team_members_added}
          primary={{
            label: "Kullanıcı Yönetimi",
            action: () => navigate("/admin/user-roles"),
          }}
        />
      )}

      {currentDef.id === "done" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PartyPopper className="w-5 h-5 text-emerald-600" /> Hazırsınız!
            </CardTitle>
            <CardDescription>
              Tebrikler — temel kurulum tamam. İleri özellikler (kanal yöneticisi,
              fatura, gece denetimi) ilgili modülleri kullanmaya başladıkça
              otomatik tamamlanacak.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={handleFinish} size="lg" className="w-full">
              Panele Git <ArrowRight className="w-4 h-4 ml-1" />
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Bottom nav */}
      <div className="flex items-center justify-between gap-2 pt-2">
        <Button
          variant="outline"
          disabled={stepIdx === 0}
          onClick={() => setStepIdx(i => Math.max(0, i - 1))}
        >
          <ChevronLeft className="w-4 h-4 mr-1" /> Geri
        </Button>

        {/* P2 #13: "Şimdilik Atla" yalnızca yöneticiye görünür */}
        {isTenantAdmin && (
          <Button variant="ghost" onClick={handleSkip}>
            <SkipForward className="w-4 h-4 mr-1" /> Şimdilik Atla
          </Button>
        )}

        <Button
          variant="outline"
          disabled={stepIdx === STEP_DEFS.length - 1}
          onClick={() => setStepIdx(i => Math.min(STEP_DEFS.length - 1, i + 1))}
        >
          Sonraki <ChevronRight className="w-4 h-4 ml-1" />
        </Button>
      </div>
    </div>
  );
}

function ActionStep({ icon: Icon, title, description, done, primary }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Icon className="w-5 h-5 text-indigo-600" /> {title}
          {done && (
            <Badge className="bg-emerald-100 text-emerald-800 border-emerald-200">
              <CheckCircle2 className="w-3 h-3 mr-1" /> Tamamlandı
            </Badge>
          )}
        </CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <Button onClick={primary.action} size="lg" className="w-full" disabled={!!primary.disabled}>
          {primary.label} <ArrowRight className="w-4 h-4 ml-1" />
        </Button>
      </CardContent>
    </Card>
  );
}
