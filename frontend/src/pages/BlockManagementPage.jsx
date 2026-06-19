import { useCallback, useEffect, useState } from "react";
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
  AlertTriangle, RefreshCw, TrendingUp, Trash2, BarChart3, Loader2, Plus,
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge } from "@/components/ui/status-badge";
import { useTranslation } from 'react-i18next';

/**
 * Opera #4 — Block Management.
 * Backend `/api/block-mgmt/*`: cutoff alerts + wash + pickup eğrisi + summary + create.
 *
 * UYARI: Bu sayfanın veri kaynağı `group_blocks` koleksiyonudur ve
 * "Grup Rezervasyonları" sayfasındaki `group_bookings` koleksiyonundan
 * BAĞIMSIZDIR — iki sistem arasında otomatik veri akışı yoktur.
 */

const todayISO = () => new Date().toISOString().slice(0, 10);
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
  const { toast } = useToast();
  const [blocks, setBlocks] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [pickup, setPickup] = useState(null);
  const [pickupOpen, setPickupOpen] = useState(false);
  const [pickupLoading, setPickupLoading] = useState(false);
  const [washTarget, setWashTarget] = useState(null); // {id, name, available}
  const [washCount, setWashCount] = useState("");
  const [washNote, setWashNote] = useState("");
  const [washSubmitting, setWashSubmitting] = useState(false);
  const [loading, setLoading] = useState(false);

  // C6: Yeni Blok Oluştur dialog state
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
        title: "Pickup raporu yüklenemedi",
        description: e?.response?.data?.detail || e.message,
        variant: "destructive",
      });
      setPickupOpen(false);
    } finally {
      setPickupLoading(false);
    }
  }, [toast]);

  const openWash = (blk) => {
    // C4: washed_count'ı da hesaba kat (defensive — backend de hesaba katar)
    const available = Math.max(
      (blk.total_rooms || 0) - (blk.rooms_picked_up || 0),
      0,
    );
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
        title: "Wash başarısız",
        description: e?.response?.data?.detail || e.message,
        variant: "destructive",
      });
    } finally {
      setWashSubmitting(false);
    }
  };

  // C6: yeni blok oluştur
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

  // C10: cutoff aciliyetine göre intent + metin
  const urgencyMeta = (days) => {
    if (days == null) return { intent: "neutral", label: "tarih belirsiz" };
    if (days <= 2) return { intent: "danger", label: "kritik" };
    if (days <= 7) return { intent: "warning", label: "uyarı" };
    return { intent: "info", label: "bilgi" };
  };

  return (
    <div className="container mx-auto p-4 md:p-6 space-y-5 max-w-7xl">
      {/* C7: PageHeader (Sprint A) + Yenile + Yeni Blok */}
      <PageHeader
        icon={BarChart3}
        title={t('cm.pages_BlockManagementPage.grup_blok_kontenjani')}
        subtitle={
          'Grup için ayrılan oda kontenjanları — cutoff uyarıları, wash ve pickup eğrisi. ' +
          'Bireysel rezervasyonlar için "Grup Rezervasyonları" sayfasını kullanın.'
        }
        actions={
          <>
            <Button variant="outline" size="sm" onClick={load} disabled={loading} data-testid="button-refresh-blocks">
              <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? "animate-spin" : ""}`} /> {t('cm.pages_BlockManagementPage.yenile')}
            </Button>
            <Button size="sm" onClick={() => { setCreateForm(emptyCreate()); setCreateOpen(true); }} data-testid="button-new-block">
              <Plus className="h-4 w-4 mr-1.5" /> {t('cm.pages_BlockManagementPage.yeni_blok')}
            </Button>
          </>
        }
      />

      {/* C1: AYRI sistem uyarısı net görünür */}
      <p className="text-xs text-slate-500 -mt-2">
        Not: Bu sayfa <strong>group_blocks</strong> {t('cm.pages_BlockManagementPage.koleksiyonundadir_grup_rezervasyonlari_s')}
      </p>

      {alerts.length > 0 && (
        <Alert variant="destructive" data-testid="alert-cutoff">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t('cm.pages_BlockManagementPage.cutoff_uyarilari_onumuzdeki_14_gun')}</AlertTitle>
          <AlertDescription>
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
                    {a.remaining}/{a.total_rooms} {t('cm.pages_BlockManagementPage.oda_hala_alinmamis')}
                  </li>
                );
              })}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>{t('cm.pages_BlockManagementPage.aktif_bloklar')}</CardTitle>
          <CardDescription>
            {t('cm.pages_BlockManagementPage.beklemede_kesinlesmis_statusundeki_tum_g')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading && blocks.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin mr-2" /> {t('cm.pages_BlockManagementPage.yukleniyor')}
            </div>
          ) : blocks.length === 0 ? (
            // C6: boş durum CTA — Yeni Blok Oluştur butonu
            <div className="text-center py-12 text-muted-foreground">
              <BarChart3 className="h-10 w-10 mx-auto mb-3 text-slate-300" />
              <div className="text-base font-medium text-slate-700">{t('cm.pages_BlockManagementPage.aktif_grup_blogu_yok')}</div>
              <div className="text-sm mt-1">{t('cm.pages_BlockManagementPage.ilk_grup_blogunuzu_olusturarak_cutoff_pi')}</div>
              <Button className="mt-4" onClick={() => { setCreateForm(emptyCreate()); setCreateOpen(true); }}>
                <Plus className="h-4 w-4 mr-1.5" /> {t('cm.pages_BlockManagementPage.yeni_blok_olustur')}
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Grup</TableHead>
                  <TableHead className="text-center">{t('cm.pages_BlockManagementPage.giris')}</TableHead>
                  <TableHead className="text-center">Cutoff</TableHead>
                  <TableHead className="text-right">{t('cm.pages_BlockManagementPage.toplam')}</TableHead>
                  <TableHead className="text-right">Pickup</TableHead>
                  <TableHead className="text-right">Wash</TableHead>
                  <TableHead className="text-right">%</TableHead>
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
                          <TrendingUp className="h-3 w-3 mr-1" /> Pickup
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => openWash(b)}
                          disabled={available <= 0}
                          data-testid={`button-wash-${b.id}`}>
                          <Trash2 className="h-3 w-3 mr-1" /> Wash
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

      {/* Pickup curve modal */}
      <Dialog open={pickupOpen} onOpenChange={setPickupOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{t('cm.pages_BlockManagementPage.pickup_egrisi')} {pickup?.group_name || "—"}</DialogTitle>
            <DialogDescription>
              {t('cm.pages_BlockManagementPage.gunluk_pickup_ve_kumulatif_toplama_picku')}
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
                  <div className="text-xs text-muted-foreground">{t('cm.pages_BlockManagementPage.toplam_29757')}</div>
                  <div className="text-lg font-semibold">{pickup.total_rooms}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">{t('cm.pages_BlockManagementPage.alinan')}</div>
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
                      <Line type="monotone" dataKey="rooms" name="Günlük" stroke="#94a3b8" strokeWidth={2} />
                      <Line type="monotone" dataKey="cumulative" name="Kümülatif" stroke="#2563eb" strokeWidth={2} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
            </>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* Wash dialog */}
      <Dialog open={!!washTarget} onOpenChange={(o) => !o && setWashTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('cm.pages_BlockManagementPage.oda_birak')} {washTarget?.name}</DialogTitle>
            <DialogDescription>
              {t('cm.pages_BlockManagementPage.kullanilmayacagi_anlasilan_odalari_envan')}{" "}
              <span className="font-medium">{washTarget?.available}</span> {t('cm.pages_BlockManagementPage.oda_birakilabilir')}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label htmlFor="wash-count">{t('cm.pages_BlockManagementPage.oda_sayisi')}</Label>
              <Input id="wash-count" type="number" min={1} max={washTarget?.available}
                value={washCount} onChange={(e) => setWashCount(e.target.value)}
                data-testid="input-wash-count" />
            </div>
            <div>
              <Label htmlFor="wash-note">Not (opsiyonel)</Label>
              <Input id="wash-note" value={washNote} onChange={(e) => setWashNote(e.target.value)}
                placeholder={t('cm.pages_BlockManagementPage.orn_grup_yanit_vermedi')} data-testid="input-wash-note" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setWashTarget(null)} disabled={washSubmitting}>{t('cm.pages_BlockManagementPage.vazgec')}</Button>
            <Button onClick={submitWash} disabled={washSubmitting} data-testid="button-confirm-wash">
              {washSubmitting && <Loader2 className="h-4 w-4 mr-1 animate-spin" />} {t('cm.pages_BlockManagementPage.birak')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* C6: Yeni Blok Oluştur dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('cm.pages_BlockManagementPage.yeni_grup_blogu')}</DialogTitle>
            <DialogDescription>
              {t('cm.pages_BlockManagementPage.onceden_ayrilmis_oda_kontenjani_olustur_')}
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
              <Label>Cutoff</Label>
              <Input type="date" value={createForm.cutoff_date}
                onChange={(e) => setCreateForm({ ...createForm, cutoff_date: e.target.value })} />
            </div>
            <div>
              <Label>{t('cm.pages_BlockManagementPage.toplam_oda')}</Label>
              <Input type="number" min={1} value={createForm.total_rooms}
                onChange={(e) => setCreateForm({ ...createForm, total_rooms: e.target.value })} />
            </div>
            <div>
              <Label>{t('cm.pages_BlockManagementPage.oda_tipi')}</Label>
              <Input value={createForm.room_type}
                onChange={(e) => setCreateForm({ ...createForm, room_type: e.target.value })} />
            </div>
            <div>
              <Label>Grup Tarifesi (TL)</Label>
              <Input type="number" min={0} step="0.01" value={createForm.group_rate}
                onChange={(e) => setCreateForm({ ...createForm, group_rate: e.target.value })} />
            </div>
            <div>
              <Label>{t('cm.pages_BlockManagementPage.statu')}</Label>
              <select className="h-10 w-full border rounded-md px-3 text-sm bg-white"
                value={createForm.status}
                onChange={(e) => setCreateForm({ ...createForm, status: e.target.value })}>
                <option value="tentative">{t('cm.pages_BlockManagementPage.beklemede_tentative')}</option>
                <option value="definite">Kesin (definite)</option>
              </select>
            </div>
            <div className="col-span-2">
              <Label>{t('cm.pages_BlockManagementPage.ozel_istekler')}</Label>
              <Input value={createForm.special_requirements}
                onChange={(e) => setCreateForm({ ...createForm, special_requirements: e.target.value })}
                placeholder={t('cm.pages_BlockManagementPage.orn_5_connecting_oda_kahvalti_dahil')} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)} disabled={creating}>{t('cm.pages_BlockManagementPage.vazgec_bf814')}</Button>
            <Button onClick={submitCreate} disabled={creating} data-testid="button-confirm-create">
              {creating && <Loader2 className="h-4 w-4 mr-1 animate-spin" />} {t('cm.pages_BlockManagementPage.olustur')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
