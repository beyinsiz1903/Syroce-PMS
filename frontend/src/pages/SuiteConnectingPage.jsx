import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/api/axios";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useToast } from "@/hooks/use-toast";
import {
  ArrowLeft, DoorOpen, Info, Link2, Loader2, Plus, RefreshCw, Shield, Trash2,
} from "lucide-react";

export default function SuiteConnectingPage({ user }) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const roles = useMemo(
    () => [...(user?.roles || []), user?.role].filter(Boolean).map((role) => String(role).toLowerCase()),
    [user?.role, user?.roles],
  );
  const canManage = roles.some((role) => ["admin", "supervisor", "super_admin"].includes(role));

  const [rooms, setRooms] = useState([]);
  const [pairs, setPairs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [deletePair, setDeletePair] = useState(null);
  const [pairForm, setPairForm] = useState({ room_a_id: "", room_b_id: "", note: "" });

  const handleError = useCallback((title, error) => {
    toast({
      title,
      description: error?.response?.data?.detail || error?.message || "İşlem tamamlanamadı.",
      variant: "destructive",
    });
  }, [toast]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [roomsResponse, pairsResponse] = await Promise.all([
        api.get("/pms/rooms"),
        api.get("/suite-connecting/connecting"),
      ]);
      setRooms(Array.isArray(roomsResponse.data) ? roomsResponse.data : (roomsResponse.data?.items || []));
      setPairs(Array.isArray(pairsResponse.data) ? pairsResponse.data : []);
    } catch (error) {
      handleError("Bağlantılı oda tanımları yüklenemedi", error);
    } finally {
      setLoading(false);
    }
  }, [handleError]);

  useEffect(() => {
    if (canManage) loadData();
  }, [canManage, loadData]);

  const roomLabel = useCallback((id) => {
    const room = rooms.find((candidate) => (candidate.id || candidate._id) === id);
    if (!room) return id ? String(id).slice(0, 8) : "—";
    const number = room.room_number || room.number || String(id).slice(0, 6);
    return `${number}${room.room_type ? ` · ${room.room_type}` : ""}`;
  }, [rooms]);

  const connectedRoomIds = useMemo(
    () => new Set(pairs.flatMap((pair) => [pair.room_a_id, pair.room_b_id]).filter(Boolean)),
    [pairs],
  );
  const connectedRoomCount = connectedRoomIds.size;

  const addPair = async (event) => {
    event.preventDefault();
    if (!pairForm.room_a_id || !pairForm.room_b_id) return;
    if (pairForm.room_a_id === pairForm.room_b_id) {
      toast({ title: "İki farklı oda seçin", variant: "destructive" });
      return;
    }
    setSubmitting(true);
    try {
      await api.post("/suite-connecting/connecting", {
        ...pairForm,
        note: pairForm.note.trim() || null,
      });
      toast({ title: "Bağlantılı oda tanımı kaydedildi" });
      setPairForm({ room_a_id: "", room_b_id: "", note: "" });
      await loadData();
    } catch (error) {
      handleError("Bağlantı kaydedilemedi", error);
    } finally {
      setSubmitting(false);
    }
  };

  const confirmDeletePair = async () => {
    if (!deletePair) return;
    try {
      await api.delete(`/suite-connecting/connecting/${deletePair.id}`);
      toast({ title: "Bağlantılı oda tanımı kaldırıldı" });
      setDeletePair(null);
      await loadData();
    } catch (error) {
      handleError("Bağlantı kaldırılamadı", error);
    }
  };

  if (!canManage) {
    return (
      <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4 px-6 text-center">
        <Shield className="h-14 w-14 text-rose-500" />
        <h1 className="text-xl font-semibold">Bu ayarı görüntüleme yetkiniz yok</h1>
        <p className="max-w-xl text-sm text-muted-foreground">
          Bağlantılı oda tanımlarını yalnızca tesis yöneticileri ve süpervizörler değiştirebilir.
        </p>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-7xl space-y-5 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="-ml-2 text-muted-foreground"
            onClick={() => navigate("/app/settings?tab=rooms")}
          >
            <ArrowLeft className="mr-1.5 h-4 w-4" /> Oda yönetimine dön
          </Button>
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-semibold">
              <DoorOpen className="h-6 w-6 text-indigo-600" /> Bağlantılı Oda Tanımları
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Aralarında fiziksel geçiş kapısı bulunan oda çiftlerini tesis envanterinde tanımlayın.
            </p>
          </div>
        </div>
        <Button type="button" variant="outline" onClick={loadData} disabled={loading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Yenile
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Card><CardContent className="p-5"><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Tanımlı çift</p><p className="mt-1 text-3xl font-semibold">{pairs.length}</p></CardContent></Card>
        <Card><CardContent className="p-5"><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Bağlantılı oda</p><p className="mt-1 text-3xl font-semibold">{connectedRoomCount}</p></CardContent></Card>
        <Card><CardContent className="p-5"><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Bağlantısız oda</p><p className="mt-1 text-3xl font-semibold">{Math.max(rooms.length - connectedRoomCount, 0)}</p></CardContent></Card>
      </div>

      <div className="flex gap-3 rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-950">
        <Info className="mt-0.5 h-5 w-5 shrink-0 text-sky-600" />
        <div>
          <p className="font-medium">Bu alan fiziksel oda envanteri içindir.</p>
          <p className="mt-0.5 text-sky-800">Bağlantı tanımlamak oda fiyatını, müsaitliği veya kanal satış envanterini otomatik olarak değiştirmez.</p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Yeni oda çifti</CardTitle>
          <CardDescription>Geçiş kapısının iki tarafındaki odaları seçin ve isterseniz operasyon notu ekleyin.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={addPair} className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_1fr_1.2fr_auto] lg:items-end">
            <div className="space-y-2">
              <Label>Birinci oda</Label>
              <Select value={pairForm.room_a_id} onValueChange={(value) => setPairForm((current) => ({ ...current, room_a_id: value }))}>
                <SelectTrigger data-testid="select-pair-a"><SelectValue placeholder="Oda seçin" /></SelectTrigger>
                <SelectContent>{rooms.map((room) => { const id = room.id || room._id; return <SelectItem key={id} value={id}>{roomLabel(id)}</SelectItem>; })}</SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>İkinci oda</Label>
              <Select value={pairForm.room_b_id} onValueChange={(value) => setPairForm((current) => ({ ...current, room_b_id: value }))}>
                <SelectTrigger data-testid="select-pair-b"><SelectValue placeholder="Oda seçin" /></SelectTrigger>
                <SelectContent>{rooms.filter((room) => (room.id || room._id) !== pairForm.room_a_id).map((room) => { const id = room.id || room._id; return <SelectItem key={id} value={id}>{roomLabel(id)}</SelectItem>; })}</SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="connection-note">Operasyon notu</Label>
              <Input id="connection-note" value={pairForm.note} onChange={(event) => setPairForm((current) => ({ ...current, note: event.target.value }))} placeholder="Örn. ara kapı anahtarı resepsiyonda" maxLength={240} />
            </div>
            <Button type="submit" disabled={submitting || !pairForm.room_a_id || !pairForm.room_b_id} data-testid="button-pair-add">
              {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />} Bağlantı ekle
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Tanımlı bağlantılar</CardTitle>
          <CardDescription>Oda çiftleri tek merkezden yönetilir; aynı tanımı oda kartlarında ayrıca girmeniz gerekmez.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow><TableHead>Birinci oda</TableHead><TableHead>İkinci oda</TableHead><TableHead>Operasyon notu</TableHead><TableHead className="w-[72px] text-right">İşlem</TableHead></TableRow></TableHeader>
              <TableBody>
                {pairs.length === 0 ? (
                  <TableRow><TableCell colSpan={4} className="py-12 text-center text-muted-foreground"><Link2 className="mx-auto mb-3 h-9 w-9 opacity-30" />Henüz bağlantılı oda çifti tanımlanmamış.</TableCell></TableRow>
                ) : pairs.map((pair) => (
                  <TableRow key={pair.id}>
                    <TableCell><Badge variant="secondary"><DoorOpen className="mr-1.5 h-3.5 w-3.5" />{roomLabel(pair.room_a_id)}</Badge></TableCell>
                    <TableCell><Badge variant="secondary"><DoorOpen className="mr-1.5 h-3.5 w-3.5" />{roomLabel(pair.room_b_id)}</Badge></TableCell>
                    <TableCell className="max-w-md whitespace-normal text-sm text-muted-foreground">{pair.note || "—"}</TableCell>
                    <TableCell className="text-right"><Button type="button" size="icon" variant="ghost" className="text-rose-600 hover:bg-rose-50 hover:text-rose-700" aria-label={`${roomLabel(pair.room_a_id)} ve ${roomLabel(pair.room_b_id)} bağlantısını kaldır`} onClick={() => setDeletePair(pair)}><Trash2 className="h-4 w-4" /></Button></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Dialog open={Boolean(deletePair)} onOpenChange={(open) => !open && setDeletePair(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Oda bağlantısını kaldır</DialogTitle>
            <DialogDescription>{deletePair ? `${roomLabel(deletePair.room_a_id)} ile ${roomLabel(deletePair.room_b_id)} arasındaki fiziksel bağlantı tanımı kaldırılacak.` : ""}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setDeletePair(null)}>Vazgeç</Button>
            <Button type="button" variant="destructive" onClick={confirmDeletePair}>Bağlantıyı kaldır</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
