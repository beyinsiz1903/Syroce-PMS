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
import { Building2, Plus, RefreshCw, X, Loader2 } from "lucide-react";
import { useTranslation } from 'react-i18next';

/**
 * Opera #6 — Function Space.
 * Toplantı/balo salonu saatlik takvim, kurulum tipi (theatre/banquet/u_shape…),
 * kapasite ve çakışma kontrolü.
 *
 * Backend `/api/function-space/*` endpoint'leri:
 *   GET/POST/DELETE /rooms
 *   GET/POST /bookings, POST /bookings/{id}/cancel
 *   GET /availability?date=YYYY-MM-DD
 */

const SETUPS = [
  { v: "theatre", l: "Tiyatro" },
  { v: "classroom", l: "Sınıf" },
  { v: "boardroom", l: "Boardroom" },
  { v: "u_shape", l: "U Düzeni" },
  { v: "banquet", l: "Banket" },
  { v: "cocktail", l: "Kokteyl" },
  { v: "hollow_square", l: "Açık Kare" },
  { v: "cabaret", l: "Kabare" },
  { v: "custom", l: "Özel" },
];
const HOURS = Array.from({ length: 16 }, (_, i) => 7 + i); // 07:00 → 22:00

export default function FunctionSpacePage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [tab, setTab] = useState("schedule");
  const [rooms, setRooms] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [loading, setLoading] = useState(false);

  const [bookingOpen, setBookingOpen] = useState(false);
  const [bkForm, setBkForm] = useState({
    room_id: "", event_name: "", organizer: "", starts_at: "", ends_at: "",
    setup_type: "theatre", attendees: 1, note: "",
  });
  const [submittingBk, setSubmittingBk] = useState(false);

  const [cancelTarget, setCancelTarget] = useState(null);
  const [cancelling, setCancelling] = useState(false);

  const [roomForm, setRoomForm] = useState({
    name: "", capacity: 50, area_m2: "", floor: "",
    hourly_rate: 0, daily_rate: 0, supported_setups: "",
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
      const [r, b] = await Promise.all([
        api.get("/function-space/rooms"),
        api.get("/function-space/bookings", { params: { date } }),
      ]);
      setRooms(r.data || []);
      setBookings(b.data || []);
    } catch (e) { handleErr("Yüklenemedi", e); }
    finally { setLoading(false); }
  }, [date, handleErr]);

  useEffect(() => { load(); }, [load]);

  const addRoom = async (e) => {
    e.preventDefault();
    try {
      await api.post("/function-space/rooms", {
        ...roomForm,
        capacity: Number(roomForm.capacity),
        area_m2: roomForm.area_m2 ? Number(roomForm.area_m2) : null,
        hourly_rate: Number(roomForm.hourly_rate),
        daily_rate: Number(roomForm.daily_rate),
        supported_setups: roomForm.supported_setups
          .split(",").map((s) => s.trim()).filter(Boolean),
      });
      setRoomForm({
        name: "", capacity: 50, area_m2: "", floor: "",
        hourly_rate: 0, daily_rate: 0, supported_setups: "",
      });
      toast({ title: "Salon eklendi" });
      load();
    } catch (e) { handleErr("Eklenemedi", e); }
  };

  const submitBooking = async () => {
    if (!bkForm.room_id || !bkForm.event_name || !bkForm.starts_at || !bkForm.ends_at) {
      toast({ title: "Eksik alan", description: "Salon, etkinlik adı, başlangıç ve bitiş zorunlu.", variant: "destructive" });
      return;
    }
    if (bkForm.starts_at >= bkForm.ends_at) {
      toast({ title: "Tarih hatası", description: "Bitiş başlangıçtan sonra olmalı.", variant: "destructive" });
      return;
    }
    setSubmittingBk(true);
    try {
      await api.post("/function-space/bookings", {
        ...bkForm,
        attendees: Number(bkForm.attendees) || 1,
        organizer: bkForm.organizer.trim() || null,
        note: bkForm.note.trim() || null,
      });
      toast({ title: "Etkinlik rezerve edildi" });
      setBookingOpen(false);
      setBkForm({
        room_id: "", event_name: "", organizer: "", starts_at: "", ends_at: "",
        setup_type: "theatre", attendees: 1, note: "",
      });
      load();
    } catch (e) { handleErr("Rezervasyon başarısız", e); }
    finally { setSubmittingBk(false); }
  };

  const requestCancel = (b) => {
    if (b.status === "cancelled") return;
    setCancelTarget({
      id: b.id,
      label: `${b.event_name} · ${b.starts_at?.slice(11, 16)}-${b.ends_at?.slice(11, 16)}`,
    });
  };

  const confirmCancel = async () => {
    if (!cancelTarget) return;
    setCancelling(true);
    try {
      await api.post(`/function-space/bookings/${cancelTarget.id}/cancel`);
      toast({ title: "Etkinlik iptal edildi" });
      setCancelTarget(null);
      load();
    } catch (e) { handleErr("İptal başarısız", e); }
    finally { setCancelling(false); }
  };

  const openSlot = (roomId, hour) => {
    const startsAt = `${date}T${String(hour).padStart(2, "0")}:00`;
    const endsAt = `${date}T${String(hour + 1).padStart(2, "0")}:00`;
    const room = rooms.find((r) => r.id === roomId);
    setBkForm({
      room_id: roomId,
      event_name: "",
      organizer: "",
      starts_at: startsAt,
      ends_at: endsAt,
      setup_type: room?.supported_setups?.[0] || "theatre",
      attendees: Math.min(50, room?.capacity || 1),
      note: "",
    });
    setBookingOpen(true);
  };

  // Booking → o saat slot'una düşen tüm hücrelere yay (start..end-1).
  // Grid dışında başlayan ama içine giren rezervasyonun ilk görünür hücresine
  // başlangıç saatini göstermek için isFirstVisible flag'i tutulur.
  const bookingsByCell = useMemo(() => {
    const map = new Map();
    const lo = HOURS[0];
    const hi = HOURS[HOURS.length - 1];
    for (const b of bookings) {
      if (!b.starts_at || !b.room_id) continue;
      const startH = parseInt(b.starts_at.slice(11, 13), 10);
      let endH = startH + 1;
      if (b.ends_at) {
        const eh = parseInt(b.ends_at.slice(11, 13), 10);
        const em = parseInt(b.ends_at.slice(14, 16), 10);
        endH = em > 0 ? eh + 1 : eh;
      }
      const visibleFrom = Math.max(startH, lo);
      const visibleTo = Math.min(endH, hi + 1);
      for (let h = visibleFrom; h < visibleTo; h++) {
        const key = `${b.room_id}@${h}`;
        if (!map.has(key)) map.set(key, []);
        map.get(key).push({
          booking: b,
          isStart: h === startH,
          isFirstVisible: h === visibleFrom,
        });
      }
    }
    return map;
  }, [bookings]);

  // Grid'i tamamen veya kısmen taşan rezervasyonlar — kullanıcı bağlamı kaybetmesin
  const outOfGrid = useMemo(() => {
    const lo = HOURS[0];
    const hi = HOURS[HOURS.length - 1];
    return bookings.filter((b) => {
      if (!b.starts_at) return false;
      const startH = parseInt(b.starts_at.slice(11, 13), 10);
      const endH = b.ends_at ? parseInt(b.ends_at.slice(11, 13), 10) : startH;
      // Tamamen dışarıda VEYA grid sınırlarını aşıyor
      const fullyOutside = (startH < lo && endH < lo) || (startH > hi && endH > hi);
      const partiallyOutside = startH < lo || endH > hi + 1;
      return fullyOutside || partiallyOutside;
    });
  }, [bookings]);

  const setupLabel = (v) => SETUPS.find((s) => s.v === v)?.l || v;

  return (
    <div className="container mx-auto p-6 space-y-4 max-w-7xl">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-2xl font-semibold flex items-center gap-2">
            <Building2 className="h-6 w-6" /> {t('cm.pages_FunctionSpacePage.toplanti_salonlari_function_space')}
          </h2>
          <p className="text-sm text-muted-foreground">
            {t('cm.pages_FunctionSpacePage.banket_toplanti_ve_etkinlik_salonu_rezer')}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading} data-testid="button-refresh-fs">
          <RefreshCw className={`h-4 w-4 mr-1 ${loading ? "animate-spin" : ""}`} /> {t('cm.pages_FunctionSpacePage.yenile')}
        </Button>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="schedule" data-testid="tab-fs-schedule">{t('cm.pages_FunctionSpacePage.gunluk_takvim')}</TabsTrigger>
          <TabsTrigger value="rooms" data-testid="tab-fs-rooms">Salonlar</TabsTrigger>
        </TabsList>

        <TabsContent value="schedule">
          <Card>
            <CardHeader>
              <CardTitle>Saatlik Salon Takvimi (07:00–22:00)</CardTitle>
              <CardDescription>
                {t('cm.pages_FunctionSpacePage.bos_hucreye_tiklayarak_yeni_etkinlik_ekl')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-end gap-3 flex-wrap">
                <div>
                  <Label>{t('cm.pages_FunctionSpacePage.tarih')}</Label>
                  <Input
                    type="date"
                    value={date}
                    onChange={(e) => setDate(e.target.value)}
                    className="w-[180px]"
                    data-testid="input-fs-date"
                  />
                </div>
                <Button
                  onClick={() => {
                    setBkForm({
                      room_id: rooms[0]?.id || "",
                      event_name: "", organizer: "",
                      starts_at: `${date}T09:00`, ends_at: `${date}T17:00`,
                      setup_type: "theatre", attendees: 1, note: "",
                    });
                    setBookingOpen(true);
                  }}
                  data-testid="button-new-event"
                >
                  <Plus className="h-4 w-4 mr-1" /> {t('cm.pages_FunctionSpacePage.yeni_etkinlik')}
                </Button>
              </div>

              {rooms.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  {t('cm.pages_FunctionSpacePage.henuz_salon_tanimli_degil_salonlar_sekme')}
                </div>
              ) : (
                <div className="overflow-x-auto border rounded">
                  <table className="w-full text-xs">
                    <thead className="bg-muted">
                      <tr>
                        <th className="px-2 py-1 text-left sticky left-0 bg-muted z-10">Salon</th>
                        {HOURS.map((h) => (
                          <th key={h} className="px-1 py-1 text-center font-medium border-l min-w-[55px]">
                            {String(h).padStart(2, "0")}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rooms.map((r) => (
                        <tr key={r.id} className="border-t">
                          <td className="px-2 py-1 sticky left-0 bg-background z-10 font-medium whitespace-nowrap">
                            {r.name}
                            <span className="ml-1 text-[10px] text-muted-foreground">
                              ({r.capacity})
                            </span>
                          </td>
                          {HOURS.map((h) => {
                            const slot = bookingsByCell.get(`${r.id}@${h}`) || [];
                            return (
                              <td key={h} className="border-l p-0.5 align-top h-12" data-testid={`fs-cell-${r.id}-${h}`}>
                                {slot.length === 0 ? (
                                  <button
                                    type="button"
                                    onClick={() => openSlot(r.id, h)}
                                    className="w-full h-full hover:bg-emerald-50 transition rounded text-emerald-600 opacity-30 hover:opacity-100"
                                    title={t('cm.pages_FunctionSpacePage.yeni_etkinlik_53b72')}
                                  >
                                    +
                                  </button>
                                ) : (
                                  slot.map(({ booking: b, isStart, isFirstVisible }) => {
                                    const cancelled = b.status === "cancelled";
                                    // Grid dışında başlamış ama bu hücre ilk görünen → başlangıç saatini göster
                                    const showAsAnchor = isStart || (isFirstVisible && !isStart);
                                    let label;
                                    if (cancelled) label = b.event_name;
                                    else if (isStart) label = `${b.event_name} (${b.attendees})`;
                                    else if (isFirstVisible) label = `↞ ${b.starts_at?.slice(11, 16)} ${b.event_name}`;
                                    else label = "↳";
                                    return (
                                      <button
                                        key={`${b.id}-${h}`}
                                        type="button"
                                        onClick={() => requestCancel(b)}
                                        disabled={cancelled}
                                        className={`w-full text-left px-1 py-0.5 mb-0.5 rounded text-[10px] truncate ${
                                          cancelled
                                            ? "bg-gray-100 line-through opacity-40"
                                            : showAsAnchor
                                              ? "bg-emerald-200 hover:bg-emerald-300 font-medium"
                                              : "bg-emerald-100 hover:bg-emerald-200 italic opacity-80"
                                        }`}
                                        title={`${b.event_name} · ${setupLabel(b.setup_type)} · ${b.attendees} kişi · ${b.starts_at?.slice(11, 16)}-${b.ends_at?.slice(11, 16)}${isStart ? "" : isFirstVisible ? " (grid öncesi başladı)" : " (devam)"}`}
                                      >
                                        {label}
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
                  {bookings.filter((b) => b.status !== "cancelled").length} aktif etkinlik ·{" "}
                  {bookings.filter((b) => b.status === "cancelled").length} iptal
                </div>
              )}

              {outOfGrid.length > 0 && (
                <div className="border rounded p-3 bg-amber-50">
                  <div className="text-xs font-medium mb-2 text-amber-900">
                    {t('cm.pages_FunctionSpacePage.grid_disi_etkinlikler_07_00_oncesi_22_00')}
                  </div>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t('cm.pages_FunctionSpacePage.saat')}</TableHead>
                        <TableHead>Etkinlik</TableHead>
                        <TableHead>Salon</TableHead>
                        <TableHead className="text-center">Kurulum</TableHead>
                        <TableHead className="text-right">{t('cm.pages_FunctionSpacePage.kisi')}</TableHead>
                        <TableHead className="w-[60px]" />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {outOfGrid.map((b) => {
                        const room = rooms.find((r) => r.id === b.room_id);
                        return (
                          <TableRow key={b.id}>
                            <TableCell className="text-xs">
                              {b.starts_at?.slice(11, 16)}-{b.ends_at?.slice(11, 16)}
                            </TableCell>
                            <TableCell>{b.event_name}</TableCell>
                            <TableCell>{room?.name || b.room_id}</TableCell>
                            <TableCell className="text-center">
                              <Badge variant="outline">{setupLabel(b.setup_type)}</Badge>
                            </TableCell>
                            <TableCell className="text-right">{b.attendees}</TableCell>
                            <TableCell>
                              {b.status !== "cancelled" && (
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

        <TabsContent value="rooms">
          <Card>
            <CardHeader>
              <CardTitle>{t('cm.pages_FunctionSpacePage.salon_tanimlari')}</CardTitle>
              <CardDescription>
                {t('cm.pages_FunctionSpacePage.kapasite_alan_desteklenen_kurulum_tipler')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={addRoom} className="grid grid-cols-1 md:grid-cols-7 gap-2 items-end">
                <div className="md:col-span-2">
                  <Label>{t('cm.pages_FunctionSpacePage.salon_adi')}</Label>
                  <Input
                    value={roomForm.name}
                    onChange={(e) => setRoomForm({ ...roomForm, name: e.target.value })}
                    required
                    data-testid="input-room-name"
                  />
                </div>
                <div>
                  <Label>Kapasite</Label>
                  <Input
                    type="number" min={1}
                    value={roomForm.capacity}
                    onChange={(e) => setRoomForm({ ...roomForm, capacity: e.target.value })}
                  />
                </div>
                <div>
                  <Label>Alan (m²)</Label>
                  <Input
                    type="number" min={0}
                    value={roomForm.area_m2}
                    onChange={(e) => setRoomForm({ ...roomForm, area_m2: e.target.value })}
                  />
                </div>
                <div>
                  <Label>Saatlik</Label>
                  <Input
                    type="number" min={0}
                    value={roomForm.hourly_rate}
                    onChange={(e) => setRoomForm({ ...roomForm, hourly_rate: e.target.value })}
                  />
                </div>
                <div>
                  <Label>{t('cm.pages_FunctionSpacePage.gunluk')}</Label>
                  <Input
                    type="number" min={0}
                    value={roomForm.daily_rate}
                    onChange={(e) => setRoomForm({ ...roomForm, daily_rate: e.target.value })}
                  />
                </div>
                <Button type="submit" data-testid="button-add-room">
                  <Plus className="h-4 w-4 mr-1" /> {t('cm.pages_FunctionSpacePage.ekle')}
                </Button>
                <div className="md:col-span-7">
                  <Label className="text-xs">{t('cm.pages_FunctionSpacePage.desteklenen_kurulumlar_virgullu_bos_bira')}</Label>
                  <Input
                    value={roomForm.supported_setups}
                    onChange={(e) => setRoomForm({ ...roomForm, supported_setups: e.target.value })}
                    placeholder="theatre, classroom, banquet"
                  />
                </div>
              </form>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Salon</TableHead>
                    <TableHead className="text-right">Kapasite</TableHead>
                    <TableHead className="text-right">Alan</TableHead>
                    <TableHead>Kurulumlar</TableHead>
                    <TableHead className="text-right">Saatlik</TableHead>
                    <TableHead className="text-right">{t('cm.pages_FunctionSpacePage.gunluk_18de9')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rooms.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} className="text-center text-muted-foreground py-6">
                        {t('cm.pages_FunctionSpacePage.salon_tanimli_degil')}
                      </TableCell>
                    </TableRow>
                  ) : rooms.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell className="font-medium">{r.name}</TableCell>
                      <TableCell className="text-right">{r.capacity}</TableCell>
                      <TableCell className="text-right">{r.area_m2 ? `${r.area_m2} m²` : "-"}</TableCell>
                      <TableCell className="text-xs">
                        {(r.supported_setups || []).length === 0
                          ? <span className="text-muted-foreground">{t('cm.pages_FunctionSpacePage.tumu')}</span>
                          : r.supported_setups.map((s) => (
                            <Badge key={s} variant="secondary" className="mr-1">{setupLabel(s)}</Badge>
                          ))}
                      </TableCell>
                      <TableCell className="text-right">{r.hourly_rate || "-"}</TableCell>
                      <TableCell className="text-right">{r.daily_rate || "-"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Cancel dialog */}
      <Dialog open={!!cancelTarget} onOpenChange={(o) => !o && setCancelTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('cm.pages_FunctionSpacePage.etkinligi_iptal_et')}</DialogTitle>
            <DialogDescription>{cancelTarget?.label}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelTarget(null)} disabled={cancelling}>
              {t('cm.pages_FunctionSpacePage.vazgec')}
            </Button>
            <Button variant="destructive" onClick={confirmCancel} disabled={cancelling} data-testid="button-fs-confirm-cancel">
              {cancelling && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
              {t('cm.pages_FunctionSpacePage.iptal_et')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Booking modal */}
      <Dialog open={bookingOpen} onOpenChange={setBookingOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{t('cm.pages_FunctionSpacePage.yeni_etkinlik_8945d')}</DialogTitle>
            <DialogDescription>
              {t('cm.pages_FunctionSpacePage.salon_kapasitesini_asan_veya_cakisan_rez')}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label>Salon</Label>
                <Select value={bkForm.room_id} onValueChange={(v) => setBkForm({ ...bkForm, room_id: v })}>
                  <SelectTrigger data-testid="select-fs-room">
                    <SelectValue placeholder={t('cm.pages_FunctionSpacePage.salon_sec')} />
                  </SelectTrigger>
                  <SelectContent>
                    {rooms.map((r) => (
                      <SelectItem key={r.id} value={r.id}>
                        {r.name} (max {r.capacity})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Kurulum</Label>
                <Select value={bkForm.setup_type} onValueChange={(v) => setBkForm({ ...bkForm, setup_type: v })}>
                  <SelectTrigger data-testid="select-fs-setup">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SETUPS.map((s) => <SelectItem key={s.v} value={s.v}>{s.l}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label>{t('cm.pages_FunctionSpacePage.etkinlik_adi')}</Label>
              <Input
                value={bkForm.event_name}
                onChange={(e) => setBkForm({ ...bkForm, event_name: e.target.value })}
                placeholder={t('cm.pages_FunctionSpacePage.orn_acme_corp_yillik_toplanti')}
                data-testid="input-fs-event"
              />
            </div>
            <div>
              <Label>{t('cm.pages_FunctionSpacePage.duzenleyen_opsiyonel')}</Label>
              <Input
                value={bkForm.organizer}
                onChange={(e) => setBkForm({ ...bkForm, organizer: e.target.value })}
                placeholder={t('cm.pages_FunctionSpacePage.sirket_grup')}
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label>{t('cm.pages_FunctionSpacePage.baslangic')}</Label>
                <Input
                  type="datetime-local"
                  value={bkForm.starts_at}
                  onChange={(e) => setBkForm({ ...bkForm, starts_at: e.target.value })}
                  data-testid="input-fs-start"
                />
              </div>
              <div>
                <Label>{t('cm.pages_FunctionSpacePage.bitis')}</Label>
                <Input
                  type="datetime-local"
                  value={bkForm.ends_at}
                  onChange={(e) => setBkForm({ ...bkForm, ends_at: e.target.value })}
                  data-testid="input-fs-end"
                />
              </div>
            </div>
            <div>
              <Label>{t('cm.pages_FunctionSpacePage.katilimci')}</Label>
              <Input
                type="number" min={1}
                value={bkForm.attendees}
                onChange={(e) => setBkForm({ ...bkForm, attendees: e.target.value })}
                data-testid="input-fs-attendees"
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
              {t('cm.pages_FunctionSpacePage.vazgec_bf814')}
            </Button>
            <Button onClick={submitBooking} disabled={submittingBk} data-testid="button-fs-confirm-booking">
              {submittingBk && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
              Rezerve Et
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
