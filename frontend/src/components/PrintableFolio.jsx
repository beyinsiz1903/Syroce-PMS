import React, { useEffect, useMemo, useState } from 'react';
import { Printer, X } from 'lucide-react';
import { Button } from './ui/button';
import { Card, CardContent, CardHeader } from './ui/card';

const EMPTY = '—';
const currencyCode = value => value === 'TL' ? 'TRY' : (value || 'TRY');
const money = (value, currency) => new Intl.NumberFormat('tr-TR', {
  style: 'currency', currency: currencyCode(currency), minimumFractionDigits: 2,
}).format(Number(value) || 0);
const dateText = (value, withTime = false) => {
  if (!value) return EMPTY;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return withTime
    ? date.toLocaleString('tr-TR', { dateStyle: 'short', timeStyle: 'short' })
    : date.toLocaleDateString('tr-TR');
};
const paymentLabel = value => ({ cash: 'Nakit', card: 'Kredi kartı', bank_transfer: 'Havale / EFT', online: 'Online ödeme', agency: 'Acente', discount: 'İndirim' }[value] || value || EMPTY);
const categoryLabel = value => ({ room: 'Konaklama', room_charge: 'Konaklama', food_beverage: 'Yiyecek & İçecek', food_and_beverage: 'Yiyecek & İçecek', restaurant: 'Yiyecek & İçecek', minibar: 'Minibar', spa: 'Spa', laundry: 'Çamaşırhane', tax: 'Vergi' }[value] || value || 'Ek hizmet');

