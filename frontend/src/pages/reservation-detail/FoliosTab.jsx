import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  CreditCard, ArrowRightLeft, Building2, DollarSign, ArrowDownUp,
  Plus, Receipt, FileText, Loader2, Split
} from 'lucide-react';
import { API, fmtTL, fmtTs, SummaryCard, FormField, SelectField, FormPanel } from './helpers';
import SplitFolioDialog from '@/components/SplitFolioDialog';
import {
  classifyGuestPayment,
  guestPaymentClassificationLabel,
} from '@/utils/paymentClassification';

export function FoliosTab({ folios, charges, payments, extra_charges, summary, booking, guest, room, onRefresh, onSwitchTab, readOnly = false }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [showPayment, setShowPayment] = useState(false);
  const [showCari, setShowCari] = useState(false);
  const [showAgency, setShowAgency] = useState(false);
  const [showCariTransfer, setShowCariTransfer] = useState(false);
  const [showReconcile, setShowReconcile] = useState(false);
  const [payForm, setPayForm] = useState({ amount: '', method: 'cash', reference: '' });
  const [cariAccounts, setCariAccounts] = useState([]);
  const [cariForm, setCariForm] = useState({ amount: '', cari_account_id: '', description: '' });
  const [agencyForm, setAgencyForm] = useState({ amount: '', agency_name: '', reference: '' });
  const [cariTransferForm, setCariTransferForm] = useState({ source_id: '', target_id: '', amount: '', description: '' });
  const [showNewCari, setShowNewCari] = useState(false);
  const [newCariForm, setNewCariForm] = useState({ name: '', account_type: 'agency', tax_id: '', tax_office: '', address: '', phone: '', email: '' });
  const [reconcileForm, setReconcileForm] = useState({ cari_account_id: '', amount: '', description: '' });
  const [showSplit, setShowSplit] = useState(false);
  const [splitSourceId, setSplitSourceId] = useState('');
  const [loading, setLoading] = useState(false);
  const [reconcilingRoomCharge, setReconcilingRoomCharge] = useState(false);

  const folioList = useMemo(() => (Array.isArray(folios) ? folios : []), [folios]);

  // Varsayılan kaynak folyo: önce misafir folyosu, yoksa açık folyo, yoksa ilk folyo.
  const defaultSourceId = useMemo(() => {
    if (folioList.length === 0) return '';
    const guest = folioList.find(f => f.folio_type === 'guest');
    const open = folioList.find(f => f.status === 'open');
    return (guest || open || folioList[0]).id;
  }, [folioList]);

  // SplitFolioDialog tek bir folyo bekler: id, folio_number, balance ve KENDİ kalemleri.
  // charge_ids backend'de source_folio_id'den taşınır; bu yüzden kalemler folio.id ile AYNI folyoya ait olmalı.
  const splitFolio = useMemo(() => {
    const sid = splitSourceId || defaultSourceId;
    const src = folioList.find(f => f.id === sid);
    if (!src) return null;
    // Folio kalemleri (folio_id eşleşen) + booking kapsamlı ekstra masraflar.
    // extra_charges'ın folio_id'si yoktur; bölme sırasında backend bunları
    // booking_id ile doğrulayıp hedef folioya folio kalemi olarak taşır.
    const folioItems = (charges || []).filter(c => c.folio_id === src.id && !c.voided);
    const extraItems = (extra_charges || []).filter(c => !c.voided);
    return {
      id: src.id,
      folio_number: src.folio_number,
      guest_name: guest?.name || guest?.full_name || booking?.guest_name,
      room_number: room?.room_number || room?.number || booking?.room_number,
      balance: src.balance,
      charges: [...folioItems, ...extraItems],
    };
  }, [splitSourceId, defaultSourceId, folioList, charges, extra_charges, booking, guest, room]);

  const hasCharges = useMemo(
    () => (charges || []).some(c => !c.voided) || (extra_charges || []).some(c => !c.voided),
    [charges, extra_charges]
  );
  const pendingRoomAmount = Number(summary?.unposted_room_amount) || 0;
  const rawFolioBalance = Number(summary?.folio_balance ?? summary?.balance) || 0;
  const reservationTotalDue = Number(summary?.reservation_total_due ?? summary?.balance) || 0;
  const hasAllocatedPrepayment = pendingRoomAmount > 0.01 && reservationTotalDue <= 0.01 && rawFolioBalance < -0.01;
  const displayedFolioBalance = hasAllocatedPrepayment ? 0 : rawFolioBalance;
  const hasHistoricalRoomCredit = readOnly && pendingRoomAmount > 0.01 && Number(summary?.folio_balance) < -0.01;

  const completePendingRoomCharge = async () => {
    setReconcilingRoomCharge(true);
    try {
      const response = await axios.post(`/pms/reservations/${booking.id}/complete-pending-room-charge`);
      if (response.data?.posted) toast.success('Eksik konaklama tahakkuku folyoya işlendi');
      else toast.info('Konaklama tahakkuku zaten tamamlanmış');
      await onRefresh?.();
    } catch (e) {
      toast.error('Tahakkuk tamamlanamadı: ' + (e.response?.data?.detail || e.message));
    } finally {
      setReconcilingRoomCharge(false);
    }
  };

  const openSplit = async () => {
    // Folio zaten varsa mevcut akış aynen çalışır.
    if (folioList.length > 0) {
      if (!splitSourceId) setSplitSourceId(defaultSourceId);
      setShowSplit(s => !s);
      return;
    }
    // Folio yok ama masraf var: önce garanti-folio uç noktasını çağır,
    // veriyi yenile, sonra bölme panelini aç.
    if (hasCharges) {
      setLoading(true);
      try {
        await axios.post(`/pms/reservations/${booking.id}/ensure-folio`);
        await onRefresh?.();
        setShowSplit(true);
      } catch (e) {
        toast.error('Folyo hazırlanamadı: ' + (e.response?.data?.detail || e.message));
      }
      setLoading(false);
      return;
    }
    // Ne masraf ne folio var: bilgilendirici mesaj.
    toast.error('Bölünecek folyo bulunmuyor');
  };

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
        <SummaryCard label="Borçlar" value={(summary?.total_charges || 0) + (summary?.total_extra || 0)} color="amber" />
        <SummaryCard label="Ödemeler" value={summary?.total_payments} color="emerald" />
        <SummaryCard label="Bakiye" value={displayedFolioBalance} color={displayedFolioBalance > 0 ? 'red' : 'green'} />
      </div>
      {hasAllocatedPrepayment && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800" data-testid="allocated-prepayment-note">
          {fmtTL(Math.abs(rawFolioBalance))} TL peşin tahsilat, {fmtTL(pendingRoomAmount)} TL bekleyen konaklama tahakkukuna ayrıldı. Tahsilat bakiyesi kapandı.
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => { const bal = summary?.balance || 0; setPayForm(p => ({ ...p, amount: bal > 0 ? String(bal) : p.amount })); setShowPayment(!showPayment); }} className="bg-emerald-600 hover:bg-emerald-700 text-white h-8 text-xs" data-testid="btn-odeme-al"><CreditCard className="w-3 h-3 mr-1" /> Ödeme Al</Button>
        <Button size="sm" variant="outline" onClick={() => { const bal = summary?.balance || 0; setCariForm(p => ({ ...p, amount: bal > 0 ? String(bal) : p.amount })); setShowCari(!showCari); loadCari(); }} className="h-8 text-xs border-amber-300 text-amber-700 hover:bg-amber-50" data-testid="btn-cariye-aktar"><ArrowRightLeft className="w-3 h-3 mr-1" /> Cariye Aktar</Button>
        <Button size="sm" variant="outline" onClick={() => { const bal = summary?.balance || 0; setAgencyForm(p => ({ ...p, amount: bal > 0 ? String(bal) : p.amount })); setShowAgency(!showAgency); }} className="h-8 text-xs border-indigo-300 text-indigo-700 hover:bg-indigo-50" data-testid="btn-acente-odemesi"><Building2 className="w-3 h-3 mr-1" /> Acente Ödemesi</Button>
        <Button size="sm" variant="outline" onClick={() => { setShowCariTransfer(!showCariTransfer); loadCari(); }} className="h-8 text-xs border-indigo-300 text-indigo-700 hover:bg-indigo-50" data-testid="btn-acenteye-aktar"><ArrowDownUp className="w-3 h-3 mr-1" /> Acenteye Aktar</Button>
        <Button size="sm" variant="outline" onClick={() => { const bal = summary?.balance || 0; setReconcileForm(p => ({ ...p, amount: bal > 0 ? String(bal) : p.amount })); setShowReconcile(!showReconcile); loadCari(); }} className="h-8 text-xs border-teal-300 text-teal-700 hover:bg-teal-50" data-testid="btn-mahsuplastir"><DollarSign className="w-3 h-3 mr-1" /> Mahsuplaştır</Button>
        <Button size="sm" variant="outline" onClick={openSplit} className="h-8 text-xs border-sky-300 text-sky-700 hover:bg-sky-50" data-testid="btn-folyo-bol">
          <Split className="w-3 h-3 mr-1" /> Folyo Böl
        </Button>
        <Button size="sm" variant="outline" onClick={() => onSwitchTab('invoice')} className="h-8 text-xs border-blue-300 text-blue-700 hover:bg-blue-50" data-testid="btn-fatura-pdf">
          <FileText className="w-3 h-3 mr-1" /> Fatura Olustur
        </Button>
        {hasHistoricalRoomCredit && (
          <Button size="sm" variant="outline" onClick={completePendingRoomCharge} disabled={reconcilingRoomCharge} className="h-8 text-xs border-amber-300 text-amber-700 hover:bg-amber-50" data-testid="btn-complete-pending-room-charge">
            {reconcilingRoomCharge ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Receipt className="w-3 h-3 mr-1" />}
            Eksik Konaklamayı Tahakkuk Ettir ({fmtTL(pendingRoomAmount)} TL)
          </Button>
        )}
      </div>

      {showSplit && (
        <div className="border rounded-lg p-4 bg-sky-50/40 space-y-3" data-testid="split-folio-panel">
          {folioList.length > 1 && (
            <SelectField
              label="Kaynak Folyo"
              value={splitSourceId || defaultSourceId}
              onChange={setSplitSourceId}
              options={folioList.map(f => [f.id, `${f.folio_number} (${f.folio_type || ''}) — Bakiye ${fmtTL(f.balance)} TL`])}
            />
          )}
          {splitFolio && (
            <SplitFolioDialog
              key={splitFolio.id}
              folio={splitFolio}
              onClose={() => setShowSplit(false)}
              onSuccess={() => { setShowSplit(false); onRefresh?.(); }}
            />
          )}
        </div>
      )}

      {showPayment && (
        <FormPanel color="emerald" title={t('common.paymentRecord')} testid="payment-form" onClose={() => setShowPayment(false)} loading={loading}
          onSubmit={() => exec(async () => {
            const amount = parseFloat(payForm.amount);
            await axios.post(`/pms/reservations/${booking.id}/record-payment`, {
              ...payForm,
              amount,
              payment_type: classifyGuestPayment(amount, summary?.balance),
            });
            toast.success('Ödeme kaydedildi'); setShowPayment(false); setPayForm({ amount: '', method: 'cash', reference: '' });
          })}>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Tutar (TL)" type="number" value={payForm.amount} onChange={v => setPayForm(p => ({ ...p, amount: v }))} />
            <SelectField label={t('common.paymentMethod')} value={payForm.method} onChange={v => setPayForm(p => ({ ...p, method: v }))}
              options={[['cash','Nakit'],['card','Kredi Kartı'],['bank_transfer','Havale/EFT'],['online','Online']]} />
            <FormField label="Referans" value={payForm.reference} onChange={v => setPayForm(p => ({ ...p, reference: v }))} placeholder="Fis/Dekont No" />
          </div>
          <div className="rounded-md border border-emerald-200 bg-white/70 px-3 py-2 text-xs text-emerald-800" data-testid="payment-classification">
            <div className="font-medium">{guestPaymentClassificationLabel(payForm.amount, summary?.balance)}</div>
            <div className="mt-0.5 text-emerald-700">Ödeme türü otomatik belirlenir. Depozito için ayrı Depozito sekmesini kullanın.</div>
          </div>
        </FormPanel>
      )}

      {showCari && (
        <FormPanel color="amber" title="Cariye Aktar" testid="cari-transfer-form" onClose={() => setShowCari(false)} loading={loading}
          onSubmit={() => exec(async () => {
            await axios.post(`/pms/reservations/${booking.id}/transfer-to-cari`, { ...cariForm, amount: parseFloat(cariForm.amount) });
            toast.success('Cariye aktarildi'); setShowCari(false); setCariForm({ amount: '', cari_account_id: '', description: '' });
          })}>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Tutar (TL)" type="number" value={cariForm.amount} onChange={v => setCariForm(p => ({ ...p, amount: v }))} />
            <SelectField label="Cari Hesap" value={cariForm.cari_account_id} onChange={v => setCariForm(p => ({ ...p, cari_account_id: v }))}
              options={[['','Hesap Seçiniz...'], ...cariAccounts.map(a => [a.id, `${a.name} (${a.account_type || ''})`])]} />
          </div>
          <FormField label="Açıklama" value={cariForm.description} onChange={v => setCariForm(p => ({ ...p, description: v }))} placeholder="Opsiyonel" />
        </FormPanel>
      )}

      {showAgency && (
        <FormPanel color="blue" title="Acente Ödemesi" testid="agency-payment-form" onClose={() => setShowAgency(false)} loading={loading}
          onSubmit={() => exec(async () => {
            await axios.post(`/pms/reservations/${booking.id}/record-agency-payment`, { ...agencyForm, amount: parseFloat(agencyForm.amount) });
            toast.success('Acente ödemesi kaydedildi'); setShowAgency(false); setAgencyForm({ amount: '', agency_name: '', reference: '' });
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
            if (cariTransferForm.source_id === cariTransferForm.target_id) { toast.error('Kaynak ve hedef cari hesap farklı olmalı'); return; }
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
              options={[['','Hesap Seçiniz...'], ...cariAccounts.map(a => [a.id, `${a.name} (${a.account_type || ''})`])]} />
            <div>
              <SelectField label="Hedef Acente Hesabi" value={cariTransferForm.target_id} onChange={v => setCariTransferForm(p => ({ ...p, target_id: v }))}
                options={[['','Acente Seçiniz...'], ...cariAccounts.filter(a => a.account_type === 'agency').map(a => [a.id, a.name])]} />
              <Button size="sm" variant="ghost" className="h-6 text-xs text-indigo-600 mt-1 px-0" onClick={() => setShowNewCari(true)} data-testid="btn-new-cari"><Plus className="w-3 h-3 mr-1" /> Yeni Cari Olustur</Button>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Tutar (TL)" type="number" value={cariTransferForm.amount} onChange={v => setCariTransferForm(p => ({ ...p, amount: v }))} />
            <FormField label="Açıklama" value={cariTransferForm.description} onChange={v => setCariTransferForm(p => ({ ...p, description: v }))} placeholder="Opsiyonel" />
          </div>
        </FormPanel>
      )}

      {showNewCari && (
        <div className="border rounded-lg p-4 bg-indigo-50/50 space-y-3" data-testid="new-cari-form">
          <div className="text-sm font-semibold text-indigo-800">Yeni Cari Hesap Olustur</div>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Hesap Adi *" value={newCariForm.name} onChange={v => setNewCariForm(p => ({ ...p, name: v }))} placeholder="Acente / Şirket adi" />
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
                toast.success('Yeni cari hesap oluşturuldu');
                setShowNewCari(false);
                setNewCariForm({ name: '', account_type: 'agency', tax_id: '', tax_office: '', address: '', phone: '', email: '' });
                loadCari();
              } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
              setLoading(false);
            }} disabled={loading} className="bg-indigo-600 hover:bg-indigo-700 text-white h-8 text-xs" data-testid="create-cari-btn">
              {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Olustur'}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowNewCari(false)} className="h-8 text-xs">İptal</Button>
          </div>
        </div>
      )}

      {showReconcile && (
        <FormPanel color="teal" title="Mahsuplastirma (Cari Ödeme)" testid="reconcile-form" onClose={() => setShowReconcile(false)} loading={loading}
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
              options={[['','Hesap Seçiniz...'], ...cariAccounts.map(a => [a.id, `${a.name} (${a.account_type || ''})`])]} />
            <FormField label="Tutar (TL)" type="number" value={reconcileForm.amount} onChange={v => setReconcileForm(p => ({ ...p, amount: v }))} />
          </div>
          <FormField label="Açıklama" value={reconcileForm.description} onChange={v => setReconcileForm(p => ({ ...p, description: v }))} placeholder="Mahsuplastirma açıklaması" />
        </FormPanel>
      )}

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="text-xs font-semibold text-gray-500 uppercase">İşlem Geçmişi</div>
          <Button variant="link" size="sm" className="h-auto p-0 text-indigo-600 hover:text-indigo-700" onClick={() => navigate(`/folio-detail/${folios?.[0]?.id}`)} disabled={!folios || folios.length === 0}>
            Gelişmiş Folyo Yönetimi &rarr;
          </Button>
        </div>
        {allItems.length === 0 ? <div className="text-center py-6 text-gray-400 text-sm">Henüz işlem bulunmuyor</div> : (
          allItems.map((item, i) => (
            <div key={item.id || i} className={`flex items-center gap-3 p-3 rounded-lg border ${item.voided ? 'opacity-50 bg-gray-50' : 'bg-white'}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center ${item._type === 'payment' ? 'bg-emerald-100' : 'bg-amber-100'}`}>
                {item._type === 'payment' ? <CreditCard className="w-4 h-4 text-emerald-600" /> : <Receipt className="w-4 h-4 text-amber-600" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-gray-800">{item.description || item.charge_name || item.method || item.payment_type || '-'}</div>
                <div className="text-xs text-gray-400">{fmtTs(item.created_at || item.processed_at)}{item.agency_name && <span className="ml-2 text-indigo-600">({item.agency_name})</span>}</div>
              </div>
              <div className={`text-sm font-bold ${item._type === 'payment' ? 'text-emerald-600' : 'text-amber-600'}`}>
                {item._type === 'payment' ? '-' : '+'}{fmtTL(item.total ?? item.charge_amount ?? item.amount)} TL
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
