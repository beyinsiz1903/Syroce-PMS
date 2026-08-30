import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/api/axios";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useToast } from "@/hooks/use-toast";
import {
  AlertTriangle, ArrowRight, BarChart3, Building2, CalendarClock, DoorOpen,
  Info, Loader2, Plus, RefreshCw, TrendingUp, Users,
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge } from "@/components/ui/status-badge";
import { useTranslation } from 'react-i18next';

const plusDays = (n) => {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
};
const emptyCreate = () => ({
  group_name: "",
  organization: "",
  contact_name: "",
  contact_email: "",
  contact_phone: "",
  check_in: plusDays(7),
  check_out: plusDays(10),
  cutoff_date: plusDays(3),
  total_rooms: "",
  group_rate: "",
  room_type: "Standard",
  status: "tentative",
  special_requirements: "",
});

export default function BlockManagementPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [blocks, setBlocks] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [pickup, setPickup] = useState(null);
  const [pickupOpen, setPickupOpen] = useState(false);
  const [pickupLoading, setPickupLoading] = useState(false);
  const [washTarget, setWashTarget] = useState(null);
  const [washCount, setWashCount] = useState("");
  const [washNote, setWashNote] = useState("");
  const [washSubmitting, setWashSubmitting] = useState(false);
  const [loading, setLoading] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState(emptyCreate());
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, a] = await Promise.all([
        api.get("/block-mgmt/summary"),
        api.get("/block-mgmt/cutoff-alerts", { params: { days_ahead: 14 } }),
      ]);
      setBlocks(s.data?.blocks || []);
      setAlerts(a.data?.alerts || []);
    } catch (e) {
      toast({
        title: "Yüklenemedi",
        description: e?.response?.data?.detail || e.message,
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  // C11: useCallback + temiz useEffect bağımlılığı (eslint-disable yorumu kaldırıldı)
  useEffect(() => { load(); }, [load]);

  const showPickup = useCallback(async (blk) => {
    setPickupOpen(true);
    setPickupLoading(true);
    setPickup({ group_name: blk.group_name, _stub: true });
    try {
      const { data } = await api.get(`/block-mgmt/${blk.id}/pickup`);
      setPickup(data);
    } catch (e) {
      toast({
        title: "Kullanım detayı yüklenemedi",
        description: e?.response?.data?.detail || e.message,
        variant: "destructive",
      });
      setPickupOpen(false);
    } finally {
      setPickupLoading(false);
    }
  }, [toast]);

  const openWash = (blk) => {
    const available = Math.max((blk.total_rooms || 0) - (blk.rooms_picked_up || 0), 0);
    setWashTarget({ id: blk.id, name: blk.group_name, available });
    setWashCount("");
    setWashNote("");
  };

  const submitWash = async () => {
    if (!washTarget) return;
    const n = Number(washCount);
    if (!Number.isInteger(n) || n < 1) {
      toast({ title: "Geçersiz oda sayısı", description: "1 veya daha büyük tam sayı girin.", variant: "destructive" });
      return;
    }
    if (n > washTarget.available) {
      toast({
        title: "Çok yüksek",
        description: `En fazla ${washTarget.available} oda bırakılabilir.`,
        variant: "destructive",
      });
      return;
    }
    setWashSubmitting(true);
    try {
      const { data } = await api.post(`/block-mgmt/${washTarget.id}/wash`, {
        wash_count: n,
        note: washNote.trim() || null,
      });
      toast({
        title: "Odalar bırakıldı",
        description: `${data.washed} oda envantere döndü. Yeni toplam: ${data.new_total_rooms}.`,
      });
      setWashTarget(null);
      load();
    } catch (e) {
      toast({
        title: "Odalar satışa açılamadı",
        description: e?.response?.data?.detail || e.message,
        variant: "destructive",
      });
    } finally {
      setWashSubmitting(false);
    }
  };

  const submitCreate = async () => {
    const f = createForm;
    if (!f.group_name.trim()) {
      toast({ title: "Grup adı zorunlu", variant: "destructive" });
      return;
    }
    const tr = parseInt(f.total_rooms, 10);
    if (!Number.isInteger(tr) || tr < 1) {
      toast({ title: "Toplam oda 1+ tam sayı olmalı", variant: "destructive" });
      return;
    }
    if (!f.check_in || !f.check_out) {
      toast({ title: "Giriş/çıkış tarihleri zorunlu", variant: "destructive" });
      return;
    }
    if (f.check_out <= f.check_in) {
      toast({ title: "Çıkış tarihi giriş sonrası olmalı", variant: "destructive" });
      return;
    }
    setCreating(true);
    try {
      await api.post("/block-mgmt/create", {
        group_name: f.group_name.trim(),
        organization: f.organization.trim() || null,
        contact_name: f.contact_name.trim() || null,
        contact_email: f.contact_email.trim() || null,
        contact_phone: f.contact_phone.trim() || null,
        check_in: f.check_in,
        check_out: f.check_out,
        cutoff_date: f.cutoff_date || f.check_in,
        total_rooms: tr,
        group_rate: f.group_rate ? Number(f.group_rate) : null,
        room_type: f.room_type || "Standard",
        status: f.status,
        special_requirements: f.special_requirements.trim() || null,
      });
      toast({ title: "Grup bloğu oluşturuldu" });
      setCreateOpen(false);
      setCreateForm(emptyCreate());
      load();
    } catch (e) {
      toast({
        title: "Oluşturulamadı",
        description: e?.response?.data?.detail || e.message,
        variant: "destructive",
      });
    } finally {
      setCreating(false);
    }
  };

  const urgencyMeta = (days) => {
    if (days == null) return { intent: "neutral", label: "tarih belirsiz" };
    if (days <= 2) return { intent: "danger", label: "kritik" };
    if (days <= 7) return { intent: "warning", label: "uyarı" };
    return { intent: "info", label: "bilgi" };
  };

  const summary = useMemo(() => {
    const allocated = blocks.reduce((sum, block) => sum + Number(block.total_rooms || 0), 0);
    const used = blocks.reduce((sum, block) => sum + Number(block.rooms_picked_up || 0), 0);
    const released = blocks.reduce((sum, block) => sum + Number(block.washed_count || 0), 0);
    return {
      active: blocks.length,
      allocated,
      used,
      remaining: Math.max(allocated - used, 0),
      released,
      utilization: allocated > 0 ? Math.round((used / allocated) * 100) : 0,
    };
  }, [blocks]);

  const openCreate = () => {
    setCreateForm(emptyCreate());
    setCreateOpen(true);
  };

  return (
    <div className="container mx-auto p-4 md:p-6 space-y-5 max-w-7xl">
      <PageHeader
        icon={BarChart3}
        title="Grup Kontenjan Yönetimi"
        subtitle="Tur, düğün, toplantı veya acente grupları için ayrılan oda stokunu tek yerden planlayın ve takip edin."
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => navigate("/group-bookings-manage")} data-testid="button-group-reservations">
              <Users className="h-4 w-4 mr-1.5" /> Grup Rezervasyonları
            </Button>
            <Button variant="outline" size="sm" onClick={load} disabled={loading} data-testid="button-refresh-blocks">
              <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? "animate-spin" : ""}`} /> {t('cm.pages_BlockManagementPage.yenile')}
            </Button>
            <Button size="sm" onClick={openCreate} data-testid="button-new-block">
              <Plus className="h-4 w-4 mr-1.5" /> Yeni Kontenjan
            </Button>
          </>
        }
      />

      <Card className="border-blue-200 bg-gradient-to-r from-blue-50 to-white">
        <CardContent className="p-5 md:p-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div className="max-w-2xl space-y-2">
              <div className="flex items-center gap-2 text-sm font-semibold text-blue-800">
                <Info className="h-4 w-4" /> Bu ekran ne işe yarar?
              </div>
              <p className="text-sm leading-6 text-slate-700">
                Bir grup için oda satmadan önce belirli sayıda odayı ayırır. Grup kesinleştikçe kullanılan oda sayısını
                izler; son bırakma tarihinde kullanılmayan odaları yeniden genel satışa açmanıza yardım eder.
              </p>
              <p className="text-xs leading-5 text-slate-500">
                Bu sayfa oda stokunu yönetir. Misafir isimleri, rezervasyonlar ve folyolar için
                <button type="button" className="ml-1 font-semibold text-blue-700 hover:underline" onClick={() => navigate("/group-bookings-manage")}>
                  Grup Rezervasyonları
                </button>
                ekranını kullanın.
              </p>
            </div>
            <div className="grid min-w-full grid-cols-1 gap-2 sm:grid-cols-3 lg:min-w-[520px]">
              {[
                { icon: Building2, step: "1", title: "Kontenjanı ayırın", text: "Tarih, oda tipi ve oda sayısını belirleyin." },
                { icon: Users, step: "2", title: "Kullanımı izleyin", text: "Gruba bağlanan oda sayısını takip edin." },
                { icon: DoorOpen, step: "3", title: "Kalanı satışa açın", text: "Kullanılmayacak odaları envantere döndürün." },
              ].map(({ icon: StepIcon, step, title, text }) => (
                <div key={step} className="rounded-xl border border-blue-100 bg-white p-3 shadow-sm">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">{step}</span>
                    <StepIcon className="h-4 w-4 text-blue-600" />
                  </div>
                  <div className="text-sm font-semibold text-slate-900">{title}</div>
                  <div className="mt-1 text-xs leading-4 text-slate-500">{text}</div>
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5" data-testid="block-summary">
        {[
          { label: "Aktif grup", value: summary.active, detail: "Açık kontenjan", icon: Building2, color: "text-blue-600 bg-blue-50" },
          { label: "Ayrılan oda", value: summary.allocated, detail: "Güncel stok", icon: DoorOpen, color: "text-violet-600 bg-violet-50" },
          { label: "Kullanılan oda", value: summary.used, detail: `%${summary.utilization} kullanım`, icon: Users, color: "text-emerald-600 bg-emerald-50" },
          { label: "Kalan oda", value: summary.remaining, detail: "Grup için ayrılmış", icon: CalendarClock, color: "text-amber-600 bg-amber-50" },
          { label: "Satışa dönen", value: summary.released, detail: "Toplam bırakılan", icon: ArrowRight, color: "text-slate-600 bg-slate-100" },
        ].map(({ label, value, detail, icon: MetricIcon, color }) => (
          <Card key={label}>
            <CardContent className="flex items-center gap-3 p-4">
              <span className={"flex h-10 w-10 shrink-0 items-center justify-center rounded-xl " + color}>
                <MetricIcon className="h-5 w-5" />
              </span>
              <div className="min-w-0">
                <div className="text-xs font-medium text-slate-500">{label}</div>
                <div className="text-2xl font-bold text-slate-900">{value}</div>
                <div className="truncate text-[11px] text-slate-400">{detail}</div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {alerts.length > 0 && (
        <Alert className="border-amber-300 bg-amber-50 text-amber-950" data-testid="alert-cutoff">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Son bırakma tarihi yaklaşan kontenjanlar</AlertTitle>
          <AlertDescription>
            <p className="mb-2 text-sm">Aşağıdaki grupların kullanılmayan odaları için karar vermeniz gerekiyor.</p>
            <ul className="list-disc pl-5 space-y-1 mt-1">
              {alerts.map((a) => {
                const m = urgencyMeta(a.days_left);
                return (
                  <li key={a.id}>
                    <span className="font-medium">{a.group_name}</span>
                    {" — "}
                    <StatusBadge intent={m.intent} className="mr-1">
                      {a.days_left != null ? `${m.label} · ${a.days_left} gün` : m.label}
                    </StatusBadge>
                    {a.total_rooms} odanın {a.remaining} tanesi henüz kullanılmadı
                  </li>
                );
              })}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Aktif grup kontenjanları</CardTitle>
          <CardDescription>
            Beklemedeki ve kesinleşmiş grupların ayrılan, kullanılan ve kalan oda durumları.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading && blocks.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin mr-2" /> {t('cm.pages_BlockManagementPage.yukleniyor')}
            </div>
          ) : blocks.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <BarChart3 className="h-10 w-10 mx-auto mb-3 text-slate-300" />
              <div className="text-base font-medium text-slate-700">Henüz aktif grup kontenjanı yok</div>
              <div className="mx-auto mt-1 max-w-lg text-sm">İlk kontenjanı oluşturarak grup için oda ayırabilir, kullanım oranını izleyebilir ve kalan odaları zamanında satışa açabilirsiniz.</div>
              <div className="mt-4 flex flex-col justify-center gap-2 sm:flex-row">
                <Button onClick={openCreate}>
                  <Plus className="h-4 w-4 mr-1.5" /> İlk Kontenjanı Oluştur
                </Button>
                <Button variant="outline" onClick={() => navigate("/group-bookings-manage")}>
                  <Users className="h-4 w-4 mr-1.5" /> Grup Rezervasyonlarına Git
                </Button>
              </div>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Grup</TableHead>
                  <TableHead className="text-center">{t('cm.pages_BlockManagementPage.giris')}</TableHead>
                  <TableHead className="text-center">Son bırakma</TableHead>
                  <TableHead className="text-right">Ayrılan</TableHead>
                  <TableHead className="text-right">Kullanılan</TableHead>
                  <TableHead className="text-right">Satışa dönen</TableHead>
                  <TableHead className="text-right">Kullanım</TableHead>
                  <TableHead className="w-[200px]" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {blocks.map((b) => {
                  const available = Math.max((b.total_rooms || 0) - (b.rooms_picked_up || 0), 0);
                  return (
                    <TableRow key={b.id} data-testid={`row-block-${b.id}`}>
                      <TableCell className="font-medium">{b.group_name}</TableCell>
                      <TableCell className="text-center">{(b.check_in || "").toString().slice(0, 10) || "-"}</TableCell>
                      <TableCell className="text-center">{(b.cutoff_date || "").toString().slice(0, 10) || "-"}</TableCell>
                      <TableCell className="text-right">{b.total_rooms}</TableCell>
                      <TableCell className="text-right">{b.rooms_picked_up}</TableCell>
                      <TableCell className="text-right">{b.washed_count}</TableCell>
                      <TableCell className="text-right">
                        <StatusBadge intent={b.pickup_pct >= 80 ? "success" : b.pickup_pct >= 40 ? "warning" : "neutral"}>
                          {b.pickup_pct}%
                        </StatusBadge>
                      </TableCell>
                      <TableCell className="text-right space-x-1">
                        <Button variant="outline" size="sm" onClick={() => showPickup(b)} data-testid={`button-pickup-${b.id}`}>
                          <TrendingUp className="h-3 w-3 mr-1" /> Kullanım Detayı
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => openWash(b)}
                          disabled={available <= 0}
                          data-testid={`button-wash-${b.id}`}>
                          <DoorOpen className="h-3 w-3 mr-1" /> Oda Bırak
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={pickupOpen} onOpenChange={setPickupOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Kullanım Gelişimi · {pickup?.group_name || "—"}</DialogTitle>
            <DialogDescription>
              Gruba bağlanan odaların günlere göre artışını gösterir. Eğrinin yavaşlaması, ayrılan odaların bir bölümünün kullanılmayabileceğini gösterir.
            </DialogDescription>
          </DialogHeader>
          {pickupLoading || pickup?._stub ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin mr-2" /> {t('cm.pages_BlockManagementPage.yukleniyor_b597b')}
            </div>
          ) : pickup ? (
            <>
              <div className="grid grid-cols-3 gap-4 py-2">
                <div>
                  <div className="text-xs text-muted-foreground">Ayrılan oda</div>
                  <div className="text-lg font-semibold">{pickup.total_rooms}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Kullanılan oda</div>
                  <div className="text-lg font-semibold">{pickup.picked_up}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Kalan</div>
                  <div className="text-lg font-semibold">{pickup.remaining}</div>
                </div>
              </div>
              <div className="h-64 w-full">
                {(pickup.pickup_curve || []).length === 0 ? (
                  <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
                    {t('cm.pages_BlockManagementPage.henuz_pickup_verisi_yok')}
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={pickup.pickup_curve}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip />
                      <Legend />
                      <Line type="monotone" dataKey="rooms" name="Günlük kullanılan" stroke="#94a3b8" strokeWidth={2} />
                      <Line type="monotone" dataKey="cumulative" name="Toplam kullanılan" stroke="#2563eb" strokeWidth={2} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
            </>
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog open={!!washTarget} onOpenChange={(o) => !o && setWashTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Odaları Genel Satışa Aç · {washTarget?.name}</DialogTitle>
            <DialogDescription>
              Grup tarafından kullanılmayacağı kesinleşen odaları genel envantere döndürür. En fazla{" "}
              <span className="font-medium">{washTarget?.available}</span> oda bırakılabilir. Bu işlem gruba atanmış odaları etkilemez.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label htmlFor="wash-count">Genel satışa açılacak oda sayısı</Label>
              <Input id="wash-count" type="number" min={1} max={washTarget?.available}
                value={washCount} onChange={(e) => setWashCount(e.target.value)}
                data-testid="input-wash-count" />
            </div>
            <div>
              <Label htmlFor="wash-note">Not (opsiyonel)</Label>
              <Input id="wash-note" value={washNote} onChange={(e) => setWashNote(e.target.value)}
                placeholder="Örn: Grup kesin oda sayısını düşürdü" data-testid="input-wash-note" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setWashTarget(null)} disabled={washSubmitting}>{t('cm.pages_BlockManagementPage.vazgec')}</Button>
            <Button onClick={submitWash} disabled={washSubmitting} data-testid="button-confirm-wash">
              {washSubmitting && <Loader2 className="h-4 w-4 mr-1 animate-spin" />} Genel Satışa Aç
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Yeni Grup Kontenjanı</DialogTitle>
            <DialogDescription>
              Grup için tarih aralığı, oda tipi ve ayrılacak oda sayısını tanımlayın. Misafir ve rezervasyon kayıtlarını daha sonra Grup Rezervasyonları ekranından yönetin.
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 py-2">
            <div className="col-span-2">
              <Label>{t('cm.pages_BlockManagementPage.grup_adi')}</Label>
              <Input value={createForm.group_name}
                onChange={(e) => setCreateForm({ ...createForm, group_name: e.target.value })}
                placeholder={t('cm.pages_BlockManagementPage.orn_abc_turizm_30_oda_mart')} />
            </div>
            <div>
              <Label>{t('cm.pages_BlockManagementPage.kurulus')}</Label>
              <Input value={createForm.organization}
                onChange={(e) => setCreateForm({ ...createForm, organization: e.target.value })} />
            </div>
            <div>
              <Label>{t('cm.pages_BlockManagementPage.iletisim_adi')}</Label>
              <Input value={createForm.contact_name}
                onChange={(e) => setCreateForm({ ...createForm, contact_name: e.target.value })} />
            </div>
            <div>
              <Label>E-posta</Label>
              <Input type="email" value={createForm.contact_email}
                onChange={(e) => setCreateForm({ ...createForm, contact_email: e.target.value })} />
            </div>
            <div>
              <Label>Telefon</Label>
              <Input value={createForm.contact_phone}
                onChange={(e) => setCreateForm({ ...createForm, contact_phone: e.target.value })} />
            </div>
            <div>
              <Label>{t('cm.pages_BlockManagementPage.giris_87621')}</Label>
              <Input type="date" value={createForm.check_in}
                onChange={(e) => setCreateForm({ ...createForm, check_in: e.target.value })} />
            </div>
            <div>
              <Label>{t('cm.pages_BlockManagementPage.cikis')}</Label>
              <Input type="date" value={createForm.check_out}
                onChange={(e) => setCreateForm({ ...createForm, check_out: e.target.value })} />
            </div>
            <div>
              <Label>Son Bırakma Tarihi</Label>
              <Input type="date" value={createForm.cutoff_date}
                onChange={(e) => setCreateForm({ ...createForm, cutoff_date: e.target.value })} />
            </div>
            <div>
              <Label>Ayrılacak Oda Sayısı *</Label>
              <Input type="number" min={1} value={createForm.total_rooms}
                onChange={(e) => setCreateForm({ ...createForm, total_rooms: e.target.value })} />
            </div>
            <div>
              <Label>{t('cm.pages_BlockManagementPage.oda_tipi')}</Label>
              <Input value={createForm.room_type}
                onChange={(e) => setCreateForm({ ...createForm, room_type: e.target.value })} />
            </div>
            <div>
              <Label>Oda Başına Grup Tarifesi (TL)</Label>
              <Input type="number" min={0} step="0.01" value={createForm.group_rate}
                onChange={(e) => setCreateForm({ ...createForm, group_rate: e.target.value })} />
            </div>
            <div>
              <Label>{t('cm.pages_BlockManagementPage.statu')}</Label>
              <select className="h-10 w-full border rounded-md px-3 text-sm bg-white"
                value={createForm.status}
                onChange={(e) => setCreateForm({ ...createForm, status: e.target.value })}>
                <option value="tentative">Teklif / Beklemede</option>
                <option value="definite">Kesinleşti</option>
              </select>
            </div>
            <div className="col-span-2">
              <Label>{t('cm.pages_BlockManagementPage.ozel_istekler')}</Label>
              <Input value={createForm.special_requirements}
                onChange={(e) => setCreateForm({ ...createForm, special_requirements: e.target.value })}
                placeholder="Örn: 5 bağlantılı oda, kahvaltı dahil" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)} disabled={creating}>{t('cm.pages_BlockManagementPage.vazgec_bf814')}</Button>
            <Button onClick={submitCreate} disabled={creating} data-testid="button-confirm-create">
              {creating && <Loader2 className="h-4 w-4 mr-1 animate-spin" />} Kontenjanı Oluştur
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