const PrintableFolio = ({ folioData = {}, guest, room, onClose }) => {
  const booking = folioData.booking || {};
  const [guestData, setGuestData] = useState(guest || null);
  const [roomData, setRoomData] = useState(room || null);
  const [loading, setLoading] = useState(Boolean(!guest && booking.guest_id) || Boolean(!room && booking.room_id));

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const requests = [];
        if (!guest && booking.guest_id) requests.push(fetch(`/api/guests/${booking.guest_id}`, { credentials: 'include' }).then(r => r.ok ? r.json() : null).then(data => { if (active) setGuestData(data?.guest || data || null); }));
        if (!room && booking.room_id) requests.push(fetch('/api/pms/rooms', { credentials: 'include' }).then(r => r.ok ? r.json() : null).then(data => {
          const rooms = Array.isArray(data) ? data : (data?.rooms || []);
          if (active) setRoomData(rooms.find(item => item.id === booking.room_id) || null);
        }));
        await Promise.all(requests);
      } catch (error) {
        console.error('Folyo ek bilgileri alınamadı:', error);
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => { active = false; };
  }, [booking.guest_id, booking.room_id, guest, room]);

  useEffect(() => {
    const closeOnEscape = event => { if (event.key === 'Escape') onClose?.(); };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);

  const currency = folioData.currency || booking.currency || 'TL';
  const charges = useMemo(() => {
    const seen = new Set();
    return [...(Array.isArray(folioData.charges) ? folioData.charges : []), ...(Array.isArray(folioData.extra_charges) ? folioData.extra_charges : [])]
      .filter(item => !item.voided)
      .filter(item => {
        const key = String(item.id || item.charge_id || `${item.description || item.charge_name}:${item.amount ?? item.total ?? item.charge_amount}:${item.created_at || item.posted_at}`);
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
  }, [folioData.charges, folioData.extra_charges]);
  const payments = useMemo(() => (Array.isArray(folioData.payments) ? folioData.payments : []).filter(item => !item.voided), [folioData.payments]);
  const totalCharges = charges.reduce((sum, item) => sum + Number(item.total ?? item.charge_amount ?? item.amount ?? 0), 0);
  const totalPayments = payments.reduce((sum, item) => sum + Number(item.amount ?? 0), 0);
  const balance = Number(folioData.balance ?? (totalCharges - totalPayments));
  const start = new Date(booking.check_in || booking.check_in_date);
  const end = new Date(booking.check_out || booking.check_out_date);
  const nights = Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) ? EMPTY : Math.max(0, Math.round((end - start) / 86400000));
  const guestName = guestData?.name || guestData?.full_name || booking.guest_name || EMPTY;
  const roomNumber = roomData?.room_number || roomData?.number || booking.room_number || EMPTY;
  const roomType = roomData?.room_type || roomData?.type_name || booking.room_type || EMPTY;
  const hotelName = folioData.hotel_name || folioData.property_name || booking.hotel_name || booking.property_name;
  const hotelAddress = folioData.hotel_address || folioData.property_address || booking.hotel_address;
  const hotelTaxNumber = folioData.hotel_tax_number || folioData.tax_number || booking.hotel_tax_number;
  const missingDocumentFields = [
    !hotelName && 'otel/unvan',
    !folioData.folio_number && 'folyo numarası',
    roomNumber === EMPTY && 'oda numarası',
    !(guestData?.id_number || guestData?.identity_number) && 'misafir kimlik numarası',
  ].filter(Boolean);

  if (loading) return <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/60 p-4"><div className="rounded-xl bg-white px-8 py-6 text-sm text-slate-600 shadow-xl">Folyo hazırlanıyor…</div></div>;

  return <div className="printable-folio-overlay fixed inset-0 z-[100] overflow-y-auto bg-slate-950/60 p-4 sm:p-8" role="dialog" aria-modal="true" aria-label="Folyo yazdırma önizlemesi">
    <Card className="printable-folio-sheet mx-auto w-full max-w-5xl overflow-hidden bg-white shadow-2xl">
      <CardHeader className="border-b bg-slate-50 px-5 py-4 sm:px-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><p className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-600">{hotelName || 'Otel bilgisi belirtilmedi'}</p><h1 className="mt-1 text-2xl font-bold text-slate-900">{folioData.document_title || 'Misafir Folyosu'}</h1><p className="mt-1 text-sm text-slate-500">Rezervasyon: {booking.reservation_number || booking.confirmation_number || booking.id || EMPTY}</p>{hotelAddress && <p className="mt-1 text-xs text-slate-500">{hotelAddress}</p>}{hotelTaxNumber && <p className="text-xs text-slate-500">Vergi/TC no: {hotelTaxNumber}</p>}</div>
          <div className="print:hidden flex gap-2"><Button type="button" variant="outline" size="sm" onClick={() => window.print()} data-testid="print-folio"><Printer className="mr-2 h-4 w-4" /> Yazdır / PDF Kaydet</Button><Button type="button" variant="outline" size="icon" onClick={onClose} aria-label="Kapat"><X className="h-4 w-4" /></Button></div>
        </div>
        <div className="mt-4 grid gap-2 text-sm sm:grid-cols-2"><div><b>Folyo no:</b> {folioData.folio_number || EMPTY}</div><div className="sm:text-right"><b>Düzenlenme:</b> {dateText(new Date(), true)}</div></div>
      </CardHeader>
      <CardContent className="space-y-6 p-5 sm:p-8">
        {missingDocumentFields.length > 0 && <div role="alert" className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900"><b>Yazdırmadan önce kontrol edin:</b> {missingDocumentFields.join(', ')} bilgisi eksik.</div>}
        <section className="grid gap-6 rounded-xl border border-slate-200 p-4 md:grid-cols-2">
          <Info title="Misafir Bilgileri" rows={[["Ad soyad", guestName], ["Telefon", guestData?.phone], ["E-posta", guestData?.email], ["Kimlik no", guestData?.id_number || guestData?.identity_number], ["Uyruk", guestData?.nationality]]} />
          <Info title="Konaklama Bilgileri" rows={[["Oda", roomNumber], ["Oda tipi", roomType], ["Giriş", dateText(booking.check_in || booking.check_in_date)], ["Çıkış", dateText(booking.check_out || booking.check_out_date)], ["Süre", nights === EMPTY ? EMPTY : `${nights} gece`], ["Kişi", `${Number(booking.adults || 0)} yetişkin${Number(booking.children || 0) > 0 ? `, ${booking.children} çocuk` : ''}`]]} />
        </section>
        <FolioTable title="Harcama ve Tahakkuklar" columns={["Tarih", "Açıklama", "Tür", "Adet", "Tutar"]} empty="Kayıtlı harcama bulunmuyor." rows={charges.map(item => [dateText(item.posted_at || item.created_at || item.date), item.description || item.charge_name || 'Harcama', categoryLabel(item.charge_category || item.category || item.charge_type), item.quantity || 1, money(item.total ?? item.charge_amount ?? item.amount, currency)])} totalLabel="Toplam harcama" total={money(totalCharges, currency)} />
        <FolioTable title="Tahsilatlar" columns={["Tarih", "Ödeme yöntemi", "Referans", "Tutar"]} empty="Kayıtlı tahsilat bulunmuyor." rows={payments.map(item => [dateText(item.posted_at || item.processed_at || item.created_at), paymentLabel(item.payment_method || item.method), item.reference || EMPTY, money(item.amount, currency)])} totalLabel="Toplam tahsilat" total={money(totalPayments, currency)} />
        <section className="ml-auto max-w-md rounded-xl border-2 border-slate-300 p-4">
          <div className="flex justify-between text-sm"><span>Toplam harcama</span><b>{money(totalCharges, currency)}</b></div><div className="mt-2 flex justify-between text-sm"><span>Toplam tahsilat</span><b className="text-emerald-700">{money(totalPayments, currency)}</b></div>
          <div className="mt-3 flex justify-between border-t pt-3 text-lg"><b>{balance > 0 ? 'Kalan bakiye' : balance < 0 ? 'Misafir alacağı' : 'Bakiye'}</b><b className={balance > 0 ? 'text-red-700' : 'text-emerald-700'}>{money(Math.abs(balance), currency)}</b></div>
          {Math.abs(balance) < 0.01 && <p className="mt-3 rounded-md bg-emerald-50 p-2 text-center text-sm font-semibold text-emerald-800">Hesap kapandı</p>}
        </section>
        <footer className="border-t pt-4 text-center text-xs text-slate-500">Bu belge Syroce PMS tarafından elektronik olarak oluşturulmuştur.</footer>
      </CardContent>
    </Card>
    <style>{`@media print { body * { visibility: hidden !important; } .printable-folio-sheet, .printable-folio-sheet * { visibility: visible !important; } .printable-folio-overlay { position: static !important; padding: 0 !important; background: white !important; } .printable-folio-sheet { position: absolute !important; inset: 0 !important; max-width: none !important; box-shadow: none !important; border: 0 !important; } @page { size: A4; margin: 10mm; } }`}</style>
  </div>;
};

const Info = ({ title, rows }) => <div><h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-700">{title}</h2><dl className="grid grid-cols-[7rem_1fr] gap-y-2 text-sm">{rows.map(([label, value]) => <React.Fragment key={label}><dt className="text-slate-500">{label}</dt><dd className="min-w-0 break-words font-medium">{value || EMPTY}</dd></React.Fragment>)}</dl></div>;
const FolioTable = ({ title, columns, rows, empty, totalLabel, total }) => <section><h2 className="mb-3 text-base font-bold text-slate-900">{title}</h2><div className="overflow-x-auto rounded-lg border"><table className="w-full min-w-[560px] text-sm"><thead className="bg-slate-50 text-slate-600"><tr>{columns.map((column, index) => <th key={column} className={`p-2 ${index === columns.length - 1 ? 'text-right' : 'text-left'}`}>{column}</th>)}</tr></thead><tbody>{rows.length === 0 ? <tr><td colSpan={columns.length} className="p-6 text-center text-slate-500">{empty}</td></tr> : rows.map((row, rowIndex) => <tr key={rowIndex} className="border-t">{row.map((cell, index) => <td key={index} className={`p-2 ${index === row.length - 1 ? 'text-right font-medium' : ''}`}>{cell}</td>)}</tr>)}</tbody><tfoot><tr className="border-t-2 bg-slate-50 font-semibold"><td colSpan={columns.length - 1} className="p-2 text-right">{totalLabel}</td><td className="p-2 text-right">{total}</td></tr></tfoot></table></div></section>;

export default PrintableFolio;
