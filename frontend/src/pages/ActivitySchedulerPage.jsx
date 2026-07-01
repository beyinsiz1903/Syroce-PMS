import { useEffect, useState, useMemo, useCallback } from "react";
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
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { CalendarDays, Plus, RefreshCw, X, Loader2 } from "lucide-react";
import { useTranslation } from 'react-i18next';

const TYPES = ["golf", "tennis", "yoga", "fitness", "bike", "diving", "kids", "other"];
const HOURS = Array.from({ length: 13 }, (_, i) => 8 + i); // 08:00 → 20:00

/**
 * Opera #3 — Activity Scheduler.
 * Backend `/api/activities/*`: aktivite + kaynak + booking + clash detection.
 *
 * Eski sürüm tek tablo + inline form. Bu sürüm:
 * - Saatlik grid (kaynak × saat) → boş hücreye tıklayınca booking modal açılır
 * - Aktivite/Kaynak yönetimi ayrı tab
 * - shadcn/ui ile tutarlı görünüm, toast + dialog
 */
export default function ActivitySchedulerPage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [tab, setTab] = useState("schedule");
  const [activities, setActivities] = useState([]);
  const [resources, setResources] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [loading, setLoading] = useState(false);

  // Booking modal
  const [bookingOpen, setBookingOpen] = useState(false);
  // İptal onay dialog'u (window.confirm yerine)
  const [cancelTarget, setCancelTarget] = useState(null); // {id, label}
  const [cancelling, setCancelling] = useState(false);
  const [bkForm, setBkForm] = useState({
    activity_id: "", resource_id: "", guest_id: "", starts_at: "", note: "",
  });
  const [submittingBk, setSubmittingBk] = useState(false);

  // Tanım formları (tab içinde)
  const [actForm, setActForm] = useState({
    name: "", type: "golf", duration_min: 60, price: 0, capacity: 1,
  });
  const [resForm, setResForm] = useState({
    name: "", kind: "instructor", activity_types: "", capacity: 1,
  });

  const handleErr = useCallback((title, e) => {
    toast({
      title,
      description: e?.response?.data?.detail || e.message,
      variant: "destructive",
    });
  }, [toast]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [a, r, b] = await Promise.all([
        api.get("/activities"),
        api.get("/activities/resources"),
        api.get("/activities/bookings", { params: { date } }),
      ]);
      setActivities(a.data || []);
      setResources(r.data || []);
      setBookings(b.data || []);
    } catch (e) { handleErr("Yüklenemedi", e); }
    finally { setLoading(false); }
  }, [date, handleErr]);

  useEffect(() => { load(); }, [load]);

  const addActivity = async (e) => {
    e.preventDefault();
    try {
      await api.post("/activities", {
        ...actForm,
        duration_min: Number(actForm.duration_min),
        price: Number(actForm.price),
        capacity: Number(actForm.capacity),
      });
      setActForm({ name: "", type: "golf", duration_min: 60, price: 0, capacity: 1 });
      toast({ title: "Aktivite eklendi" });
      load();
    } catch (e2) { handleErr("Eklenemedi", e2); }
  };

  const addResource = async (e) => {
    e.preventDefault();
    try {
      await api.post("/activities/resources", {
        ...resForm,
        capacity: Number(resForm.capacity),
        activity_types: resForm.activity_types.split(",").map((s) => s.trim()).filter(Boolean),
      });
      setResForm({ name: "", kind: "instructor", activity_types: "", capacity: 1 });
      toast({ title: "Kaynak eklendi" });
      load();
    } catch (e2) { handleErr("Eklenemedi", e2); }
  };

  const requestCancel = (b) => {
    if (b.status === "cancelled") return;
    const act = activityById[b.activity_id];
    setCancelTarget({
      id: b.id,
      label: `${act?.name || b.activity_id} · ${b.starts_at?.slice(11, 16)}-${b.ends_at?.slice(11, 16)} · ${b.guest_id}`,
    });
  };

  const confirmCancel = async () => {
    if (!cancelTarget) return;
    setCancelling(true);
    try {
      await api.post(`/activities/bookings/${cancelTarget.id}/cancel`);
      toast({ title: "Rezervasyon iptal edildi" });
      setCancelTarget(null);
      load();
    } catch (e) { handleErr("İptal başarısız", e); }
    finally { setCancelling(false); }
  };

  const submitBooking = async () => {
    if (!bkForm.activity_id || !bkForm.resource_id || !bkForm.guest_id || !bkForm.starts_at) {
      toast({ title: "Eksik alan", description: "Aktivite, kaynak, misafir ve saat zorunlu.", variant: "destructive" });
      return;
    }
    setSubmittingBk(true);
    try {
      await api.post("/activities/bookings", bkForm);
      toast({ title: "Rezervasyon oluşturuldu" });
      setBookingOpen(false);
      setBkForm({ activity_id: "", resource_id: "", guest_id: "", starts_at: "", note: "" });
      load();
    } catch (e) { handleErr("Rezervasyon başarısız", e); }
    finally { setSubmittingBk(false); }
  };

  // Boş hücre tıklayınca form'u o saat + kaynakla önceden doldur.
  const openSlot = (resourceId, hour) => {
    const startsAt = `${date}T${String(hour).padStart(2, "0")}:00`;
    setBkForm({
      activity_id: activities[0]?.id || "",
      resource_id: resourceId,
      guest_id: "",
      starts_at: startsAt,
      note: "",
    });
    setBookingOpen(true);
  };

  // Grid: her hücre için (resource_id, hour) → o saati işgal eden tüm
  // booking'leri tut. Uzun rezervasyon (örn. 2h golf) starts..ends arası
  // tüm hücrelere yayılır (span); ilk hücreye `isStart=true` flag konur ki
  // ad/etiket sadece başlangıçta yazılsın, sonraki hücrelerde sade dolgu.
  const bookingsByCell = useMemo(() => {
    const map = new Map();
    for (const b of bookings) {
      if (!b.starts_at || !b.resource_id) continue;
      const startH = parseInt(b.starts_at.slice(11, 13), 10);
      // ends_at yoksa varsayılan 1 saat; HH:MM > :00 ise yukarı yuvarla
      let endH = startH + 1;
      if (b.ends_at) {
        const eh = parseInt(b.ends_at.slice(11, 13), 10);
        const em = parseInt(b.ends_at.slice(14, 16), 10);
        endH = em > 0 ? eh + 1 : eh;
      }
      for (let h = startH; h < endH; h++) {
        if (h < HOURS[0] || h > HOURS[HOURS.length - 1]) continue;
        const key = `${b.resource_id}@${h}`;
        if (!map.has(key)) map.set(key, []);
        map.get(key).push({ booking: b, isStart: h === startH });
      }
    }
    return map;
  }, [bookings]);

  // 08-20 grid'i dışına düşen rezervasyonlar (gece/erken sabah).
  // Eski sürüm bunları tablo halinde gösteriyordu; grid view kaybetmesin.
  const outOfGrid = useMemo(() => {
    const lo = HOURS[0];
    const hi = HOURS[HOURS.length - 1];
    return bookings.filter((b) => {
      if (!b.starts_at) return false;
      const startH = parseInt(b.starts_at.slice(11, 13), 10);
      const endH = b.ends_at ? parseInt(b.ends_at.slice(11, 13), 10) : startH;
      // Hem başlangıç hem bitiş grid dışında ise listeye al
      return (startH < lo && endH < lo) || (startH > hi && endH > hi);
    });
  }, [bookings]);

  const activityById = useMemo(
    () => Object.fromEntries(activities.map((a) => [a.id, a])),
    [activities],
  );

  return (
    <div className="container mx-auto p-6 space-y-4 max-w-7xl">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-2xl font-semibold flex items-center gap-2">
            <CalendarDays className="h-6 w-6" /> Aktivite Takvimi
          </h2>
          <p className="text-sm text-muted-foreground">
            {t('cm.pages_ActivitySchedulerPage.golf_tenis_yoga_dalis_cocuk_kulubu_egitm')}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading} data-testid="button-refresh-activities">
          <RefreshCw className={`h-4 w-4 mr-1 ${loading ? "animate-spin" : ""}`} /> {t('cm.pages_ActivitySchedulerPage.yenile')}
        </Button>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="schedule" data-testid="tab-schedule">{t('cm.pages_ActivitySchedulerPage.gunluk_takvim')}</TabsTrigger>
          <TabsTrigger value="activities" data-testid="tab-activities">{t('cm.pages_ActivitySchedulerPage.aktivite_tanimlari')}</TabsTrigger>
          <TabsTrigger value="resources" data-testid="tab-resources">Kaynaklar</TabsTrigger>
        </TabsList>

        <TabsContent value="schedule">
          <Card>
            <CardHeader>
              <CardTitle>Saatlik Kaynak Takvimi</CardTitle>
              <CardDescription>
                {t('cm.pages_ActivitySchedulerPage.bos_hucreye_tiklayarak_yeni_rezervasyon_')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-end gap-3 flex-wrap">
                <div>
                  <Label>{t('cm.pages_ActivitySchedulerPage.tarih')}</Label>
                  <Input
                    type="date"
                    value={date}
                    onChange={(e) => setDate(e.target.value)}
                    className="w-[180px]"
                    data-testid="input-schedule-date"
                  />
                </div>
                <Button onClick={() => { setBkForm({ activity_id: "", resource_id: "", guest_id: "", starts_at: "", note: "" }); setBookingOpen(true); }}>
                  <Plus className="h-4 w-4 mr-1" /> {t('cm.pages_ActivitySchedulerPage.yeni_rezervasyon')}
                </Button>
              </div>

              {resources.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  {t('cm.pages_ActivitySchedulerPage.henuz_kaynak_tanimli_degil_kaynaklar_sek')}
                </div>
              ) : (
                <div className="overflow-x-auto border rounded">
                  <table className="w-full text-xs">
                    <thead className="bg-muted">
                      <tr>
                        <th className="px-2 py-1 text-left sticky left-0 bg-muted z-10">Kaynak</th>
                        {HOURS.map((h) => (
                          <th key={h} className="px-1 py-1 text-center font-medium border-l min-w-[60px]">
                            {String(h).padStart(2, "0")}:00
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {resources.map((r) => (
                        <tr key={r.id} className="border-t">
                          <td className="px-2 py-1 sticky left-0 bg-background z-10 font-medium whitespace-nowrap">
                            {r.name}
                            <span className="ml-1 text-[10px] text-muted-foreground">[{r.kind}]</span>
                          </td>
                          {HOURS.map((h) => {
                            const slot = bookingsByCell.get(`${r.id}@${h}`) || [];
                            return (
                              <td
                                key={h}
                                className="border-l p-0.5 align-top h-12"
                                data-testid={`cell-${r.id}-${h}`}
                              >
                                {slot.length === 0 ? (
                                  <button
                                    type="button"
                                    onClick={() => openSlot(r.id, h)}
                                    className="w-full h-full hover:bg-blue-50 transition rounded text-blue-600 opacity-30 hover:opacity-100"
                                    title={t('cm.pages_ActivitySchedulerPage.yeni_rezervasyon_a7e8c')}
                                  >
                                    +
                                  </button>
                                ) : (
                                  slot.map(({ booking: b, isStart }) => {
                                    const act = activityById[b.activity_id];
                                    const cancelled = b.status === "cancelled";
                                    return (
                                      <button
                                        key={`${b.id}-${h}`}
                                        type="button"
                                        onClick={() => requestCancel(b)}
                                        disabled={cancelled}
                                        className={`w-full text-left px-1 py-0.5 mb-0.5 rounded text-[10px] truncate ${
                                          cancelled
                                            ? "bg-gray-100 line-through opacity-40"
                                            : isStart
                                              ? "bg-blue-200 hover:bg-blue-300 font-medium"
                                              : "bg-blue-100 hover:bg-blue-200 italic opacity-80"
                                        }`}
                                        title={`${act?.name || b.activity_id} · ${b.guest_id} · ${b.starts_at?.slice(11, 16)}-${b.ends_at?.slice(11, 16)}${isStart ? "" : " (devam)"}`}
                                      >
                                        {isStart
                                          ? `${act?.name || "?"} · ${b.guest_id?.slice(0, 6)}`
                                          : "↳"}
                                      </button>
                                    );
                                  })
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {bookings.length > 0 && (
                <div className="text-xs text-muted-foreground pt-2">
                  {bookings.filter((b) => b.status !== "cancelled").length} aktif rezervasyon ·{" "}
                  {bookings.filter((b) => b.status === "cancelled").length} iptal
                </div>
              )}

              {outOfGrid.length > 0 && (
                <div className="border rounded p-3 bg-amber-50">
                  <div className="text-xs font-medium mb-2 text-amber-900">
                    {t('cm.pages_ActivitySchedulerPage.grid_disi_rezervasyonlar_08_00_oncesi_20')}
                  </div>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t('cm.pages_ActivitySchedulerPage.saat')}</TableHead>
                        <TableHead>Aktivite</TableHead>
                        <TableHead>Kaynak</TableHead>
                        <TableHead>{t('cm.pages_ActivitySchedulerPage.misafir')}</TableHead>
                        <TableHead className="w-[80px]" />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {outOfGrid.map((b) => {
                        const act = activityById[b.activity_id];
                        const res = resources.find((r) => r.id === b.resource_id);
                        const cancelled = b.status === "cancelled";
                        return (
                          <TableRow key={b.id} className={cancelled ? "opacity-50" : ""}>
                            <TableCell className="text-xs">
                              {b.starts_at?.slice(11, 16)}-{b.ends_at?.slice(11, 16)}
                            </TableCell>
                            <TableCell>{act?.name || b.activity_id}</TableCell>
                            <TableCell>{res?.name || b.resource_id}</TableCell>
                            <TableCell className="text-xs">{b.guest_id}</TableCell>
                            <TableCell>
                              {!cancelled && (
                                <Button size="sm" variant="ghost" onClick={() => requestCancel(b)}>
                                  <X className="h-3 w-3" />
                                </Button>
                              )}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="activities">
          <Card>
            <CardHeader>
              <CardTitle>{t('cm.pages_ActivitySchedulerPage.aktivite_tanimlari_2c0fd')}</CardTitle>
              <CardDescription>
                {t('cm.pages_ActivitySchedulerPage.sunulan_aktivite_cesitleri_saat_suresi_f')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={addActivity} className="grid grid-cols-1 md:grid-cols-6 gap-2 items-end">
                <div className="md:col-span-2">
                  <Label>Ad</Label>
                  <Input
                    value={actForm.name}
                    onChange={(e) => setActForm({ ...actForm, name: e.target.value })}
                    required
                    data-testid="input-activity-name"
                  />
                </div>
                <div>
                  <Label>Tip</Label>
                  <Select value={actForm.type} onValueChange={(v) => setActForm({ ...actForm, type: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>{t('cm.pages_ActivitySchedulerPage.sure_dk')}</Label>
                  <Input
                    type="number" min={5}
                    value={actForm.duration_min}
                    onChange={(e) => setActForm({ ...actForm, duration_min: e.target.value })}
                  />
                </div>
                <div>
                  <Label>Fiyat</Label>
                  <Input
                    type="number" min={0}
                    value={actForm.price}
                    onChange={(e) => setActForm({ ...actForm, price: e.target.value })}
                  />
                </div>
                <Button type="submit" data-testid="button-add-activity">
                  <Plus className="h-4 w-4 mr-1" /> {t('cm.pages_ActivitySchedulerPage.ekle')}
                </Button>
              </form>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ad</TableHead>
                    <TableHead className="text-center">Tip</TableHead>
                    <TableHead className="text-center">{t('cm.pages_ActivitySchedulerPage.sure')}</TableHead>
                    <TableHead className="text-right">Fiyat</TableHead>
                    <TableHead className="text-right">Kapasite</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {activities.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-muted-foreground py-6">
                        {t('cm.pages_ActivitySchedulerPage.aktivite_tanimli_degil')}
                      </TableCell>
                    </TableRow>
                  ) : activities.map((a) => (
                    <TableRow key={a.id}>
                      <TableCell className="font-medium">{a.name}</TableCell>
                      <TableCell className="text-center">
                        <Badge variant="secondary">{a.type}</Badge>
                      </TableCell>
                      <TableCell className="text-center">{a.duration_min} dk</TableCell>
                      <TableCell className="text-right">{a.price}</TableCell>
                      <TableCell className="text-right">{a.capacity}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="resources">
          <Card>
            <CardHeader>
              <CardTitle>Kaynaklar</CardTitle>
              <CardDescription>
                {t('cm.pages_ActivitySchedulerPage.egitmen_mekan_kort_havuz_sahil_ekipman')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={addResource} className="grid grid-cols-1 md:grid-cols-5 gap-2 items-end">
                <div>
                  <Label>Ad</Label>
                  <Input
                    value={resForm.name}
                    onChange={(e) => setResForm({ ...resForm, name: e.target.value })}
                    placeholder="Hakan, Court 1"
                    required
                    data-testid="input-resource-name"
                  />
                </div>
                <div>
                  <Label>{t('cm.pages_ActivitySchedulerPage.tur')}</Label>
                  <Select value={resForm.kind} onValueChange={(v) => setResForm({ ...resForm, kind: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="instructor">{t('cm.pages_ActivitySchedulerPage.egitmen')}</SelectItem>
                      <SelectItem value="venue">Mekan</SelectItem>
                      <SelectItem value="equipment">Ekipman</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="md:col-span-2">
                  <Label>{t('cm.pages_ActivitySchedulerPage.aktivite_tipleri_virgullu')}</Label>
                  <Input
                    value={resForm.activity_types}
                    onChange={(e) => setResForm({ ...resForm, activity_types: e.target.value })}
                    placeholder="golf, tennis"
                  />
                </div>
                <div>
                  <Label>Kapasite</Label>
                  <Input
                    type="number" min={1}
                    value={resForm.capacity}
                    onChange={(e) => setResForm({ ...resForm, capacity: e.target.value })}
                  />
                </div>
                <Button type="submit" className="md:col-start-5" data-testid="button-add-resource">
                  <Plus className="h-4 w-4 mr-1" /> {t('cm.pages_ActivitySchedulerPage.ekle_b9fc4')}
                </Button>
              </form>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ad</TableHead>
                    <TableHead className="text-center">{t('cm.pages_ActivitySchedulerPage.tur_2f9ca')}</TableHead>
                    <TableHead>Aktiviteler</TableHead>
                    <TableHead className="text-right">Kapasite</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {resources.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} className="text-center text-muted-foreground py-6">
                        {t('cm.pages_ActivitySchedulerPage.kaynak_tanimli_degil')}
                      </TableCell>
                    </TableRow>
                  ) : resources.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell className="font-medium">{r.name}</TableCell>
                      <TableCell className="text-center">
                        <Badge variant="outline">{r.kind}</Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {(r.activity_types || []).join(", ") || "tümü"}
                      </TableCell>
                      <TableCell className="text-right">{r.capacity}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* İptal onay dialog'u */}
      <Dialog open={!!cancelTarget} onOpenChange={(o) => !o && setCancelTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rezervasyonu iptal et?</DialogTitle>
            <DialogDescription>{cancelTarget?.label}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelTarget(null)} disabled={cancelling}>
              {t('cm.pages_ActivitySchedulerPage.vazgec')}
            </Button>
            <Button variant="destructive" onClick={confirmCancel} disabled={cancelling} data-testid="button-confirm-cancel">
              {cancelling && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
              {t('cm.pages_ActivitySchedulerPage.iptal_et')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Booking modal */}
      <Dialog open={bookingOpen} onOpenChange={setBookingOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('cm.pages_ActivitySchedulerPage.yeni_rezervasyon_92459')}</DialogTitle>
            <DialogDescription>
              {t('cm.pages_ActivitySchedulerPage.ayni_kaynak_icin_cakisan_saatler_backend')}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label>Aktivite</Label>
              <Select value={bkForm.activity_id} onValueChange={(v) => setBkForm({ ...bkForm, activity_id: v })}>
                <SelectTrigger data-testid="select-booking-activity">
                  <SelectValue placeholder={t('cm.pages_ActivitySchedulerPage.aktivite_sec')} />
                </SelectTrigger>
                <SelectContent>
                  {activities.map((a) => (
                    <SelectItem key={a.id} value={a.id}>{a.name} ({a.type})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Kaynak</Label>
              <Select value={bkForm.resource_id} onValueChange={(v) => setBkForm({ ...bkForm, resource_id: v })}>
                <SelectTrigger data-testid="select-booking-resource">
                  <SelectValue placeholder={t('cm.pages_ActivitySchedulerPage.kaynak_sec')} />
                </SelectTrigger>
                <SelectContent>
                  {resources.map((r) => (
                    <SelectItem key={r.id} value={r.id}>{r.name} [{r.kind}]</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('cm.pages_ActivitySchedulerPage.misafir_id')}</Label>
              <Input
                value={bkForm.guest_id}
                onChange={(e) => setBkForm({ ...bkForm, guest_id: e.target.value })}
                data-testid="input-booking-guest"
              />
            </div>
            <div>
              <Label>{t('cm.pages_ActivitySchedulerPage.baslangic')}</Label>
              <Input
                type="datetime-local"
                value={bkForm.starts_at}
                onChange={(e) => setBkForm({ ...bkForm, starts_at: e.target.value })}
                data-testid="input-booking-start"
              />
            </div>
            <div>
              <Label>Not</Label>
              <Input
                value={bkForm.note}
                onChange={(e) => setBkForm({ ...bkForm, note: e.target.value })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBookingOpen(false)} disabled={submittingBk}>
              <X className="h-4 w-4 mr-1" /> {t('cm.pages_ActivitySchedulerPage.vazgec_bf814')}
            </Button>
            <Button onClick={submitBooking} disabled={submittingBk} data-testid="button-confirm-booking">
              {submittingBk && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
              Rezerve Et
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
