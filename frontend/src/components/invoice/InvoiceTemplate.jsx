import React from 'react';
import { formatAmount } from '@/lib/currency';

/**
 * A4 size printable e-Invoice template.
 * Designed to look crisp and white on both screen and paper.
 */
const InvoiceTemplate = ({ invoice, tenant }) => {
  if (!invoice) return null;

  // Mock data fallbacks for preview
  const invoiceNo = invoice.invoiceNo || `SYR2026${Math.floor(Math.random() * 100000000).toString().padStart(8, '0')}`;
  const ettn = invoice.ettn || '00000000-0000-0000-0000-000000000000';
  const issueDate = invoice.date ? new Date(invoice.date).toLocaleDateString('tr-TR') : new Date().toLocaleDateString('tr-TR');
  const issueTime = invoice.date ? new Date(invoice.date).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }) : new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
  
  const customerName = invoice.customerName || invoice.guestName || 'Bilinmeyen Müşteri';
  const customerTaxId = invoice.taxId || '11111111111';
  const customerTaxOffice = invoice.taxOffice || 'Bilinmiyor';
  const customerAddress = invoice.address || 'Adres belirtilmemiş.';

  const tenantName = tenant?.property_name || 'Syroce PMS Hotel';
  const tenantTaxId = tenant?.tax_id || '9999999999';
  const tenantTaxOffice = tenant?.tax_office || 'Kurumlar VD.';
  const tenantAddress = tenant?.address || 'Otel Adresi, Şehir, Türkiye';

  // Sample items if invoice has no items
  const items = invoice.items && invoice.items.length > 0 ? invoice.items : [
    { description: 'Konaklama Bedeli', quantity: 1, unitPrice: invoice.amount || 1500, taxRate: 10 },
  ];

  const subtotal = items.reduce((acc, item) => acc + (item.quantity * item.unitPrice), 0);
  const taxTotal = items.reduce((acc, item) => acc + (item.quantity * item.unitPrice * (item.taxRate / 100)), 0);
  const grandTotal = subtotal + taxTotal;

  return (
    <div className="bg-white text-black p-8 sm:p-12 w-full max-w-[800px] mx-auto min-h-[1123px] shadow-sm relative text-sm" id="invoice-printable-area">
      {/* Hide on screen, show on print to reset styles */}
      <style>{`
        @media print {
          body * {
            visibility: hidden !important;
          }
          #invoice-printable-area, #invoice-printable-area * {
            visibility: visible !important;
          }
          #invoice-printable-area {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            margin: 0;
            padding: 20px;
            box-shadow: none;
          }
        }
      `}</style>

      {/* Header */}
      <div className="flex justify-between items-start border-b-2 border-gray-100 pb-8 mb-8">
        <div className="flex flex-col">
          {/* Logo Placeholder */}
          <div className="flex items-center gap-2 mb-4">
            <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold text-xl">
              {tenantName.charAt(0)}
            </div>
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight">{tenantName}</h1>
          </div>
          <div className="text-gray-600 space-y-1 text-xs">
            <p className="max-w-[250px]">{tenantAddress}</p>
            <p><strong>VD:</strong> {tenantTaxOffice} | <strong>VKN/TCKN:</strong> {tenantTaxId}</p>
            <p><strong>Tel:</strong> +90 555 123 4567 | <strong>Email:</strong> info@syrocepms.com</p>
          </div>
        </div>

        <div className="text-right">
          <div className="inline-block border-2 border-gray-800 p-2 mb-4">
            <h2 className="text-xl font-bold text-gray-800 tracking-widest uppercase">e-Fatura</h2>
          </div>
          <div className="space-y-1 text-xs text-gray-600">
            <p><span className="font-semibold text-gray-800">Fatura No:</span> {invoiceNo}</p>
            <p><span className="font-semibold text-gray-800">Düzenleme Tarihi:</span> {issueDate}</p>
            <p><span className="font-semibold text-gray-800">Düzenleme Zamanı:</span> {issueTime}</p>
            <p className="text-[10px] mt-2 max-w-[200px] break-all"><span className="font-semibold text-gray-800">ETTN:</span> {ettn}</p>
          </div>
        </div>
      </div>

      {/* Customer Details */}
      <div className="bg-gray-50 rounded-xl p-6 mb-8 border border-gray-100">
        <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3">SAYIN / TO</h3>
        <p className="text-base font-bold text-gray-900 mb-1">{customerName}</p>
        <p className="text-sm text-gray-600 mb-2 max-w-[400px]">{customerAddress}</p>
        <div className="flex gap-4 text-sm text-gray-600">
          <p><strong>Vergi Dairesi:</strong> {customerTaxOffice}</p>
          <p><strong>VKN/TCKN:</strong> {customerTaxId}</p>
        </div>
      </div>

      {/* Line Items Table */}
      <div className="mb-8">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b-2 border-gray-800 text-gray-800 text-xs uppercase tracking-wider">
              <th className="py-3 px-2 font-bold">Hizmet / Ürün Adı</th>
              <th className="py-3 px-2 font-bold text-center">Miktar</th>
              <th className="py-3 px-2 font-bold text-right">Birim Fiyat</th>
              <th className="py-3 px-2 font-bold text-center">KDV (%)</th>
              <th className="py-3 px-2 font-bold text-right">Tutar</th>
            </tr>
          </thead>
          <tbody className="text-sm text-gray-700">
            {items.map((item, idx) => (
              <tr key={idx} className="border-b border-gray-100 last:border-0">
                <td className="py-4 px-2">{item.description}</td>
                <td className="py-4 px-2 text-center">{item.quantity}</td>
                <td className="py-4 px-2 text-right">{formatAmount(item.unitPrice, invoice.currency || 'TRY')}</td>
                <td className="py-4 px-2 text-center">% {item.taxRate}</td>
                <td className="py-4 px-2 text-right font-medium">{formatAmount(item.quantity * item.unitPrice, invoice.currency || 'TRY')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Totals */}
      <div className="flex justify-end">
        <div className="w-full max-w-[300px] space-y-3">
          <div className="flex justify-between text-sm text-gray-600 px-2">
            <span>Mal Hizmet Toplamı:</span>
            <span>{formatAmount(subtotal, invoice.currency || 'TRY')}</span>
          </div>
          <div className="flex justify-between text-sm text-gray-600 px-2">
            <span>Hesaplanan KDV:</span>
            <span>{formatAmount(taxTotal, invoice.currency || 'TRY')}</span>
          </div>
          <div className="flex justify-between text-lg font-bold text-gray-900 border-t-2 border-gray-800 pt-3 px-2">
            <span>Ödenecek Tutar:</span>
            <span>{formatAmount(grandTotal, invoice.currency || 'TRY')}</span>
          </div>
        </div>
      </div>

      {/* Footer / Notes */}
      <div className="mt-16 pt-8 border-t border-gray-100 text-xs text-gray-500 space-y-2">
        <p><strong>Not:</strong> Yalnız {grandTotal.toFixed(2)} TL'dir. (Yazı ile simülasyon)</p>
        <p>Banka Hesap Bilgilerimiz:</p>
        <p>TR12 0000 0000 0000 0000 0000 00 - X Bankası A.Ş.</p>
        <p className="mt-4 text-center text-gray-400">Bu belge e-Fatura kapsamında elektronik olarak düzenlenmiştir.</p>
      </div>
    </div>
  );
};

export default InvoiceTemplate;
