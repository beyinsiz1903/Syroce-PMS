import React, { useEffect, useState } from "react";
import axios from "axios";
import Layout from "@/components/Layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Loader2, Printer, Download, QrCode, Search, Copy } from "lucide-react";

export default function RoomQrCodes({ user, tenant, onLogout }) {
  const [rooms, setRooms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(null);
  const [qrData, setQrData] = useState(null);
  const [qrLoading, setQrLoading] = useState(false);

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

  const filtered = rooms.filter((r) =>
    !search ||
    r.room_number?.toLowerCase().includes(search.toLowerCase()) ||
    r.room_type?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="room_qr_codes">
      <div className="p-6 space-y-6 print:hidden">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-2">
              <QrCode className="w-7 h-7" /> Oda QR Kodları
            </h1>
            <p className="text-gray-500 text-sm mt-1">
              Her oda için benzersiz QR — misafir okutup direkt talep gönderebilir.
            </p>
          </div>
          <Button onClick={printAll} variant="outline">
            <Printer className="w-4 h-4 mr-2" /> Tümünü Yazdır
          </Button>
        </div>

        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input
            value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Oda no veya tip ara..." className="pl-9"
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
                  <div className="font-bold">Oda {r.room_number}</div>
                  <div className="text-xs text-gray-500">{r.room_type}</div>
                  {r.floor != null && <div className="text-xs text-gray-400">Kat {r.floor}</div>}
                </CardContent>
              </Card>
            ))}
            {filtered.length === 0 && (
              <div className="col-span-full text-center text-gray-500 py-12">Oda bulunamadı</div>
            )}
          </div>
        )}
      </div>

      {/* Tek oda QR dialog */}
      <Dialog open={!!selected} onOpenChange={(v) => !v && setSelected(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Oda {selected?.room_number} QR Kodu</DialogTitle>
          </DialogHeader>
          {qrLoading ? (
            <div className="flex justify-center py-10"><Loader2 className="w-8 h-8 animate-spin text-gray-400" /></div>
          ) : qrData ? (
            <div className="space-y-4">
              <div className="flex justify-center bg-white p-6 rounded-lg border-2 border-dashed">
                <img src={qrData.qr_png_base64} alt={`Oda ${qrData.room_number}`} className="w-64 h-64" />
              </div>
              <div className="text-center">
                <div className="text-3xl font-bold">Oda {qrData.room_number}</div>
                <div className="text-xs text-gray-500 mt-2 break-all">{qrData.url}</div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Button onClick={downloadPng} variant="outline">
                  <Download className="w-4 h-4 mr-2" /> PNG İndir
                </Button>
                <Button onClick={copyUrl} variant="outline">
                  <Copy className="w-4 h-4 mr-2" /> URL Kopyala
                </Button>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* Yazdırma görünümü — tüm QR'lar */}
      <div className="hidden print:block">
        <PrintAllQrCodes rooms={filtered} />
      </div>
    </Layout>
  );
}

function PrintAllQrCodes({ rooms }) {
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
          <div className="text-2xl font-bold mt-2">Oda {r.room_number}</div>
          <div className="text-sm text-gray-600">{r.room_type}</div>
        </div>
      ))}
    </div>
  );
}
