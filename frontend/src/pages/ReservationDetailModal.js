import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  X, Calendar, CreditCard, Clock, Building2, FileText,
  DollarSign, Plus, History, MessageSquare,
  ArrowRightLeft, Star, AlertTriangle, LogIn, LogOut, Home,
  Users, Pencil, Check, Receipt, Loader2,
  Globe, Phone, Mail, Send, ArrowDownUp,
  Banknote, RefreshCw, Repeat2, Shield
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

// ── Shared Helpers ──
const fmtDate = (d) => {
  if (!d) return '-';
  return new Date(d).toLocaleDateString('tr-TR', { day: '2-digit', month: 'short', year: 'numeric', weekday: 'short' });
};
const fmtTs = (d) => (d || '').toString().slice(0, 16).replace('T', ' ');
const fmtTL = (v) => (v || 0).toLocaleString('tr-TR');

// ── Tab: Genel Bilgiler ──
function GeneralInfoTab({ booking, guest, room, company, onGuestUpdate }) {
  const [editing, setEditing] = useState(false);
  const [guestForm, setGuestForm] = useState({});
  useEffect(() => { if (guest) setGuestForm({ ...guest }); }, [guest]);

  const handleSave = async () => {
    try {
      await axios.put(`${API}/api/pms/reservations/${booking.id}/update-guest`, guestForm);
      toast.success('Misafir bilgileri guncellendi');
      setEditing(false);
      onGuestUpdate?.();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6" data-testid="general-info-tab">
      <div className="lg:col-span-2 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <InfoField label="Giris Tarihi" value={fmtDate(booking?.check_in)} />
          <InfoField label="Giris Saati" value="14:00" />
          <InfoField label="Cikis Tarihi" value={fmtDate(booking?.check_out)} />
          <InfoField label="Cikis Saati" value="12:00" />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <InfoField label="Yetiskin" value={booking?.adults || booking?.guests_count || 1} />
          <InfoField label="Cocuk" value={booking?.children || 0} />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <InfoField label="Oda Tipi" value={room?.room_type || '-'} />
          <InfoField label="Oda No" value={booking?.room_number || room?.room_number || '-'} />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <InfoField label="Konaklama Turu" value={booking?.rate_plan || 'Standart'} />
          <InfoField label="Iptal Kurali" value={booking?.cancellation_policy || 'Esnek'} />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Durum</Label>
            <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200">{statusLabel(booking?.status)}</Badge>
          </div>
          <InfoField label="Kaynak" value={booking?.source_channel || booking?.channel || 'Direkt'} />
        </div>
        {booking?.special_requests && <InfoField label="Ozel Istekler" value={booking.special_requests} className="bg-amber-50 border-amber-200" />}
      </div>
      <div className="space-y-4">
        <div className="border rounded-lg p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-500 uppercase">Ana Kontak</span>
            <Button variant="ghost" size="sm" onClick={() => setEditing(!editing)} className="h-7 px-2">
              <Pencil className="w-3 h-3 mr-1" /> {editing ? 'Iptal' : 'Duzenle'}
            </Button>
          </div>
          {editing ? (
            <div className="space-y-2">
              <Input value={guestForm.name || ''} onChange={e => setGuestForm(p => ({ ...p, name: e.target.value }))} placeholder="Ad Soyad" className="h-8 text-sm" />
              <Input value={guestForm.email || ''} onChange={e => setGuestForm(p => ({ ...p, email: e.target.value }))} placeholder="E-posta" className="h-8 text-sm" />
              <Input value={guestForm.phone || ''} onChange={e => setGuestForm(p => ({ ...p, phone: e.target.value }))} placeholder="Telefon" className="h-8 text-sm" />
              <Button size="sm" onClick={handleSave} className="w-full h-8"><Check className="w-3 h-3 mr-1" /> Kaydet</Button>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="flex items-center gap-2 bg-teal-50 rounded-lg p-2">
                <Avatar name={guest?.name || booking?.guest_name} />
                <div>
                  <div className="text-sm font-semibold text-gray-800">{guest?.name || booking?.guest_name}</div>
                  <div className="text-xs text-gray-500">{guest?.email || '-'}</div>
                </div>
              </div>
              {guest?.phone && <div className="flex items-center gap-2 text-xs text-gray-600"><Phone className="w-3 h-3" /> {guest.phone}</div>}
              {guest?.nationality && <div className="flex items-center gap-2 text-xs text-gray-600"><Globe className="w-3 h-3" /> {guest.nationality}</div>}
              {guest?.vip_status && <Badge className="bg-amber-100 text-amber-700 border-amber-200"><Star className="w-3 h-3 mr-1" /> VIP</Badge>}
            </div>
          )}
        </div>
        <div className="border rounded-lg p-4 space-y-2">
          <span className="text-xs font-semibold text-gray-500 uppercase">Kanal</span>
          <div className="flex items-center gap-2"><Globe className="w-4 h-4 text-blue-600" /><span className="text-sm font-medium">{booking?.source_channel || 'Direkt'}</span></div>
        </div>
        {company && <div className="border rounded-lg p-4 space-y-2"><span className="text-xs font-semibold text-gray-500 uppercase">Sirket</span><div className="flex items-center gap-2"><Building2 className="w-4 h-4 text-gray-500" /><span className="text-sm">{company.name}</span></div></div>}
      </div>
    </div>
  );
}

// ── Tab: Misafirler ──
function GuestsTab({ guests, booking }) {
  return (
    <div data-testid="guests-tab" className="space-y-3">
      {(!guests || guests.length === 0) ? <EmptyState icon={Users} text="Kayitli misafir bulunamadi" /> : (
        guests.map((g, i) => (
          <div key={g.id || i} className="border rounded-lg p-4 flex items-center gap-4">
            <Avatar name={g.name} size="lg" />
            <div className="flex-1">
              <div className="text-sm font-semibold">{g.name}</div>
              <div className="text-xs text-gray-500">{g.email || '-'} {g.phone ? `| ${g.phone}` : ''}</div>
            </div>
            {g.vip_status && <Badge className="bg-amber-100 text-amber-700">VIP</Badge>}
            {i === 0 && <Badge className="bg-blue-100 text-blue-700">Ana Misafir</Badge>}
          </div>
        ))
      )}
    </div>
  );
}

// ── Tab: Folyolar ──
function FoliosTab({ folios, charges, payments, extra_charges, summary, booking, onRefresh }) {
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
  const [reconcileForm, setReconcileForm] = useState({ cari_account_id: '', amount: '', description: '' });
  const [loading, setLoading] = useState(false);

  const loadCari = async () => { try { const r = await axios.get(`${API}/api/pms/cari-accounts`); setCariAccounts(r.data.accounts || []); } catch {} };

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
      </div>

      {showPayment && (
        <FormPanel color="emerald" title="Odeme Kaydet" testid="payment-form" onClose={() => setShowPayment(false)} loading={loading}
          onSubmit={() => exec(async () => {
            await axios.post(`${API}/api/pms/reservations/${booking.id}/record-payment`, { ...payForm, amount: parseFloat(payForm.amount) });
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
            await axios.post(`${API}/api/pms/reservations/${booking.id}/transfer-to-cari`, { ...cariForm, amount: parseFloat(cariForm.amount) });
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
            await axios.post(`${API}/api/pms/reservations/${booking.id}/record-agency-payment`, { ...agencyForm, amount: parseFloat(agencyForm.amount) });
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
            await axios.post(`${API}/api/pms/cari-accounts/${cariTransferForm.source_id}/transfer-to-agency`, {
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
            <SelectField label="Hedef Acente Hesabi" value={cariTransferForm.target_id} onChange={v => setCariTransferForm(p => ({ ...p, target_id: v }))}
              options={[['','Acente Seciniz...'], ...cariAccounts.filter(a => a.account_type === 'agency').map(a => [a.id, a.name])]} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Tutar (TL)" type="number" value={cariTransferForm.amount} onChange={v => setCariTransferForm(p => ({ ...p, amount: v }))} />
            <FormField label="Aciklama" value={cariTransferForm.description} onChange={v => setCariTransferForm(p => ({ ...p, description: v }))} placeholder="Opsiyonel" />
          </div>
        </FormPanel>
      )}

      {showReconcile && (
        <FormPanel color="teal" title="Mahsuplastirma (Cari Odeme)" testid="reconcile-form" onClose={() => setShowReconcile(false)} loading={loading}
          onSubmit={() => exec(async () => {
            if (!reconcileForm.cari_account_id) { toast.error('Cari hesap seciniz'); return; }
            await axios.post(`${API}/api/pms/cari-accounts/${reconcileForm.cari_account_id}/reconcile`, {
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

// ── Tab: Gunluk Fiyatlar ──
function DailyRatesTab({ dailyRates, booking, onRefresh }) {
  const [editMode, setEditMode] = useState(false);
  const [rates, setRates] = useState([]);
  const [saving, setSaving] = useState(false);
  useEffect(() => { setRates(dailyRates || []); }, [dailyRates]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/api/pms/reservations/${booking.id}/daily-rates`, { rates });
      toast.success('Gunluk fiyatlar guncellendi'); setEditMode(false); onRefresh?.();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setSaving(false);
  };

  return (
    <div data-testid="daily-rates-tab" className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-700">Gunluk Fiyatlar</span>
        <Button size="sm" variant="outline" onClick={() => editMode ? handleSave() : setEditMode(true)} disabled={saving} className="h-7 text-xs">
          {saving ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : editMode ? <Check className="w-3 h-3 mr-1" /> : <Pencil className="w-3 h-3 mr-1" />}
          {editMode ? 'Kaydet' : 'Duzenle'}
        </Button>
      </div>
      <div className="border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50"><tr><th className="text-left py-2 px-3 text-xs text-gray-500 font-medium">Tarih</th><th className="text-right py-2 px-3 text-xs text-gray-500 font-medium">Fiyat (TL)</th></tr></thead>
          <tbody>
            {rates.map((r, i) => (
              <tr key={i} className="border-t">
                <td className="py-2 px-3 text-gray-700">{fmtDate(r.date)}</td>
                <td className="py-2 px-3 text-right">
                  {editMode ? <Input type="number" value={r.rate} onChange={e => { const u = [...rates]; u[i] = { ...u[i], rate: parseFloat(e.target.value) || 0 }; setRates(u); }} className="h-7 text-sm text-right w-24 ml-auto" />
                  : <span className="font-medium text-gray-800">{fmtTL(r.rate)} TL</span>}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot className="bg-gray-50 border-t-2"><tr><td className="py-2 px-3 font-semibold">Toplam</td><td className="py-2 px-3 text-right font-bold">{fmtTL(rates.reduce((s, r) => s + (r.rate || 0), 0))} TL</td></tr></tfoot>
        </table>
      </div>
    </div>
  );
}

// ── Tab: Ek Ucretler ──
function ExtraChargesTab({ extra_charges, charges, booking, onRefresh, allBookings }) {
  const [showAdd, setShowAdd] = useState(false);
  const [showSplit, setShowSplit] = useState(null);
  const [form, setForm] = useState({ description: '', category: 'other', amount: '', quantity: '1' });
  const [splitForm, setSplitForm] = useState({ target_booking_id: '', split_amount: '', reason: '' });
  const [loading, setLoading] = useState(false);
  const allCharges = [...(extra_charges || []), ...(charges || [])].filter(c => !c.voided);
  const cats = { room_service: 'Oda Servisi', room: 'Oda', food: 'Yemek', beverage: 'Icecek', minibar: 'Minibar', spa: 'SPA', laundry: 'Camasir', parking: 'Otopark', telephone: 'Telefon', transfer: 'Transfer', other: 'Diger' };

  const handleAdd = async () => {
    if (!form.description || !form.amount) { toast.error('Aciklama ve tutar zorunlu'); return; }
    setLoading(true);
    try {
      await axios.post(`${API}/api/pms/reservations/${booking.id}/add-extra-charge`, { ...form, amount: parseFloat(form.amount), quantity: parseFloat(form.quantity) || 1 });
      toast.success('Ekstra ucret eklendi'); setShowAdd(false); setForm({ description: '', category: 'other', amount: '', quantity: '1' }); onRefresh?.();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  const handleSplit = async (chargeId) => {
    if (!splitForm.split_amount || !splitForm.target_booking_id) { toast.error('Tutar ve hedef secimi zorunlu'); return; }
    setLoading(true);
    try {
      await axios.post(`${API}/api/pms/reservations/${booking.id}/split-charge`, { charge_id: chargeId, target_booking_id: splitForm.target_booking_id, split_amount: parseFloat(splitForm.split_amount), reason: splitForm.reason });
      toast.success('Masraf bolundu'); setShowSplit(null); setSplitForm({ target_booking_id: '', split_amount: '', reason: '' }); onRefresh?.();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  return (
    <div data-testid="extra-charges-tab" className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-700">Ek Ucretler</span>
        <Button size="sm" onClick={() => setShowAdd(!showAdd)} className="h-7 text-xs bg-amber-600 hover:bg-amber-700 text-white"><Plus className="w-3 h-3 mr-1" /> Ekle</Button>
      </div>
      {showAdd && (
        <div className="border rounded-lg p-4 bg-amber-50/50 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Aciklama" value={form.description} onChange={v => setForm(p => ({ ...p, description: v }))} placeholder="Ornek: Minibar" />
            <SelectField label="Kategori" value={form.category} onChange={v => setForm(p => ({ ...p, category: v }))} options={Object.entries(cats)} />
            <FormField label="Tutar (TL)" type="number" value={form.amount} onChange={v => setForm(p => ({ ...p, amount: v }))} />
            <FormField label="Adet" type="number" value={form.quantity} onChange={v => setForm(p => ({ ...p, quantity: v }))} />
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={handleAdd} disabled={loading} className="bg-amber-600 hover:bg-amber-700 text-white h-8 text-xs">{loading ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Ekle'}</Button>
            <Button size="sm" variant="ghost" onClick={() => setShowAdd(false)} className="h-8 text-xs">Iptal</Button>
          </div>
        </div>
      )}
      <div className="space-y-2">
        {allCharges.length === 0 ? <div className="text-center py-6 text-gray-400 text-sm">Ek ucret bulunmuyor</div> : (
          allCharges.map((c, i) => (
            <div key={c.id || i} className="border rounded-lg p-3 relative">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 bg-amber-100 rounded-full flex items-center justify-center"><Receipt className="w-4 h-4 text-amber-600" /></div>
                <div className="flex-1">
                  <div className="text-sm font-medium">{c.description || c.charge_name || '-'}</div>
                  <div className="text-xs text-gray-400">{cats[c.category || c.charge_category] || ''} {c.split_from_booking_id && <span className="text-blue-500">(Aktarildi)</span>}</div>
                </div>
                <div className="text-sm font-bold text-amber-700">{fmtTL(c.total || c.charge_amount || c.amount)} TL</div>
                <Button size="sm" variant="ghost" onClick={() => setShowSplit(showSplit === c.id ? null : c.id)} className="h-7 px-2 text-xs text-blue-600"><ArrowRightLeft className="w-3 h-3" /></Button>
              </div>
              {showSplit === c.id && (
                <div className="mt-3 border-t pt-3 space-y-2">
                  <div className="text-xs font-semibold text-gray-700">Masraf Bol</div>
                  <div className="grid grid-cols-3 gap-2">
                    <FormField label="Tutar" type="number" value={splitForm.split_amount} onChange={v => setSplitForm(p => ({ ...p, split_amount: v }))} />
                    <SelectField label="Hedef Oda" value={splitForm.target_booking_id} onChange={v => setSplitForm(p => ({ ...p, target_booking_id: v }))}
                      options={[['','Seciniz...'], ...(allBookings || []).filter(b => b.id !== booking.id).map(b => [b.id, `${b.room_number || ''} - ${b.guest_name || b.id?.slice(0,8)}`])]} />
                    <div className="flex items-end">
                      <Button size="sm" onClick={() => handleSplit(c.id)} disabled={loading} className="w-full h-8 text-xs bg-blue-600">Bol</Button>
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

// ── Tab: Oda Degistir ──
function RoomChangeTab({ booking, room, roomMoves, onRefresh }) {
  const [availableRooms, setAvailableRooms] = useState([]);
  const [selectedRoomId, setSelectedRoomId] = useState('');
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingRooms, setLoadingRooms] = useState(false);

  useEffect(() => {
    const loadRooms = async () => {
      setLoadingRooms(true);
      try {
        const ci = booking?.check_in?.toString().slice(0, 10) || '';
        const co = booking?.check_out?.toString().slice(0, 10) || '';
        const res = await axios.get(`${API}/api/pms/available-rooms?check_in=${ci}&check_out=${co}`);
        setAvailableRooms((res.data.rooms || []).filter(r => r.id !== booking?.room_id));
      } catch (e) { console.log('Room load error:', e); }
      setLoadingRooms(false);
    };
    loadRooms();
  }, [booking]);

  const handleChange = async () => {
    if (!selectedRoomId || !reason) { toast.error('Oda ve sebep secimi zorunlu'); return; }
    setLoading(true);
    try {
      await axios.post(`${API}/api/pms/reservations/${booking.id}/room-change`, { new_room_id: selectedRoomId, reason, transfer_folio: true });
      toast.success('Oda degistirildi');
      setSelectedRoomId(''); setReason(''); onRefresh?.();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  return (
    <div data-testid="room-change-tab" className="space-y-4">
      {/* Current Room */}
      <div className="border rounded-lg p-4 bg-blue-50/50">
        <div className="text-xs font-semibold text-blue-600 uppercase mb-2">Mevcut Oda</div>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-blue-600 text-white rounded-lg flex items-center justify-center font-bold">{booking?.room_number || '-'}</div>
          <div>
            <div className="text-sm font-semibold">{room?.room_type || 'Oda'} - {booking?.room_number || '-'}</div>
            <div className="text-xs text-gray-500">Kat: {room?.floor || '-'}</div>
          </div>
        </div>
      </div>

      {/* Room Change Form */}
      <div className="border rounded-lg p-4 space-y-3">
        <div className="text-sm font-semibold text-gray-700">Yeni Oda Sec</div>
        {loadingRooms ? (
          <div className="flex items-center gap-2 text-sm text-gray-400"><Loader2 className="w-4 h-4 animate-spin" /> Musait odalar yukleniyor...</div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Yeni Oda</Label>
              <select value={selectedRoomId} onChange={e => setSelectedRoomId(e.target.value)} className="w-full h-8 text-sm border rounded-md px-2 bg-white">
                <option value="">Oda Seciniz...</option>
                {availableRooms.map(r => (
                  <option key={r.id} value={r.id}>{r.room_number} - {r.room_type || ''} (Kat: {r.floor || '-'})</option>
                ))}
              </select>
            </div>
            <div>
              <Label className="text-xs">Degisiklik Sebebi</Label>
              <select value={reason} onChange={e => setReason(e.target.value)} className="w-full h-8 text-sm border rounded-md px-2 bg-white">
                <option value="">Sebep Seciniz...</option>
                <option value="Misafir istegi">Misafir istegi</option>
                <option value="Teknik ariza">Teknik ariza</option>
                <option value="Upgrade">Upgrade</option>
                <option value="Downgrade">Downgrade</option>
                <option value="Temizlik sorunu">Temizlik sorunu</option>
                <option value="Diger">Diger</option>
              </select>
            </div>
          </div>
        )}
        <Button size="sm" onClick={handleChange} disabled={loading || !selectedRoomId || !reason} className="bg-indigo-600 hover:bg-indigo-700 text-white h-8 text-xs">
          {loading ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Repeat2 className="w-3 h-3 mr-1" />} Oda Degistir
        </Button>
      </div>

      {/* Room Move History */}
      <div className="space-y-2">
        <div className="text-xs font-semibold text-gray-500 uppercase">Oda Degisiklik Gecmisi</div>
        {(!roomMoves || roomMoves.length === 0) ? <div className="text-center py-4 text-gray-400 text-sm">Gecmis oda degisikligi yok</div> : (
          roomMoves.map((rm, i) => (
            <div key={rm.id || i} className="border rounded-lg p-3 flex items-center gap-3">
              <div className="w-8 h-8 bg-indigo-100 rounded-full flex items-center justify-center"><Home className="w-4 h-4 text-indigo-600" /></div>
              <div className="flex-1">
                <div className="text-sm font-medium">{rm.from_room_number || '?'} → {rm.to_room_number || '?'}</div>
                <div className="text-xs text-gray-400">{rm.reason} | {rm.moved_by} | {fmtTs(rm.moved_at)}</div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// ── Tab: Iletisim (Communication Log) ──
function CommunicationTab({ booking, onRefresh, communicationLogs }) {
  const [logs, setLogs] = useState(communicationLogs || []);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ channel: 'email', direction: 'outbound', subject: '', content: '', recipient: '' });
  const [loading, setLoading] = useState(false);

  useEffect(() => { setLogs(communicationLogs || []); }, [communicationLogs]);

  const handleAdd = async () => {
    if (!form.content.trim()) { toast.error('Mesaj icerigi zorunlu'); return; }
    setLoading(true);
    try {
      await axios.post(`${API}/api/pms/reservations/${booking.id}/communication`, form);
      toast.success('Iletisim kaydedildi'); setShowForm(false); setForm({ channel: 'email', direction: 'outbound', subject: '', content: '', recipient: '' }); onRefresh?.();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  const channelIcons = { email: Mail, sms: MessageSquare, phone: Phone, whatsapp: MessageSquare };
  const channelLabels = { email: 'E-posta', sms: 'SMS', phone: 'Telefon', whatsapp: 'WhatsApp' };
  const dirLabels = { inbound: 'Gelen', outbound: 'Giden' };

  return (
    <div data-testid="communication-tab" className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-700">Iletisim Gecmisi</span>
        <Button size="sm" onClick={() => setShowForm(!showForm)} className="h-7 text-xs bg-sky-600 hover:bg-sky-700 text-white"><Plus className="w-3 h-3 mr-1" /> Kayit Ekle</Button>
      </div>

      {showForm && (
        <div className="border rounded-lg p-4 bg-sky-50/50 space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <SelectField label="Kanal" value={form.channel} onChange={v => setForm(p => ({ ...p, channel: v }))}
              options={[['email','E-posta'],['sms','SMS'],['phone','Telefon'],['whatsapp','WhatsApp']]} />
            <SelectField label="Yon" value={form.direction} onChange={v => setForm(p => ({ ...p, direction: v }))}
              options={[['outbound','Giden'],['inbound','Gelen']]} />
            <FormField label="Alici" value={form.recipient} onChange={v => setForm(p => ({ ...p, recipient: v }))} placeholder="E-posta/Tel" />
          </div>
          <FormField label="Konu" value={form.subject} onChange={v => setForm(p => ({ ...p, subject: v }))} placeholder="Konu (opsiyonel)" />
          <div>
            <Label className="text-xs">Icerik</Label>
            <textarea value={form.content} onChange={e => setForm(p => ({ ...p, content: e.target.value }))} className="w-full h-20 text-sm border rounded-lg p-2 resize-none bg-white" placeholder="Mesaj icerigi..." />
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={handleAdd} disabled={loading} className="bg-sky-600 hover:bg-sky-700 text-white h-8 text-xs">
              {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3 mr-1" />} Kaydet
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowForm(false)} className="h-8 text-xs">Iptal</Button>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {logs.length === 0 ? <EmptyState icon={Mail} text="Henuz iletisim kaydi yok" /> : (
          logs.map((log, i) => {
            const Icon = channelIcons[log.channel] || Mail;
            return (
              <div key={log.id || i} className="border rounded-lg p-3 space-y-1">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className={`w-7 h-7 rounded-full flex items-center justify-center ${log.direction === 'inbound' ? 'bg-green-100' : 'bg-blue-100'}`}>
                      <Icon className={`w-3.5 h-3.5 ${log.direction === 'inbound' ? 'text-green-600' : 'text-blue-600'}`} />
                    </div>
                    <Badge className={`text-xs ${log.direction === 'inbound' ? 'bg-green-100 text-green-700' : 'bg-blue-100 text-blue-700'}`}>
                      {dirLabels[log.direction] || log.direction} {channelLabels[log.channel] || log.channel}
                    </Badge>
                    {log.recipient && <span className="text-xs text-gray-500">{log.recipient}</span>}
                  </div>
                  <span className="text-xs text-gray-400">{fmtTs(log.created_at)}</span>
                </div>
                {log.subject && <div className="text-sm font-medium text-gray-700">{log.subject}</div>}
                <div className="text-sm text-gray-600">{log.content}</div>
                <div className="text-xs text-gray-400">- {log.sent_by}</div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

// ── Tab: Depozitolar ──
function DepositsTab({ deposits, booking, onRefresh }) {
  const [showDeposit, setShowDeposit] = useState(false);
  const [showRefund, setShowRefund] = useState(null);
  const [depForm, setDepForm] = useState({ amount: '', method: 'cash', reference: '' });
  const [refundForm, setRefundForm] = useState({ refund_amount: '', refund_method: 'cash', reason: '' });
  const [loading, setLoading] = useState(false);

  const handleDeposit = async () => {
    if (!depForm.amount) { toast.error('Tutar giriniz'); return; }
    setLoading(true);
    try {
      await axios.post(`${API}/api/pms/reservations/${booking.id}/record-deposit`, { ...depForm, amount: parseFloat(depForm.amount) });
      toast.success('Depozito kaydedildi'); setShowDeposit(false); setDepForm({ amount: '', method: 'cash', reference: '' }); onRefresh?.();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  const handleRefund = async (depositId) => {
    if (!refundForm.refund_amount) { toast.error('Iade tutari giriniz'); return; }
    setLoading(true);
    try {
      await axios.post(`${API}/api/pms/reservations/${booking.id}/refund-deposit`, { deposit_id: depositId, ...refundForm, refund_amount: parseFloat(refundForm.refund_amount) });
      toast.success('Depozito iade edildi'); setShowRefund(null); setRefundForm({ refund_amount: '', refund_method: 'cash', reason: '' }); onRefresh?.();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  const totalDeposits = (deposits || []).reduce((s, d) => s + (d.amount || 0), 0);
  const totalRefunded = (deposits || []).filter(d => d.status === 'refunded').reduce((s, d) => s + (d.amount || 0), 0);

  return (
    <div data-testid="deposits-tab" className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <SummaryCard label="Toplam Depozito" value={totalDeposits} color="blue" />
        <SummaryCard label="Iade Edilen" value={totalRefunded} color="amber" />
        <SummaryCard label="Aktif" value={totalDeposits - totalRefunded} color="emerald" />
      </div>

      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-700">Depozitolar</span>
        <Button size="sm" onClick={() => setShowDeposit(!showDeposit)} className="h-7 text-xs bg-blue-600 hover:bg-blue-700 text-white"><Plus className="w-3 h-3 mr-1" /> Depozito Al</Button>
      </div>

      {showDeposit && (
        <div className="border rounded-lg p-4 bg-blue-50/50 space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <FormField label="Tutar (TL)" type="number" value={depForm.amount} onChange={v => setDepForm(p => ({ ...p, amount: v }))} />
            <SelectField label="Yontem" value={depForm.method} onChange={v => setDepForm(p => ({ ...p, method: v }))}
              options={[['cash','Nakit'],['card','Kredi Karti'],['bank_transfer','Havale/EFT']]} />
            <FormField label="Referans" value={depForm.reference} onChange={v => setDepForm(p => ({ ...p, reference: v }))} />
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={handleDeposit} disabled={loading} className="bg-blue-600 text-white h-8 text-xs">{loading ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Kaydet'}</Button>
            <Button size="sm" variant="ghost" onClick={() => setShowDeposit(false)} className="h-8 text-xs">Iptal</Button>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {(!deposits || deposits.length === 0) ? <EmptyState icon={Shield} text="Henuz depozito yok" /> : (
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

// ── Tab: Notlar ──
function NotesTab({ notes, booking, onRefresh }) {
  const [content, setContent] = useState('');
  const [noteType, setNoteType] = useState('general');
  const [loading, setLoading] = useState(false);
  const typeColors = { general: 'bg-gray-100 text-gray-700', important: 'bg-red-100 text-red-700', internal: 'bg-blue-100 text-blue-700', guest_request: 'bg-amber-100 text-amber-700' };
  const typeLabels = { general: 'Genel', important: 'Onemli', internal: 'Dahili', guest_request: 'Misafir Istegi' };

  const handleAdd = async () => {
    if (!content.trim()) return;
    setLoading(true);
    try {
      await axios.post(`${API}/api/pms/reservations/${booking.id}/add-note`, { content, note_type: noteType });
      toast.success('Not eklendi'); setContent(''); onRefresh?.();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  return (
    <div data-testid="notes-tab" className="space-y-4">
      <div className="border rounded-lg p-4 space-y-3 bg-gray-50/50">
        <textarea value={content} onChange={e => setContent(e.target.value)} className="w-full h-20 text-sm border rounded-lg p-2 resize-none bg-white" placeholder="Not ekleyin..." />
        <div className="flex items-center gap-2">
          <select value={noteType} onChange={e => setNoteType(e.target.value)} className="h-8 text-xs border rounded-md px-2 bg-white">
            {Object.entries(typeLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <Button size="sm" onClick={handleAdd} disabled={loading || !content.trim()} className="h-8 text-xs">{loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3 mr-1" />} Ekle</Button>
        </div>
      </div>
      <div className="space-y-2">
        {(!notes || notes.length === 0) ? <EmptyState icon={MessageSquare} text="Henuz not yok" /> : (
          notes.map((n, i) => (
            <div key={n.id || i} className="border rounded-lg p-3 space-y-1">
              <div className="flex items-center justify-between">
                <Badge className={`${typeColors[n.note_type] || typeColors.general} text-xs`}>{typeLabels[n.note_type] || 'Genel'}</Badge>
                <span className="text-xs text-gray-400">{fmtTs(n.created_at)}</span>
              </div>
              <p className="text-sm text-gray-700">{n.content}</p>
              <div className="text-xs text-gray-400">- {n.created_by}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// ── Tab: Gecmis ──
function HistoryTab({ history, roomMoves }) {
  const allEvents = [
    ...(history || []).map(h => ({ ...h, _src: 'activity' })),
    ...(roomMoves || []).map(rm => ({ ...rm, _src: 'room_move', action: 'room_changed', actor: rm.moved_by, created_at: rm.moved_at, details: { from_room: rm.from_room_number, to_room: rm.to_room_number, reason: rm.reason } })),
  ].sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));

  const labels = {
    payment_recorded: 'Odeme kaydedildi', transferred_to_cari: 'Cariye aktarildi', agency_payment_recorded: 'Acente odemesi',
    charge_split: 'Masraf bolundu', note_added: 'Not eklendi', room_changed: 'Oda degistirildi',
    early_checkin: 'Erken giris', late_checkout: 'Gec cikis', marked_noshow: 'No-show',
    vip_status_changed: 'VIP durumu', deposit_recorded: 'Depozito', deposit_refunded: 'Depozito iade',
    extra_charge_added: 'Ekstra ucret', daily_rates_updated: 'Fiyat guncelleme', guest_updated: 'Misafir guncelleme',
    communication_logged: 'Iletisim', group_checkin: 'Grup giris', group_checkout: 'Grup cikis',
  };
  const colors = {
    payment_recorded: 'bg-emerald-100 text-emerald-700', transferred_to_cari: 'bg-orange-100 text-orange-700',
    agency_payment_recorded: 'bg-purple-100 text-purple-700', charge_split: 'bg-blue-100 text-blue-700',
    room_changed: 'bg-indigo-100 text-indigo-700', early_checkin: 'bg-teal-100 text-teal-700',
    late_checkout: 'bg-teal-100 text-teal-700', marked_noshow: 'bg-red-100 text-red-700',
    deposit_recorded: 'bg-blue-100 text-blue-700', deposit_refunded: 'bg-red-100 text-red-700',
  };

  return (
    <div data-testid="history-tab" className="space-y-3">
      <div className="text-sm font-semibold text-gray-700">Islem Gecmisi</div>
      {allEvents.length === 0 ? <EmptyState icon={History} text="Henuz islem gecmisi yok" /> : (
        <div className="relative">
          <div className="absolute left-4 top-0 bottom-0 w-px bg-gray-200" />
          {allEvents.map((ev, i) => (
            <div key={ev.id || i} className="relative flex gap-4 pb-4">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center z-10 ${colors[ev.action] || 'bg-gray-100 text-gray-600'}`}>
                {ev.action === 'room_changed' ? <Home className="w-3.5 h-3.5" /> :
                 ev.action?.includes('payment') || ev.action?.includes('deposit') ? <CreditCard className="w-3.5 h-3.5" /> :
                 ev.action?.includes('communication') ? <Mail className="w-3.5 h-3.5" /> :
                 <Clock className="w-3.5 h-3.5" />}
              </div>
              <div className="flex-1 border rounded-lg p-3 bg-white">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-gray-800">{labels[ev.action] || ev.action}</span>
                  <span className="text-xs text-gray-400">{fmtTs(ev.created_at)}</span>
                </div>
                {ev.actor && <div className="text-xs text-gray-500">Yapan: {ev.actor}</div>}
                {ev.details && Object.keys(ev.details).length > 0 && (
                  <div className="mt-1 text-xs text-gray-500 flex flex-wrap gap-2">
                    {ev.details.from_room && <span>Eski: {ev.details.from_room}</span>}
                    {ev.details.to_room && <span>Yeni: {ev.details.to_room}</span>}
                    {ev.details.amount && <span>Tutar: {ev.details.amount} TL</span>}
                    {ev.details.method && <span>Yontem: {ev.details.method}</span>}
                    {ev.details.reason && <span>Sebep: {ev.details.reason}</span>}
                    {ev.details.cari_account && <span>Cari: {ev.details.cari_account}</span>}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Reusable small components ──
function InfoField({ label, value, className = '' }) {
  return <div><Label className="text-xs text-gray-500 mb-1 block">{label}</Label><div className={`border rounded-lg px-3 py-2 text-sm bg-gray-50 ${className}`}>{value}</div></div>;
}
function Avatar({ name, size = 'md' }) {
  const s = size === 'lg' ? 'w-10 h-10 text-sm' : 'w-8 h-8 text-xs';
  return <div className={`${s} bg-teal-600 text-white rounded-full flex items-center justify-center font-bold`}>{(name || 'M')[0]?.toUpperCase()}</div>;
}
function EmptyState({ icon: Icon, text }) {
  return <div className="text-center py-8 text-gray-400"><Icon className="w-8 h-8 mx-auto mb-2 opacity-50" /><p className="text-sm">{text}</p></div>;
}
function SummaryCard({ label, value, color }) {
  return (
    <div className={`bg-${color}-50 border border-${color}-200 rounded-lg p-3 text-center`}>
      <div className={`text-xs text-${color}-600 font-medium`}>{label}</div>
      <div className={`text-lg font-bold text-${color}-800`}>{fmtTL(value)} TL</div>
    </div>
  );
}
function FormField({ label, value, onChange, type = 'text', placeholder = '' }) {
  return <div><Label className="text-xs">{label}</Label><Input type={type} value={value} onChange={e => onChange(e.target.value)} className="h-8 text-sm" placeholder={placeholder} /></div>;
}
function SelectField({ label, value, onChange, options }) {
  return (
    <div><Label className="text-xs">{label}</Label>
      <select value={value} onChange={e => onChange(e.target.value)} className="w-full h-8 text-sm border rounded-md px-2 bg-white">
        {options.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
    </div>
  );
}
function FormPanel({ color, title, testid, children, onClose, onSubmit, loading }) {
  return (
    <div className={`border rounded-lg p-4 bg-${color}-50/50 space-y-3`} data-testid={testid}>
      <div className={`text-sm font-semibold text-${color}-800`}>{title}</div>
      {children}
      <div className="flex gap-2">
        <Button size="sm" onClick={onSubmit} disabled={loading} className={`bg-${color}-600 hover:bg-${color}-700 text-white h-8 text-xs`}>
          {loading ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Check className="w-3 h-3 mr-1" />} Kaydet
        </Button>
        <Button size="sm" variant="ghost" onClick={onClose} className="h-8 text-xs">Iptal</Button>
      </div>
    </div>
  );
}
function statusLabel(s) {
  return s === 'checked_in' ? 'Giris Yapildi' : s === 'confirmed' ? 'Onaylandi' : s === 'checked_out' ? 'Cikis Yapildi' : s === 'cancelled' ? 'Iptal' : s === 'no_show' ? 'No-Show' : s || 'Beklemede';
}

// ── Main Modal Component ──
export default function ReservationDetailModal({ bookingId, onClose, allBookings }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('general');

  const loadData = useCallback(async () => {
    if (!bookingId) return;
    try {
      const res = await axios.get(`${API}/api/pms/reservations/${bookingId}/full-detail`);
      setData(res.data);
    } catch (e) {
      toast.error('Rezervasyon detayi yuklenemedi');
      console.error(e);
    }
    setLoading(false);
  }, [bookingId]);

  useEffect(() => { setLoading(true); loadData(); }, [loadData]);

  const action = async (url, body = {}, msg = 'Islem tamamlandi') => {
    try { await axios.post(`${API}${url}`, body); toast.success(msg); loadData(); }
    catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  if (loading) return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-2xl p-8 flex flex-col items-center gap-3"><Loader2 className="w-8 h-8 animate-spin text-blue-600" /><span className="text-sm text-gray-500">Yukleniyor...</span></div>
    </div>
  );

  if (!data) return null;

  const { booking, guest, room, company, folios, charges, payments, extra_charges, notes, history, room_moves, daily_rates, guests, summary, communication_logs, deposits } = data;

  const tabs = [
    { id: 'general', label: 'Genel Bilgiler', icon: FileText },
    { id: 'guests', label: `Misafirler (${guests?.length || 0})`, icon: Users },
    { id: 'folios', label: 'Folyolar', icon: DollarSign },
    { id: 'daily_rates', label: 'Gunluk Fiyatlar', icon: Calendar },
    { id: 'extras', label: 'Ek Ucretler', icon: Receipt },
    { id: 'room_change', label: 'Oda Degistir', icon: Repeat2 },
    { id: 'deposits', label: `Depozito ${deposits?.length ? `(${deposits.length})` : ''}`, icon: Shield },
    { id: 'communication', label: `Iletisim ${communication_logs?.length ? `(${communication_logs.length})` : ''}`, icon: Mail },
    { id: 'notes', label: `Notlar ${notes?.length ? `(${notes.length})` : ''}`, icon: MessageSquare },
    { id: 'history', label: 'Gecmis', icon: History },
  ];

  return (
    <div className="fixed inset-0 z-[60]" data-testid="reservation-detail-modal">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="absolute inset-2 md:inset-4 lg:inset-6 bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-3 border-b bg-gradient-to-r from-slate-800 to-slate-700">
          <div className="flex items-center gap-4">
            <h2 className="text-white font-semibold text-base">Rezervasyon - {booking?.ota_confirmation || booking?.id?.slice(0, 12) || ''}</h2>
            <Badge className="bg-white/20 text-white border-white/30 text-xs">{statusLabel(booking?.status)}</Badge>
            {booking?.group_booking_id && <Badge className="bg-amber-400/30 text-amber-100 border-amber-400/40 text-xs">Grup</Badge>}
          </div>
          <button onClick={onClose} className="text-white/70 hover:text-white hover:bg-white/10 rounded-full p-2 transition-colors" data-testid="close-reservation-detail"><X className="w-5 h-5" /></button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Left Sidebar */}
          <div className="w-64 border-r bg-gray-50 overflow-y-auto flex-shrink-0">
            <div className="p-4 space-y-4">
              <div className="text-center">
                <div className="w-14 h-14 bg-teal-600 text-white rounded-full flex items-center justify-center text-xl font-bold mx-auto mb-2">{(guest?.name || booking?.guest_name || 'M')[0]?.toUpperCase()}</div>
                <div className="font-bold text-gray-800 text-sm">{guest?.name || booking?.guest_name}</div>
                {guest?.vip_status && <Badge className="bg-amber-100 text-amber-700 border-amber-200 mt-1 text-xs"><Star className="w-3 h-3 mr-0.5" /> VIP</Badge>}
              </div>
              <div className="space-y-2 text-xs">
                <div className="flex justify-between"><span className="text-gray-500">Durum</span><Badge className="bg-emerald-100 text-emerald-700 text-xs h-5">{statusLabel(booking?.status)}</Badge></div>
                <div className="flex justify-between"><span className="text-gray-500">Kanal</span><span className="font-medium text-gray-700">{booking?.source_channel || 'Direkt'}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Oda</span><span className="font-medium text-blue-600">{booking?.room_number || room?.room_number || '-'}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Giris</span><span className="font-medium">{booking?.check_in?.toString().slice(0, 10)}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Cikis</span><span className="font-medium">{booking?.check_out?.toString().slice(0, 10)}</span></div>
              </div>
              <div className="border rounded-lg p-3 bg-white space-y-2">
                <div className="flex justify-between text-xs"><span className="text-gray-500">TOPLAM</span><span className="font-bold">{fmtTL(summary?.total_amount)} TL</span></div>
                <div className="flex justify-between text-xs"><span className="text-gray-500">ODENEN</span><span className="font-bold text-emerald-600">{fmtTL(summary?.total_payments)} TL</span></div>
                {(summary?.total_deposits || 0) > 0 && <div className="flex justify-between text-xs"><span className="text-gray-500">DEPOZITO</span><span className="font-bold text-blue-600">{fmtTL(summary?.total_deposits)} TL</span></div>}
                <div className="border-t pt-2 flex justify-between text-xs"><span className="text-gray-500">BAKIYE</span><span className={`font-bold ${(summary?.balance || 0) > 0 ? 'text-red-600' : 'text-green-600'}`}>{fmtTL(summary?.balance)} TL</span></div>
              </div>
              <div className="space-y-1.5">
                {booking?.status === 'confirmed' && (
                  <Button size="sm" variant="outline" onClick={async () => {
                    try {
                      const idempKey = `checkin-${bookingId}-${Date.now()}`;
                      await axios.put(`${API}/api/pms/bookings/${bookingId}`, { status: 'checked_in' }, { headers: { 'Idempotency-Key': idempKey } });
                      toast.success('Giris yapildi'); loadData();
                    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
                  }} className="w-full h-8 text-xs justify-start bg-emerald-50 text-emerald-700 border-emerald-300 hover:bg-emerald-100"><LogIn className="w-3 h-3 mr-2" /> Giris Yap</Button>
                )}
                {booking?.status === 'checked_in' && (
                  <Button size="sm" variant="outline" onClick={async () => {
                    if (!window.confirm('Cikis yapilsin mi?')) return;
                    try {
                      const idempKey = `checkout-${bookingId}-${Date.now()}`;
                      await axios.put(`${API}/api/pms/bookings/${bookingId}`, { status: 'checked_out' }, { headers: { 'Idempotency-Key': idempKey } });
                      toast.success('Cikis yapildi'); loadData();
                    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
                  }} className="w-full h-8 text-xs justify-start bg-blue-50 text-blue-700 border-blue-300 hover:bg-blue-100"><LogOut className="w-3 h-3 mr-2" /> Cikis Yap</Button>
                )}
                <Button size="sm" variant="outline" onClick={() => action(`/api/pms/reservations/${bookingId}/early-checkin`, { extra_charge: 0 }, 'Erken giris yapildi')} className="w-full h-8 text-xs justify-start"><LogIn className="w-3 h-3 mr-2" /> Erken Giris</Button>
                <Button size="sm" variant="outline" onClick={() => action(`/api/pms/reservations/${bookingId}/late-checkout`, { extra_charge: 0 }, 'Gec cikis kaydedildi')} className="w-full h-8 text-xs justify-start"><LogOut className="w-3 h-3 mr-2" /> Gec Cikis</Button>
                <Button size="sm" variant="outline" onClick={async () => {
                  const vip = data?.guest?.vip_status || false;
                  try { await axios.put(`${API}/api/pms/reservations/${bookingId}/vip-status?vip=${!vip}`); toast.success(vip ? 'VIP kaldirildi' : 'VIP yapildi'); loadData(); }
                  catch (e) { toast.error('Hata'); }
                }} className="w-full h-8 text-xs justify-start"><Star className="w-3 h-3 mr-2" /> {data?.guest?.vip_status ? 'VIP Kaldir' : 'VIP Yap'}</Button>
                <Button size="sm" variant="outline" onClick={() => { if (window.confirm('No-show olarak isaretlensin mi?')) action(`/api/pms/reservations/${bookingId}/mark-noshow`, {}, 'No-show isaretlendi'); }} className="w-full h-8 text-xs justify-start text-red-600 border-red-200 hover:bg-red-50"><AlertTriangle className="w-3 h-3 mr-2" /> No-Show</Button>
              </div>
            </div>
          </div>

          {/* Main Content */}
          <div className="flex-1 overflow-y-auto">
            <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col">
              <TabsList className="border-b rounded-none h-auto p-0 bg-white flex-shrink-0 justify-start gap-0 overflow-x-auto">
                {tabs.map(tab => (
                  <TabsTrigger key={tab.id} value={tab.id}
                    className="rounded-none border-b-2 border-transparent data-[state=active]:border-orange-500 data-[state=active]:text-orange-700 data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 py-2.5 text-xs font-medium text-gray-500 hover:text-gray-700 transition-colors whitespace-nowrap">
                    <tab.icon className="w-3.5 h-3.5 mr-1.5" />{tab.label}
                  </TabsTrigger>
                ))}
              </TabsList>
              <div className="flex-1 overflow-y-auto p-6">
                <TabsContent value="general" className="mt-0"><GeneralInfoTab booking={booking} guest={guest} room={room} company={company} onGuestUpdate={loadData} /></TabsContent>
                <TabsContent value="guests" className="mt-0"><GuestsTab guests={guests} booking={booking} /></TabsContent>
                <TabsContent value="folios" className="mt-0"><FoliosTab folios={folios} charges={charges} payments={payments} extra_charges={extra_charges} summary={summary} booking={booking} onRefresh={loadData} /></TabsContent>
                <TabsContent value="daily_rates" className="mt-0"><DailyRatesTab dailyRates={daily_rates} booking={booking} onRefresh={loadData} /></TabsContent>
                <TabsContent value="extras" className="mt-0"><ExtraChargesTab extra_charges={extra_charges} charges={charges} booking={booking} onRefresh={loadData} allBookings={allBookings} /></TabsContent>
                <TabsContent value="room_change" className="mt-0"><RoomChangeTab booking={booking} room={room} roomMoves={room_moves} onRefresh={loadData} /></TabsContent>
                <TabsContent value="deposits" className="mt-0"><DepositsTab deposits={deposits} booking={booking} onRefresh={loadData} /></TabsContent>
                <TabsContent value="communication" className="mt-0"><CommunicationTab booking={booking} onRefresh={loadData} communicationLogs={communication_logs} /></TabsContent>
                <TabsContent value="notes" className="mt-0"><NotesTab notes={notes} booking={booking} onRefresh={loadData} /></TabsContent>
                <TabsContent value="history" className="mt-0"><HistoryTab history={history} roomMoves={room_moves} /></TabsContent>
              </div>
            </Tabs>
          </div>
        </div>
      </div>
    </div>
  );
}
