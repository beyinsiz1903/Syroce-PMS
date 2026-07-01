import React, { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { toast } from "sonner";
import { Loader2, Phone, Plus, Trash2, Save, RefreshCw, X, Info } from "lucide-react";

import { confirmDialog } from "@/lib/dialogs";

function isSuperAdmin(user) {
  return user?.role === "super_admin" || (user?.roles || []).includes("super_admin");
}

const EMPTY_FORM = { id: null, to_number: "", agent_identity: "", label: "", tenant_id: "" };

export default function VoiceNumberMapping({ user }) {
  const superAdmin = isSuperAdmin(user);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [items, setItems] = useState([]);
  const [tenants, setTenants] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);

  const editing = Boolean(form.id);

  const tenantName = useMemo(() => {
    const map = {};
    for (const t of tenants) map[t.id] = t.property_name || t.name || t.id;
    return map;
  }, [tenants]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get("/contact-center/voice/numbers");
      setItems(r.data?.items || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Eşlemeler yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadTenants = useCallback(async () => {
    if (!superAdmin) return;
    try {
      const r = await axios.get("/admin/tenants");
      const list = r.data?.tenants || r.data?.items || r.data || [];
      setTenants(Array.isArray(list) ? list : []);
    } catch {
      // tenant listesi alınamazsa super_admin yine de elle id girebilir
    }
  }, [superAdmin]);

  useEffect(() => {
    load();
    loadTenants();
  }, [load, loadTenants]);

  const resetForm = () => setForm(EMPTY_FORM);

  const startEdit = (it) => {
    setForm({
      id: it.id,
      to_number: it.to_number || "",
      agent_identity: it.agent_identity || "",
      label: it.label || "",
      tenant_id: it.tenant_id || "",
    });
  };

  const save = async () => {
    const to_number = form.to_number.trim();
    if (!to_number) {
      toast.error("Numara zorunlu");
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        const payload = {
          to_number,
          agent_identity: form.agent_identity.trim() || null,
          label: form.label.trim() || null,
        };
        await axios.put(`/contact-center/voice/numbers/${form.id}`, payload);
        toast.success("Eşleme güncellendi");
      } else {
        const payload = {
          to_number,
          agent_identity: form.agent_identity.trim() || null,
          label: form.label.trim() || null,
        };
        if (superAdmin && form.tenant_id.trim()) payload.tenant_id = form.tenant_id.trim();
        await axios.post("/contact-center/voice/numbers", payload);
        toast.success("Eşleme eklendi");
      }
      resetForm();
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Kaydetme hatası");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (it) => {
    const ok = await confirmDialog({
      title: "Eşlemeyi sil",
      message: `${it.to_number} numarasının eşlemesi silinsin mi? Bu numaraya gelen çağrılar artık yönlendirilemez.`,
      confirmText: "Sil",
      cancelText: "Vazgeç",
      variant: "danger",
    });
    if (!ok) return;
    try {
      await axios.delete(`/contact-center/voice/numbers/${it.id}`);
      toast.success("Eşleme silindi");
      if (form.id === it.id) resetForm();
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Silme hatası");
    }
  };

  return (
    <div className="max-w-5xl mx-auto p-4 space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <Phone className="h-6 w-6" /> Ses Numaraları
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Gelen çağrıların doğru otele ve ajana yönlenmesi için numara eşlemelerini yönetin.
          </p>
        </div>
        <Button variant="outline" onClick={load} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} /> Yenile
        </Button>
      </div>

      <Alert>
        <Info className="h-4 w-4" />
        <AlertTitle>Numara formatı</AlertTitle>
        <AlertDescription>
          Numaralar E.164 biçiminde girilmelidir (örn. +905321234567). Ajan kimliği
          opsiyoneldir; girilirse ilgili otel kapsamında olmalıdır.
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle>{editing ? "Eşlemeyi düzenle" : "Yeni eşleme ekle"}</CardTitle>
          <CardDescription>
            {editing
              ? "Seçili numaranın otel/ajan eşlemesini güncelleyin."
              : "Otelinizin gelen hattı için yeni bir eşleme oluşturun."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="to_number">Aranan numara (E.164)</Label>
              <Input
                id="to_number"
                placeholder="+905321234567"
                value={form.to_number}
                onChange={(e) => setForm((f) => ({ ...f, to_number: e.target.value }))}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="label">Etiket (opsiyonel)</Label>
              <Input
                id="label"
                placeholder="Resepsiyon hattı"
                value={form.label}
                onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="agent_identity">Ajan kimliği (opsiyonel)</Label>
              <Input
                id="agent_identity"
                placeholder="<tenant_id>:<kullanıcı>"
                value={form.agent_identity}
                onChange={(e) => setForm((f) => ({ ...f, agent_identity: e.target.value }))}
              />
            </div>
            {superAdmin && !editing && (
              <div className="space-y-1.5">
                <Label htmlFor="tenant_id">Otel</Label>
                {tenants.length > 0 ? (
                  <Select
                    value={form.tenant_id}
                    onValueChange={(v) => setForm((f) => ({ ...f, tenant_id: v }))}
                  >
                    <SelectTrigger id="tenant_id">
                      <SelectValue placeholder="Otel seçin (boş = kendi oteliniz)" />
                    </SelectTrigger>
                    <SelectContent>
                      {tenants.map((t) => (
                        <SelectItem key={t.id} value={t.id}>
                          {t.property_name || t.name || t.id}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input
                    id="tenant_id"
                    placeholder="tenant_id (boş = kendi oteliniz)"
                    value={form.tenant_id}
                    onChange={(e) => setForm((f) => ({ ...f, tenant_id: e.target.value }))}
                  />
                )}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={save} disabled={saving}>
              {saving ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : editing ? (
                <Save className="h-4 w-4 mr-2" />
              ) : (
                <Plus className="h-4 w-4 mr-2" />
              )}
              {editing ? "Güncelle" : "Ekle"}
            </Button>
            {editing && (
              <Button variant="ghost" onClick={resetForm} disabled={saving}>
                <X className="h-4 w-4 mr-2" /> Vazgeç
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Mevcut eşlemeler</CardTitle>
          <CardDescription>
            {loading ? "Yükleniyor..." : `${items.length} eşleme`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-10 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin mr-2" /> Yükleniyor...
            </div>
          ) : items.length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">
              Henüz eşleme yok. Yukarıdan ilk eşlemeyi ekleyin.
            </p>
          ) : (
            <div className="divide-y">
              {items.map((it) => (
                <div
                  key={it.id}
                  className="flex items-center justify-between gap-4 py-3"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium">{it.to_number}</span>
                      {it.label && <Badge variant="secondary">{it.label}</Badge>}
                      {superAdmin && it.tenant_id && (
                        <Badge variant="outline">
                          {tenantName[it.tenant_id] || it.tenant_id}
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 truncate">
                      Ajan: {it.agent_identity || "— (varsayılan yönlendirme)"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Button variant="outline" size="sm" onClick={() => startEdit(it)}>
                      Düzenle
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => remove(it)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
