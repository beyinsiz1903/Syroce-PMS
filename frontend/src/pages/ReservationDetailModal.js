import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  X, User, Calendar, CreditCard, Clock, Building2, FileText,
  DollarSign, Plus, History, MessageSquare, ClipboardList,
  ArrowRightLeft, Star, AlertTriangle, LogIn, LogOut, Home,
  Users, Pencil, Check, ChevronDown, Receipt, Loader2,
  Globe, Phone, Mail, Hash, Banknote
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

// ── Tab Components ──

function GeneralInfoTab({ booking, guest, room, company, onGuestUpdate }) {
  const [editing, setEditing] = useState(false);
  const [guestForm, setGuestForm] = useState({});

  useEffect(() => {
    if (guest) setGuestForm({ ...guest });
  }, [guest]);

  const handleSave = async () => {
    try {
      await axios.put(`${API}/api/pms/reservations/${booking.id}/update-guest`, guestForm);
      toast.success('Misafir bilgileri guncellendi');
      setEditing(false);
      onGuestUpdate?.();
    } catch (e) {
      toast.error('Guncelleme hatasi: ' + (e.response?.data?.detail || e.message));
    }
  };

  const formatDate = (d) => {
    if (!d) return '-';
    const date = new Date(d);
    return date.toLocaleDateString('tr-TR', { day: '2-digit', month: 'short', year: 'numeric', weekday: 'short' });
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6" data-testid="general-info-tab">
      {/* Left - Main Form */}
      <div className="lg:col-span-2 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Giris Tarihi</Label>
            <div className="border rounded-lg px-3 py-2 text-sm bg-gray-50">{formatDate(booking?.check_in)}</div>
          </div>
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Giris Saati</Label>
            <div className="border rounded-lg px-3 py-2 text-sm bg-gray-50">14:00</div>
          </div>
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Cikis Tarihi</Label>
            <div className="border rounded-lg px-3 py-2 text-sm bg-gray-50">{formatDate(booking?.check_out)}</div>
          </div>
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Cikis Saati</Label>
            <div className="border rounded-lg px-3 py-2 text-sm bg-gray-50">12:00</div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Yetiskin</Label>
            <div className="border rounded-lg px-3 py-2 text-sm bg-gray-50">{booking?.adults || booking?.guests_count || 1}</div>
          </div>
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Cocuk</Label>
            <div className="border rounded-lg px-3 py-2 text-sm bg-gray-50">{booking?.children || 0}</div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Oda Tipi</Label>
            <div className="border rounded-lg px-3 py-2 text-sm bg-gray-50">{room?.room_type || '-'}</div>
          </div>
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Oda No</Label>
            <div className="border rounded-lg px-3 py-2 text-sm bg-gray-50">{booking?.room_number || room?.room_number || '-'}</div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Konaklama Turu</Label>
            <div className="border rounded-lg px-3 py-2 text-sm bg-gray-50">{booking?.rate_plan || 'Standart'}</div>
          </div>
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Iptal Kurali</Label>
            <div className="border rounded-lg px-3 py-2 text-sm bg-gray-50">{booking?.cancellation_policy || 'Esnek'}</div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Durum</Label>
            <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200">
              {booking?.status === 'checked_in' ? 'Giris Yapildi' :
               booking?.status === 'confirmed' ? 'Onaylandi' :
               booking?.status === 'checked_out' ? 'Cikis Yapildi' :
               booking?.status === 'cancelled' ? 'Iptal' :
               booking?.status === 'no_show' ? 'No-Show' :
               booking?.status || 'Beklemede'}
            </Badge>
          </div>
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Kaynak</Label>
            <div className="border rounded-lg px-3 py-2 text-sm bg-gray-50">
              {booking?.source_channel || booking?.channel || 'Direkt'}
            </div>
          </div>
        </div>

        {booking?.special_requests && (
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Ozel Istekler</Label>
            <div className="border rounded-lg px-3 py-2 text-sm bg-amber-50 border-amber-200">
              {booking.special_requests}
            </div>
          </div>
        )}
      </div>

      {/* Right - Contact & Channel Info */}
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
              <Button size="sm" onClick={handleSave} className="w-full h-8">
                <Check className="w-3 h-3 mr-1" /> Kaydet
              </Button>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="flex items-center gap-2 bg-teal-50 rounded-lg p-2">
                <div className="w-8 h-8 bg-teal-600 text-white rounded-full flex items-center justify-center text-xs font-bold">
                  {(guest?.name || booking?.guest_name || 'M')[0]?.toUpperCase()}
                </div>
                <div>
                  <div className="text-sm font-semibold text-gray-800">{guest?.name || booking?.guest_name}</div>
                  <div className="text-xs text-gray-500">{guest?.email || '-'}</div>
                </div>
              </div>
              {guest?.phone && (
                <div className="flex items-center gap-2 text-xs text-gray-600">
                  <Phone className="w-3 h-3" /> {guest.phone}
                </div>
              )}
              {guest?.nationality && (
                <div className="flex items-center gap-2 text-xs text-gray-600">
                  <Globe className="w-3 h-3" /> {guest.nationality}
                </div>
              )}
              {guest?.vip_status && (
                <Badge className="bg-amber-100 text-amber-700 border-amber-200">
                  <Star className="w-3 h-3 mr-1" /> VIP
                </Badge>
              )}
            </div>
          )}
        </div>

        <div className="border rounded-lg p-4 space-y-3">
          <span className="text-xs font-semibold text-gray-500 uppercase">Kanal</span>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
              <Globe className="w-4 h-4 text-blue-600" />
            </div>
            <div>
              <div className="text-sm font-medium">{booking?.source_channel || booking?.channel || 'Direkt'}</div>
              <div className="text-xs text-gray-500">{booking?.ota_confirmation || ''}</div>
            </div>
          </div>
        </div>

        {company && (
          <div className="border rounded-lg p-4 space-y-2">
            <span className="text-xs font-semibold text-gray-500 uppercase">Sirket</span>
            <div className="flex items-center gap-2">
              <Building2 className="w-4 h-4 text-gray-500" />
              <span className="text-sm font-medium">{company.name}</span>
            </div>
          </div>
        )}

        <div className="border rounded-lg p-4 space-y-2">
          <span className="text-xs font-semibold text-gray-500 uppercase">Para Birimi</span>
          <div className="text-sm font-medium">TRY</div>
        </div>
      </div>
    </div>
  );
}

