import React, { useEffect, useState } from "react";
import axios from "axios";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Loader2, Printer, Download, QrCode, Search, Copy, Plus, Save, Trash2, Utensils } from "lucide-react";
import { useTranslation } from 'react-i18next';

export default function RoomQrCodes({ user, tenant, onLogout }) {
  const { t } = useTranslation();
  const [rooms, setRooms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(null);
  const [qrData, setQrData] = useState(null);
  const [qrLoading, setQrLoading] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuItems, setMenuItems] = useState([]);
  const [menuLoading, setMenuLoading] = useState(false);
  const [menuSaving, setMenuSaving] = useState(false);

  const propertyId = selected?.property_id || rooms.find((room) => room.property_id)?.property_id || tenant?.property_id;

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get("/rooms/qr-codes/bulk");
      setRooms(r.data.items || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const openQr = async (room) => {
    setSelected(room);
    setQrData(null);
    setQrLoading(true);
    try {
      const r = await axios.get(`/rooms/${room.room_id}/qr-code`);
      setQrData(r.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "QR oluşturulamadı");
    } finally {
      setQrLoading(false);
    }
  };

  const downloadPng = () => {
    if (!qrData?.qr_png_base64) return;
    const a = document.createElement("a");
    a.href = qrData.qr_png_base64;
    a.download = `oda-${qrData.room_number}-qr.png`;
    a.click();
  };

  const printAll = () => {
    window.print();
  };

  const copyUrl = () => {
    navigator.clipboard.writeText(qrData.url);
    toast.success("URL kopyalandı");
  };

  const loadMenu = async () => {
    if (!propertyId) {
      toast.error("Aktif tesis bulunamadı");
      return;
    }
    setMenuOpen(true);
    setMenuLoading(true);
    try {
      const response = await axios.get("/room-qr/room-service-menu", { params: { property_id: propertyId } });
      setMenuItems((response.data.items || []).map((item) => ({
        service_code: item.service_code,
        name: item.labels?.tr || item.labels?.en || "",
        nameEn: item.labels?.en || "",
        description: item.description?.tr || "",
        price: ((Number(item.unit_price_minor) || 0) / 100).toFixed(2),
        currency: item.currency || "TRY",
        estimated_minutes: item.estimated_minutes || 30,
        enabled: item.enabled !== false,
      })));
    } catch (error) {
      toast.error(error.response?.data?.detail || "Oda servisi menüsü yüklenemedi");
    } finally {
      setMenuLoading(false);
    }
  };

  const updateMenuItem = (index, field, value) => {
    setMenuItems((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: value } : item));
  };

  const addMenuItem = () => setMenuItems((items) => [...items, {
    service_code: `fnb.menu_${Date.now()}`, name: "", nameEn: "", description: "", price: "0.00", currency: "TRY", estimated_minutes: 30, enabled: true,
  }]);

  const saveMenu = async () => {
    if (!propertyId) return;
    const invalid = menuItems.find((item) => !item.service_code || !item.name || !Number.isFinite(Number(String(item.price).replace(",", "."))) || Number(String(item.price).replace(",", ".")) <= 0);
    if (invalid) {
      toast.error("Her ürün için kod, Türkçe ad ve sıfırdan büyük fiyat girin");
      return;
    }
    setMenuSaving(true);
    try {
      await axios.put("/room-qr/room-service-menu", {
        property_id: propertyId,
        items: menuItems.map((item) => ({
          service_code: item.service_code.trim().toLowerCase().replace(/[^a-z0-9_.]/g, "_"),
          labels: { tr: item.name.trim(), en: (item.nameEn || item.name).trim() },
          description: item.description ? { tr: item.description.trim(), en: item.description.trim() } : undefined,
          unit_price_minor: Math.round(Number(String(item.price).replace(",", ".")) * 100),
          currency: item.currency.toUpperCase(), estimated_minutes: Number(item.estimated_minutes) || 30, enabled: item.enabled,
        })),
      });
      toast.success("Oda servisi menüsü kaydedildi");
      setMenuOpen(false);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Menü kaydedilemedi");
    } finally {
      setMenuSaving(false);
    }
  };

  const filtered = rooms.filter((r) =>
    !search ||
    r.room_number?.toLowerCase().includes(search.toLowerCase()) ||
    r.room_type?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <>
      <div className="p-6 space-y-6 print:hidden">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-2">
              <QrCode className="w-7 h-7" /> {t('cm.pages_admin_RoomQrCodes.oda_qr_kodlari')}
            </h1>
            <p className="text-gray-500 text-sm mt-1">
              {t('cm.pages_admin_RoomQrCodes.her_oda_icin_benzersiz_qr_misafir_okutup')}
            </p>
          </div>
          <div className="flex gap-2">
            <Button onClick={loadMenu} variant="outline">
              <Utensils className="w-4 h-4 mr-2" /> Oda Servisi Menüsü
            </Button>
            <Button onClick={printAll} variant="outline">
              <Printer className="w-4 h-4 mr-2" /> {t('cm.pages_admin_RoomQrCodes.tumunu_yazdir')}
            </Button>
          </div>
        </div>

        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input
            value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder={t('cm.pages_admin_RoomQrCodes.oda_no_veya_tip_ara')} className="pl-9"
          />
        </div>

        {loading ? (
          <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-gray-400" /></div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {filtered.map((r) => (
              <Card key={r.room_id} className="cursor-pointer hover:shadow-md transition-all" onClick={() => openQr(r)}>
                <CardContent className="p-4 text-center">
                  <div className="w-12 h-12 mx-auto rounded-lg bg-slate-100 flex items-center justify-center mb-2">
                    <QrCode className="w-6 h-6 text-slate-600" />
                  </div>
                  <div className="font-bold">{t('cm.pages_admin_RoomQrCodes.oda')} {r.room_number}</div>
                  <div className="text-xs text-gray-500">{r.room_type}</div>
                  {r.floor != null && <div className="text-xs text-gray-400">Kat {r.floor}</div>}
                </CardContent>
              </Card>
            ))}
            {filtered.length === 0 && (
              <div className="col-span-full text-center text-gray-500 py-12">{t('cm.pages_admin_RoomQrCodes.oda_bulunamadi')}</div>
            )}
          </div>
        )}
      </div>

      {/* Tek oda QR dialog */}
      <Dialog open={!!selected} onOpenChange={(v) => !v && setSelected(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t('cm.pages_admin_RoomQrCodes.oda_e4b47')} {selected?.room_number} QR Kodu</DialogTitle>
          </DialogHeader>
          {qrLoading ? (
            <div className="flex justify-center py-10"><Loader2 className="w-8 h-8 animate-spin text-gray-400" /></div>
          ) : qrData ? (
            <div className="space-y-4">
              <div className="flex justify-center bg-white p-6 rounded-lg border-2 border-dashed">
                <img src={qrData.qr_png_base64} alt={`Oda ${qrData.room_number}`} className="w-64 h-64" />
              </div>
              <div className="text-center">
                <div className="text-3xl font-bold">{t('cm.pages_admin_RoomQrCodes.oda_e4b47')} {qrData.room_number}</div>
                <div className="text-xs text-gray-500 mt-2 break-all">{qrData.url}</div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Button onClick={downloadPng} variant="outline">
                  <Download className="w-4 h-4 mr-2" /> {t('cm.pages_admin_RoomQrCodes.png_indir')}
                </Button>
                <Button onClick={copyUrl} variant="outline">
                  <Copy className="w-4 h-4 mr-2" /> URL Kopyala
                </Button>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog open={menuOpen} onOpenChange={setMenuOpen}>
        <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><Utensils className="h-5 w-5" /> QR Oda Servisi Menüsü</DialogTitle></DialogHeader>
          <p className="text-sm text-slate-500">Misafir bu ürünleri QR’dan sipariş eder; onayladığı tutar otomatik olarak açık oda folyosuna yazılır.</p>
          {menuLoading ? <div className="flex justify-center py-10"><Loader2 className="h-7 w-7 animate-spin" /></div> : (
            <div className="space-y-3">
              {menuItems.map((item, index) => <div key={`${item.service_code}-${index}`} className="grid grid-cols-1 gap-2 rounded-xl border bg-slate-50 p-3 md:grid-cols-12">
                <Input className="md:col-span-3" value={item.name} onChange={(e) => updateMenuItem(index, "name", e.target.value)} placeholder="Ürün adı" />
                <Input className="md:col-span-2" value={item.price} onChange={(e) => updateMenuItem(index, "price", e.target.value)} inputMode="decimal" placeholder="Fiyat" aria-label="Ürün fiyatı" />
                <Input className="md:col-span-1" value={item.currency} onChange={(e) => updateMenuItem(index, "currency", e.target.value)} maxLength={3} aria-label="Para birimi" />
                <Input className="md:col-span-2" value={item.estimated_minutes} onChange={(e) => updateMenuItem(index, "estimated_minutes", e.target.value)} inputMode="numeric" placeholder="Dakika" aria-label="Hazırlık süresi" />
                <Input className="md:col-span-3" value={item.description} onChange={(e) => updateMenuItem(index, "description", e.target.value)} placeholder="Kısa açıklama" />
                <Button variant="ghost" size="icon" className="md:col-span-1" onClick={() => setMenuItems((items) => items.filter((_, itemIndex) => itemIndex !== index))} aria-label="Ürünü kaldır"><Trash2 className="h-4 w-4 text-red-600" /></Button>
              </div>)}
              <Button variant="outline" onClick={addMenuItem}><Plus className="mr-2 h-4 w-4" /> Ürün ekle</Button>
              <Button className="ml-2" onClick={saveMenu} disabled={menuSaving}>{menuSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />} Kaydet</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Yazdırma görünümü — tüm QR'lar */}
      <div className="hidden print:block">
        <PrintAllQrCodes rooms={filtered} />
      </div>
    </>
  );
}

function PrintAllQrCodes({ rooms }) {
  const { t } = useTranslation();
  const [loaded, setLoaded] = useState({});
  useEffect(() => {
    const loadAll = async () => {
      const res = {};
      for (const r of rooms) {
        try {
          const d = await axios.get(`/rooms/${r.room_id}/qr-code`);
          res[r.room_id] = d.data.qr_png_base64;
        } catch (e) { /* skip */ }
      }
      setLoaded(res);
    };
    if (rooms.length) loadAll();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [rooms.length]);

  return (
    <div className="grid grid-cols-2 gap-4 p-4">
      {rooms.map((r) => (
        <div key={r.room_id} className="border-2 border-dashed p-4 text-center page-break-inside-avoid">
          {loaded[r.room_id] ? (
            <img src={loaded[r.room_id]} alt="" className="w-48 h-48 mx-auto" />
          ) : (
            <div className="w-48 h-48 mx-auto bg-slate-100 flex items-center justify-center">...</div>
          )}
          <div className="text-2xl font-bold mt-2">{t('cm.pages_admin_RoomQrCodes.oda_e4b47')} {r.room_number}</div>
          <div className="text-sm text-gray-600">{r.room_type}</div>
        </div>
      ))}
    </div>
  );
}
