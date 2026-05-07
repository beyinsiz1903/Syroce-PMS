import { useEffect, useState } from "react";
import api from "@/api/axios";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
  AlertTriangle, RefreshCw, TrendingUp, Trash2, BarChart3, Loader2,
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";

/**
 * Opera #4 — Block Management.
 * Backend `/api/block-mgmt/*`: cutoff alerts + wash + pickup eğrisi + summary.
 *
 * Eski sürüm inline style + window.alert/prompt kullanıyordu; bu sürüm
 * shadcn/ui ile temizlendi, wash için modal + recharts ile pickup
 * eğrisi (kümülatif çizgi) eklendi.
 */
export default function BlockManagementPage() {
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

  const load = async () => {
    setLoading(true);
    try {
      const [s, a] = await Promise.all([
        api.get("/api/block-mgmt/summary"),
        api.get("/api/block-mgmt/cutoff-alerts", { params: { days_ahead: 14 } }),
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
  };

  // Mount'ta bir kez yükle; load referansı her render değişir ama
  // sayfa açılışında yalnızca tek seferlik fetch istiyoruz, kullanıcı
  // sonraki yenilemeleri "Yenile" düğmesi ile tetikler.
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  useEffect(() => { load(); }, []);

  const showPickup = async (blk) => {
    setPickupOpen(true);
    setPickupLoading(true);
    setPickup({ group_name: blk.group_name, _stub: true });
    try {
      const { data } = await api.get(`/api/block-mgmt/${blk.id}/pickup`);
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
  };

  const openWash = (blk) => {
    const available = (blk.total_rooms || 0) - (blk.rooms_picked_up || 0);
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
      const { data } = await api.post(`/api/block-mgmt/${washTarget.id}/wash`, {
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

  // Cutoff aciliyetini renklendir: 0-2 gün kritik, 3-7 uyarı, 8+ bilgi.
  const urgencyVariant = (days) => {
    if (days == null) return "secondary";
    if (days <= 2) return "destructive";
    if (days <= 7) return "default";
    return "secondary";
  };

  return (
    <div className="container mx-auto p-6 space-y-4 max-w-7xl">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-2xl font-semibold flex items-center gap-2">
            <BarChart3 className="h-6 w-6" /> Grup Blok Kontenjanı
          </h2>
          <p className="text-sm text-muted-foreground">
            Grup için ayrılan oda kontenjanları — cutoff uyarıları, oda bırakma (wash) ve pickup eğrisi.
            Bireysel rezervasyonlar için “Grup Rezervasyonları” sayfasını kullanın.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading} data-testid="button-refresh-blocks">
          <RefreshCw className={`h-4 w-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Yenile
        </Button>
      </div>

      {alerts.length > 0 && (
        <Alert variant="destructive" data-testid="alert-cutoff">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Cutoff Uyarıları (önümüzdeki 14 gün)</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-5 space-y-0.5 mt-1">
              {alerts.map((a) => (
                <li key={a.id}>
                  <span className="font-medium">{a.group_name}</span>
                  {" — "}
                  <Badge variant={urgencyVariant(a.days_left)} className="mr-1">
                    {a.days_left != null ? `${a.days_left} gün kaldı` : "tarih belirsiz"}
                  </Badge>
                  {a.remaining}/{a.total_rooms} oda hâlâ alınmamış
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Aktif Bloklar</CardTitle>
          <CardDescription>
            Beklemede + kesinleşmiş statüsündeki tüm gruplar.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading && blocks.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin mr-2" /> Yükleniyor…
            </div>
          ) : blocks.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              Aktif grup bloğu yok.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Grup</TableHead>
                  <TableHead className="text-center">Giriş</TableHead>
                  <TableHead className="text-center">Cutoff</TableHead>
                  <TableHead className="text-right">Toplam</TableHead>
                  <TableHead className="text-right">Pickup</TableHead>
                  <TableHead className="text-right">Wash</TableHead>
                  <TableHead className="text-right">%</TableHead>
                  <TableHead className="w-[200px]" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {blocks.map((b) => (
                  <TableRow key={b.id} data-testid={`row-block-${b.id}`}>
                    <TableCell className="font-medium">{b.group_name}</TableCell>
                    <TableCell className="text-center">{b.check_in?.slice(0, 10) || "-"}</TableCell>
                    <TableCell className="text-center">{b.cutoff_date?.slice(0, 10) || "-"}</TableCell>
                    <TableCell className="text-right">{b.total_rooms}</TableCell>
                    <TableCell className="text-right">{b.rooms_picked_up}</TableCell>
                    <TableCell className="text-right">{b.washed_count}</TableCell>
                    <TableCell className="text-right">
                      <Badge variant={b.pickup_pct >= 80 ? "default" : "secondary"}>
                        {b.pickup_pct}%
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right space-x-1">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => showPickup(b)}
                        data-testid={`button-pickup-${b.id}`}
                      >
                        <TrendingUp className="h-3 w-3 mr-1" /> Pickup
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => openWash(b)}
                        disabled={(b.total_rooms - b.rooms_picked_up) <= 0}
                        data-testid={`button-wash-${b.id}`}
                      >
                        <Trash2 className="h-3 w-3 mr-1" /> Wash
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Pickup curve modal */}
      <Dialog open={pickupOpen} onOpenChange={setPickupOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Pickup Eğrisi · {pickup?.group_name || "—"}</DialogTitle>
            <DialogDescription>
              Günlük pickup ve kümülatif toplama. Cutoff'a yaklaşırken eğrinin
              düz hat verdiği bloklar wash adayıdır.
            </DialogDescription>
          </DialogHeader>
          {pickupLoading || pickup?._stub ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin mr-2" /> Yükleniyor…
            </div>
          ) : pickup ? (
            <>
              <div className="grid grid-cols-3 gap-4 py-2">
                <div>
                  <div className="text-xs text-muted-foreground">Toplam</div>
                  <div className="text-lg font-semibold">{pickup.total_rooms}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Alınan</div>
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
                    Henüz pickup verisi yok.
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
            <DialogTitle>Oda Bırak · {washTarget?.name}</DialogTitle>
            <DialogDescription>
              Kullanılmayacağı anlaşılan odaları envantere geri verir. En fazla{" "}
              <span className="font-medium">{washTarget?.available}</span> oda bırakılabilir.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label htmlFor="wash-count">Oda sayısı</Label>
              <Input
                id="wash-count"
                type="number"
                min={1}
                max={washTarget?.available}
                value={washCount}
                onChange={(e) => setWashCount(e.target.value)}
                data-testid="input-wash-count"
              />
            </div>
            <div>
              <Label htmlFor="wash-note">Not (opsiyonel)</Label>
              <Input
                id="wash-note"
                value={washNote}
                onChange={(e) => setWashNote(e.target.value)}
                placeholder="Örn: Grup yanıt vermedi"
                data-testid="input-wash-note"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setWashTarget(null)} disabled={washSubmitting}>
              Vazgeç
            </Button>
            <Button onClick={submitWash} disabled={washSubmitting} data-testid="button-confirm-wash">
              {washSubmitting && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
              Bırak
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
