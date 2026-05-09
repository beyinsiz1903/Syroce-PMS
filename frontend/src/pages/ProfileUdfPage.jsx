import { useEffect, useState, useCallback } from "react";
import api from "@/api/axios";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { Settings2, Plus, RefreshCw, Trash2, Save, Search, Loader2 } from "lucide-react";
import { useTranslation } from 'react-i18next';

/**
 * Opera #12 — Profile UDF (User-Defined Fields).
 * Misafir profilleri için tenant'a özel ek alanlar:
 *   - Tanımlar: key/label/type/required/options/section
 *   - Değer yönetimi: misafir ara → değerleri gir/güncelle
 */

const TYPES = [
  { v: "text", l: "Metin" },
  { v: "number", l: "Sayı" },
  { v: "date", l: "Tarih" },
  { v: "boolean", l: "Evet/Hayır" },
  { v: "select", l: "Tek Seçim" },
  { v: "multiselect", l: "Çoklu Seçim" },
];

export default function ProfileUdfPage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [tab, setTab] = useState("definitions");
  const [defs, setDefs] = useState([]);
  const [loading, setLoading] = useState(false);

  const [defForm, setDefForm] = useState({
    key: "", label: "", type: "text", required: false,
    options: "", section: "", order: 100, help_text: "",
  });
  const [submittingDef, setSubmittingDef] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);

  // Misafir UDF değer yönetimi
  const [searchQ, setSearchQ] = useState("");
  const [guests, setGuests] = useState([]);
  const [searching, setSearching] = useState(false);
  const [selectedGuest, setSelectedGuest] = useState(null);
  const [values, setValues] = useState({});
  const [savingValues, setSavingValues] = useState(false);

  const handleErr = useCallback((title, e) => {
    toast({
      title,
      description: e?.response?.data?.detail || e.message,
      variant: "destructive",
    });
  }, [toast]);

  const loadDefs = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/api/profile-udf/definitions");
      setDefs(r.data || []);
    } catch (e) { handleErr("Tanımlar yüklenemedi", e); }
    finally { setLoading(false); }
  }, [handleErr]);

  useEffect(() => { loadDefs(); }, [loadDefs]);

  const addDef = async (e) => {
    e.preventDefault();
    setSubmittingDef(true);
    try {
      await api.post("/api/profile-udf/definitions", {
        ...defForm,
        order: Number(defForm.order) || 100,
        options: defForm.options.split(",").map((s) => s.trim()).filter(Boolean),
        help_text: defForm.help_text || null,
        section: defForm.section || null,
      });
      toast({ title: "Tanım eklendi" });
      setDefForm({
        key: "", label: "", type: "text", required: false,
        options: "", section: "", order: 100, help_text: "",
      });
      loadDefs();
    } catch (e) { handleErr("Eklenemedi", e); }
    finally { setSubmittingDef(false); }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await api.delete(`/api/profile-udf/definitions/${deleteTarget.id}`);
      toast({ title: "Tanım silindi" });
      setDeleteTarget(null);
      loadDefs();
    } catch (e) { handleErr("Silinemedi", e); }
  };

  // Misafir ara — guests endpoint
  const searchGuests = async () => {
    if (!searchQ.trim()) return;
    setSearching(true);
    try {
      // Var olan guests endpoint'i kullan; basit q parametresi
      const r = await api.get("/api/guests", { params: { search: searchQ, limit: 20 } });
      const list = Array.isArray(r.data) ? r.data : r.data?.items || r.data?.guests || [];
      setGuests(list.slice(0, 20));
    } catch (e) { handleErr("Misafir araması başarısız", e); setGuests([]); }
    finally { setSearching(false); }
  };

  const loadGuestUdf = async (g) => {
    try {
      const id = g.id || g._id;
      const r = await api.get(`/api/profile-udf/guests/${id}`);
      setSelectedGuest({ id, name: r.data.guest_name });
      setValues(r.data.values || {});
    } catch (e) { handleErr("Misafir UDF yüklenemedi", e); }
  };

  const saveValues = async () => {
    if (!selectedGuest) return;
    setSavingValues(true);
    try {
      await api.put(`/api/profile-udf/guests/${selectedGuest.id}`, { values });
      toast({ title: "UDF değerleri kaydedildi" });
    } catch (e) { handleErr("Kaydedilemedi", e); }
    finally { setSavingValues(false); }
  };

  const renderInput = (def) => {
    const v = values[def.key];
    const set = (val) => setValues({ ...values, [def.key]: val });
    switch (def.type) {
      case "number":
        return (
          <Input type="number" value={v ?? ""} onChange={(e) => set(e.target.value)}
            data-testid={`udf-input-${def.key}`} />
        );
      case "date":
        return (
          <Input type="date" value={v ?? ""} onChange={(e) => set(e.target.value)}
            data-testid={`udf-input-${def.key}`} />
        );
      case "boolean":
        return (
          <div className="flex items-center gap-2 h-10">
            <Switch checked={!!v} onCheckedChange={set} data-testid={`udf-input-${def.key}`} />
            <span className="text-sm text-muted-foreground">{v ? "Evet" : "Hayır"}</span>
          </div>
        );
      case "select":
        return (
          <Select value={v ?? ""} onValueChange={set}>
            <SelectTrigger data-testid={`udf-input-${def.key}`}>
              <SelectValue placeholder={t('cm.pages_ProfileUdfPage.seciniz')} />
            </SelectTrigger>
            <SelectContent>
              {def.options.map((o) => (
                <SelectItem key={o} value={o}>{o}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        );
      case "multiselect": {
        const arr = Array.isArray(v) ? v : [];
        return (
          <div className="flex flex-wrap gap-2 p-2 border rounded">
            {def.options.map((o) => {
              const on = arr.includes(o);
              return (
                <Button
                  key={o}
                  type="button"
                  size="sm"
                  variant={on ? "default" : "outline"}
                  onClick={() => set(on ? arr.filter((x) => x !== o) : [...arr, o])}
                >
                  {o}
                </Button>
              );
            })}
          </div>
        );
      }
      default:
        return (
          <Input value={v ?? ""} onChange={(e) => set(e.target.value)}
            data-testid={`udf-input-${def.key}`} />
        );
    }
  };

  const sections = Array.from(new Set(defs.map((d) => d.section || "Genel")));

  return (
    <div className="container mx-auto p-6 space-y-4 max-w-7xl">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-2xl font-semibold flex items-center gap-2">
            <Settings2 className="h-6 w-6" /> {t('cm.pages_ProfileUdfPage.profil_ozel_alanlari_udf')}
          </h2>
          <p className="text-sm text-muted-foreground">
            {t('cm.pages_ProfileUdfPage.misafir_profillerine_tenant_a_ozel_ek_al')}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={loadDefs} disabled={loading} data-testid="button-udf-refresh">
          <RefreshCw className={`h-4 w-4 mr-1 ${loading ? "animate-spin" : ""}`} /> {t('cm.pages_ProfileUdfPage.yenile')}
        </Button>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="definitions" data-testid="tab-udf-defs">{t('cm.pages_ProfileUdfPage.tanimlar')}</TabsTrigger>
          <TabsTrigger value="values" data-testid="tab-udf-values">{t('cm.pages_ProfileUdfPage.misafir_degerleri')}</TabsTrigger>
        </TabsList>

        <TabsContent value="definitions">
          <Card>
            <CardHeader>
              <CardTitle>{t('cm.pages_ProfileUdfPage.udf_tanimlari')}</CardTitle>
              <CardDescription>
                {t('cm.pages_ProfileUdfPage.misafir_profilinde_gorunecek_ek_alanlari')} <code>ozel_diyet</code>).
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={addDef} className="grid grid-cols-1 md:grid-cols-6 gap-2 items-end">
                <div>
                  <Label>Anahtar</Label>
                  <Input
                    value={defForm.key}
                    onChange={(e) => setDefForm({ ...defForm, key: e.target.value.toLowerCase() })}
                    placeholder="ornek_alan"
                    pattern="[a-z][a-z0-9_]*"
                    required
                    data-testid="input-udf-key"
                  />
                </div>
                <div>
                  <Label>Etiket</Label>
                  <Input
                    value={defForm.label}
                    onChange={(e) => setDefForm({ ...defForm, label: e.target.value })}
                    required
                    data-testid="input-udf-label"
                  />
                </div>
                <div>
                  <Label>Tip</Label>
                  <Select
                    value={defForm.type}
                    onValueChange={(v) => setDefForm({ ...defForm, type: v })}
                  >
                    <SelectTrigger data-testid="select-udf-type"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {TYPES.map((t) => <SelectItem key={t.v} value={t.v}>{t.l}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>{t('cm.pages_ProfileUdfPage.bolum')}</Label>
                  <Input
                    value={defForm.section}
                    onChange={(e) => setDefForm({ ...defForm, section: e.target.value })}
                    placeholder="Tercihler"
                  />
                </div>
                <div>
                  <Label>{t('cm.pages_ProfileUdfPage.sira')}</Label>
                  <Input
                    type="number"
                    value={defForm.order}
                    onChange={(e) => setDefForm({ ...defForm, order: e.target.value })}
                  />
                </div>
                <div className="flex items-center gap-2 h-10">
                  <Switch
                    checked={defForm.required}
                    onCheckedChange={(c) => setDefForm({ ...defForm, required: c })}
                  />
                  <Label>Zorunlu</Label>
                </div>
                {(defForm.type === "select" || defForm.type === "multiselect") && (
                  <div className="md:col-span-5">
                    <Label>{t('cm.pages_ProfileUdfPage.secenekler_virgullu')}</Label>
                    <Input
                      value={defForm.options}
                      onChange={(e) => setDefForm({ ...defForm, options: e.target.value })}
                      placeholder="vegan, vejeteryan, glutensiz"
                    />
                  </div>
                )}
                <div className="md:col-span-5">
                  <Label>{t('cm.pages_ProfileUdfPage.yardim_metni')}</Label>
                  <Input
                    value={defForm.help_text}
                    onChange={(e) => setDefForm({ ...defForm, help_text: e.target.value })}
                  />
                </div>
                <Button type="submit" disabled={submittingDef} data-testid="button-udf-add">
                  {submittingDef ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Plus className="h-4 w-4 mr-1" />}
                  {t('cm.pages_ProfileUdfPage.ekle')}
                </Button>
              </form>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('cm.pages_ProfileUdfPage.bolum_50198')}</TableHead>
                    <TableHead>Anahtar</TableHead>
                    <TableHead>Etiket</TableHead>
                    <TableHead>Tip</TableHead>
                    <TableHead className="text-center">Zorunlu</TableHead>
                    <TableHead>{t('cm.pages_ProfileUdfPage.secenekler')}</TableHead>
                    <TableHead className="w-[60px]" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {defs.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center text-muted-foreground py-6">
                        {t('cm.pages_ProfileUdfPage.henuz_udf_tanimi_yok')}
                      </TableCell>
                    </TableRow>
                  ) : defs.map((d) => (
                    <TableRow key={d.id}>
                      <TableCell><Badge variant="secondary">{d.section || "Genel"}</Badge></TableCell>
                      <TableCell><code className="text-xs">{d.key}</code></TableCell>
                      <TableCell className="font-medium">{d.label}</TableCell>
                      <TableCell>{TYPES.find((t) => t.v === d.type)?.l || d.type}</TableCell>
                      <TableCell className="text-center">{d.required ? "" : ""}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {(d.options || []).join(", ")}
                      </TableCell>
                      <TableCell>
                        <Button size="sm" variant="ghost"
                          onClick={() => setDeleteTarget({ id: d.id, label: d.label })}>
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="values">
          <Card>
            <CardHeader>
              <CardTitle>{t('cm.pages_ProfileUdfPage.misafir_udf_degerleri')}</CardTitle>
              <CardDescription>
                {t('cm.pages_ProfileUdfPage.misafir_ara_profile_ina_ozel_alan_degerl')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2 items-end">
                <div className="flex-1">
                  <Label>{t('cm.pages_ProfileUdfPage.misafir_ara_ad_email_telefon')}</Label>
                  <Input
                    value={searchQ}
                    onChange={(e) => setSearchQ(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && searchGuests()}
                    placeholder="Ahmet, info@..., 0532..."
                    data-testid="input-udf-search"
                  />
                </div>
                <Button onClick={searchGuests} disabled={searching} data-testid="button-udf-search">
                  {searching ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Search className="h-4 w-4 mr-1" />}
                  {t('cm.pages_ProfileUdfPage.ara')}
                </Button>
              </div>

              {guests.length > 0 && (
                <div className="border rounded max-h-48 overflow-y-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Ad</TableHead>
                        <TableHead>Email</TableHead>
                        <TableHead>Telefon</TableHead>
                        <TableHead className="w-[80px]" />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {guests.map((g) => (
                        <TableRow key={g.id || g._id}>
                          <TableCell>{g.full_name || g.name || "—"}</TableCell>
                          <TableCell className="text-xs">{g.email || "—"}</TableCell>
                          <TableCell className="text-xs">{g.phone || "—"}</TableCell>
                          <TableCell>
                            <Button size="sm" variant="outline" onClick={() => loadGuestUdf(g)}>
                              {t('cm.pages_ProfileUdfPage.sec')}
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}

              {selectedGuest && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">{selectedGuest.name}</CardTitle>
                    <CardDescription>{defs.length} {t('cm.pages_ProfileUdfPage.tanimli_udf_alani')}</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {defs.length === 0 ? (
                      <div className="text-center text-muted-foreground py-4">
                        {t('cm.pages_ProfileUdfPage.once_tanimlar_sekmesinden_alan_ekleyin')}
                      </div>
                    ) : (
                      sections.map((sec) => (
                        <div key={sec}>
                          <div className="text-xs font-semibold text-muted-foreground mb-2 uppercase">{sec}</div>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            {defs.filter((d) => (d.section || "Genel") === sec).map((d) => (
                              <div key={d.id}>
                                <Label>
                                  {d.label}
                                  {d.required && <span className="text-red-500 ml-1">*</span>}
                                </Label>
                                {renderInput(d)}
                                {d.help_text && (
                                  <p className="text-xs text-muted-foreground mt-1">{d.help_text}</p>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      ))
                    )}
                    {defs.length > 0 && (
                      <Button onClick={saveValues} disabled={savingValues} data-testid="button-udf-save">
                        {savingValues ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}
                        {t('cm.pages_ProfileUdfPage.kaydet')}
                      </Button>
                    )}
                  </CardContent>
                </Card>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('cm.pages_ProfileUdfPage.tanimi_sil')}</DialogTitle>
            <DialogDescription>
              "{deleteTarget?.label}{t('cm.pages_ProfileUdfPage.tanimi_pasife_alinacak_misafirlerdeki_me')}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>{t('cm.pages_ProfileUdfPage.vazgec')}</Button>
            <Button variant="destructive" onClick={confirmDelete} data-testid="button-udf-confirm-delete">
              {t('cm.pages_ProfileUdfPage.sil')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
