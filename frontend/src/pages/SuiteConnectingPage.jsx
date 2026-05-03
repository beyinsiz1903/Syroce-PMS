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
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { Building2, Plus, RefreshCw, Trash2, DoorOpen, Loader2, Link2 } from "lucide-react";

/**
 * Opera #9 — Suite & Connecting Rooms.
 * - Suite: master + bileşenler (satılınca tüm bileşenler bloke).
 * - Connecting: iki oda arası kapı bağlı çift.
 */

export default function SuiteConnectingPage() {
  const { toast } = useToast();
  const [tab, setTab] = useState("suites");

  const [rooms, setRooms] = useState([]);
  const [suites, setSuites] = useState([]);
  const [pairs, setPairs] = useState([]);
  const [loading, setLoading] = useState(false);

  const [suiteForm, setSuiteForm] = useState({
    name: "", master_room_id: "", component_room_ids: [], description: "",
  });
  const [pairForm, setPairForm] = useState({ room_a_id: "", room_b_id: "", note: "" });

  const [submitting, setSubmitting] = useState(false);
  const [deleteSuite, setDeleteSuite] = useState(null);
  const [deletePair, setDeletePair] = useState(null);

  const handleErr = useCallback((title, e) => {
    toast({
      title,
      description: e?.response?.data?.detail || e.message,
      variant: "destructive",
    });
  }, [toast]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2, r3] = await Promise.all([
        api.get("/api/rooms").catch(() => ({ data: [] })),
        api.get("/api/suite-connecting/suites"),
        api.get("/api/suite-connecting/connecting"),
      ]);
      const roomList = Array.isArray(r1.data) ? r1.data : (r1.data?.items || []);
      setRooms(roomList);
      setSuites(r2.data || []);
      setPairs(r3.data || []);
    } catch (e) { handleErr("Yüklenemedi", e); }
    finally { setLoading(false); }
  }, [handleErr]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const roomLabel = (id) => {
    const r = rooms.find((x) => (x.id || x._id) === id);
    return r ? `${r.room_number || r.number || id.slice(0, 6)}${r.room_type ? ` · ${r.room_type}` : ""}` : id.slice(0, 8);
  };

  const toggleComponent = (rid) => {
    const arr = suiteForm.component_room_ids;
    setSuiteForm({
      ...suiteForm,
      component_room_ids: arr.includes(rid) ? arr.filter((x) => x !== rid) : [...arr, rid],
    });
  };

  const addSuite = async (e) => {
    e.preventDefault();
    if (!suiteForm.master_room_id) {
      toast({ title: "Master oda seçin", variant: "destructive" });
      return;
    }
    setSubmitting(true);
    try {
      await api.post("/api/suite-connecting/suites", {
        ...suiteForm,
        description: suiteForm.description || null,
      });
      toast({ title: "Suite eklendi" });
      setSuiteForm({ name: "", master_room_id: "", component_room_ids: [], description: "" });
      loadAll();
    } catch (e) { handleErr("Eklenemedi", e); }
    finally { setSubmitting(false); }
  };

  const addPair = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.post("/api/suite-connecting/connecting", {
        ...pairForm,
        note: pairForm.note || null,
      });
      toast({ title: "Bağlantı eklendi" });
      setPairForm({ room_a_id: "", room_b_id: "", note: "" });
      loadAll();
    } catch (e) { handleErr("Eklenemedi", e); }
    finally { setSubmitting(false); }
  };

  const confirmDeleteSuite = async () => {
    if (!deleteSuite) return;
    try {
      await api.delete(`/api/suite-connecting/suites/${deleteSuite.id}`);
      toast({ title: "Suite silindi" });
      setDeleteSuite(null);
      loadAll();
    } catch (e) { handleErr("Silinemedi", e); }
  };

  const confirmDeletePair = async () => {
    if (!deletePair) return;
    try {
      await api.delete(`/api/suite-connecting/connecting/${deletePair.id}`);
      toast({ title: "Bağlantı silindi" });
      setDeletePair(null);
      loadAll();
    } catch (e) { handleErr("Silinemedi", e); }
  };

  return (
    <div className="container mx-auto p-6 space-y-4 max-w-7xl">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-2xl font-semibold flex items-center gap-2">
            <Building2 className="h-6 w-6" /> Suite & Connecting Rooms
          </h2>
          <p className="text-sm text-muted-foreground">
            Suite tanımları (master + bileşenler) ve oda kapı bağlantıları.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={loadAll} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Yenile
        </Button>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="suites" data-testid="tab-suites">Suite Tanımları</TabsTrigger>
          <TabsTrigger value="connecting" data-testid="tab-connecting">Connecting Pairs</TabsTrigger>
        </TabsList>

        <TabsContent value="suites">
          <Card>
            <CardHeader>
              <CardTitle>Suite Tanımları</CardTitle>
              <CardDescription>
                Bir master oda + bileşen odalar. Suite satıldığında tüm bileşenler bloke edilir.
                Bir oda yalnızca bir suite'te kullanılabilir.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={addSuite} className="grid grid-cols-1 md:grid-cols-3 gap-3 items-start">
                <div>
                  <Label>Suite Adı</Label>
                  <Input
                    value={suiteForm.name}
                    onChange={(e) => setSuiteForm({ ...suiteForm, name: e.target.value })}
                    placeholder="Presidential Suite" required
                    data-testid="input-suite-name"
                  />
                </div>
                <div>
                  <Label>Master Oda</Label>
                  <Select
                    value={suiteForm.master_room_id}
                    onValueChange={(v) => setSuiteForm({ ...suiteForm, master_room_id: v })}
                  >
                    <SelectTrigger data-testid="select-suite-master"><SelectValue placeholder="Oda seç" /></SelectTrigger>
                    <SelectContent>
                      {rooms.map((r) => (
                        <SelectItem key={r.id || r._id} value={r.id || r._id}>{roomLabel(r.id || r._id)}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Açıklama</Label>
                  <Input
                    value={suiteForm.description}
                    onChange={(e) => setSuiteForm({ ...suiteForm, description: e.target.value })}
                  />
                </div>
                <div className="md:col-span-3">
                  <Label>Bileşen Odalar (çoklu seçim)</Label>
                  <div className="flex flex-wrap gap-1 p-2 border rounded max-h-32 overflow-y-auto">
                    {rooms.length === 0 ? (
                      <span className="text-xs text-muted-foreground">Oda bulunamadı.</span>
                    ) : rooms.filter((r) => (r.id || r._id) !== suiteForm.master_room_id).map((r) => {
                      const id = r.id || r._id;
                      const on = suiteForm.component_room_ids.includes(id);
                      return (
                        <Button
                          key={id} type="button" size="sm"
                          variant={on ? "default" : "outline"}
                          onClick={() => toggleComponent(id)}
                        >
                          {roomLabel(id)}
                        </Button>
                      );
                    })}
                  </div>
                </div>
                <Button type="submit" disabled={submitting} data-testid="button-suite-add">
                  {submitting ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Plus className="h-4 w-4 mr-1" />}
                  Suite Ekle
                </Button>
              </form>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ad</TableHead>
                    <TableHead>Master</TableHead>
                    <TableHead>Bileşenler</TableHead>
                    <TableHead>Toplam Oda</TableHead>
                    <TableHead className="w-[60px]" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {suites.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-muted-foreground py-6">
                        Henüz suite tanımı yok.
                      </TableCell>
                    </TableRow>
                  ) : suites.map((s) => (
                    <TableRow key={s.id}>
                      <TableCell className="font-medium">{s.name}</TableCell>
                      <TableCell><Badge>{roomLabel(s.master_room_id)}</Badge></TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {(s.component_room_ids || []).map((rid) => (
                            <Badge key={rid} variant="secondary">{roomLabel(rid)}</Badge>
                          ))}
                        </div>
                      </TableCell>
                      <TableCell>{1 + (s.component_room_ids?.length || 0)}</TableCell>
                      <TableCell>
                        <Button size="sm" variant="ghost" onClick={() => setDeleteSuite({ id: s.id, name: s.name })}>
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

        <TabsContent value="connecting">
          <Card>
            <CardHeader>
              <CardTitle>Connecting Room Çiftleri</CardTitle>
              <CardDescription>
                Yan yana kapı bağlı odalar. Aile rezervasyonları ve housekeeping için bilgi.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={addPair} className="grid grid-cols-1 md:grid-cols-4 gap-2 items-end">
                <div>
                  <Label>Oda A</Label>
                  <Select value={pairForm.room_a_id} onValueChange={(v) => setPairForm({ ...pairForm, room_a_id: v })}>
                    <SelectTrigger data-testid="select-pair-a"><SelectValue placeholder="Oda A" /></SelectTrigger>
                    <SelectContent>
                      {rooms.map((r) => <SelectItem key={r.id || r._id} value={r.id || r._id}>{roomLabel(r.id || r._id)}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Oda B</Label>
                  <Select value={pairForm.room_b_id} onValueChange={(v) => setPairForm({ ...pairForm, room_b_id: v })}>
                    <SelectTrigger data-testid="select-pair-b"><SelectValue placeholder="Oda B" /></SelectTrigger>
                    <SelectContent>
                      {rooms.filter((r) => (r.id || r._id) !== pairForm.room_a_id).map((r) =>
                        <SelectItem key={r.id || r._id} value={r.id || r._id}>{roomLabel(r.id || r._id)}</SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Not</Label>
                  <Input
                    value={pairForm.note}
                    onChange={(e) => setPairForm({ ...pairForm, note: e.target.value })}
                    placeholder="opsiyonel"
                  />
                </div>
                <Button type="submit" disabled={submitting || !pairForm.room_a_id || !pairForm.room_b_id} data-testid="button-pair-add">
                  {submitting ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Plus className="h-4 w-4 mr-1" />}
                  Bağlantı Ekle
                </Button>
              </form>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Oda A</TableHead>
                    <TableHead>Oda B</TableHead>
                    <TableHead>Not</TableHead>
                    <TableHead className="w-[60px]" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {pairs.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} className="text-center text-muted-foreground py-6">
                        Bağlantı yok.
                      </TableCell>
                    </TableRow>
                  ) : pairs.map((p) => (
                    <TableRow key={p.id}>
                      <TableCell><Badge variant="secondary"><DoorOpen className="h-3 w-3 mr-1" />{roomLabel(p.room_a_id)}</Badge></TableCell>
                      <TableCell><Badge variant="secondary"><Link2 className="h-3 w-3 mr-1" />{roomLabel(p.room_b_id)}</Badge></TableCell>
                      <TableCell className="text-xs text-muted-foreground">{p.note || "—"}</TableCell>
                      <TableCell>
                        <Button size="sm" variant="ghost" onClick={() => setDeletePair({ id: p.id })}>
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
      </Tabs>

      <Dialog open={!!deleteSuite} onOpenChange={(o) => !o && setDeleteSuite(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Suite sil?</DialogTitle>
            <DialogDescription>"{deleteSuite?.name}" pasife alınacak.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteSuite(null)}>Vazgeç</Button>
            <Button variant="destructive" onClick={confirmDeleteSuite}>Sil</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deletePair} onOpenChange={(o) => !o && setDeletePair(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Bağlantıyı sil?</DialogTitle>
            <DialogDescription>Bu connecting pair pasife alınacak.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletePair(null)}>Vazgeç</Button>
            <Button variant="destructive" onClick={confirmDeletePair}>Sil</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
