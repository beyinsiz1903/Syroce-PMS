import { useEffect, useState, useCallback } from "react";
import api from "@/api/axios";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { Gauge, Plus, RefreshCw, Trash2, Loader2, CheckCircle2, XCircle, Search } from "lucide-react";
import { useTranslation } from 'react-i18next';

/**
 * Opera #10 — Hurdle Rates.
 * - Tarih bazlı minimum kabul edilebilir oranlar
 * - Check aracı: tarih+oda+kanal+teklif → kabul/red
 */

export default function HurdleRatesPage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [tab, setTab] = useState("list");
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(false);

  const [form, setForm] = useState({
    name: "", date_from: "", date_to: "",
    room_type: "", channel: "", min_rate: "", currency: "TRY", note: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const [check, setCheck] = useState({
    date: "", proposed_rate: "", room_type: "", channel: "",
  });
  const [checking, setChecking] = useState(false);
  const [checkResult, setCheckResult] = useState(null);

  const handleErr = useCallback((title, e) => {
    toast({
      title,
      description: e?.response?.data?.detail || e.message,
      variant: "destructive",
    });
  }, [toast]);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/hurdle-rates/");
      setList(r.data || []);
    } catch (e) { handleErr("Liste yüklenemedi", e); }
    finally { setLoading(false); }
  }, [handleErr]);

  useEffect(() => { loadList(); }, [loadList]);

  const addHurdle = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.post("/hurdle-rates/", {
        ...form,
        min_rate: Number(form.min_rate) || 0,
        room_type: form.room_type || null,
        channel: form.channel || null,
        note: form.note || null,
      });
      toast({ title: "Hurdle eklendi" });
      setForm({
        name: "", date_from: "", date_to: "",
        room_type: "", channel: "", min_rate: "", currency: "TRY", note: "",
      });
      loadList();
    } catch (e) { handleErr("Eklenemedi", e); }
    finally { setSubmitting(false); }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await api.delete(`/hurdle-rates/${deleteTarget.id}`);
      toast({ title: "Silindi" });
      setDeleteTarget(null);
      loadList();
    } catch (e) { handleErr("Silinemedi", e); }
  };

  const runCheck = async (e) => {
    e.preventDefault();
    if (!check.date || !check.proposed_rate) return;
    setChecking(true);
    setCheckResult(null);
    try {
      const r = await api.get("/hurdle-rates/check", {
        params: {
          date: check.date,
          proposed_rate: Number(check.proposed_rate),
          room_type: check.room_type || undefined,
          channel: check.channel || undefined,
        },
      });
      setCheckResult(r.data);
    } catch (e) { handleErr("Check başarısız", e); }
    finally { setChecking(false); }
  };

  return (
    <div className="container mx-auto p-6 space-y-4 max-w-7xl">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-2xl font-semibold flex items-center gap-2">
            <Gauge className="h-6 w-6" /> Hurdle Rates
          </h2>
          <p className="text-sm text-muted-foreground">
            {t('cm.pages_HurdleRatesPage.tarih_oda_kanal_bazli_minimum_kabul_edil')}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={loadList} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-1 ${loading ? "animate-spin" : ""}`} /> {t('cm.pages_HurdleRatesPage.yenile')}
        </Button>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="list" data-testid="tab-hurdles-list">{t('cm.pages_HurdleRatesPage.tanimlar')}</TabsTrigger>
          <TabsTrigger value="check" data-testid="tab-hurdles-check">{t('cm.pages_HurdleRatesPage.oran_kontrolu')}</TabsTrigger>
        </TabsList>

        <TabsContent value="list">
          <Card>
            <CardHeader>
              <CardTitle>{t('cm.pages_HurdleRatesPage.hurdle_tanimlari')}</CardTitle>
              <CardDescription>
                {t('cm.pages_HurdleRatesPage.bos_room_type_channel_tum_anlamina_gelir')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={addHurdle} className="grid grid-cols-1 md:grid-cols-6 gap-2 items-end">
                <div className="md:col-span-2">
                  <Label>Ad</Label>
                  <Input
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder={t('cm.pages_HurdleRatesPage.hafta_sonu_min')} required
                    data-testid="input-hurdle-name"
                  />
                </div>
                <div>
                  <Label>{t('cm.pages_HurdleRatesPage.baslangic')}</Label>
                  <Input type="date" value={form.date_from}
                    onChange={(e) => setForm({ ...form, date_from: e.target.value })}
                    required data-testid="input-hurdle-from" />
                </div>
                <div>
                  <Label>{t('cm.pages_HurdleRatesPage.bitis')}</Label>
                  <Input type="date" value={form.date_to}
                    onChange={(e) => setForm({ ...form, date_to: e.target.value })}
                    required data-testid="input-hurdle-to" />
                </div>
                <div>
                  <Label>Min Oran</Label>
                  <Input type="number" step="0.01" min="0"
                    value={form.min_rate}
                    onChange={(e) => setForm({ ...form, min_rate: e.target.value })}
                    required data-testid="input-hurdle-min" />
                </div>
                <div>
                  <Label>Para Birimi</Label>
                  <Input value={form.currency} maxLength={3}
                    onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} />
                </div>
                <div>
                  <Label>{t('cm.pages_HurdleRatesPage.oda_tipi_bos_tum')}</Label>
                  <Input value={form.room_type}
                    onChange={(e) => setForm({ ...form, room_type: e.target.value })}
                    placeholder="standard" />
                </div>
                <div>
                  <Label>{t('cm.pages_HurdleRatesPage.kanal_bos_tum')}</Label>
                  <Input value={form.channel}
                    onChange={(e) => setForm({ ...form, channel: e.target.value })}
                    placeholder="booking.com" />
                </div>
                <div className="md:col-span-3">
                  <Label>Not</Label>
                  <Input value={form.note}
                    onChange={(e) => setForm({ ...form, note: e.target.value })} />
                </div>
                <Button type="submit" disabled={submitting} data-testid="button-hurdle-add">
                  {submitting ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Plus className="h-4 w-4 mr-1" />}
                  {t('cm.pages_HurdleRatesPage.ekle')}
                </Button>
              </form>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ad</TableHead>
                    <TableHead>{t('cm.pages_HurdleRatesPage.tarih_araligi')}</TableHead>
                    <TableHead>{t('cm.pages_HurdleRatesPage.oda_tipi')}</TableHead>
                    <TableHead>Kanal</TableHead>
                    <TableHead className="text-right">Min Oran</TableHead>
                    <TableHead className="w-[60px]" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {list.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} className="text-center text-muted-foreground py-6">
                        {t('cm.pages_HurdleRatesPage.henuz_hurdle_tanimi_yok')}
                      </TableCell>
                    </TableRow>
                  ) : list.map((h) => (
                    <TableRow key={h.id}>
                      <TableCell className="font-medium">{h.name}</TableCell>
                      <TableCell className="text-xs">{h.date_from} → {h.date_to}</TableCell>
                      <TableCell>{h.room_type ? <Badge variant="secondary">{h.room_type}</Badge> : <span className="text-muted-foreground text-xs">{t('cm.pages_HurdleRatesPage.tum')}</span>}</TableCell>
                      <TableCell>{h.channel ? <Badge variant="secondary">{h.channel}</Badge> : <span className="text-muted-foreground text-xs">{t('cm.pages_HurdleRatesPage.tum_37971')}</span>}</TableCell>
                      <TableCell className="text-right font-mono">{Number(h.min_rate).toFixed(2)} {h.currency}</TableCell>
                      <TableCell>
                        <Button size="sm" variant="ghost" onClick={() => setDeleteTarget({ id: h.id, name: h.name })}>
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

        <TabsContent value="check">
          <Card>
            <CardHeader>
              <CardTitle>{t('cm.pages_HurdleRatesPage.oran_kontrolu_1ac6f')}</CardTitle>
              <CardDescription>
                {t('cm.pages_HurdleRatesPage.bir_teklif_fiyatin_hurdle_a_uyup_uymadig')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={runCheck} className="grid grid-cols-1 md:grid-cols-5 gap-2 items-end">
                <div>
                  <Label>{t('cm.pages_HurdleRatesPage.tarih')}</Label>
                  <Input type="date" value={check.date}
                    onChange={(e) => setCheck({ ...check, date: e.target.value })}
                    required data-testid="input-check-date" />
                </div>
                <div>
                  <Label>Teklif Oran</Label>
                  <Input type="number" step="0.01" min="0"
                    value={check.proposed_rate}
                    onChange={(e) => setCheck({ ...check, proposed_rate: e.target.value })}
                    required data-testid="input-check-rate" />
                </div>
                <div>
                  <Label>{t('cm.pages_HurdleRatesPage.oda_tipi_adb74')}</Label>
                  <Input value={check.room_type}
                    onChange={(e) => setCheck({ ...check, room_type: e.target.value })}
                    placeholder="opsiyonel" />
                </div>
                <div>
                  <Label>Kanal</Label>
                  <Input value={check.channel}
                    onChange={(e) => setCheck({ ...check, channel: e.target.value })}
                    placeholder="opsiyonel" />
                </div>
                <Button type="submit" disabled={checking} data-testid="button-check">
                  {checking ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Search className="h-4 w-4 mr-1" />}
                  Kontrol
                </Button>
              </form>

              {checkResult && (
                <Card className={checkResult.allowed ? "border-green-300 bg-green-50/40" : "border-red-300 bg-red-50/40"}>
                  <CardContent className="pt-6 space-y-2">
                    <div className="flex items-center gap-2 text-lg font-semibold">
                      {checkResult.allowed
                        ? <><CheckCircle2 className="h-6 w-6 text-green-600" /> Kabul edilir</>
                        : <><XCircle className="h-6 w-6 text-red-600" /> Reddedilir</>}
                    </div>
                    <div className="text-sm">{checkResult.reason}</div>
                    {checkResult.applied_hurdle && (
                      <div className="text-xs text-muted-foreground border-t pt-2">
                        Uygulanan hurdle: <strong>{checkResult.applied_hurdle.name}</strong>
                        {" · min "}
                        {checkResult.applied_hurdle.min_rate} {checkResult.applied_hurdle.currency}
                        {" · specificity "}
                        {checkResult.applied_hurdle.specificity}
                      </div>
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
            <DialogTitle>Hurdle sil?</DialogTitle>
            <DialogDescription>"{deleteTarget?.name}{t('cm.pages_HurdleRatesPage.pasife_alinacak')}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>{t('cm.pages_HurdleRatesPage.vazgec')}</Button>
            <Button variant="destructive" onClick={confirmDelete} data-testid="button-hurdle-confirm-delete">{t('cm.pages_HurdleRatesPage.sil')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
