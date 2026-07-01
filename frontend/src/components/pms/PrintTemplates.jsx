/**
 * Print templates for guest registration card, folio statement, and proforma invoice.
 *
 * Each function accepts an optional `hotelInfo` object so the printed header
 * shows real hotel contact details from the tenant settings instead of
 * placeholders. Backward compatible: when callers pass only `hotelName` (the
 * legacy 4th arg as a string) we still honour it.
 */
const DEFAULT_HOTEL_INFO = {
  name: 'Syroce Hotel',
  address: '',
  phone: '',
  email: '',
  tax_no: '',
  tax_office: '',
};

function normalizeHotelInfo(arg) {
  if (!arg) return { ...DEFAULT_HOTEL_INFO };
  if (typeof arg === 'string') return { ...DEFAULT_HOTEL_INFO, name: arg };
  return {
    ...DEFAULT_HOTEL_INFO,
    name: arg.name || arg.hotel_name || arg.org_name || DEFAULT_HOTEL_INFO.name,
    address: arg.address || arg.hotel_address || '',
    phone: arg.phone || arg.hotel_phone || arg.contact_phone || '',
    email: arg.email || arg.hotel_email || arg.contact_email || '',
    tax_no: arg.tax_no || arg.tax_number || arg.vergi_no || '',
    tax_office: arg.tax_office || arg.vergi_dairesi || '',
  };
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

export function printRegistrationCard(booking, guest, room, hotelArg) {
  const hotel = normalizeHotelInfo(hotelArg);
  const w = window.open('', '_blank');
  if (!w) return;
  w.document.write(`<html><head><title>Kayıt Kartı - ${escapeHtml(guest?.name || '')}</title>
  <style>
    body{font-family:Arial,sans-serif;padding:30px;font-size:12px;color:#333}
    h1{font-size:16px;text-align:center;border-bottom:2px solid #333;padding-bottom:8px;margin-bottom:16px}
    .hotel-name{font-size:20px;text-align:center;font-weight:bold;margin-bottom:4px}
    .hotel-meta{text-align:center;font-size:10px;color:#666;margin-bottom:8px;line-height:1.5}
    .subtitle{text-align:center;font-size:11px;color:#666;margin-bottom:20px}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px}
    .field{border-bottom:1px dotted #ccc;padding:4px 0}
    .field .label{font-size:10px;color:#888;text-transform:uppercase;letter-spacing:0.5px}
    .field .value{font-size:13px;font-weight:500;min-height:18px}
    .section{margin-top:16px;padding-top:8px;border-top:1px solid #ddd}
    .section-title{font-size:11px;font-weight:bold;color:#555;text-transform:uppercase;margin-bottom:8px}
    .signature-area{margin-top:40px;display:flex;justify-content:space-between}
    .signature-box{width:45%;text-align:center;border-top:1px solid #333;padding-top:8px;font-size:10px;color:#666}
    .kvkk{margin-top:24px;font-size:8px;color:#999;line-height:1.4;border:1px solid #eee;padding:8px;border-radius:4px}
    @media print{body{padding:20px}}
  </style></head><body>
  <div class="hotel-name">${escapeHtml(hotel.name)}</div>
  <div class="hotel-meta">
    ${[hotel.address, hotel.phone, hotel.email].filter(Boolean).map(escapeHtml).join(' &nbsp;·&nbsp; ')}
  </div>
  <div class="subtitle">MISAFIR KAYIT KARTI / GUEST REGISTRATION CARD</div>
  <div class="grid">
    <div class="field"><div class="label">Ad Soyad / Full Name</div><div class="value">${escapeHtml(guest?.name || '')}</div></div>
    <div class="field"><div class="label">TC/Pasaport No / ID/Passport</div><div class="value">${escapeHtml(guest?.id_number || guest?.passport_number || '')}</div></div>
    <div class="field"><div class="label">Uyruk / Nationality</div><div class="value">${escapeHtml(guest?.nationality || 'TC')}</div></div>
    <div class="field"><div class="label">Dogum Tarihi / Birth Date</div><div class="value">${escapeHtml(guest?.birth_date || '')}</div></div>
    <div class="field"><div class="label">E-posta / Email</div><div class="value">${escapeHtml(guest?.email || '')}</div></div>
    <div class="field"><div class="label">Telefon / Phone</div><div class="value">${escapeHtml(guest?.phone || '')}</div></div>
    <div class="field"><div class="label">Adres / Address</div><div class="value">${escapeHtml(guest?.address || '')}</div></div>
    <div class="field"><div class="label">Şirket / Company</div><div class="value">${escapeHtml(booking?.company_name || '')}</div></div>
  </div>
  <div class="section">
    <div class="section-title">Konaklama Bilgileri / Stay Details</div>
    <div class="grid">
      <div class="field"><div class="label">Oda No / Room No</div><div class="value">${escapeHtml(booking?.room_number || room?.room_number || '')}</div></div>
      <div class="field"><div class="label">Oda Tipi / Room Type</div><div class="value">${escapeHtml(room?.room_type || booking?.room_type || '')}</div></div>
      <div class="field"><div class="label">Giriş / Check-in</div><div class="value">${escapeHtml(booking?.check_in?.toString().slice(0, 10) || '')}</div></div>
      <div class="field"><div class="label">Çıkış / Check-out</div><div class="value">${escapeHtml(booking?.check_out?.toString().slice(0, 10) || '')}</div></div>
      <div class="field"><div class="label">Yetiskin / Adults</div><div class="value">${booking?.adults || 1}</div></div>
      <div class="field"><div class="label">Cocuk / Children</div><div class="value">${booking?.children || 0}</div></div>
      <div class="field"><div class="label">Pansiyon / Board</div><div class="value">${escapeHtml(booking?.board_type || 'Oda+Kahvalti')}</div></div>
      <div class="field"><div class="label">Kanal / Channel</div><div class="value">${escapeHtml(booking?.channel || booking?.source_channel || 'Direkt')}</div></div>
    </div>
  </div>
  <div class="section">
    <div class="section-title">Özel Istekler / Special Requests</div>
    <div class="field"><div class="value" style="min-height:40px">${escapeHtml(booking?.special_requests || guest?.notes || '')}</div></div>
  </div>
  <div class="kvkk">
    KVKK AYDINLATMA METNI: Kisisel verileriniz, 6698 sayili Kisisel Verilerin Korunmasi Kanunu kapsaminda, konaklama hizmetlerinin sunulmasi, yasal yukumluluklerin yerine getirilmesi ve güvenlik amaciyla islenmektedir. Detaylı bilgi için resepsiyondan KVKK aydinlatma metnini talep edebilirsiniz.
    <br/><br/>
    PERSONAL DATA NOTICE: Your personal data is processed in accordance with applicable data protection regulations for the purpose of providing accommodation services, fulfilling legal obligations, and security purposes.
  </div>
  <div class="signature-area">
    <div class="signature-box">Misafir Imzasi / Guest Signature<br/><br/>Tarih / Date: ${new Date().toLocaleDateString('tr-TR')}</div>
    <div class="signature-box">Resepsiyon / Reception<br/><br/>Tarih / Date: ${new Date().toLocaleDateString('tr-TR')}</div>
  </div>
  </body></html>`);
  w.document.close();
  w.print();
}

export function printFolio(folioData, hotelArg) {
  const hotel = normalizeHotelInfo(hotelArg);
  const w = window.open('', '_blank');
  if (!w) return;
  const folio = folioData?.folio;
  const summary = folioData?.summary;
  const timeline = folioData?.timeline || [];
  w.document.write(`<html><head><title>Folio - ${escapeHtml(folio?.folio_number || '')}</title>
  <style>
    body{font-family:Arial,sans-serif;padding:30px;font-size:11px;color:#333}
    .header{text-align:center;margin-bottom:20px}
    .hotel-name{font-size:20px;font-weight:bold}
    .hotel-meta{font-size:10px;color:#666;margin-top:4px;line-height:1.5}
    .subtitle{color:#666;font-size:11px}
    .info-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px;font-size:11px}
    .info-item{display:flex;gap:4px}
    .info-label{color:#888;min-width:80px}
    .info-value{font-weight:500}
    table{width:100%;border-collapse:collapse;margin:16px 0}
    th{background:#f5f5f5;border:1px solid #ddd;padding:6px 8px;text-align:left;font-size:10px;text-transform:uppercase}
    td{border:1px solid #ddd;padding:5px 8px}
    .amount-in{color:#059669}
    .amount-out{color:#DC2626}
    .voided{text-decoration:line-through;color:#999}
    .totals{margin-top:16px;border-top:2px solid #333;padding-top:8px}
    .total-row{display:flex;justify-content:space-between;padding:4px 0;font-size:12px}
    .total-row.final{font-size:14px;font-weight:bold;border-top:1px solid #333;padding-top:8px}
    .footer{margin-top:30px;text-align:center;font-size:9px;color:#999}
    @media print{body{padding:15px}}
  </style></head><body>
  <div class="header">
    <div class="hotel-name">${escapeHtml(hotel.name)}</div>
    <div class="hotel-meta">
      ${[hotel.address, hotel.phone, hotel.email].filter(Boolean).map(escapeHtml).join(' &nbsp;·&nbsp; ')}
      ${hotel.tax_no ? `<br/>Vergi No: ${escapeHtml(hotel.tax_no)}${hotel.tax_office ? ' · Vergi Dairesi: ' + escapeHtml(hotel.tax_office) : ''}` : ''}
    </div>
    <div class="subtitle">MISAFIR HESAP DOKUMU / GUEST FOLIO</div>
  </div>
  <div class="info-grid">
    <div class="info-item"><span class="info-label">Folio No:</span><span class="info-value">${escapeHtml(folio?.folio_number || folio?.id?.slice(0, 12) || '')}</span></div>
    <div class="info-item"><span class="info-label">Tarih:</span><span class="info-value">${new Date().toLocaleDateString('tr-TR')}</span></div>
    <div class="info-item"><span class="info-label">Misafir:</span><span class="info-value">${escapeHtml(folio?.guest_name || '')}</span></div>
    <div class="info-item"><span class="info-label">Oda No:</span><span class="info-value">${escapeHtml(folio?.room_number || '')}</span></div>
    <div class="info-item"><span class="info-label">Giriş:</span><span class="info-value">${escapeHtml(folio?.check_in?.toString().slice(0, 10) || '')}</span></div>
    <div class="info-item"><span class="info-label">Çıkış:</span><span class="info-value">${escapeHtml(folio?.check_out?.toString().slice(0, 10) || '')}</span></div>
    <div class="info-item"><span class="info-label">Durum:</span><span class="info-value">${escapeHtml(folio?.status || '')}</span></div>
    <div class="info-item"><span class="info-label">Tip:</span><span class="info-value">${escapeHtml(folio?.folio_type || '')}</span></div>
  </div>
  <table>
    <thead><tr><th>Tarih</th><th>Açıklama</th><th>Kategori</th><th style="text-align:right">Borc</th><th style="text-align:right">Alacak</th><th style="text-align:right">Bakiye</th></tr></thead>
    <tbody>
    ${timeline.map(e => `
      <tr class="${e.voided ? 'voided' : ''}">
        <td>${escapeHtml(e.timestamp?.slice(0, 10) || '')}</td>
        <td>${escapeHtml(e.description || e.type || '')}</td>
        <td>${escapeHtml(e.category || '')}</td>
        <td style="text-align:right" class="amount-out">${e.type === 'charge' ? (e.amount || 0).toFixed(2) : ''}</td>
        <td style="text-align:right" class="amount-in">${e.type === 'payment' ? (e.amount || 0).toFixed(2) : ''}</td>
        <td style="text-align:right">${e.running_balance?.toFixed(2) || ''}</td>
      </tr>
    `).join('')}
    </tbody>
  </table>
  <div class="totals">
    <div class="total-row"><span>Toplam Masraf / Total Charges:</span><span>${(summary?.total_charges || 0).toFixed(2)} TL</span></div>
    <div class="total-row"><span>Toplam Ödeme / Total Payments:</span><span>${(summary?.total_payments || 0).toFixed(2)} TL</span></div>
    <div class="total-row final"><span>BAKIYE / BALANCE:</span><span>${(summary?.balance || 0).toFixed(2)} TL</span></div>
  </div>
  <div class="footer">
    <p>Bu belge ${new Date().toLocaleString('tr-TR')} tarihinde olusturulmustur.</p>
    <p>${escapeHtml(hotel.name)} - Tüm haklar saklidir</p>
  </div>
  </body></html>`);
  w.document.close();
  w.print();
}

export function printProformaInvoice(booking, guest, charges, hotelArg) {
  const hotel = normalizeHotelInfo(hotelArg);
  const w = window.open('', '_blank');
  if (!w) return;
  const totalAmount = booking?.total_amount || charges?.reduce((s, c) => s + (c.amount || 0), 0) || 0;
  const taxRate = 0.10;
  const netAmount = totalAmount / (1 + taxRate);
  const taxAmount = totalAmount - netAmount;
  w.document.write(`<html><head><title>Proforma Fatura</title>
  <style>
    body{font-family:Arial,sans-serif;padding:30px;font-size:12px;color:#333}
    .header{display:flex;justify-content:space-between;border-bottom:2px solid #333;padding-bottom:12px;margin-bottom:20px}
    .hotel-info{font-size:10px;color:#666;line-height:1.5}
    .hotel-name{font-size:18px;font-weight:bold;color:#333}
    .proforma-title{font-size:16px;font-weight:bold;color:#C00;text-align:right}
    .proforma-no{font-size:11px;color:#666;text-align:right}
    .parties{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}
    .party{border:1px solid #ddd;border-radius:4px;padding:12px}
    .party-title{font-size:10px;color:#888;text-transform:uppercase;margin-bottom:8px;font-weight:bold}
    table{width:100%;border-collapse:collapse;margin:16px 0}
    th{background:#f5f5f5;border:1px solid #ddd;padding:6px 8px;font-size:10px}
    td{border:1px solid #ddd;padding:5px 8px}
    .total-section{float:right;width:250px;margin-top:12px}
    .total-row{display:flex;justify-content:space-between;padding:4px 0}
    .total-row.grand{font-weight:bold;font-size:14px;border-top:2px solid #333;padding-top:8px}
    .note{margin-top:40px;font-size:10px;color:#666;border-top:1px solid #ddd;padding-top:12px}
    @media print{body{padding:15px}}
  </style></head><body>
  <div class="header">
    <div>
      <div class="hotel-name">${escapeHtml(hotel.name)}</div>
      <div class="hotel-info">
        ${hotel.address ? 'Adres: ' + escapeHtml(hotel.address) + '<br/>' : ''}
        ${hotel.phone ? 'Tel: ' + escapeHtml(hotel.phone) + '<br/>' : ''}
        ${hotel.email ? 'E-posta: ' + escapeHtml(hotel.email) + '<br/>' : ''}
        ${hotel.tax_no ? 'Vergi No: ' + escapeHtml(hotel.tax_no) : ''}
        ${hotel.tax_office ? ' · Vergi Dairesi: ' + escapeHtml(hotel.tax_office) : ''}
      </div>
    </div>
    <div>
      <div class="proforma-title">PROFORMA FATURA</div>
      <div class="proforma-no">No: PF-${Date.now().toString().slice(-8)}</div>
      <div class="proforma-no">Tarih: ${new Date().toLocaleDateString('tr-TR')}</div>
    </div>
  </div>
  <div class="parties">
    <div class="party">
      <div class="party-title">Misafir Bilgileri</div>
      <div>${escapeHtml(guest?.name || booking?.guest_name || '')}</div>
      <div>${escapeHtml(guest?.email || '')}</div>
      <div>${escapeHtml(guest?.phone || '')}</div>
      <div>${escapeHtml(guest?.address || '')}</div>
    </div>
    <div class="party">
      <div class="party-title">Konaklama Bilgileri</div>
      <div>Oda: ${escapeHtml(booking?.room_number || '')} (${escapeHtml(booking?.room_type || '')})</div>
      <div>Giriş: ${escapeHtml(booking?.check_in?.toString().slice(0, 10) || '')}</div>
      <div>Çıkış: ${escapeHtml(booking?.check_out?.toString().slice(0, 10) || '')}</div>
      <div>Misafir: ${booking?.adults || 1} Yetiskin, ${booking?.children || 0} Cocuk</div>
    </div>
  </div>
  <table>
    <thead><tr><th>#</th><th>Açıklama</th><th style="text-align:right">Birim Fiyat</th><th style="text-align:center">Adet</th><th style="text-align:right">Tutar</th></tr></thead>
    <tbody>
      <tr><td>1</td><td>Konaklama Ucreti</td><td style="text-align:right">${(totalAmount).toFixed(2)} TL</td><td style="text-align:center">1</td><td style="text-align:right">${totalAmount.toFixed(2)} TL</td></tr>
    </tbody>
  </table>
  <div class="total-section">
    <div class="total-row"><span>Net:</span><span>${netAmount.toFixed(2)} TL</span></div>
    <div class="total-row"><span>KDV (%10):</span><span>${taxAmount.toFixed(2)} TL</span></div>
    <div class="total-row grand"><span>TOPLAM:</span><span>${totalAmount.toFixed(2)} TL</span></div>
  </div>
  <div style="clear:both"></div>
  <div class="note">
    <strong>Not:</strong> Bu bir proforma faturadir; resmi fatura yerine gecmez. Ödeme yapildiginda resmi e-Fatura/e-Arsiv duzenlenecektir.
  </div>
  </body></html>`);
  w.document.close();
  w.print();
}
