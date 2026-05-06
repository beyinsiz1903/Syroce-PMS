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

const AUTO_PROVIDER = "__auto__";
const PROVIDERS = [
  { id: AUTO_PROVIDER, name: "Otomatik (Akıllı)", desc: "Görüntü kalitesine göre seçilir" },
  { id: "gpt-4o", name: "GPT-4o", desc: "En yüksek doğruluk (OpenAI)" },
  { id: "gpt-4o-mini", name: "GPT-4o Mini", desc: "Hızlı ve ucuz (OpenAI)" },
  { id: "gemini-flash", name: "Gemini 2.0 Flash", desc: "Google alternatifi" },
  { id: "tesseract", name: "Tesseract OCR", desc: "Offline, ücretsiz, düşük doğruluk" },
];

export default function QuickIdSettings({ user, tenant, onLogout }) {
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
    if (cfg) return <Badge variant="default" className="bg-emerald-600">Yapılandırılmış</Badge>;
    if (env) return <Badge variant="secondary">Ortam değişkeninden</Badge>;
    return <Badge variant="outline" className="text-amber-600 border-amber-600">Yapılandırılmamış</Badge>;
  };

  return (
    <>
      <div className="max-w-4xl mx-auto p-6 space-y-6">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <ScanLine className="w-8 h-8" /> Kimlik Tarama (Quick-ID) Ayarları
          </h1>
          <p className="text-gray-500 mt-2">
            OCR sağlayıcı API anahtarlarını yönetin. Anahtarlar şifrelenmiş olarak veritabanında saklanır.
          </p>
        </div>

        {settings.demo_mode && (
          <Alert className="border-amber-300 bg-amber-50">
            <ShieldAlert className="w-4 h-4 text-amber-600" />
            <AlertTitle>Demo modu aktif</AlertTitle>
            <AlertDescription>
              Hiçbir API anahtarı yapılandırılmadığı için tarama sahte demo veri döndürüyor.
              Gerçek tarama için aşağıya OpenAI veya Gemini anahtarınızı girin.
            </AlertDescription>
          </Alert>
        )}

        {!settings.service_key_configured && (
          <Alert variant="destructive">
            <XCircle className="w-4 h-4" />
            <AlertTitle>Servis anahtarı eksik</AlertTitle>
            <AlertDescription>
              QUICKID_SERVICE_KEY ortam değişkeni tanımlı değil. Sunucu yöneticisiyle iletişime geçin.
            </AlertDescription>
          </Alert>
        )}

        {settings.transport_safe === false && (
          <Alert variant="destructive">
            <ShieldAlert className="w-4 h-4" />
            <AlertTitle>Güvensiz iletim</AlertTitle>
            <AlertDescription>
              Quick-ID uzak bir HTTP adresine yapılandırılmış. API anahtarları güvenlik nedeniyle
              header üzerinden iletilmeyecek. Loopback (localhost) veya HTTPS gerekiyor.
            </AlertDescription>
          </Alert>
        )}

        {settings.encryption_key_source === "jwt_secret" && (
          <Alert className="border-amber-300 bg-amber-50">
            <ShieldAlert className="w-4 h-4 text-amber-600" />
            <AlertTitle>Adanmış şifreleme anahtarı önerilir</AlertTitle>
            <AlertDescription>
              Şu anda anahtarlar JWT_SECRET'tan türetilen anahtarla şifreleniyor. JWT secret döndürüldüğünde
              kayıtlı API anahtarları okunamaz hale gelir. Üretim için <code>QUICKID_SETTINGS_ENC_KEY</code>
              ayarlamanız önerilir.
            </AlertDescription>
          </Alert>
        )}

        {(settings.openai.decrypt_failed || settings.gemini.decrypt_failed) && (
          <Alert variant="destructive">
            <XCircle className="w-4 h-4" />
            <AlertTitle>Şifre çözme başarısız</AlertTitle>
            <AlertDescription>
              Kayıtlı bir veya daha fazla anahtar mevcut şifreleme anahtarıyla okunamadı.
              Eski anahtarınız varsa <code>QUICKID_SETTINGS_ENC_KEY_OLD</code> olarak ekleyip
              yeniden kaydedin; yoksa anahtarları silip tekrar girin.
            </AlertDescription>
          </Alert>
        )}

        {/* OpenAI */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <KeyRound className="w-5 h-5" /> OpenAI API Anahtarı
                </CardTitle>
                <CardDescription>GPT-4o ve GPT-4o-mini için kullanılır</CardDescription>
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
              <Label>Yeni anahtar (boş bırakırsanız değişmez)</Label>
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
                Anahtarınızı <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer" className="text-blue-600 underline">platform.openai.com</a> üzerinden alabilirsiniz.
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
                  <KeyRound className="w-5 h-5" /> Google Gemini API Anahtarı
                </CardTitle>
                <CardDescription>Gemini 2.0 Flash için kullanılır</CardDescription>
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
              <Label>Yeni anahtar (boş bırakırsanız değişmez)</Label>
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
                Anahtarınızı <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer" className="text-blue-600 underline">aistudio.google.com</a> üzerinden alabilirsiniz.
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Tercih edilen sağlayıcı */}
        <Card>
          <CardHeader>
            <CardTitle>Tercih Edilen Sağlayıcı</CardTitle>
            <CardDescription>Kullanıcı belirtmezse bu sağlayıcı kullanılır</CardDescription>
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
              <CardTitle>Bağlantı Testi Sonuçları</CardTitle>
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
            Kaydet
          </Button>
          <Button variant="outline" onClick={runTest} disabled={testing}>
            {testing ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
            Bağlantıyı Test Et
          </Button>
        </div>

        {settings.updated_at && (
          <p className="text-xs text-gray-400 text-center">
            Son güncelleme: {new Date(settings.updated_at).toLocaleString("tr-TR")} • {settings.updated_by}
          </p>
        )}
      </div>
    </>
  );
}
