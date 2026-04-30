import React, { useState } from "react";
import axios from "axios";
import { Printer, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function buildPrintHTML(items, hotelName) {
  const cards = items.map((it) => `
    <div class="qr-card">
      <div class="hotel">${escapeHtml(hotelName)}</div>
      <div class="room">Oda ${escapeHtml(it.room_number)}</div>
      <img src="${it.qr}" alt="QR" />
      <div class="msg">İhtiyacınızı bildirmek için bu kodu okutun</div>
      <div class="msg-en">Scan to request service</div>
    </div>
  `).join("");

  return `<!doctype html><html lang="tr">
<head>
<meta charset="utf-8" />
<title>Oda QR Kodları</title>
<style>
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    margin: 0; padding: 12mm; background: #f8fafc; color: #0f172a;
  }
  .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10mm; }
  .qr-card {
    border: 2px dashed #cbd5e1; border-radius: 14px;
    padding: 16px 12px; text-align: center; background: white;
    page-break-inside: avoid; break-inside: avoid;
  }
  .hotel {
    font-size: 10px; color: #64748b; text-transform: uppercase;
    letter-spacing: 1.5px; margin-bottom: 4px;
  }
  .room { font-size: 26px; font-weight: 800; margin-bottom: 10px; color: #0f172a; }
  .qr-card img { width: 56mm; height: 56mm; image-rendering: pixelated; }
  .msg { font-size: 12px; color: #334155; margin-top: 10px; font-weight: 500; }
  .msg-en { font-size: 10px; color: #94a3b8; margin-top: 2px; }
  @media print {
    body { background: white; padding: 0; }
    @page { margin: 10mm; size: A4; }
  }
</style>
</head>
<body>
  <div class="grid">${cards}</div>
  <script>
    // Tüm <img>'ler dataURL — yine de complete olduğundan emin olduktan
    // sonra yazdır. Aksi halde bazı tarayıcılar boş kareler basar.
    (function () {
      var imgs = Array.prototype.slice.call(document.images);
      var pending = imgs.filter(function (i) { return !i.complete; });
      if (pending.length === 0) {
        setTimeout(function () { window.focus(); window.print(); }, 50);
        return;
      }
      var done = 0;
      pending.forEach(function (img) {
        var fin = function () {
          done++;
          if (done === pending.length) {
            setTimeout(function () { window.focus(); window.print(); }, 50);
          }
        };
        img.addEventListener('load', fin);
        img.addEventListener('error', fin);
      });
    })();
  </script>
</body>
</html>`;
}

export default function RoomQRPrintAction({
  hotelName = "",
  variant = "default",
  size = "default",
  className = "",
  label = "QR Kodlarını Yazdır",
}) {
  const [loading, setLoading] = useState(false);

  const handlePrint = async () => {
    if (loading) return;
    setLoading(true);
    const tid = toast.loading("QR kodları hazırlanıyor...");
    let popup = null;
    try {
      popup = window.open("", "_blank", "width=900,height=1000");
      if (!popup) {
        toast.dismiss(tid);
        toast.error("Pop-up engellenmiş. Tarayıcı ayarlarından bu siteye izin verin.");
        return;
      }
      popup.document.write(
        '<!doctype html><meta charset="utf-8"><title>Hazırlanıyor...</title>' +
        '<body style="font-family:system-ui;padding:40px;color:#475569;">QR kodları hazırlanıyor...</body>'
      );

      const r = await axios.get("/rooms/qr-codes/bulk");
      const rooms = r.data?.items || [];
      if (rooms.length === 0) {
        popup.close();
        toast.dismiss(tid);
        toast.error("Yazdırılacak oda bulunamadı");
        return;
      }

      // CJS/ESM interop: bazı Vite/Rollup yapılandırmalarında `qrcode`
      // paketi default export olmadan modül namespace'i olarak gelebilir.
      // Önce `.default`, yoksa modülün kendisini kullan.
      const mod = await import("qrcode");
      const QRCode = mod?.default ?? mod;
      const qrs = await Promise.all(rooms.map(async (it) => ({
        room_id: it.room_id,
        room_number: it.room_number ?? it.room_id,
        qr: await QRCode.toDataURL(it.url, {
          width: 480,
          margin: 1,
          errorCorrectionLevel: "M",
        }),
      })));

      const html = buildPrintHTML(qrs, hotelName || "Hotel");
      popup.document.open();
      popup.document.write(html);
      popup.document.close();

      toast.dismiss(tid);
      toast.success(`${qrs.length} oda QR kodu hazır`);
    } catch (e) {
      if (popup) {
        try { popup.close(); } catch { /* ignore */ }
      }
      toast.dismiss(tid);
      toast.error(e?.response?.data?.detail || "QR kodları yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button
      onClick={handlePrint}
      disabled={loading}
      variant={variant}
      size={size}
      className={className}
    >
      {loading ? (
        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
      ) : (
        <Printer className="w-4 h-4 mr-2" />
      )}
      {label}
    </Button>
  );
}
