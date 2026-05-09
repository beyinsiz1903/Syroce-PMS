import React, { useEffect, useState } from "react";
import axios from "axios";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { toast } from "sonner";
import { Loader2, Save, KeyRound, Eye, EyeOff, CheckCircle2, XCircle, ShieldAlert, ScanLine } from "lucide-react";
import { useTranslation } from 'react-i18next';

const AUTO_PROVIDER = "__auto__";
const PROVIDERS = [
  { id: AUTO_PROVIDER, name: "Otomatik (Akıllı)", desc: "Görüntü kalitesine göre seçilir" },
  { id: "gpt-4o", name: "GPT-4o", desc: "En yüksek doğruluk (OpenAI)" },
  { id: "gpt-4o-mini", name: "GPT-4o Mini", desc: "Hızlı ve ucuz (OpenAI)" },
  { id: "gemini-flash", name: "Gemini 2.0 Flash", desc: "Google alternatifi" },
  { id: "tesseract", name: "Tesseract OCR", desc: "Offline, ücretsiz, düşük doğruluk" },
];

export default function QuickIdSettings({ user, tenant, onLogout }) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [settings, setSettings] = useState(null);
  const [openaiKey, setOpenaiKey] = useState("");
  const [geminiKey, setGeminiKey] = useState("");
  const [showOpenai, setShowOpenai] = useState(false);
  const [showGemini, setShowGemini] = useState(false);
  const [provider, setProvider] = useState(AUTO_PROVIDER);
  const [testResults, setTestResults] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get("/quick-id/settings");
      setSettings(r.data);
      setProvider(r.data.preferred_provider || AUTO_PROVIDER);
    } catch (e) {
      const msg = e.response?.data?.detail || e.message;
      toast.error(`Ayarlar yüklenemedi: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const save = async (clearOpenai = false, clearGemini = false) => {
    setSaving(true);
    try {
      const payload = { preferred_provider: provider === AUTO_PROVIDER ? "" : provider };
      if (clearOpenai) payload.openai_api_key = "";
      else if (openaiKey.trim()) payload.openai_api_key = openaiKey.trim();
      if (clearGemini) payload.gemini_api_key = "";
      else if (geminiKey.trim()) payload.gemini_api_key = geminiKey.trim();

      const r = await axios.put("/quick-id/settings", payload);
      setSettings(r.data);
      setOpenaiKey("");
      setGeminiKey("");
      toast.success("Ayarlar kaydedildi");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Kaydetme hatası");
    } finally {
      setSaving(false);
    }
  };

  const runTest = async () => {
    setTesting(true);
    setTestResults(null);
    try {
      const r = await axios.post("/quick-id/settings/test");
      setTestResults(r.data.results);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Test başarısız");
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <>
        <div className="flex items-center justify-center min-h-[60vh]">
          <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
        </div>
      </>
    );
  }

  if (!settings) return null;

  const StatusBadge = ({ cfg, env }) => {
    if (cfg) return <Badge variant="default" className="bg-emerald-600">{t('cm.pages_admin_QuickIdSettings.yapilandirilmis')}</Badge>;
    if (env) return <Badge variant="secondary">{t('cm.pages_admin_QuickIdSettings.ortam_degiskeninden')}</Badge>;
    return <Badge variant="outline" className="text-amber-600 border-amber-600">{t('cm.pages_admin_QuickIdSettings.yapilandirilmamis')}</Badge>;
  };

  return (
    <>
      <div className="max-w-4xl mx-auto p-6 space-y-6">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <ScanLine className="w-8 h-8" /> {t('cm.pages_admin_QuickIdSettings.kimlik_tarama_quick_id_ayarlari')}
          </h1>
          <p className="text-gray-500 mt-2">
            {t('cm.pages_admin_QuickIdSettings.ocr_saglayici_api_anahtarlarini_yonetin_')}
          </p>
        </div>

        {settings.demo_mode && (
          <Alert className="border-amber-300 bg-amber-50">
            <ShieldAlert className="w-4 h-4 text-amber-600" />
            <AlertTitle>Demo modu aktif</AlertTitle>
            <AlertDescription>
              {t('cm.pages_admin_QuickIdSettings.hicbir_api_anahtari_yapilandirilmadigi_i')}
            </AlertDescription>
          </Alert>
        )}

        {!settings.service_key_configured && (
          <Alert variant="destructive">
            <XCircle className="w-4 h-4" />
            <AlertTitle>{t('cm.pages_admin_QuickIdSettings.servis_anahtari_eksik')}</AlertTitle>
            <AlertDescription>
              {t('cm.pages_admin_QuickIdSettings.quickid_service_key_ortam_degiskeni_tani')}
            </AlertDescription>
          </Alert>
        )}

        {settings.transport_safe === false && (
          <Alert variant="destructive">
            <ShieldAlert className="w-4 h-4" />
            <AlertTitle>{t('cm.pages_admin_QuickIdSettings.guvensiz_iletim')}</AlertTitle>
            <AlertDescription>
              {t('cm.pages_admin_QuickIdSettings.quick_id_uzak_bir_http_adresine_yapiland')}
            </AlertDescription>
          </Alert>
        )}

        {settings.encryption_key_source === "jwt_secret" && (
          <Alert className="border-amber-300 bg-amber-50">
            <ShieldAlert className="w-4 h-4 text-amber-600" />
            <AlertTitle>{t('cm.pages_admin_QuickIdSettings.adanmis_sifreleme_anahtari_onerilir')}</AlertTitle>
            <AlertDescription>
              {t('cm.pages_admin_QuickIdSettings.su_anda_anahtarlar_jwt_secret_tan_tureti')} <code>QUICKID_SETTINGS_ENC_KEY</code>
              {t('cm.pages_admin_QuickIdSettings.ayarlamaniz_onerilir')}
            </AlertDescription>
          </Alert>
        )}

        {(settings.openai.decrypt_failed || settings.gemini.decrypt_failed) && (
          <Alert variant="destructive">
            <XCircle className="w-4 h-4" />
            <AlertTitle>{t('cm.pages_admin_QuickIdSettings.sifre_cozme_basarisiz')}</AlertTitle>
            <AlertDescription>
              {t('cm.pages_admin_QuickIdSettings.kayitli_bir_veya_daha_fazla_anahtar_mevc')} <code>QUICKID_SETTINGS_ENC_KEY_OLD</code> {t('cm.pages_admin_QuickIdSettings.olarak_ekleyip_yeniden_kaydedin_yoksa_an')}
            </AlertDescription>
          </Alert>
        )}

        {/* OpenAI */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <KeyRound className="w-5 h-5" /> {t('cm.pages_admin_QuickIdSettings.openai_api_anahtari')}
                </CardTitle>
                <CardDescription>{t('cm.pages_admin_QuickIdSettings.gpt_4o_ve_gpt_4o_mini_icin_kullanilir')}</CardDescription>
              </div>
              <StatusBadge cfg={settings.openai.configured} env={settings.openai.env_fallback} />
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {settings.openai.masked && (
              <div className="text-sm text-gray-600">
                Mevcut: <code className="bg-gray-100 px-2 py-1 rounded">{settings.openai.masked}</code>
              </div>
            )}
            <div>
              <Label>{t('cm.pages_admin_QuickIdSettings.yeni_anahtar_bos_birakirsaniz_degismez')}</Label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Input
                    type={showOpenai ? "text" : "password"}
                    value={openaiKey}
                    onChange={(e) => setOpenaiKey(e.target.value)}
                    placeholder="sk-..."
                    autoComplete="off"
                  />
                  <button
                    type="button"
                    onClick={() => setShowOpenai(!showOpenai)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  >
                    {showOpenai ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                {settings.openai.configured && (
                  <Button variant="outline" onClick={() => save(true, false)} disabled={saving}>
                    Temizle
                  </Button>
                )}
              </div>
              <p className="text-xs text-gray-500 mt-1">
                {t('cm.pages_admin_QuickIdSettings.anahtarinizi')} <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer" className="text-blue-600 underline">platform.openai.com</a> {t('cm.pages_admin_QuickIdSettings.uzerinden_alabilirsiniz')}
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Gemini */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <KeyRound className="w-5 h-5" /> {t('cm.pages_admin_QuickIdSettings.google_gemini_api_anahtari')}
                </CardTitle>
                <CardDescription>{t('cm.pages_admin_QuickIdSettings.gemini_2_0_flash_icin_kullanilir')}</CardDescription>
              </div>
              <StatusBadge cfg={settings.gemini.configured} env={settings.gemini.env_fallback} />
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {settings.gemini.masked && (
              <div className="text-sm text-gray-600">
                Mevcut: <code className="bg-gray-100 px-2 py-1 rounded">{settings.gemini.masked}</code>
              </div>
            )}
            <div>
              <Label>{t('cm.pages_admin_QuickIdSettings.yeni_anahtar_bos_birakirsaniz_degismez_bd136')}</Label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Input
                    type={showGemini ? "text" : "password"}
                    value={geminiKey}
                    onChange={(e) => setGeminiKey(e.target.value)}
                    placeholder="AIza..."
                    autoComplete="off"
                  />
                  <button
                    type="button"
                    onClick={() => setShowGemini(!showGemini)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  >
                    {showGemini ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                {settings.gemini.configured && (
                  <Button variant="outline" onClick={() => save(false, true)} disabled={saving}>
                    Temizle
                  </Button>
                )}
              </div>
              <p className="text-xs text-gray-500 mt-1">
                {t('cm.pages_admin_QuickIdSettings.anahtarinizi_d0442')} <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer" className="text-blue-600 underline">aistudio.google.com</a> {t('cm.pages_admin_QuickIdSettings.uzerinden_alabilirsiniz_8b375')}
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Tercih edilen sağlayıcı */}
        <Card>
          <CardHeader>
            <CardTitle>{t('cm.pages_admin_QuickIdSettings.tercih_edilen_saglayici')}</CardTitle>
            <CardDescription>{t('cm.pages_admin_QuickIdSettings.kullanici_belirtmezse_bu_saglayici_kulla')}</CardDescription>
          </CardHeader>
          <CardContent>
            <Select value={provider} onValueChange={setProvider}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {PROVIDERS.map((p) => (
                  <SelectItem key={p.id || "auto"} value={p.id}>
                    <div>
                      <div className="font-medium">{p.name}</div>
                      <div className="text-xs text-gray-500">{p.desc}</div>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </CardContent>
        </Card>

        {/* Test sonuçları */}
        {testResults && (
          <Card>
            <CardHeader>
              <CardTitle>{t('cm.pages_admin_QuickIdSettings.baglanti_testi_sonuclari')}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {Object.entries(testResults).map(([prov, res]) => (
                <div key={prov} className="flex items-center gap-3 p-3 rounded border">
                  {res.ok ? (
                    <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                  ) : (
                    <XCircle className="w-5 h-5 text-red-600" />
                  )}
                  <div className="flex-1">
                    <div className="font-medium capitalize">{prov}</div>
                    <div className="text-xs text-gray-500">{res.detail}</div>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Aksiyon butonları */}
        <div className="flex gap-3 sticky bottom-4 bg-white p-4 border rounded-lg shadow-lg">
          <Button onClick={() => save()} disabled={saving} className="flex-1">
            {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
            {t('cm.pages_admin_QuickIdSettings.kaydet')}
          </Button>
          <Button variant="outline" onClick={runTest} disabled={testing}>
            {testing ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
            {t('cm.pages_admin_QuickIdSettings.baglantiyi_test_et')}
          </Button>
        </div>

        {settings.updated_at && (
          <p className="text-xs text-gray-400 text-center">
            {t('cm.pages_admin_QuickIdSettings.son_guncelleme')} {new Date(settings.updated_at).toLocaleString("tr-TR")} • {settings.updated_by}
          </p>
        )}
      </div>
    </>
  );
}
