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
import { ChefHat, Plus, RefreshCw, Trash2, Save, Loader2, Leaf, Wheat } from "lucide-react";

/**
 * Opera #7 — Catering Menu.
 * - Menu items kataloğu (CRUD, soft-delete)
 * - Function booking'e menü atama: kalemler × headcount → toplam
 */

const CATS = [
  { v: "breakfast", l: "Kahvaltı" },
  { v: "lunch", l: "Öğle Yemeği" },
  { v: "dinner", l: "Akşam Yemeği" },
  { v: "coffee_break", l: "Coffee Break" },
  { v: "cocktail", l: "Cocktail" },
  { v: "buffet", l: "Açık Büfe" },
  { v: "plated", l: "Servis Tabağı" },
];
const catLabel = (v) => CATS.find((c) => c.v === v)?.l || v;

export default function CateringMenuPage() {
  const { toast } = useToast();
  const [tab, setTab] = useState("items");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filterCat, setFilterCat] = useState("all");

  const [form, setForm] = useState({
    code: "", name: "", category: "lunch", price_per_person: "",
    currency: "TRY", description: "", allergens: "",
    is_vegan: false, is_vegetarian: false, is_gluten_free: false,
    min_headcount: 1,
  });
  const [submitting, setSubmitting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const [bookings, setBookings] = useState([]);
  const [selectedBookingId, setSelectedBookingId] = useState("");
  const [bookingMenus, setBookingMenus] = useState({ lines: [], total: 0, currency: "TRY" });
  const [editLines, setEditLines] = useState([]);
  const [savingBooking, setSavingBooking] = useState(false);

  const handleErr = useCallback((title, e) => {
    toast({
      title,
      description: e?.response?.data?.detail || e.message,
      variant: "destructive",
    });
  }, [toast]);

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const params = filterCat !== "all" ? { category: filterCat } : {};
      const r = await api.get("/api/catering/menu-items", { params });
      setItems(r.data || []);
    } catch (e) { handleErr("Menü yüklenemedi", e); }
    finally { setLoading(false); }
  }, [filterCat, handleErr]);

  const loadBookings = useCallback(async () => {
    try {
      const r = await api.get("/api/function-space/bookings");
      setBookings(r.data || []);
    } catch (e) { handleErr("Booking listesi alınamadı", e); }
  }, [handleErr]);

  useEffect(() => { loadItems(); }, [loadItems]);
  useEffect(() => { loadBookings(); }, [loadBookings]);

  const addItem = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.post("/api/catering/menu-items", {
        ...form,
        price_per_person: Number(form.price_per_person) || 0,
        min_headcount: Number(form.min_headcount) || 1,
        allergens: form.allergens.split(",").map((s) => s.trim()).filter(Boolean),
        description: form.description || null,
      });
      toast({ title: "Menü kalemi eklendi" });
      setForm({
        code: "", name: "", category: "lunch", price_per_person: "",
        currency: "TRY", description: "", allergens: "",
        is_vegan: false, is_vegetarian: false, is_gluten_free: false,
        min_headcount: 1,
      });
      loadItems();
    } catch (e) { handleErr("Eklenemedi", e); }
    finally { setSubmitting(false); }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await api.delete(`/api/catering/menu-items/${deleteTarget.id}`);
      toast({ title: "Silindi" });
      setDeleteTarget(null);
      loadItems();
    } catch (e) { handleErr("Silinemedi", e); }
  };

  const loadBookingMenus = async (bookingId) => {
    if (!bookingId) return;
    try {
      const r = await api.get(`/api/catering/bookings/${bookingId}`);
      setBookingMenus(r.data);
      setEditLines((r.data.lines || []).map((l) => ({
        menu_item_id: l.menu_item_id,
        headcount: l.headcount,
        note: l.note || "",
      })));
    } catch (e) { handleErr("Booking menü yüklenemedi", e); }
  };

  const addLine = () => setEditLines([...editLines, { menu_item_id: "", headcount: 10, note: "" }]);
  const removeLine = (i) => setEditLines(editLines.filter((_, idx) => idx !== i));
  const updateLine = (i, k, v) => {
    const next = [...editLines];
    next[i] = { ...next[i], [k]: v };
    setEditLines(next);
  };

  const saveBookingMenus = async () => {
    if (!selectedBookingId) return;
    setSavingBooking(true);
    try {
      const lines = editLines
        .filter((l) => l.menu_item_id)
        .map((l) => ({
          menu_item_id: l.menu_item_id,
          headcount: Number(l.headcount) || 1,
          note: l.note || null,
        }));
      await api.put(`/api/catering/bookings/${selectedBookingId}`, { lines });
      toast({ title: "Menü atamaları kaydedildi" });
      loadBookingMenus(selectedBookingId);
    } catch (e) { handleErr("Kaydedilemedi", e); }
    finally { setSavingBooking(false); }
  };

  const calcTotal = () => {
    let t = 0;
    const currencies = new Set();
    for (const l of editLines) {
      const it = items.find((i) => i.id === l.menu_item_id);
      if (it) {
        t += (Number(it.price_per_person) || 0) * (Number(l.headcount) || 0);
        currencies.add(it.currency || "TRY");
      }
    }
    return { total: t, currency: currencies.size === 1 ? [...currencies][0] : "MIXED", mixed: currencies.size > 1 };
  };

  return (
    <div className="container mx-auto p-6 space-y-4 max-w-7xl">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-2xl font-semibold flex items-center gap-2">
            <ChefHat className="h-6 w-6" /> Catering Menü
          </h2>
          <p className="text-sm text-muted-foreground">
            Menü kataloğu ve function space booking'lerine menü atama (kişi başı × headcount).
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={loadItems} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Yenile
        </Button>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="items" data-testid="tab-catering-items">Menü Kalemleri</TabsTrigger>
          <TabsTrigger value="bookings" data-testid="tab-catering-bookings">Booking Menüleri</TabsTrigger>
        </TabsList>

        <TabsContent value="items">
          <Card>
            <CardHeader>
              <CardTitle>Menü Kataloğu</CardTitle>
              <CardDescription>
                Function space etkinliklerinde sunulacak menü kalemleri. Kod tenant içinde benzersiz olmalı.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={addItem} className="grid grid-cols-1 md:grid-cols-6 gap-2 items-end">
                <div>
                  <Label>Kod</Label>
                  <Input
                    value={form.code}
                    onChange={(e) => setForm({ ...form, code: e.target.value })}
                    pattern="[A-Za-z0-9_\-]+" required
                    placeholder="LUNCH-A"
                    data-testid="input-catering-code"
                  />
                </div>
                <div className="md:col-span-2">
                  <Label>Ad</Label>
                  <Input
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    required data-testid="input-catering-name"
                  />
                </div>
                <div>
                  <Label>Kategori</Label>
                  <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
                    <SelectTrigger data-testid="select-catering-cat"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {CATS.map((c) => <SelectItem key={c.v} value={c.v}>{c.l}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Kişi Başı (₺)</Label>
                  <Input
                    type="number" step="0.01" min="0"
                    value={form.price_per_person}
                    onChange={(e) => setForm({ ...form, price_per_person: e.target.value })}
                    required data-testid="input-catering-price"
                  />
                </div>
                <div>
                  <Label>Min Kişi</Label>
                  <Input
                    type="number" min="1"
                    value={form.min_headcount}
                    onChange={(e) => setForm({ ...form, min_headcount: e.target.value })}
                  />
                </div>
                <div className="md:col-span-3">
                  <Label>Açıklama</Label>
                  <Input
                    value={form.description}
                    onChange={(e) => setForm({ ...form, description: e.target.value })}
                  />
                </div>
                <div className="md:col-span-3">
                  <Label>Alerjenler (virgüllü)</Label>
                  <Input
                    value={form.allergens}
                    onChange={(e) => setForm({ ...form, allergens: e.target.value })}
                    placeholder="gluten, süt, fındık"
                  />
                </div>
                <div className="flex items-center gap-2 h-10">
                  <Switch checked={form.is_vegan} onCheckedChange={(c) => setForm({ ...form, is_vegan: c })} />
                  <Label>Vegan</Label>
                </div>
                <div className="flex items-center gap-2 h-10">
                  <Switch checked={form.is_vegetarian} onCheckedChange={(c) => setForm({ ...form, is_vegetarian: c })} />
                  <Label>Vejetaryen</Label>
                </div>
                <div className="flex items-center gap-2 h-10">
                  <Switch checked={form.is_gluten_free} onCheckedChange={(c) => setForm({ ...form, is_gluten_free: c })} />
                  <Label>Glutensiz</Label>
                </div>
                <Button type="submit" disabled={submitting} data-testid="button-catering-add">
                  {submitting ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Plus className="h-4 w-4 mr-1" />}
                  Ekle
                </Button>
              </form>

              <div className="flex items-center gap-2">
                <Label>Filtre:</Label>
                <Select value={filterCat} onValueChange={setFilterCat}>
                  <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Tümü</SelectItem>
                    {CATS.map((c) => <SelectItem key={c.v} value={c.v}>{c.l}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Kod</TableHead>
                    <TableHead>Ad</TableHead>
                    <TableHead>Kategori</TableHead>
                    <TableHead className="text-right">Kişi Başı</TableHead>
                    <TableHead>Diyet/Alerjen</TableHead>
                    <TableHead className="w-[60px]" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} className="text-center text-muted-foreground py-6">
                        Menü kalemi yok.
                      </TableCell>
                    </TableRow>
                  ) : items.map((it) => (
                    <TableRow key={it.id}>
                      <TableCell><code className="text-xs">{it.code}</code></TableCell>
                      <TableCell className="font-medium">{it.name}</TableCell>
                      <TableCell><Badge variant="secondary">{catLabel(it.category)}</Badge></TableCell>
                      <TableCell className="text-right">
                        {Number(it.price_per_person).toFixed(2)} {it.currency}
                      </TableCell>
                      <TableCell className="text-xs">
                        <div className="flex gap-1 flex-wrap items-center">
                          {it.is_vegan && <Badge variant="outline" className="bg-green-50"><Leaf className="h-3 w-3 mr-1" />Vegan</Badge>}
                          {it.is_vegetarian && !it.is_vegan && <Badge variant="outline">Vej</Badge>}
                          {it.is_gluten_free && <Badge variant="outline" className="bg-amber-50"><Wheat className="h-3 w-3 mr-1" />GF</Badge>}
                          {it.allergens?.length > 0 && (
                            <span className="text-muted-foreground">⚠ {it.allergens.join(", ")}</span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Button size="sm" variant="ghost" onClick={() => setDeleteTarget({ id: it.id, name: it.name })}>
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

        <TabsContent value="bookings">
          <Card>
            <CardHeader>
              <CardTitle>Booking Menü Atama</CardTitle>
              <CardDescription>
                Function booking seç, menü kalemlerini ekle, kişi sayısı gir. Toplam otomatik hesaplanır.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2 items-end">
                <div className="flex-1">
                  <Label>Function Booking</Label>
                  <Select value={selectedBookingId} onValueChange={(v) => { setSelectedBookingId(v); loadBookingMenus(v); }}>
                    <SelectTrigger data-testid="select-catering-booking">
                      <SelectValue placeholder="Booking seç" />
                    </SelectTrigger>
                    <SelectContent>
                      {bookings.length === 0 ? (
                        <div className="p-2 text-xs text-muted-foreground">Booking yok</div>
                      ) : bookings.map((b) => (
                        <SelectItem key={b.id} value={b.id}>
                          {b.event_name || b.title || b.id.slice(0, 8)} — {b.starts_at?.slice(0, 10) || "—"}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {selectedBookingId && (
                <>
                  <div className="space-y-2">
                    {editLines.map((ln, i) => (
                      <div key={i} className="grid grid-cols-12 gap-2 items-end border rounded p-2">
                        <div className="col-span-5">
                          <Label>Menü</Label>
                          <Select value={ln.menu_item_id} onValueChange={(v) => updateLine(i, "menu_item_id", v)}>
                            <SelectTrigger><SelectValue placeholder="Menü seç" /></SelectTrigger>
                            <SelectContent>
                              {items.map((it) => (
                                <SelectItem key={it.id} value={it.id}>
                                  {it.name} — {Number(it.price_per_person).toFixed(2)} {it.currency}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="col-span-2">
                          <Label>Kişi</Label>
                          <Input
                            type="number" min="1"
                            value={ln.headcount}
                            onChange={(e) => updateLine(i, "headcount", e.target.value)}
                          />
                        </div>
                        <div className="col-span-4">
                          <Label>Not</Label>
                          <Input
                            value={ln.note}
                            onChange={(e) => updateLine(i, "note", e.target.value)}
                            placeholder="opsiyonel"
                          />
                        </div>
                        <div className="col-span-1">
                          <Button size="sm" variant="ghost" onClick={() => removeLine(i)}>
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      </div>
                    ))}
                    <Button variant="outline" size="sm" onClick={addLine} data-testid="button-catering-add-line">
                      <Plus className="h-4 w-4 mr-1" /> Kalem Ekle
                    </Button>
                  </div>

                  <div className="flex items-center justify-between border-t pt-3">
                    {(() => {
                      const c = calcTotal();
                      return (
                        <div className={`text-lg font-semibold ${c.mixed ? "text-red-600" : ""}`}>
                          {c.mixed
                            ? "Karışık para birimi — kaydetme reddedilecek"
                            : `Tahmini Toplam: ${c.total.toFixed(2)} ${c.currency}`}
                        </div>
                      );
                    })()}
                    <Button onClick={saveBookingMenus} disabled={savingBooking || calcTotal().mixed} data-testid="button-catering-save-booking">
                      {savingBooking ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}
                      Kaydet
                    </Button>
                  </div>

                  {bookingMenus.lines?.length > 0 && (
                    <div className="text-xs text-muted-foreground">
                      Kayıtlı toplam: {bookingMenus.total} {bookingMenus.currency} ({bookingMenus.lines.length} kalem)
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Menü kalemini sil?</DialogTitle>
            <DialogDescription>
              "{deleteTarget?.name}" pasife alınacak. Mevcut booking atamalarındaki referanslar korunur.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>Vazgeç</Button>
            <Button variant="destructive" onClick={confirmDelete} data-testid="button-catering-confirm-delete">Sil</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
