var e={name:`Syroce Hotel`,address:``,phone:``,email:``,tax_no:``,tax_office:``};function t(t){return t?typeof t==`string`?{...e,name:t}:{...e,name:t.name||t.hotel_name||t.org_name||e.name,address:t.address||t.hotel_address||``,phone:t.phone||t.hotel_phone||t.contact_phone||``,email:t.email||t.hotel_email||t.contact_email||``,tax_no:t.tax_no||t.tax_number||t.vergi_no||``,tax_office:t.tax_office||t.vergi_dairesi||``}:{...e}}function n(e){return String(e??``).replaceAll(`&`,`&amp;`).replaceAll(`<`,`&lt;`).replaceAll(`>`,`&gt;`).replaceAll(`"`,`&quot;`)}function r(e,r,i,a){let o=t(a),s=window.open(``,`_blank`);s&&(s.document.write(`<html><head><title>Kayıt Kartı - ${n(r?.name||``)}</title>
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
  <div class="hotel-name">${n(o.name)}</div>
  <div class="hotel-meta">
    ${[o.address,o.phone,o.email].filter(Boolean).map(n).join(` &nbsp;·&nbsp; `)}
  </div>
  <div class="subtitle">MISAFIR KAYIT KARTI / GUEST REGISTRATION CARD</div>
  <div class="grid">
    <div class="field"><div class="label">Ad Soyad / Full Name</div><div class="value">${n(r?.name||``)}</div></div>
    <div class="field"><div class="label">TC/Pasaport No / ID/Passport</div><div class="value">${n(r?.id_number||r?.passport_number||``)}</div></div>
    <div class="field"><div class="label">Uyruk / Nationality</div><div class="value">${n(r?.nationality||`TC`)}</div></div>
    <div class="field"><div class="label">Dogum Tarihi / Birth Date</div><div class="value">${n(r?.birth_date||``)}</div></div>
    <div class="field"><div class="label">E-posta / Email</div><div class="value">${n(r?.email||``)}</div></div>
    <div class="field"><div class="label">Telefon / Phone</div><div class="value">${n(r?.phone||``)}</div></div>
    <div class="field"><div class="label">Adres / Address</div><div class="value">${n(r?.address||``)}</div></div>
    <div class="field"><div class="label">Şirket / Company</div><div class="value">${n(e?.company_name||``)}</div></div>
  </div>
  <div class="section">
    <div class="section-title">Konaklama Bilgileri / Stay Details</div>
    <div class="grid">
      <div class="field"><div class="label">Oda No / Room No</div><div class="value">${n(e?.room_number||i?.room_number||``)}</div></div>
      <div class="field"><div class="label">Oda Tipi / Room Type</div><div class="value">${n(i?.room_type||e?.room_type||``)}</div></div>
      <div class="field"><div class="label">Giriş / Check-in</div><div class="value">${n(e?.check_in?.toString().slice(0,10)||``)}</div></div>
      <div class="field"><div class="label">Çıkış / Check-out</div><div class="value">${n(e?.check_out?.toString().slice(0,10)||``)}</div></div>
      <div class="field"><div class="label">Yetiskin / Adults</div><div class="value">${e?.adults||1}</div></div>
      <div class="field"><div class="label">Cocuk / Children</div><div class="value">${e?.children||0}</div></div>
      <div class="field"><div class="label">Pansiyon / Board</div><div class="value">${n(e?.board_type||`Oda+Kahvalti`)}</div></div>
      <div class="field"><div class="label">Kanal / Channel</div><div class="value">${n(e?.channel||e?.source_channel||`Direkt`)}</div></div>
    </div>
  </div>
  <div class="section">
    <div class="section-title">Özel Istekler / Special Requests</div>
    <div class="field"><div class="value" style="min-height:40px">${n(e?.special_requests||r?.notes||``)}</div></div>
  </div>
  <div class="kvkk">
    KVKK AYDINLATMA METNI: Kisisel verileriniz, 6698 sayili Kisisel Verilerin Korunmasi Kanunu kapsaminda, konaklama hizmetlerinin sunulmasi, yasal yukumluluklerin yerine getirilmesi ve güvenlik amaciyla islenmektedir. Detaylı bilgi için resepsiyondan KVKK aydinlatma metnini talep edebilirsiniz.
    <br/><br/>
    PERSONAL DATA NOTICE: Your personal data is processed in accordance with applicable data protection regulations for the purpose of providing accommodation services, fulfilling legal obligations, and security purposes.
  </div>
  <div class="signature-area">
    <div class="signature-box">Misafir Imzasi / Guest Signature<br/><br/>Tarih / Date: ${new Date().toLocaleDateString(`tr-TR`)}</div>
    <div class="signature-box">Resepsiyon / Reception<br/><br/>Tarih / Date: ${new Date().toLocaleDateString(`tr-TR`)}</div>
  </div>
  </body></html>`),s.document.close(),s.print())}function i(e,r){let i=t(r),a=window.open(``,`_blank`);if(!a)return;let o=e?.folio,s=e?.summary,c=e?.timeline||[];a.document.write(`<html><head><title>Folio - ${n(o?.folio_number||``)}</title>
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
    <div class="hotel-name">${n(i.name)}</div>
    <div class="hotel-meta">
      ${[i.address,i.phone,i.email].filter(Boolean).map(n).join(` &nbsp;·&nbsp; `)}
      ${i.tax_no?`<br/>Vergi No: ${n(i.tax_no)}${i.tax_office?` · Vergi Dairesi: `+n(i.tax_office):``}`:``}
    </div>
    <div class="subtitle">MISAFIR HESAP DOKUMU / GUEST FOLIO</div>
  </div>
  <div class="info-grid">
    <div class="info-item"><span class="info-label">Folio No:</span><span class="info-value">${n(o?.folio_number||o?.id?.slice(0,12)||``)}</span></div>
    <div class="info-item"><span class="info-label">Tarih:</span><span class="info-value">${new Date().toLocaleDateString(`tr-TR`)}</span></div>
    <div class="info-item"><span class="info-label">Misafir:</span><span class="info-value">${n(o?.guest_name||``)}</span></div>
    <div class="info-item"><span class="info-label">Oda No:</span><span class="info-value">${n(o?.room_number||``)}</span></div>
    <div class="info-item"><span class="info-label">Giriş:</span><span class="info-value">${n(o?.check_in?.toString().slice(0,10)||``)}</span></div>
    <div class="info-item"><span class="info-label">Çıkış:</span><span class="info-value">${n(o?.check_out?.toString().slice(0,10)||``)}</span></div>
    <div class="info-item"><span class="info-label">Durum:</span><span class="info-value">${n(o?.status||``)}</span></div>
    <div class="info-item"><span class="info-label">Tip:</span><span class="info-value">${n(o?.folio_type||``)}</span></div>
  </div>
  <table>
    <thead><tr><th>Tarih</th><th>Açıklama</th><th>Kategori</th><th style="text-align:right">Borc</th><th style="text-align:right">Alacak</th><th style="text-align:right">Bakiye</th></tr></thead>
    <tbody>
    ${c.map(e=>`
      <tr class="${e.voided?`voided`:``}">
        <td>${n(e.timestamp?.slice(0,10)||``)}</td>
        <td>${n(e.description||e.type||``)}</td>
        <td>${n(e.category||``)}</td>
        <td style="text-align:right" class="amount-out">${e.type===`charge`?(e.amount||0).toFixed(2):``}</td>
        <td style="text-align:right" class="amount-in">${e.type===`payment`?(e.amount||0).toFixed(2):``}</td>
        <td style="text-align:right">${e.running_balance?.toFixed(2)||``}</td>
      </tr>
    `).join(``)}
    </tbody>
  </table>
  <div class="totals">
    <div class="total-row"><span>Toplam Masraf / Total Charges:</span><span>${(s?.total_charges||0).toFixed(2)} TL</span></div>
    <div class="total-row"><span>Toplam Ödeme / Total Payments:</span><span>${(s?.total_payments||0).toFixed(2)} TL</span></div>
    <div class="total-row final"><span>BAKIYE / BALANCE:</span><span>${(s?.balance||0).toFixed(2)} TL</span></div>
  </div>
  <div class="footer">
    <p>Bu belge ${new Date().toLocaleString(`tr-TR`)} tarihinde olusturulmustur.</p>
    <p>${n(i.name)} - Tüm haklar saklidir</p>
  </div>
  </body></html>`),a.document.close(),a.print()}function a(e,r,i,a){let o=t(a),s=window.open(``,`_blank`);if(!s)return;let c=e?.total_amount||i?.reduce((e,t)=>e+(t.amount||0),0)||0,l=c/1.1,u=c-l;s.document.write(`<html><head><title>Proforma Fatura</title>
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
      <div class="hotel-name">${n(o.name)}</div>
      <div class="hotel-info">
        ${o.address?`Adres: `+n(o.address)+`<br/>`:``}
        ${o.phone?`Tel: `+n(o.phone)+`<br/>`:``}
        ${o.email?`E-posta: `+n(o.email)+`<br/>`:``}
        ${o.tax_no?`Vergi No: `+n(o.tax_no):``}
        ${o.tax_office?` · Vergi Dairesi: `+n(o.tax_office):``}
      </div>
    </div>
    <div>
      <div class="proforma-title">PROFORMA FATURA</div>
      <div class="proforma-no">No: PF-${Date.now().toString().slice(-8)}</div>
      <div class="proforma-no">Tarih: ${new Date().toLocaleDateString(`tr-TR`)}</div>
    </div>
  </div>
  <div class="parties">
    <div class="party">
      <div class="party-title">Misafir Bilgileri</div>
      <div>${n(r?.name||e?.guest_name||``)}</div>
      <div>${n(r?.email||``)}</div>
      <div>${n(r?.phone||``)}</div>
      <div>${n(r?.address||``)}</div>
    </div>
    <div class="party">
      <div class="party-title">Konaklama Bilgileri</div>
      <div>Oda: ${n(e?.room_number||``)} (${n(e?.room_type||``)})</div>
      <div>Giriş: ${n(e?.check_in?.toString().slice(0,10)||``)}</div>
      <div>Çıkış: ${n(e?.check_out?.toString().slice(0,10)||``)}</div>
      <div>Misafir: ${e?.adults||1} Yetiskin, ${e?.children||0} Cocuk</div>
    </div>
  </div>
  <table>
    <thead><tr><th>#</th><th>Açıklama</th><th style="text-align:right">Birim Fiyat</th><th style="text-align:center">Adet</th><th style="text-align:right">Tutar</th></tr></thead>
    <tbody>
      <tr><td>1</td><td>Konaklama Ucreti</td><td style="text-align:right">${c.toFixed(2)} TL</td><td style="text-align:center">1</td><td style="text-align:right">${c.toFixed(2)} TL</td></tr>
    </tbody>
  </table>
  <div class="total-section">
    <div class="total-row"><span>Net:</span><span>${l.toFixed(2)} TL</span></div>
    <div class="total-row"><span>KDV (%10):</span><span>${u.toFixed(2)} TL</span></div>
    <div class="total-row grand"><span>TOPLAM:</span><span>${c.toFixed(2)} TL</span></div>
  </div>
  <div style="clear:both"></div>
  <div class="note">
    <strong>Not:</strong> Bu bir proforma faturadir; resmi fatura yerine gecmez. Ödeme yapildiginda resmi e-Fatura/e-Arsiv duzenlenecektir.
  </div>
  </body></html>`),s.document.close(),s.print()}export{a as n,r,i as t};