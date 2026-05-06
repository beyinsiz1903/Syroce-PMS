import React, { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import Layout from "@/components/Layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { confirmDialog } from '@/lib/dialogs';
import {
  KeyRound, Shield, Eye, EyeOff, RefreshCw, Trash2, ExternalLink,
  CheckCircle2, XCircle, Save, Lock, Cloud, Bot, Mail, Activity, Database, Plug,
} from "lucide-react";

const CATEGORY_META = {
  ai:             { label: "AI & LLM",            icon: Bot,      color: "from-purple-500/10 to-indigo-500/10", border: "border-purple-500/30" },
  email:          { label: "E-posta",             icon: Mail,     color: "from-blue-500/10 to-cyan-500/10",     border: "border-blue-500/30" },
  monitoring:    { label: "İzleme & Uyarı",      icon: Activity, color: "from-amber-500/10 to-orange-500/10",  border: "border-amber-500/30" },
  infrastructure:{ label: "Altyapı",              icon: Database, color: "from-slate-500/10 to-slate-700/10",   border: "border-slate-500/30" },
  integrations:  { label: "3. Parti Servisler",   icon: Plug,     color: "from-emerald-500/10 to-teal-500/10",  border: "border-emerald-500/30" },
  aws:           { label: "AWS & KMS",            icon: Cloud,    color: "from-orange-500/10 to-red-500/10",    border: "border-orange-500/30" },
  capx:          { label: "CapX B2B Network",     icon: Plug,     color: "from-emerald-500/10 to-green-500/10", border: "border-emerald-500/30" },
};

export default function IntegrationCredentials({ user, tenant, onLogout }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [inputs, setInputs] = useState({});
  const [revealed, setRevealed] = useState({});
  const [saving, setSaving] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get("/admin/integration-credentials/catalog");
      setItems(data.items || []);
    } catch (e) {
      toast.error("Anahtar listesi yüklenemedi: " + (e?.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async (key) => {
    const value = (inputs[key] || "").trim();
    if (!value) {
      toast.error("Değer boş olamaz");
      return;
    }
    setSaving((s) => ({ ...s, [key]: true }));
    try {
      await axios.post("/admin/integration-credentials/upsert", { key, value });
      toast.success(`${key} kaydedildi ve aktif`);
      setInputs((s) => ({ ...s, [key]: "" }));
      setRevealed((s) => ({ ...s, [key]: false }));
      await load();
    } catch (e) {
      toast.error("Kaydedilemedi: " + (e?.response?.data?.detail || e.message));
    } finally {
      setSaving((s) => ({ ...s, [key]: false }));
    }
  };

  const remove = async (key) => {
    if (!await confirmDialog({ message: `${key} değerini silmek istediğine emin misin? Servis ilgili özelliği kullanamayacak.`, variant: 'danger' })) return;
    try {
      await axios.delete(`/admin/integration-credentials/${encodeURIComponent(key)}`);
      toast.success(`${key} silindi`);
      await load();
    } catch (e) {
      toast.error("Silinemedi: " + (e?.response?.data?.detail || e.message));
    }
  };

  const grouped = useMemo(() => {
    const g = {};
    for (const it of items) {
      (g[it.category] ||= []).push(it);
    }
    return g;
  }, [items]);

  const stats = useMemo(() => {
    const total = items.length;
    const set = items.filter((i) => i.is_set).length;
    return { total, set, missing: total - set };
  }, [items]);

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="integration-credentials">
      <div className="max-w-6xl mx-auto p-6 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-3 rounded-xl bg-gradient-to-br from-indigo-500/20 to-purple-500/20 border border-indigo-500/30">
              <KeyRound className="w-6 h-6 text-indigo-400" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold">Entegrasyon Anahtarları</h1>
              <p className="text-sm text-muted-foreground mt-0.5">
                3. parti servis anahtarları — girdiğinde anında çalışmaya başlar, restart gerekmez.
              </p>
            </div>
          </div>
          <Button variant="outline" onClick={load} disabled={loading} data-testid="btn-reload">
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} /> Yenile
          </Button>
        </div>

        {/* Security warning */}
        <Card className="border-amber-300 bg-amber-50">
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <Shield className="w-5 h-5 text-amber-700 mt-0.5" />
              <div className="text-sm text-amber-900">
                <p className="font-semibold text-amber-900">Güvenlik</p>
                <p className="mt-1">
                  Tüm değerler şifreli saklanır ve sadece super admin tarafından düzenlenebilir.
                  Kaydedilen değerler hemen <code className="px-1 py-0.5 rounded bg-amber-100 text-amber-900 font-mono">os.environ</code>&apos;a yansır —
                  backend'in tüm <code className="px-1 py-0.5 rounded bg-amber-100 text-amber-900 font-mono">os.getenv(...)</code> çağırdığı yerler otomatik bu değeri kullanır.
                  Restart, yeniden deploy ya da kod değişikliği gerekmez.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4">
          <Card>
            <CardContent className="pt-6 flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Toplam</p>
                <p className="text-2xl font-semibold">{stats.total}</p>
              </div>
              <KeyRound className="w-8 h-8 text-muted-foreground/40" />
            </CardContent>
          </Card>
          <Card className="border-emerald-500/20 bg-emerald-500/5">
            <CardContent className="pt-6 flex items-center justify-between">
              <div>
                <p className="text-xs text-emerald-400/80">Tanımlı</p>
                <p className="text-2xl font-semibold text-emerald-300">{stats.set}</p>
              </div>
              <CheckCircle2 className="w-8 h-8 text-emerald-500/40" />
            </CardContent>
          </Card>
          <Card className="border-red-500/20 bg-red-500/5">
            <CardContent className="pt-6 flex items-center justify-between">
              <div>
                <p className="text-xs text-red-400/80">Eksik</p>
                <p className="text-2xl font-semibold text-red-300">{stats.missing}</p>
              </div>
              <XCircle className="w-8 h-8 text-red-500/40" />
            </CardContent>
          </Card>
        </div>

        {/* Grouped credentials */}
        {Object.entries(CATEGORY_META).map(([catKey, meta]) => {
          const list = grouped[catKey] || [];
          if (list.length === 0) return null;
          const Icon = meta.icon;
          return (
            <div key={catKey} className="space-y-3">
              <div className={`flex items-center gap-2 p-3 rounded-lg bg-gradient-to-r ${meta.color} border ${meta.border}`}>
                <Icon className="w-5 h-5" />
                <h2 className="text-lg font-medium">{meta.label}</h2>
                <Badge variant="outline" className="ml-auto text-xs">
                  {list.filter((i) => i.is_set).length} / {list.length} dolu
                </Badge>
              </div>

              <div className="grid gap-3">
                {list.map((cred) => (
                  <Card key={cred.key} data-testid={`cred-card-${cred.key}`}>
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <CardTitle className="text-base">{cred.name}</CardTitle>
                            {cred.is_set ? (
                              <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/30 border">
                                <CheckCircle2 className="w-3 h-3 mr-1" /> Tanımlı
                              </Badge>
                            ) : (
                              <Badge className="bg-red-500/10 text-red-400 border-red-500/30 border">
                                <XCircle className="w-3 h-3 mr-1" /> Eksik
                              </Badge>
                            )}
                            {cred.source === "env" && (
                              <Badge variant="outline" className="text-xs">
                                <Lock className="w-3 h-3 mr-1" /> env
                              </Badge>
                            )}
                            {cred.source === "db" && (
                              <Badge variant="outline" className="text-xs">
                                <Database className="w-3 h-3 mr-1" /> kayıtlı
                              </Badge>
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground mt-1">{cred.description}</p>
                          <code className="inline-block mt-2 text-[11px] px-2 py-0.5 rounded bg-slate-800/50 border border-slate-700/50">
                            {cred.key}
                          </code>
                        </div>
                        {cred.doc_url && (
                          <a href={cred.doc_url} target="_blank" rel="noreferrer" className="shrink-0">
                            <Button variant="ghost" size="sm">
                              <ExternalLink className="w-3.5 h-3.5 mr-1" /> Dokümantasyon
                            </Button>
                          </a>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent className="pt-0 space-y-3">
                      {cred.masked_value && (
                        <div className="text-xs text-muted-foreground flex items-center gap-2">
                          <span className="opacity-60">Aktif değer:</span>
                          <code className="px-2 py-0.5 rounded bg-slate-800/60">{cred.masked_value}</code>
                          {cred.updated_at && (
                            <span className="ml-auto opacity-60">
                              {new Date(cred.updated_at).toLocaleString("tr-TR")}
                              {cred.updated_by && ` • ${cred.updated_by}`}
                            </span>
                          )}
                        </div>
                      )}
                      <div className="flex gap-2">
                        <div className="relative flex-1">
                          <Input
                            type={revealed[cred.key] ? "text" : "password"}
                            placeholder={cred.is_set ? "Yeni değer gir (mevcut değişecek)" : "Değeri yapıştır"}
                            value={inputs[cred.key] || ""}
                            onChange={(e) => setInputs((s) => ({ ...s, [cred.key]: e.target.value }))}
                            className="pr-10 font-mono text-sm"
                            data-testid={`input-${cred.key}`}
                          />
                          <button
                            type="button"
                            onClick={() => setRevealed((s) => ({ ...s, [cred.key]: !s[cred.key] }))}
                            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                            tabIndex={-1}
                          >
                            {revealed[cred.key] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                          </button>
                        </div>
                        <Button
                          onClick={() => save(cred.key)}
                          disabled={saving[cred.key] || !inputs[cred.key]}
                          data-testid={`btn-save-${cred.key}`}
                        >
                          {saving[cred.key] ? (
                            <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
                          ) : (
                            <Save className="w-4 h-4 mr-1" />
                          )}
                          Kaydet
                        </Button>
                        {cred.is_set && cred.source === "db" && (
                          <Button variant="outline" onClick={() => remove(cred.key)} data-testid={`btn-delete-${cred.key}`}>
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          );
        })}

        {items.length === 0 && !loading && (
          <Card>
            <CardContent className="py-12 text-center text-sm text-muted-foreground">
              Kayıt bulunamadı. Super admin olarak oturum açtığınızdan emin olun.
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
}
