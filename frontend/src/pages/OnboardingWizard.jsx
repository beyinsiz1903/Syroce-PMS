import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import Layout from "@/components/Layout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import {
  Building2, BedDouble, DollarSign, Users, CheckCircle2,
  Circle, ChevronLeft, ChevronRight, SkipForward, Loader2,
  PartyPopper, ArrowRight,
} from "lucide-react";

const STEP_DEFS = [
  { id: "hotel", label: "Otel Bilgileri", icon: Building2,
    related_step: "hotel_info_completed" },
  { id: "rooms", label: "Odalar", icon: BedDouble,
    related_step: "rooms_configured" },
  { id: "rates", label: "Fiyatlar", icon: DollarSign,
    related_step: "rates_configured" },
  { id: "team", label: "Ekip", icon: Users,
    related_step: "team_members_added" },
  { id: "done", label: "Tamamlandı", icon: PartyPopper, related_step: null },
];

export default function OnboardingWizard({ user, tenant, onLogout }) {
  const navigate = useNavigate();
  const [stepIdx, setStepIdx] = useState(0);
  const [progress, setProgress] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hotelForm, setHotelForm] = useState({
    property_name: tenant?.property_name || "",
    contact_phone: tenant?.contact_phone || "",
    address: tenant?.address || "",
    location: tenant?.location || "",
    total_rooms: tenant?.total_rooms || "",
  });

  const refresh = async () => {
    try {
      const r = await axios.get("/onboarding/progress");
      setProgress(r.data);
    } catch (e) {
      toast.error("İlerleme okunamadı");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  const stepStatus = useMemo(() => {
    const map = {};
    (progress?.steps || []).forEach((s) => { map[s.step_id] = s.completed; });
    return map;
  }, [progress]);

  const isStepDone = (def) => def.related_step ? !!stepStatus[def.related_step] : false;

  const overallPct = progress?.progress_pct ?? 0;
  const currentDef = STEP_DEFS[stepIdx];

  const saveHotelInfo = async () => {
    if (!hotelForm.property_name?.trim()) {
      toast.error("Mülk adı zorunlu");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        ...hotelForm,
        total_rooms: hotelForm.total_rooms
          ? parseInt(hotelForm.total_rooms, 10)
          : undefined,
      };
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
    try {
      await axios.post("/onboarding/dismiss");
      toast.info("Sihirbaz kapatıldı. Menüden istediğiniz zaman geri açabilirsiniz.");
      navigate("/app/dashboard");
    } catch {
      navigate("/app/dashboard");
    }
  };

  const handleFinish = async () => {
    try { await axios.post("/onboarding/dismiss"); } catch { /* ignore */ }
    navigate("/app/dashboard");
  };

  if (loading) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="onboarding">
        <div className="min-h-[60vh] flex items-center justify-center">
          <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
        </div>
      </Layout>
    );
  }

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="onboarding">
      <div className="max-w-4xl mx-auto p-4 sm:p-6 space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Hoş geldiniz 👋</h1>
          <p className="text-sm text-slate-600 mt-1">
            Sistemi 5 adımda kullanıma hazırlayın. Her adımı atlayabilir,
            menüden tekrar geri dönebilirsiniz.
          </p>
        </div>

        {/* Overall progress */}
        <Card>
          <CardContent className="pt-6 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-slate-700">
                Genel ilerleme
              </span>
              <Badge variant="outline" className="font-mono">
                {progress?.completed ?? 0}/{progress?.total ?? 0}
                {" · "}{overallPct}%
              </Badge>
            </div>
            <Progress value={overallPct} className="h-2" />
          </CardContent>
        </Card>

        {/* Step strip */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
          {STEP_DEFS.map((def, i) => {
            const Icon = def.icon;
            const done = isStepDone(def);
            const active = i === stepIdx;
            return (
              <button
                key={def.id}
                onClick={() => setStepIdx(i)}
                className={`text-left rounded-lg border px-3 py-2 transition ${
                  active
                    ? "border-violet-500 bg-violet-50 ring-2 ring-violet-200"
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
                    {i + 1}. {def.label}
                  </span>
                </div>
                <Icon className={`w-5 h-5 mt-1 ${active ? "text-violet-600" : "text-slate-400"}`} />
              </button>
            );
          })}
        </div>

        {/* Step body */}
        {currentDef.id === "hotel" && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Building2 className="w-5 h-5 text-violet-600" /> Otel Bilgileri
              </CardTitle>
              <CardDescription>
                Mülk adı, iletişim ve kapasite bilgilerini güncelleyin.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label htmlFor="property_name">Mülk Adı *</Label>
                <Input
                  id="property_name"
                  value={hotelForm.property_name}
                  onChange={(e) => setHotelForm((f) => ({ ...f, property_name: e.target.value }))}
                  placeholder="Örn. Syroce Park Otel"
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <Label htmlFor="contact_phone">Telefon</Label>
                  <Input
                    id="contact_phone"
                    value={hotelForm.contact_phone}
                    onChange={(e) => setHotelForm((f) => ({ ...f, contact_phone: e.target.value }))}
                    placeholder="+90 ..."
                  />
                </div>
                <div>
                  <Label htmlFor="total_rooms">Toplam Oda Sayısı</Label>
                  <Input
                    id="total_rooms"
                    type="number"
                    min="1"
                    value={hotelForm.total_rooms}
                    onChange={(e) => setHotelForm((f) => ({ ...f, total_rooms: e.target.value }))}
                    placeholder="50"
                  />
                </div>
              </div>
              <div>
                <Label htmlFor="address">Adres</Label>
                <Input
                  id="address"
                  value={hotelForm.address}
                  onChange={(e) => setHotelForm((f) => ({ ...f, address: e.target.value }))}
                  placeholder="İl / İlçe / Mahalle"
                />
              </div>
              <div>
                <Label htmlFor="location">Konum / Bölge</Label>
                <Input
                  id="location"
                  value={hotelForm.location}
                  onChange={(e) => setHotelForm((f) => ({ ...f, location: e.target.value }))}
                  placeholder="İstanbul, Antalya, ..."
                />
              </div>
              <Button onClick={saveHotelInfo} disabled={saving} size="lg" className="w-full">
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
            description={user?.role === 'super_admin'
              ? "Oda oluşturma yalnızca süper-admin kullanıcılar tarafından yapılabilir. Toplu eklemeden önce oda numaraları önizlenir ve onayınız istenir."
              : "Oda oluşturma yetkisi yalnızca süper-admin kullanıcılara aittir. Lütfen süper-admin ile iletişime geçin."}
            done={!!stepStatus.rooms_configured}
            primary={{
              label: user?.role === 'super_admin' ? "Toplu Oda Ekle (önizlemeli)" : "Yetki Gerekli",
              disabled: user?.role !== 'super_admin',
              action: () => {
                if (user?.role !== 'super_admin') return;
                window.localStorage.setItem(
                  `pms_open_dialog_once:${tenant?.id || "x"}`, "bulk-rooms"
                );
                navigate("/app/pms#rooms");
              },
            }}
          />
        )}

        {currentDef.id === "rates" && (
          <ActionStep
            icon={DollarSign}
            title="Fiyat planı tanımlayın"
            description="En az bir rate plan eklediğinizde bu adım otomatik tamamlanır. Tarife yönetimi sayfasına gidin."
            done={!!stepStatus.rates_configured}
            primary={{
              label: "Tarife Yönetimi",
              action: () => navigate("/app/rate-management"),
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
              action: () => navigate("/app/users"),
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
            onClick={() => setStepIdx((i) => Math.max(0, i - 1))}
          >
            <ChevronLeft className="w-4 h-4 mr-1" /> Geri
          </Button>

          <Button variant="ghost" onClick={handleSkip}>
            <SkipForward className="w-4 h-4 mr-1" /> Şimdilik Atla
          </Button>

          <Button
            variant="outline"
            disabled={stepIdx === STEP_DEFS.length - 1}
            onClick={() => setStepIdx((i) => Math.min(STEP_DEFS.length - 1, i + 1))}
          >
            Sonraki <ChevronRight className="w-4 h-4 ml-1" />
          </Button>
        </div>
      </div>
    </Layout>
  );
}

function ActionStep({ icon: Icon, title, description, done, primary }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Icon className="w-5 h-5 text-violet-600" /> {title}
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
