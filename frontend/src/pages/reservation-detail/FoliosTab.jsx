import { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  CreditCard, ArrowRightLeft, Building2, DollarSign, ArrowDownUp,
  Plus, Receipt, FileText, Loader2
} from 'lucide-react';
import { API, fmtTL, fmtTs, SummaryCard, FormField, SelectField, FormPanel } from './helpers';

export function FoliosTab({ folios, charges, payments, extra_charges, summary, booking, onRefresh, onSwitchTab }) {
  const [showPayment, setShowPayment] = useState(false);
  const [showCari, setShowCari] = useState(false);
  const [showAgency, setShowAgency] = useState(false);
  const [showCariTransfer, setShowCariTransfer] = useState(false);
  const [showReconcile, setShowReconcile] = useState(false);
  const [payForm, setPayForm] = useState({ amount: '', method: 'cash', payment_type: 'interim', reference: '' });
  const [cariAccounts, setCariAccounts] = useState([]);
  const [cariForm, setCariForm] = useState({ amount: '', cari_account_id: '', description: '' });
  const [agencyForm, setAgencyForm] = useState({ amount: '', agency_name: '', reference: '' });
  const [cariTransferForm, setCariTransferForm] = useState({ source_id: '', target_id: '', amount: '', description: '' });
  const [showNewCari, setShowNewCari] = useState(false);
  const [newCariForm, setNewCariForm] = useState({ name: '', account_type: 'agency', tax_id: '', tax_office: '', address: '', phone: '', email: '' });
  const [reconcileForm, setReconcileForm] = useState({ cari_account_id: '', amount: '', description: '' });
  const [loading, setLoading] = useState(false);

  const loadCari = async () => { try { const r = await axios.get(`/pms/cari-accounts`); setCariAccounts(r.data.accounts || []); } catch { /* fetch error */ } };

  const exec = async (fn) => { setLoading(true); try { await fn(); onRefresh?.(); } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); } setLoading(false); };

  const allItems = [
    ...(charges || []).map(c => ({ ...c, _type: 'charge' })),
    ...(extra_charges || []).map(c => ({ ...c, _type: 'charge' })),
    ...(payments || []).map(p => ({ ...p, _type: 'payment' })),
  ].sort((a, b) => new Date(b.created_at || b.processed_at || 0) - new Date(a.created_at || a.processed_at || 0));

  return (
    <div data-testid="folios-tab" className="space-y-4">
      <div className="grid grid-cols-4 gap-3">
        <SummaryCard label="Toplam" value={summary?.total_amount} color="blue" />
        <SummaryCard label="Masraflar" value={(summary?.total_charges || 0) + (summary?.total_extra || 0)} color="amber" />
        <SummaryCard label="Odemeler" value={summary?.total_payments} color="emerald" />
        <SummaryCard label="Bakiye" value={summary?.balance} color={(summary?.balance || 0) > 0 ? 'red' : 'green'} />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => setShowPayment(!showPayment)} className="bg-emerald-600 hover:bg-emerald-700 text-white h-8 text-xs" data-testid="btn-odeme-al"><CreditCard className="w-3 h-3 mr-1" /> Odeme Al</Button>
        <Button size="sm" variant="outline" onClick={() => { setShowCari(!showCari); loadCari(); }} className="h-8 text-xs border-orange-300 text-orange-700 hover:bg-orange-50" data-testid="btn-cariye-aktar"><ArrowRightLeft className="w-3 h-3 mr-1" /> Cariye Aktar</Button>
        <Button size="sm" variant="outline" onClick={() => setShowAgency(!showAgency)} className="h-8 text-xs border-purple-300 text-purple-700 hover:bg-purple-50" data-testid="btn-acente-odemesi"><Building2 className="w-3 h-3 mr-1" /> Acente Odemesi</Button>
        <Button size="sm" variant="outline" onClick={() => { setShowCariTransfer(!showCariTransfer); loadCari(); }} className="h-8 text-xs border-indigo-300 text-indigo-700 hover:bg-indigo-50" data-testid="btn-acenteye-aktar"><ArrowDownUp className="w-3 h-3 mr-1" /> Acenteye Aktar</Button>
        <Button size="sm" variant="outline" onClick={() => { setShowReconcile(!showReconcile); loadCari(); }} className="h-8 text-xs border-teal-300 text-teal-700 hover:bg-teal-50" data-testid="btn-mahsuplastir"><DollarSign className="w-3 h-3 mr-1" /> Mahsuplastir</Button>
        <Button size="sm" variant="outline" onClick={() => onSwitchTab('invoice')} className="h-8 text-xs border-blue-300 text-blue-700 hover:bg-blue-50" data-testid="btn-fatura-pdf">
          <FileText className="w-3 h-3 mr-1" /> Fatura Olustur
        </Button>
      </div>

      {showPayment && (
        <FormPanel color="emerald" title="Odeme Kaydet" testid="payment-form" onClose={() => setShowPayment(false)} loading={loading}
          onSubmit={() => exec(async () => {
            await axios.post(`/pms/reservations/${booking.id}/record-payment`, { ...payForm, amount: parseFloat(payForm.amount) });
            toast.success('Odeme kaydedildi'); setShowPayment(false); setPayForm({ amount: '', method: 'cash', payment_type: 'interim', reference: '' });
          })}>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Tutar (TL)" type="number" value={payForm.amount} onChange={v => setPayForm(p => ({ ...p, amount: v }))} />
            <SelectField label="Odeme Yontemi" value={payForm.method} onChange={v => setPayForm(p => ({ ...p, method: v }))}
              options={[['cash','Nakit'],['card','Kredi Karti'],['bank_transfer','Havale/EFT'],['online','Online']]} />
            <SelectField label="Odeme Tipi" value={payForm.payment_type} onChange={v => setPayForm(p => ({ ...p, payment_type: v }))}
              options={[['prepayment','On Odeme'],['deposit','Depozito'],['interim','Ara Odeme'],['final','Final']]} />
            <FormField label="Referans" value={payForm.reference} onChange={v => setPayForm(p => ({ ...p, reference: v }))} placeholder="Fis/Dekont No" />
          </div>
        </FormPanel>
      )}

      {showCari && (
        <FormPanel color="orange" title="Cariye Aktar" testid="cari-transfer-form" onClose={() => setShowCari(false)} loading={loading}
          onSubmit={() => exec(async () => {
            await axios.post(`/pms/reservations/${booking.id}/transfer-to-cari`, { ...cariForm, amount: parseFloat(cariForm.amount) });
            toast.success('Cariye aktarildi'); setShowCari(false); setCariForm({ amount: '', cari_account_id: '', description: '' });
          })}>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Tutar (TL)" type="number" value={cariForm.amount} onChange={v => setCariForm(p => ({ ...p, amount: v }))} />
            <SelectField label="Cari Hesap" value={cariForm.cari_account_id} onChange={v => setCariForm(p => ({ ...p, cari_account_id: v }))}
              options={[['','Hesap Seciniz...'], ...cariAccounts.map(a => [a.id, `${a.name} (${a.account_type || ''})`])]} />
          </div>
          <FormField label="Aciklama" value={cariForm.description} onChange={v => setCariForm(p => ({ ...p, description: v }))} placeholder="Opsiyonel" />
        </FormPanel>
      )}

      {showAgency && (
        <FormPanel color="purple" title="Acente Odemesi" testid="agency-payment-form" onClose={() => setShowAgency(false)} loading={loading}
          onSubmit={() => exec(async () => {
            await axios.post(`/pms/reservations/${booking.id}/record-agency-payment`, { ...agencyForm, amount: parseFloat(agencyForm.amount) });
            toast.success('Acente odemesi kaydedildi'); setShowAgency(false); setAgencyForm({ amount: '', agency_name: '', reference: '' });
          })}>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Tutar (TL)" type="number" value={agencyForm.amount} onChange={v => setAgencyForm(p => ({ ...p, amount: v }))} />
            <FormField label="Acente Adi" value={agencyForm.agency_name} onChange={v => setAgencyForm(p => ({ ...p, agency_name: v }))} />
          </div>
          <FormField label="Referans" value={agencyForm.reference} onChange={v => setAgencyForm(p => ({ ...p, reference: v }))} placeholder="Voucher No" />
        </FormPanel>
      )}

      {showCariTransfer && (
        <FormPanel color="indigo" title="Cariyi Acenteye Aktar" testid="cari-agency-transfer-form" onClose={() => setShowCariTransfer(false)} loading={loading}
          onSubmit={() => exec(async () => {
            if (!cariTransferForm.source_id || !cariTransferForm.target_id) { toast.error('Kaynak ve hedef cari hesap seciniz'); return; }
            await axios.post(`/pms/cari-accounts/${cariTransferForm.source_id}/transfer-to-agency`, {
              amount: parseFloat(cariTransferForm.amount),
              cari_account_id: cariTransferForm.target_id,
              description: cariTransferForm.description || 'Acenteye aktarim'
            });
            toast.success('Cari bakiye acenteye aktarildi');
            setShowCariTransfer(false);
            setCariTransferForm({ source_id: '', target_id: '', amount: '', description: '' });
          })}>
          <div className="grid grid-cols-2 gap-3">
            <SelectField label="Kaynak Cari Hesap" value={cariTransferForm.source_id} onChange={v => setCariTransferForm(p => ({ ...p, source_id: v }))}
              options={[['','Hesap Seciniz...'], ...cariAccounts.map(a => [a.id, `${a.name} (${a.account_type || ''})`])]} />
            <div>
              <SelectField label="Hedef Acente Hesabi" value={cariTransferForm.target_id} onChange={v => setCariTransferForm(p => ({ ...p, target_id: v }))}
                options={[['','Acente Seciniz...'], ...cariAccounts.filter(a => a.account_type === 'agency').map(a => [a.id, a.name])]} />
              <Button size="sm" variant="ghost" className="h-6 text-xs text-indigo-600 mt-1 px-0" onClick={() => setShowNewCari(true)} data-testid="btn-new-cari"><Plus className="w-3 h-3 mr-1" /> Yeni Cari Olustur</Button>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Tutar (TL)" type="number" value={cariTransferForm.amount} onChange={v => setCariTransferForm(p => ({ ...p, amount: v }))} />
            <FormField label="Aciklama" value={cariTransferForm.description} onChange={v => setCariTransferForm(p => ({ ...p, description: v }))} placeholder="Opsiyonel" />
          </div>
        </FormPanel>
      )}

      {showNewCari && (
        <div className="border rounded-lg p-4 bg-indigo-50/50 space-y-3" data-testid="new-cari-form">
          <div className="text-sm font-semibold text-indigo-800">Yeni Cari Hesap Olustur</div>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Hesap Adi *" value={newCariForm.name} onChange={v => setNewCariForm(p => ({ ...p, name: v }))} placeholder="Acente / Sirket adi" />
            <SelectField label="Hesap Tipi" value={newCariForm.account_type} onChange={v => setNewCariForm(p => ({ ...p, account_type: v }))}
              options={[['agency','Acente'],['corporate','Kurumsal'],['individual','Bireysel']]} />
            <FormField label="Vergi No" value={newCariForm.tax_id} onChange={v => setNewCariForm(p => ({ ...p, tax_id: v }))} placeholder="Vergi / TC No" />
            <FormField label="Vergi Dairesi" value={newCariForm.tax_office} onChange={v => setNewCariForm(p => ({ ...p, tax_office: v }))} placeholder="Vergi dairesi" />
            <FormField label="Telefon" value={newCariForm.phone} onChange={v => setNewCariForm(p => ({ ...p, phone: v }))} placeholder="Telefon" />
            <FormField label="E-posta" value={newCariForm.email} onChange={v => setNewCariForm(p => ({ ...p, email: v }))} placeholder="E-posta" />
          </div>
          <FormField label="Adres" value={newCariForm.address} onChange={v => setNewCariForm(p => ({ ...p, address: v }))} placeholder="Adres" />
          <div className="flex gap-2">
            <Button size="sm" onClick={async () => {
              if (!newCariForm.name) { toast.error('Hesap adi zorunlu'); return; }
              setLoading(true);
              try {
                await axios.post(`/pms/cari-accounts/create`, newCariForm);
                toast.success('Yeni cari hesap olusturuldu');
                setShowNewCari(false);
                setNewCariForm({ name: '', account_type: 'agency', tax_id: '', tax_office: '', address: '', phone: '', email: '' });
                loadCari();
              } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
              setLoading(false);
            }} disabled={loading} className="bg-indigo-600 hover:bg-indigo-700 text-white h-8 text-xs" data-testid="create-cari-btn">
              {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Olustur'}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowNewCari(false)} className="h-8 text-xs">Iptal</Button>
          </div>
        </div>
      )}

      {showReconcile && (
        <FormPanel color="teal" title="Mahsuplastirma (Cari Odeme)" testid="reconcile-form" onClose={() => setShowReconcile(false)} loading={loading}
          onSubmit={() => exec(async () => {
            if (!reconcileForm.cari_account_id) { toast.error('Cari hesap seciniz'); return; }
            await axios.post(`/pms/cari-accounts/${reconcileForm.cari_account_id}/reconcile`, {
              amount: parseFloat(reconcileForm.amount),
              description: reconcileForm.description || 'Mahsuplastirma'
            });
            toast.success('Mahsuplastirma kaydedildi');
            setShowReconcile(false);
            setReconcileForm({ cari_account_id: '', amount: '', description: '' });
          })}>
          <div className="grid grid-cols-2 gap-3">
            <SelectField label="Cari Hesap" value={reconcileForm.cari_account_id} onChange={v => setReconcileForm(p => ({ ...p, cari_account_id: v }))}
              options={[['','Hesap Seciniz...'], ...cariAccounts.map(a => [a.id, `${a.name} (${a.account_type || ''})`])]} />
            <FormField label="Tutar (TL)" type="number" value={reconcileForm.amount} onChange={v => setReconcileForm(p => ({ ...p, amount: v }))} />
          </div>
          <FormField label="Aciklama" value={reconcileForm.description} onChange={v => setReconcileForm(p => ({ ...p, description: v }))} placeholder="Mahsuplastirma aciklamasi" />
        </FormPanel>
      )}

      <div className="space-y-2">
        <div className="text-xs font-semibold text-gray-500 uppercase">Islem Gecmisi</div>
        {allItems.length === 0 ? <div className="text-center py-6 text-gray-400 text-sm">Henuz islem bulunmuyor</div> : (
          allItems.map((item, i) => (
            <div key={item.id || i} className={`flex items-center gap-3 p-3 rounded-lg border ${item.voided ? 'opacity-50 bg-gray-50' : 'bg-white'}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center ${item._type === 'payment' ? 'bg-emerald-100' : 'bg-amber-100'}`}>
                {item._type === 'payment' ? <CreditCard className="w-4 h-4 text-emerald-600" /> : <Receipt className="w-4 h-4 text-amber-600" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-gray-800">{item.description || item.charge_name || item.method || item.payment_type || '-'}</div>
                <div className="text-xs text-gray-400">{fmtTs(item.created_at || item.processed_at)}{item.agency_name && <span className="ml-2 text-purple-600">({item.agency_name})</span>}</div>
              </div>
              <div className={`text-sm font-bold ${item._type === 'payment' ? 'text-emerald-600' : 'text-amber-600'}`}>
                {item._type === 'payment' ? '-' : '+'}{fmtTL(item.amount || item.total || item.charge_amount)} TL
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