function GuestsTab({ guests, booking }) {
  return (
    <div data-testid="guests-tab" className="space-y-3">
      {(!guests || guests.length === 0) ? (
        <div className="text-center py-8 text-gray-400">
          <Users className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm">Kayitli misafir bulunamadi</p>
        </div>
      ) : (
        guests.map((g, i) => (
          <div key={g.id || i} className="border rounded-lg p-4 flex items-center gap-4">
            <div className="w-10 h-10 bg-teal-600 text-white rounded-full flex items-center justify-center text-sm font-bold">
              {(g.name || 'M')[0]?.toUpperCase()}
            </div>
            <div className="flex-1">
              <div className="text-sm font-semibold">{g.name}</div>
              <div className="text-xs text-gray-500">{g.email || '-'}</div>
              {g.phone && <div className="text-xs text-gray-500">{g.phone}</div>}
            </div>
            {g.vip_status && <Badge className="bg-amber-100 text-amber-700">VIP</Badge>}
            {i === 0 && <Badge className="bg-blue-100 text-blue-700">Ana Misafir</Badge>}
          </div>
        ))
      )}
    </div>
  );
}

function FoliosTab({ folios, charges, payments, extra_charges, summary, booking, onRefresh }) {
  const [showPayment, setShowPayment] = useState(false);
  const [showCari, setShowCari] = useState(false);
  const [showAgency, setShowAgency] = useState(false);
  const [payForm, setPayForm] = useState({ amount: '', method: 'cash', payment_type: 'interim', reference: '', notes: '' });
  const [cariAccounts, setCariAccounts] = useState([]);
  const [cariForm, setCariForm] = useState({ amount: '', cari_account_id: '', description: '' });
  const [agencyForm, setAgencyForm] = useState({ amount: '', agency_name: '', reference: '', notes: '' });
  const [loading, setLoading] = useState(false);

  const loadCariAccounts = async () => {
    try {
      const res = await axios.get(`${API}/api/pms/cari-accounts`);
      setCariAccounts(res.data.accounts || []);
    } catch (e) { console.log('Cari accounts error:', e); }
  };

  const handlePayment = async () => {
    if (!payForm.amount || parseFloat(payForm.amount) <= 0) { toast.error('Gecerli bir tutar giriniz'); return; }
    setLoading(true);
    try {
      await axios.post(`${API}/api/pms/reservations/${booking.id}/record-payment`, {
        ...payForm, amount: parseFloat(payForm.amount),
      });
      toast.success('Odeme kaydedildi');
      setShowPayment(false);
      setPayForm({ amount: '', method: 'cash', payment_type: 'interim', reference: '', notes: '' });
      onRefresh?.();
    } catch (e) {
      toast.error('Odeme hatasi: ' + (e.response?.data?.detail || e.message));
    }
    setLoading(false);
  };

  const handleCariTransfer = async () => {
    if (!cariForm.amount || !cariForm.cari_account_id) { toast.error('Tutar ve cari hesap seciniz'); return; }
    setLoading(true);
    try {
      await axios.post(`${API}/api/pms/reservations/${booking.id}/transfer-to-cari`, {
        ...cariForm, amount: parseFloat(cariForm.amount),
      });
      toast.success('Cariye aktarildi');
      setShowCari(false);
      setCariForm({ amount: '', cari_account_id: '', description: '' });
      onRefresh?.();
    } catch (e) {
      toast.error('Aktarim hatasi: ' + (e.response?.data?.detail || e.message));
    }
    setLoading(false);
  };

  const handleAgencyPayment = async () => {
    if (!agencyForm.amount) { toast.error('Gecerli bir tutar giriniz'); return; }
    setLoading(true);
    try {
      await axios.post(`${API}/api/pms/reservations/${booking.id}/record-agency-payment`, {
        ...agencyForm, amount: parseFloat(agencyForm.amount),
      });
      toast.success('Acente odemesi kaydedildi');
      setShowAgency(false);
      setAgencyForm({ amount: '', agency_name: '', reference: '', notes: '' });
      onRefresh?.();
    } catch (e) {
      toast.error('Hata: ' + (e.response?.data?.detail || e.message));
    }
    setLoading(false);
  };

  const allItems = [
    ...(charges || []).map(c => ({ ...c, _type: 'charge', _sign: '+' })),
    ...(extra_charges || []).map(c => ({ ...c, _type: 'charge', _sign: '+' })),
    ...(payments || []).map(p => ({ ...p, _type: 'payment', _sign: '-' })),
  ].sort((a, b) => new Date(b.created_at || b.processed_at || b.date || 0) - new Date(a.created_at || a.processed_at || a.date || 0));

  return (
    <div data-testid="folios-tab" className="space-y-4">
      {/* Summary Bar */}
      <div className="grid grid-cols-4 gap-3">
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-center">
          <div className="text-xs text-blue-600 font-medium">Toplam</div>
          <div className="text-lg font-bold text-blue-800">{(summary?.total_amount || 0).toLocaleString('tr-TR')} TL</div>
        </div>
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-center">
          <div className="text-xs text-amber-600 font-medium">Masraflar</div>
          <div className="text-lg font-bold text-amber-800">{((summary?.total_charges || 0) + (summary?.total_extra || 0)).toLocaleString('tr-TR')} TL</div>
        </div>
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 text-center">
          <div className="text-xs text-emerald-600 font-medium">Odemeler</div>
          <div className="text-lg font-bold text-emerald-800">{(summary?.total_payments || 0).toLocaleString('tr-TR')} TL</div>
        </div>
        <div className={`rounded-lg p-3 text-center border ${(summary?.balance || 0) > 0 ? 'bg-red-50 border-red-200' : 'bg-green-50 border-green-200'}`}>
          <div className={`text-xs font-medium ${(summary?.balance || 0) > 0 ? 'text-red-600' : 'text-green-600'}`}>Bakiye</div>
          <div className={`text-lg font-bold ${(summary?.balance || 0) > 0 ? 'text-red-800' : 'text-green-800'}`}>{(summary?.balance || 0).toLocaleString('tr-TR')} TL</div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => setShowPayment(!showPayment)} className="bg-emerald-600 hover:bg-emerald-700 text-white h-8 text-xs">
          <CreditCard className="w-3 h-3 mr-1" /> Odeme Al
        </Button>
        <Button size="sm" variant="outline" onClick={() => { setShowCari(!showCari); loadCariAccounts(); }} className="h-8 text-xs border-orange-300 text-orange-700 hover:bg-orange-50">
          <ArrowRightLeft className="w-3 h-3 mr-1" /> Cariye Aktar
        </Button>
        <Button size="sm" variant="outline" onClick={() => setShowAgency(!showAgency)} className="h-8 text-xs border-purple-300 text-purple-700 hover:bg-purple-50">
          <Building2 className="w-3 h-3 mr-1" /> Acente Odemesi
        </Button>
      </div>

      {/* Payment Form */}
      {showPayment && (
        <div className="border rounded-lg p-4 bg-emerald-50/50 space-y-3" data-testid="payment-form">
          <div className="text-sm font-semibold text-emerald-800">Odeme Kaydet</div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Tutar (TL)</Label>
              <Input type="number" value={payForm.amount} onChange={e => setPayForm(p => ({ ...p, amount: e.target.value }))} className="h-8 text-sm" placeholder="0.00" />
            </div>
            <div>
              <Label className="text-xs">Odeme Yontemi</Label>
              <select value={payForm.method} onChange={e => setPayForm(p => ({ ...p, method: e.target.value }))} className="w-full h-8 text-sm border rounded-md px-2 bg-white">
                <option value="cash">Nakit</option>
                <option value="card">Kredi Karti</option>
                <option value="bank_transfer">Havale/EFT</option>
                <option value="online">Online</option>
              </select>
            </div>
            <div>
              <Label className="text-xs">Odeme Tipi</Label>
              <select value={payForm.payment_type} onChange={e => setPayForm(p => ({ ...p, payment_type: e.target.value }))} className="w-full h-8 text-sm border rounded-md px-2 bg-white">
                <option value="prepayment">On Odeme</option>
                <option value="deposit">Depozito</option>
                <option value="interim">Ara Odeme</option>
                <option value="final">Final Odeme</option>
              </select>
            </div>
            <div>
              <Label className="text-xs">Referans</Label>
              <Input value={payForm.reference} onChange={e => setPayForm(p => ({ ...p, reference: e.target.value }))} className="h-8 text-sm" placeholder="Fiş/Dekont No" />
            </div>
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={handlePayment} disabled={loading} className="bg-emerald-600 hover:bg-emerald-700 h-8 text-xs">
              {loading ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Check className="w-3 h-3 mr-1" />} Kaydet
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowPayment(false)} className="h-8 text-xs">Iptal</Button>
          </div>
        </div>
      )}

      {/* Cari Transfer Form */}
      {showCari && (
        <div className="border rounded-lg p-4 bg-orange-50/50 space-y-3" data-testid="cari-transfer-form">
          <div className="text-sm font-semibold text-orange-800">Cariye Aktar</div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Tutar (TL)</Label>
              <Input type="number" value={cariForm.amount} onChange={e => setCariForm(p => ({ ...p, amount: e.target.value }))} className="h-8 text-sm" placeholder="0.00" />
            </div>
            <div>
              <Label className="text-xs">Cari Hesap</Label>
              <select value={cariForm.cari_account_id} onChange={e => setCariForm(p => ({ ...p, cari_account_id: e.target.value }))} className="w-full h-8 text-sm border rounded-md px-2 bg-white">
                <option value="">Hesap Seciniz...</option>
                {cariAccounts.map(a => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <Label className="text-xs">Aciklama</Label>
            <Input value={cariForm.description} onChange={e => setCariForm(p => ({ ...p, description: e.target.value }))} className="h-8 text-sm" placeholder="Aciklama (opsiyonel)" />
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={handleCariTransfer} disabled={loading} className="bg-orange-600 hover:bg-orange-700 text-white h-8 text-xs">
              {loading ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <ArrowRightLeft className="w-3 h-3 mr-1" />} Aktar
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowCari(false)} className="h-8 text-xs">Iptal</Button>
          </div>
        </div>
      )}

      {/* Agency Payment Form */}
      {showAgency && (
        <div className="border rounded-lg p-4 bg-purple-50/50 space-y-3" data-testid="agency-payment-form">
          <div className="text-sm font-semibold text-purple-800">Acente Odemesi</div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Tutar (TL)</Label>
              <Input type="number" value={agencyForm.amount} onChange={e => setAgencyForm(p => ({ ...p, amount: e.target.value }))} className="h-8 text-sm" placeholder="0.00" />
            </div>
            <div>
              <Label className="text-xs">Acente Adi</Label>
              <Input value={agencyForm.agency_name} onChange={e => setAgencyForm(p => ({ ...p, agency_name: e.target.value }))} className="h-8 text-sm" placeholder="Acente adi" />
            </div>
          </div>
          <div>
            <Label className="text-xs">Referans</Label>
            <Input value={agencyForm.reference} onChange={e => setAgencyForm(p => ({ ...p, reference: e.target.value }))} className="h-8 text-sm" placeholder="Voucher/Referans No" />
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={handleAgencyPayment} disabled={loading} className="bg-purple-600 hover:bg-purple-700 text-white h-8 text-xs">
              {loading ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Building2 className="w-3 h-3 mr-1" />} Kaydet
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowAgency(false)} className="h-8 text-xs">Iptal</Button>
          </div>
        </div>
      )}

      {/* Transaction List */}
      <div className="space-y-2">
        <div className="text-xs font-semibold text-gray-500 uppercase">Islem Gecmisi</div>
        {allItems.length === 0 ? (
          <div className="text-center py-6 text-gray-400 text-sm">Henuz islem bulunmuyor</div>
        ) : (
          allItems.map((item, i) => (
            <div key={item.id || i} className={`flex items-center gap-3 p-3 rounded-lg border ${item.voided ? 'opacity-50 bg-gray-50' : 'bg-white'}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center ${item._type === 'payment' ? 'bg-emerald-100' : 'bg-amber-100'}`}>
                {item._type === 'payment' ? <CreditCard className="w-4 h-4 text-emerald-600" /> : <Receipt className="w-4 h-4 text-amber-600" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-gray-800">
                  {item.description || item.charge_name || item.method || item.payment_type || '-'}
                </div>
                <div className="text-xs text-gray-400">
                  {(item.created_at || item.processed_at || item.date || '').toString().slice(0, 19).replace('T', ' ')}
                  {item.agency_name && <span className="ml-2 text-purple-600">({item.agency_name})</span>}
                </div>
              </div>
              <div className={`text-sm font-bold ${item._type === 'payment' ? 'text-emerald-600' : 'text-amber-600'}`}>
                {item._sign}{(item.amount || item.total || item.charge_amount || 0).toLocaleString('tr-TR')} TL
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function DailyRatesTab({ dailyRates, booking, onRefresh }) {
  const [editMode, setEditMode] = useState(false);
  const [rates, setRates] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setRates(dailyRates || []);
  }, [dailyRates]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/api/pms/reservations/${booking.id}/daily-rates`, { rates });
      toast.success('Gunluk fiyatlar guncellendi');
      setEditMode(false);
      onRefresh?.();
    } catch (e) {
      toast.error('Guncelleme hatasi: ' + (e.response?.data?.detail || e.message));
    }
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
          <thead className="bg-gray-50">
            <tr>
              <th className="text-left py-2 px-3 text-xs text-gray-500 font-medium">Tarih</th>
              <th className="text-right py-2 px-3 text-xs text-gray-500 font-medium">Fiyat (TL)</th>
            </tr>
          </thead>
          <tbody>
            {rates.map((r, i) => (
              <tr key={i} className="border-t">
                <td className="py-2 px-3 text-gray-700">
                  {new Date(r.date).toLocaleDateString('tr-TR', { day: '2-digit', month: 'short', year: 'numeric', weekday: 'short' })}
                </td>
                <td className="py-2 px-3 text-right">
                  {editMode ? (
                    <Input type="number" value={r.rate} onChange={e => {
                      const updated = [...rates];
                      updated[i] = { ...updated[i], rate: parseFloat(e.target.value) || 0 };
                      setRates(updated);
                    }} className="h-7 text-sm text-right w-24 ml-auto" />
                  ) : (
                    <span className="font-medium text-gray-800">{(r.rate || 0).toLocaleString('tr-TR')} TL</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot className="bg-gray-50 border-t-2">
            <tr>
              <td className="py-2 px-3 font-semibold text-gray-700">Toplam</td>
              <td className="py-2 px-3 text-right font-bold text-gray-800">
                {rates.reduce((sum, r) => sum + (r.rate || 0), 0).toLocaleString('tr-TR')} TL
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}

function ExtraChargesTab({ extra_charges, charges, booking, onRefresh, allBookings }) {
  const [showAdd, setShowAdd] = useState(false);
  const [showSplit, setShowSplit] = useState(null);
  const [form, setForm] = useState({ description: '', category: 'other', amount: '', quantity: '1' });
  const [splitForm, setSplitForm] = useState({ target_booking_id: '', split_amount: '', reason: '' });
  const [loading, setLoading] = useState(false);

  const allCharges = [...(extra_charges || []), ...(charges || [])].filter(c => !c.voided);

  const handleAdd = async () => {
    if (!form.description || !form.amount) { toast.error('Aciklama ve tutar zorunlu'); return; }
    setLoading(true);
    try {
      await axios.post(`${API}/api/pms/reservations/${booking.id}/add-extra-charge`, {
        ...form, amount: parseFloat(form.amount), quantity: parseFloat(form.quantity) || 1,
      });
      toast.success('Ekstra ucret eklendi');
      setShowAdd(false);
      setForm({ description: '', category: 'other', amount: '', quantity: '1' });
      onRefresh?.();
    } catch (e) {
      toast.error('Hata: ' + (e.response?.data?.detail || e.message));
    }
    setLoading(false);
  };

  const handleSplit = async (chargeId) => {
    if (!splitForm.split_amount || !splitForm.target_booking_id) { toast.error('Tutar ve hedef secimi zorunlu'); return; }
    setLoading(true);
    try {
      await axios.post(`${API}/api/pms/reservations/${booking.id}/split-charge`, {
        charge_id: chargeId,
        target_booking_id: splitForm.target_booking_id,
        split_amount: parseFloat(splitForm.split_amount),
        reason: splitForm.reason,
      });
      toast.success('Masraf bolundu');
      setShowSplit(null);
      setSplitForm({ target_booking_id: '', split_amount: '', reason: '' });
      onRefresh?.();
    } catch (e) {
      toast.error('Hata: ' + (e.response?.data?.detail || e.message));
    }
    setLoading(false);
  };

  const categoryLabels = {
    room: 'Oda', food: 'Yemek', beverage: 'Icecek', minibar: 'Minibar',
    spa: 'SPA', laundry: 'Camasir', parking: 'Otopark', other: 'Diger',
  };

  return (
    <div data-testid="extra-charges-tab" className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-700">Ek Ucretler</span>
        <Button size="sm" onClick={() => setShowAdd(!showAdd)} className="h-7 text-xs bg-amber-600 hover:bg-amber-700 text-white">
          <Plus className="w-3 h-3 mr-1" /> Ekle
        </Button>
      </div>

      {showAdd && (
        <div className="border rounded-lg p-4 bg-amber-50/50 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Aciklama</Label>
              <Input value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} className="h-8 text-sm" placeholder="Ornek: Minibar" />
            </div>
            <div>
              <Label className="text-xs">Kategori</Label>
              <select value={form.category} onChange={e => setForm(p => ({ ...p, category: e.target.value }))} className="w-full h-8 text-sm border rounded-md px-2 bg-white">
                {Object.entries(categoryLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-xs">Tutar (TL)</Label>
              <Input type="number" value={form.amount} onChange={e => setForm(p => ({ ...p, amount: e.target.value }))} className="h-8 text-sm" placeholder="0.00" />
            </div>
            <div>
              <Label className="text-xs">Adet</Label>
              <Input type="number" value={form.quantity} onChange={e => setForm(p => ({ ...p, quantity: e.target.value }))} className="h-8 text-sm" />
            </div>
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={handleAdd} disabled={loading} className="bg-amber-600 hover:bg-amber-700 text-white h-8 text-xs">
              {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Ekle'}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowAdd(false)} className="h-8 text-xs">Iptal</Button>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {allCharges.length === 0 ? (
          <div className="text-center py-6 text-gray-400 text-sm">Ek ucret bulunmuyor</div>
        ) : (
          allCharges.map((c, i) => (
            <div key={c.id || i} className="border rounded-lg p-3 flex items-center gap-3">
              <div className="w-8 h-8 bg-amber-100 rounded-full flex items-center justify-center">
                <Receipt className="w-4 h-4 text-amber-600" />
              </div>
              <div className="flex-1">
                <div className="text-sm font-medium">{c.description || c.charge_name || '-'}</div>
                <div className="text-xs text-gray-400">
                  {categoryLabels[c.category || c.charge_category] || c.category || c.charge_category || ''}
                  {c.split_from_booking_id && <span className="ml-1 text-blue-500">(Aktarildi)</span>}
                </div>
              </div>
              <div className="text-sm font-bold text-amber-700">
                {(c.total || c.charge_amount || c.amount || 0).toLocaleString('tr-TR')} TL
              </div>
              <Button size="sm" variant="ghost" onClick={() => setShowSplit(showSplit === c.id ? null : c.id)} className="h-7 px-2 text-xs text-blue-600">
                <ArrowRightLeft className="w-3 h-3" />
              </Button>
              {showSplit === c.id && (
                <div className="absolute right-0 top-full mt-1 bg-white border rounded-lg shadow-xl p-3 z-50 w-72 space-y-2">
                  <div className="text-xs font-semibold text-gray-700">Masraf Bol</div>
                  <div>
                    <Label className="text-xs">Tutar</Label>
                    <Input type="number" value={splitForm.split_amount} onChange={e => setSplitForm(p => ({ ...p, split_amount: e.target.value }))} className="h-7 text-xs" placeholder="0.00" />
                  </div>
                  <div>
                    <Label className="text-xs">Hedef Oda/Rez.</Label>
                    <select value={splitForm.target_booking_id} onChange={e => setSplitForm(p => ({ ...p, target_booking_id: e.target.value }))} className="w-full h-7 text-xs border rounded px-2 bg-white">
                      <option value="">Seciniz...</option>
                      {(allBookings || []).filter(b => b.id !== booking.id).map(b => (
                        <option key={b.id} value={b.id}>{b.room_number || b.guest_name || b.id?.slice(0,8)}</option>
                      ))}
                    </select>
                  </div>
                  <Button size="sm" onClick={() => handleSplit(c.id)} disabled={loading} className="w-full h-7 text-xs bg-blue-600">Bol</Button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function NotesTab({ notes, booking, onRefresh }) {
  const [content, setContent] = useState('');
  const [noteType, setNoteType] = useState('general');
  const [loading, setLoading] = useState(false);

  const handleAdd = async () => {
    if (!content.trim()) return;
    setLoading(true);
    try {
      await axios.post(`${API}/api/pms/reservations/${booking.id}/add-note`, { content, note_type: noteType });
      toast.success('Not eklendi');
      setContent('');
      onRefresh?.();
    } catch (e) {
      toast.error('Hata: ' + (e.response?.data?.detail || e.message));
    }
    setLoading(false);
  };

  const typeColors = {
    general: 'bg-gray-100 text-gray-700',
    important: 'bg-red-100 text-red-700',
    internal: 'bg-blue-100 text-blue-700',
    guest_request: 'bg-amber-100 text-amber-700',
  };

  return (
    <div data-testid="notes-tab" className="space-y-4">
      <div className="border rounded-lg p-4 space-y-3 bg-gray-50/50">
        <textarea
          value={content}
          onChange={e => setContent(e.target.value)}
          className="w-full h-20 text-sm border rounded-lg p-2 resize-none bg-white"
          placeholder="Not ekleyin..."
        />
        <div className="flex items-center gap-2">
          <select value={noteType} onChange={e => setNoteType(e.target.value)} className="h-8 text-xs border rounded-md px-2 bg-white">
            <option value="general">Genel</option>
            <option value="important">Onemli</option>
            <option value="internal">Dahili</option>
            <option value="guest_request">Misafir Istegi</option>
          </select>
          <Button size="sm" onClick={handleAdd} disabled={loading || !content.trim()} className="h-8 text-xs">
            {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3 mr-1" />} Ekle
          </Button>
        </div>
      </div>
      <div className="space-y-2">
        {(!notes || notes.length === 0) ? (
          <div className="text-center py-6 text-gray-400 text-sm">Henuz not yok</div>
        ) : (
          notes.map((n, i) => (
            <div key={n.id || i} className="border rounded-lg p-3 space-y-1">
              <div className="flex items-center justify-between">
                <Badge className={`${typeColors[n.note_type] || typeColors.general} text-xs`}>
                  {n.note_type === 'general' ? 'Genel' : n.note_type === 'important' ? 'Onemli' : n.note_type === 'internal' ? 'Dahili' : 'Misafir Istegi'}
                </Badge>
                <span className="text-xs text-gray-400">{(n.created_at || '').toString().slice(0, 16).replace('T', ' ')}</span>
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

function HistoryTab({ history, roomMoves }) {
  const allEvents = [
    ...(history || []).map(h => ({ ...h, _source: 'activity' })),
    ...(roomMoves || []).map(rm => ({
      ...rm,
      _source: 'room_move',
      action: 'room_changed',
      actor: rm.moved_by,
      created_at: rm.moved_at,
      details: { from_room: rm.from_room_number, to_room: rm.to_room_number, reason: rm.reason },
    })),
  ].sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));

  const actionLabels = {
    payment_recorded: 'Odeme kaydedildi',
    transferred_to_cari: 'Cariye aktarildi',
    agency_payment_recorded: 'Acente odemesi kaydedildi',
    charge_split: 'Masraf bolundu',
    note_added: 'Not eklendi',
    room_changed: 'Oda degistirildi',
    early_checkin: 'Erken giris',
    late_checkout: 'Gec cikis',
    marked_noshow: 'No-show isareti',
    vip_status_changed: 'VIP durumu degisti',
    deposit_recorded: 'Depozito kaydedildi',
    extra_charge_added: 'Ekstra ucret eklendi',
    daily_rates_updated: 'Gunluk fiyatlar guncellendi',
    guest_updated: 'Misafir bilgileri guncellendi',
  };

  const actionColors = {
    payment_recorded: 'bg-emerald-100 text-emerald-700',
    transferred_to_cari: 'bg-orange-100 text-orange-700',
    agency_payment_recorded: 'bg-purple-100 text-purple-700',
    charge_split: 'bg-blue-100 text-blue-700',
    room_changed: 'bg-indigo-100 text-indigo-700',
    early_checkin: 'bg-teal-100 text-teal-700',
    late_checkout: 'bg-teal-100 text-teal-700',
    marked_noshow: 'bg-red-100 text-red-700',
  };

  return (
    <div data-testid="history-tab" className="space-y-3">
      <div className="text-sm font-semibold text-gray-700">Islem Gecmisi</div>
      {allEvents.length === 0 ? (
        <div className="text-center py-8 text-gray-400 text-sm">
          <History className="w-8 h-8 mx-auto mb-2 opacity-50" />
          Henuz islem gecmisi yok
        </div>
      ) : (
        <div className="relative">
          <div className="absolute left-4 top-0 bottom-0 w-px bg-gray-200"></div>
          {allEvents.map((ev, i) => (
            <div key={ev.id || i} className="relative flex gap-4 pb-4">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center z-10 ${actionColors[ev.action] || 'bg-gray-100 text-gray-600'}`}>
                {ev.action === 'room_changed' ? <Home className="w-3.5 h-3.5" /> :
                 ev.action?.includes('payment') ? <CreditCard className="w-3.5 h-3.5" /> :
                 ev.action?.includes('charge') ? <Receipt className="w-3.5 h-3.5" /> :
                 <Clock className="w-3.5 h-3.5" />}
              </div>
              <div className="flex-1 border rounded-lg p-3 bg-white">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-gray-800">{actionLabels[ev.action] || ev.action}</span>
                  <span className="text-xs text-gray-400">{(ev.created_at || '').toString().slice(0, 16).replace('T', ' ')}</span>
                </div>
                <div className="text-xs text-gray-500">
                  {ev.actor && <span>Yapan: {ev.actor}</span>}
                </div>
                {ev.details && Object.keys(ev.details).length > 0 && (
                  <div className="mt-1 text-xs text-gray-500 space-x-2">
                    {ev.details.from_room && <span>Eski Oda: {ev.details.from_room}</span>}
                    {ev.details.to_room && <span>Yeni Oda: {ev.details.to_room}</span>}
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

  useEffect(() => {
    setLoading(true);
    loadData();
  }, [loadData]);

  // Front Office Actions
  const handleEarlyCheckin = async () => {
    try {
      await axios.post(`${API}/api/pms/reservations/${bookingId}/early-checkin`, { extra_charge: 0 });
      toast.success('Erken giris yapildi');
      loadData();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  const handleLateCheckout = async () => {
    try {
      await axios.post(`${API}/api/pms/reservations/${bookingId}/late-checkout`, { extra_charge: 0 });
      toast.success('Gec cikis kaydedildi');
      loadData();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  const handleNoShow = async () => {
    if (!window.confirm('Bu rezervasyonu no-show olarak isaretlemek istediginize emin misiniz?')) return;
    try {
      await axios.post(`${API}/api/pms/reservations/${bookingId}/mark-noshow`);
      toast.success('No-show olarak isaretlendi');
      loadData();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  const handleVipToggle = async () => {
    const currentVip = data?.guest?.vip_status || false;
    try {
      await axios.put(`${API}/api/pms/reservations/${bookingId}/vip-status?vip=${!currentVip}`);
      toast.success(currentVip ? 'VIP kaldirildi' : 'VIP olarak isaretlendi');
      loadData();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  if (loading) {
    return (
      <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50">
        <div className="bg-white rounded-2xl p-8 flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
          <span className="text-sm text-gray-500">Yukleniyor...</span>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const { booking, guest, room, company, folios, charges, payments, extra_charges, notes, history, room_moves, daily_rates, guests, summary } = data;
  const nights = booking ? Math.max(Math.ceil((new Date(booking.check_out) - new Date(booking.check_in)) / 86400000), 1) : 1;
  const adr = (booking?.total_amount || 0) / nights;

  return (
    <div className="fixed inset-0 z-[60]" data-testid="reservation-detail-modal">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="absolute inset-2 md:inset-4 lg:inset-6 bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-3 border-b bg-gradient-to-r from-slate-800 to-slate-700">
          <div className="flex items-center gap-4">
            <h2 className="text-white font-semibold text-base">
              Rezervasyon - {booking?.ota_confirmation || booking?.id?.slice(0, 12) || ''}
            </h2>
            <Badge className="bg-white/20 text-white border-white/30 text-xs">
              {booking?.status === 'checked_in' ? 'Giris Yapildi' :
               booking?.status === 'confirmed' ? 'Onaylandi' :
               booking?.status === 'checked_out' ? 'Cikis Yapildi' :
               booking?.status === 'cancelled' ? 'Iptal' :
               booking?.status || 'Beklemede'}
            </Badge>
          </div>
          <button onClick={onClose} className="text-white/70 hover:text-white hover:bg-white/10 rounded-full p-2 transition-colors" data-testid="close-reservation-detail">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Left Sidebar - Guest Summary */}
          <div className="w-64 border-r bg-gray-50 overflow-y-auto flex-shrink-0">
            <div className="p-4 space-y-4">
              {/* Guest Info */}
              <div className="text-center">
                <div className="w-14 h-14 bg-teal-600 text-white rounded-full flex items-center justify-center text-xl font-bold mx-auto mb-2">
                  {(guest?.name || booking?.guest_name || 'M')[0]?.toUpperCase()}
                </div>
                <div className="font-bold text-gray-800 text-sm">{guest?.name || booking?.guest_name}</div>
                {guest?.vip_status && (
                  <Badge className="bg-amber-100 text-amber-700 border-amber-200 mt-1 text-xs">
                    <Star className="w-3 h-3 mr-0.5" /> VIP
                  </Badge>
                )}
              </div>

              {/* Key Details */}
              <div className="space-y-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-gray-500">Durum</span>
                  <Badge className="bg-emerald-100 text-emerald-700 text-xs h-5">
                    {booking?.status === 'checked_in' ? 'Giris' : booking?.status === 'confirmed' ? 'Onay' : booking?.status || '-'}
                  </Badge>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Kanal</span>
                  <span className="font-medium text-gray-700">{booking?.source_channel || booking?.channel || 'Direkt'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Oda</span>
                  <span className="font-medium text-blue-600">{booking?.room_number || room?.room_number || '-'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Giris</span>
                  <span className="font-medium text-gray-700">{booking?.check_in?.toString().slice(0, 10)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Cikis</span>
                  <span className="font-medium text-gray-700">{booking?.check_out?.toString().slice(0, 10)}</span>
                </div>
              </div>

              {/* Financial Summary */}
              <div className="border rounded-lg p-3 bg-white space-y-2">
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">TOPLAM</span>
                  <span className="font-bold text-gray-800">{(summary?.total_amount || 0).toLocaleString('tr-TR')} TL</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">ODENEN</span>
                  <span className="font-bold text-emerald-600">{(summary?.total_payments || 0).toLocaleString('tr-TR')} TL</span>
                </div>
                <div className="border-t pt-2 flex justify-between text-xs">
                  <span className="text-gray-500">BAKIYE</span>
                  <span className={`font-bold ${(summary?.balance || 0) > 0 ? 'text-red-600' : 'text-green-600'}`}>
                    {(summary?.balance || 0).toLocaleString('tr-TR')} TL
                  </span>
                </div>
              </div>

              {/* Quick Actions */}
              <div className="space-y-1.5">
                <Button size="sm" variant="outline" onClick={handleEarlyCheckin} className="w-full h-8 text-xs justify-start">
                  <LogIn className="w-3 h-3 mr-2" /> Erken Giris
                </Button>
                <Button size="sm" variant="outline" onClick={handleLateCheckout} className="w-full h-8 text-xs justify-start">
                  <LogOut className="w-3 h-3 mr-2" /> Gec Cikis
                </Button>
                <Button size="sm" variant="outline" onClick={handleVipToggle} className="w-full h-8 text-xs justify-start">
                  <Star className="w-3 h-3 mr-2" /> {data?.guest?.vip_status ? 'VIP Kaldir' : 'VIP Yap'}
                </Button>
                <Button size="sm" variant="outline" onClick={handleNoShow} className="w-full h-8 text-xs justify-start text-red-600 border-red-200 hover:bg-red-50">
                  <AlertTriangle className="w-3 h-3 mr-2" /> No-Show
                </Button>
              </div>
            </div>
          </div>

          {/* Main Content - Tabs */}
          <div className="flex-1 overflow-y-auto">
            <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col">
              <TabsList className="border-b rounded-none h-auto p-0 bg-white flex-shrink-0 justify-start gap-0 overflow-x-auto">
                {[
                  { id: 'general', label: 'Genel Bilgiler', icon: FileText },
                  { id: 'guests', label: `Misafirler (${guests?.length || 0})`, icon: Users },
                  { id: 'folios', label: 'Folyolar', icon: DollarSign },
                  { id: 'daily_rates', label: 'Gunluk Fiyatlar', icon: Calendar },
                  { id: 'extras', label: 'Ek Ucretler', icon: Receipt },
                  { id: 'notes', label: `Notlar ${notes?.length ? `(${notes.length})` : ''}`, icon: MessageSquare },
                  { id: 'history', label: 'Gecmis', icon: History },
                ].map(tab => (
                  <TabsTrigger
                    key={tab.id}
                    value={tab.id}
                    className="rounded-none border-b-2 border-transparent data-[state=active]:border-orange-500 data-[state=active]:text-orange-700 data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 py-2.5 text-xs font-medium text-gray-500 hover:text-gray-700 transition-colors whitespace-nowrap"
                  >
                    <tab.icon className="w-3.5 h-3.5 mr-1.5" />
                    {tab.label}
                  </TabsTrigger>
                ))}
              </TabsList>

              <div className="flex-1 overflow-y-auto p-6">
                <TabsContent value="general" className="mt-0">
                  <GeneralInfoTab booking={booking} guest={guest} room={room} company={company} onGuestUpdate={loadData} />
                </TabsContent>
                <TabsContent value="guests" className="mt-0">
                  <GuestsTab guests={guests} booking={booking} />
                </TabsContent>
                <TabsContent value="folios" className="mt-0">
                  <FoliosTab folios={folios} charges={charges} payments={payments} extra_charges={extra_charges} summary={summary} booking={booking} onRefresh={loadData} />
                </TabsContent>
                <TabsContent value="daily_rates" className="mt-0">
                  <DailyRatesTab dailyRates={daily_rates} booking={booking} onRefresh={loadData} />
                </TabsContent>
                <TabsContent value="extras" className="mt-0">
                  <ExtraChargesTab extra_charges={extra_charges} charges={charges} booking={booking} onRefresh={loadData} allBookings={allBookings} />
                </TabsContent>
                <TabsContent value="notes" className="mt-0">
                  <NotesTab notes={notes} booking={booking} onRefresh={loadData} />
                </TabsContent>
                <TabsContent value="history" className="mt-0">
                  <HistoryTab history={history} roomMoves={room_moves} />
                </TabsContent>
              </div>
            </Tabs>
          </div>
        </div>
      </div>
    </div>
  );
}
