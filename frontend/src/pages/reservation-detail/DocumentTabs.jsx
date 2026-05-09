import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, Plus, Banknote, RefreshCw, Shield, FileText } from 'lucide-react';
import { API, fmtTL, fmtTs, SummaryCard, EmptyState, FormField, SelectField } from './helpers';
import { useTranslation } from 'react-i18next';

export function DepositsTab({ deposits, booking, onRefresh }) {
  const { t } = useTranslation();
  const [showDeposit, setShowDeposit] = useState(false);
  const [showRefund, setShowRefund] = useState(null);
  const [depForm, setDepForm] = useState({ amount: '', method: 'cash', reference: '' });
  const [refundForm, setRefundForm] = useState({ refund_amount: '', refund_method: 'cash', reason: '' });
  const [loading, setLoading] = useState(false);

  const handleDeposit = async () => {
    if (!depForm.amount) { toast.error('Tutar giriniz'); return; }
    setLoading(true);
    try {
      await axios.post(`/pms/reservations/${booking.id}/record-deposit`, { ...depForm, amount: parseFloat(depForm.amount) });
      toast.success('Depozito kaydedildi'); setShowDeposit(false); setDepForm({ amount: '', method: 'cash', reference: '' }); onRefresh?.();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  const handleRefund = async (depositId) => {
    if (!refundForm.refund_amount) { toast.error('Iade tutari giriniz'); return; }
    setLoading(true);
    try {
      await axios.post(`/pms/reservations/${booking.id}/refund-deposit`, { deposit_id: depositId, ...refundForm, refund_amount: parseFloat(refundForm.refund_amount) });
      toast.success('Depozito iade edildi'); setShowRefund(null); setRefundForm({ refund_amount: '', refund_method: 'cash', reason: '' }); onRefresh?.();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  const totalDeposits = (deposits || []).reduce((s, d) => s + (d.amount || 0), 0);
  const totalRefunded = (deposits || []).filter(d => d.status === 'refunded').reduce((s, d) => s + (d.amount || 0), 0);

  return (
    <div data-testid="deposits-tab" className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <SummaryCard label={t('cm.pages_reservationdetail_DocumentTabs.toplam_depozito')} value={totalDeposits} color="blue" />
        <SummaryCard label="Iade Edilen" value={totalRefunded} color="amber" />
        <SummaryCard label={t('cm.pages_reservationdetail_DocumentTabs.aktif')} value={totalDeposits - totalRefunded} color="emerald" />
      </div>

      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-700">Depozitolar</span>
        <Button size="sm" onClick={() => setShowDeposit(!showDeposit)} className="h-7 text-xs bg-blue-600 hover:bg-blue-700 text-white"><Plus className="w-3 h-3 mr-1" /> Depozito Al</Button>
      </div>

      {showDeposit && (
        <div className="border rounded-lg p-4 bg-blue-50/50 space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <FormField label={t('cm.pages_reservationdetail_DocumentTabs.tutar_tl')} type="number" value={depForm.amount} onChange={v => setDepForm(p => ({ ...p, amount: v }))} />
            <SelectField label="Yontem" value={depForm.method} onChange={v => setDepForm(p => ({ ...p, method: v }))}
              options={[['cash','Nakit'],['card','Kredi Kartı'],['bank_transfer','Havale/EFT']]} />
            <FormField label="Referans" value={depForm.reference} onChange={v => setDepForm(p => ({ ...p, reference: v }))} />
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={handleDeposit} disabled={loading} className="bg-blue-600 text-white h-8 text-xs">{loading ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Kaydet'}</Button>
            <Button size="sm" variant="ghost" onClick={() => setShowDeposit(false)} className="h-8 text-xs">{t('cm.pages_reservationdetail_DocumentTabs.iptal')}</Button>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {(!deposits || deposits.length === 0) ? <EmptyState icon={Shield} text="Henüz depozito yok" /> : (
          deposits.map((d, i) => (
            <div key={d.id || i} className="border rounded-lg p-3 relative">
              <div className="flex items-center gap-3">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center ${d.status === 'refunded' ? 'bg-gray-100' : 'bg-blue-100'}`}>
                  <Banknote className={`w-4 h-4 ${d.status === 'refunded' ? 'text-gray-400' : 'text-blue-600'}`} />
                </div>
                <div className="flex-1">
                  <div className="text-sm font-medium">Depozito - {d.method === 'cash' ? 'Nakit' : d.method === 'card' ? 'Kart' : 'Havale'}</div>
                  <div className="text-xs text-gray-400">{fmtTs(d.created_at)} | {d.recorded_by} {d.reference && `| Ref: ${d.reference}`}</div>
                </div>
                <div className={`text-sm font-bold ${d.status === 'refunded' ? 'text-gray-400 line-through' : 'text-blue-700'}`}>{fmtTL(d.amount)} TL</div>
                <Badge className={`text-xs ${d.status === 'refunded' ? 'bg-gray-100 text-gray-500' : d.status === 'partially_refunded' ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'}`}>
                  {d.status === 'refunded' ? 'Iade Edildi' : d.status === 'partially_refunded' ? 'Kismi Iade' : 'Aktif'}
                </Badge>
                {d.status !== 'refunded' && (
                  <Button size="sm" variant="ghost" onClick={() => setShowRefund(showRefund === d.id ? null : d.id)} className="h-7 px-2 text-xs text-red-600">
                    <RefreshCw className="w-3 h-3" />
                  </Button>
                )}
              </div>
              {showRefund === d.id && (
                <div className="mt-3 border-t pt-3 space-y-2">
                  <div className="text-xs font-semibold text-red-600">Depozito Iade</div>
                  <div className="grid grid-cols-3 gap-2">
                    <FormField label="Iade Tutari" type="number" value={refundForm.refund_amount} onChange={v => setRefundForm(p => ({ ...p, refund_amount: v }))} />
                    <SelectField label="Yontem" value={refundForm.refund_method} onChange={v => setRefundForm(p => ({ ...p, refund_method: v }))}
                      options={[['cash','Nakit'],['card','Kart'],['bank_transfer','Havale']]} />
                    <div className="flex items-end">
                      <Button size="sm" onClick={() => handleRefund(d.id)} disabled={loading} className="w-full h-8 text-xs bg-red-600 hover:bg-red-700 text-white">Iade Et</Button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export function VoucherTab({ booking, bookingId }) {
  const [voucherHtml, setVoucherHtml] = useState('');
  const [loading, setLoading] = useState(false);

  const generateVoucher = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`/pms/reservations/${bookingId}/voucher`);
      setVoucherHtml(res.data?.voucher_html || '');
    } catch (e) { toast.error('Voucher oluşturulamadı: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  const printVoucher = () => {
    const w = window.open('', '_blank');
    w.document.write(voucherHtml);
    w.document.close();
    w.focus();
    setTimeout(() => w.print(), 300);
  };

  return (
    <div data-testid="voucher-tab" className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-700">{t('cm.pages_reservationdetail_DocumentTabs.misafir_voucher')}</span>
        <Button size="sm" onClick={generateVoucher} disabled={loading} className="bg-teal-600 hover:bg-teal-700 text-white h-8 text-xs" data-testid="generate-voucher-btn">
          {loading ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <FileText className="w-3 h-3 mr-1" />} Voucher Olustur
        </Button>
      </div>
      {voucherHtml && (
        <div className="space-y-3">
          <div className="flex gap-2">
            <Button size="sm" onClick={printVoucher} className="h-8 text-xs" data-testid="print-voucher-btn">{t('cm.pages_reservationdetail_DocumentTabs.yazdir_pdf')}</Button>
          </div>
          <div className="border rounded-lg overflow-hidden">
            <iframe srcDoc={voucherHtml} className="w-full h-[500px] border-0" title="Voucher" />
          </div>
        </div>
      )}
      {!voucherHtml && !loading && (
        <div className="text-center py-12 text-gray-400">
          <FileText className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p className="text-sm">{t('cm.pages_reservationdetail_DocumentTabs.voucher_olusturmak_icin_yukaridaki_buton')}</p>
        </div>
      )}
    </div>
  );
}

export function InvoiceTab({ booking, bookingId }) {
  const [charges, setCharges] = useState([]);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [billingInfo, setBillingInfo] = useState({ name: '', tax_id: '', tax_office: '', address: '', email: '', note: '' });
  const [invoiceHtml, setInvoiceHtml] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingCharges, setLoadingCharges] = useState(false);

  useEffect(() => {
    const loadCharges = async () => {
      setLoadingCharges(true);
      try {
        const res = await axios.get(`/pms/reservations/${bookingId}/invoice-charges`);
        const items = res.data?.charges || [];
        setCharges(items);
        setSelectedIds(new Set(items.map(c => c.id)));
      } catch (_e) { /* charge load failed — empty list is acceptable UX */ }
      setLoadingCharges(false);
    };
    loadCharges();
  }, [bookingId]);

  const toggleItem = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const selectedTotal = charges.filter(c => selectedIds.has(c.id)).reduce((s, c) => s + c.amount, 0);

  const generateInvoice = async () => {
    setLoading(true);
    try {
      const res = await axios.post(`/pms/reservations/${bookingId}/generate-invoice`, {
        selected_charge_ids: [...selectedIds],
        billing_name: billingInfo.name || null,
        billing_tax_id: billingInfo.tax_id || null,
        billing_tax_office: billingInfo.tax_office || null,
        billing_address: billingInfo.address || null,
        billing_email: billingInfo.email || null,
        invoice_note: billingInfo.note || null,
      });
      setInvoiceHtml(res.data?.invoice_html || '');
      toast.success('Fatura oluşturuldu');
    } catch (e) { toast.error('Fatura oluşturulamadı: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  const printInvoice = () => {
    const w = window.open('', '_blank');
    w.document.write(invoiceHtml);
    w.document.close();
    w.focus();
    setTimeout(() => w.print(), 300);
  };

  const catLabels = { room: 'Konaklama', food: 'Yemek', beverage: 'İçecek', minibar: 'Minibar', spa: 'SPA', laundry: 'Çamaşır', parking: 'Otopark', telephone: 'Telefon', transfer: 'Transfer', room_service: 'Oda Servisi', other: 'Diğer' };

  return (
    <div data-testid="invoice-tab" className="space-y-4">
      {!invoiceHtml ? (
        <>
          <div className="text-sm font-semibold text-gray-700">Fatura Bilgileri</div>
          <div className="border rounded-lg p-4 space-y-3 bg-blue-50/30">
            <div className="grid grid-cols-2 gap-3">
              <FormField label="Fatura Edilen Ad/Unvan" value={billingInfo.name} onChange={v => setBillingInfo(p => ({ ...p, name: v }))} placeholder="Firma veya kisi adi" />
              <FormField label="Vergi No" value={billingInfo.tax_id} onChange={v => setBillingInfo(p => ({ ...p, tax_id: v }))} placeholder="Vergi / TC No" />
              <FormField label="Vergi Dairesi" value={billingInfo.tax_office} onChange={v => setBillingInfo(p => ({ ...p, tax_office: v }))} placeholder="Vergi dairesi" />
              <FormField label="E-posta" value={billingInfo.email} onChange={v => setBillingInfo(p => ({ ...p, email: v }))} placeholder="fatura@firma.com" />
            </div>
            <FormField label="Adres" value={billingInfo.address} onChange={v => setBillingInfo(p => ({ ...p, address: v }))} placeholder="Fatura adresi" />
            <FormField label="Fatura Notu" value={billingInfo.note} onChange={v => setBillingInfo(p => ({ ...p, note: v }))} placeholder="Opsiyonel not" />
          </div>

          <div className="text-sm font-semibold text-gray-700 flex items-center justify-between">
            <span>Faturaya Eklenecek Kalemler</span>
            <span className="text-xs text-gray-500">{selectedIds.size}/{charges.length} {t('cm.pages_reservationdetail_DocumentTabs.secili_toplam')} {fmtTL(selectedTotal)} TL</span>
          </div>
          {loadingCharges ? (
            <div className="flex items-center gap-2 text-sm text-gray-400"><Loader2 className="w-4 h-4 animate-spin" /> {t('cm.pages_reservationdetail_DocumentTabs.yukleniyor')}</div>
          ) : (
            <div className="space-y-1 border rounded-lg overflow-hidden">
              {charges.map(c => (
                <label key={c.id} className={`flex items-center gap-3 p-3 cursor-pointer hover:bg-gray-50 transition-colors ${selectedIds.has(c.id) ? 'bg-blue-50/50' : ''}`}>
                  <input type="checkbox" checked={selectedIds.has(c.id)} onChange={() => toggleItem(c.id)} className="rounded" />
                  <div className="flex-1">
                    <div className="text-sm font-medium">{c.description}</div>
                    <div className="text-xs text-gray-400">{catLabels[c.category] || c.category} | {c.date}</div>
                  </div>
                  <div className="text-sm font-bold text-gray-700">{fmtTL(c.amount)} TL</div>
                </label>
              ))}
            </div>
          )}

          <Button onClick={generateInvoice} disabled={loading || selectedIds.size === 0} className="w-full h-9 text-sm bg-blue-600 hover:bg-blue-700 text-white" data-testid="generate-invoice-btn">
            {loading ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <FileText className="w-4 h-4 mr-1" />} Fatura Olustur ({fmtTL(selectedTotal)} TL)
          </Button>
        </>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-gray-700">Fatura Onizleme</span>
            <div className="flex gap-2">
              <Button size="sm" onClick={printInvoice} className="h-8 text-xs" data-testid="print-invoice-btn">{t('cm.pages_reservationdetail_DocumentTabs.yazdir_pdf_871eb')}</Button>
              <Button size="sm" variant="outline" onClick={() => setInvoiceHtml('')} className="h-8 text-xs">{t('cm.pages_reservationdetail_DocumentTabs.yeni_fatura')}</Button>
            </div>
          </div>
          <div className="border rounded-lg overflow-hidden">
            <iframe srcDoc={invoiceHtml} className="w-full h-[600px] border-0" title="Fatura" />
          </div>
        </div>
      )}
    </div>
  );
}
