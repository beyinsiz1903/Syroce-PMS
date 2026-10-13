import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const steps = {
  agency_active: '1. Acente hesabı aktif',
  portal_user_active: '2–3. Yetkili daveti kabul etti ve şifresini belirledi',
  contract_approved: '4. Konaklama tarihlerini kapsayan tesis sözleşmesi onaylı',
  sellable_offer: '5. Seçilen tarihlerde satılabilir fiyat ve kontenjan var',
};
const tomorrow = (offset) => new Date(Date.now() + offset * 86400000).toISOString().slice(0, 10);
const errorMessage = (error) => typeof error.response?.data?.detail === 'string'
  ? error.response.data.detail : 'İşlem tamamlanamadı. Lütfen yeniden deneyin.';

export default function AgencyOnboardingPanel({ agency, onUpdated }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState(agency.contact_email || '');
  const [dates, setDates] = useState({ check_in: tomorrow(1), check_out: tomorrow(2) });
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let active = true;
    setReport(null);
    setLoading(true);
    setError('');
    axios.get(`/marketplace/v1/admin/agencies/${agency.id}/readiness`, { params: dates })
      .then(({ data }) => {
        if (!data?.checks || !Array.isArray(data.invitations) || !Array.isArray(data.offers)) throw new Error('Invalid readiness response');
        if (active) setReport(data);
      })
      .catch((err) => { if (active) setError(errorMessage(err)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [agency.id, dates, revision]);

  const sendInvite = async (event) => {
    event.preventDefault();
    setSending(true); setMessage('');
    try {
      const { data } = await axios.post(`/marketplace/v1/admin/agencies/${agency.id}/invitations`, { name: name.trim(), email: email.trim() });
      setMessage(data.message);
      setRevision((value) => value + 1);
      // A list refresh failure must not disguise an already-issued invitation.
      Promise.resolve(onUpdated?.()).catch(() => {});
    } catch (err) { setMessage(errorMessage(err)); }
    finally { setSending(false); }
  };

  return <section className="space-y-4 rounded-lg border p-4" aria-label="Acente hesap kurulumu">
    <h3 className="font-semibold">Satışa hazırlık</h3>
    <p className="text-sm">Hesabın aktif olması veya API anahtarı bulunması, satışa hazır olduğu anlamına gelmez.</p>
    <form onSubmit={sendInvite} className="space-y-2">
      <Label htmlFor="agency-invite-name">Yetkili adı soyadı</Label>
      <Input id="agency-invite-name" required minLength={2} maxLength={160} value={name} onChange={(e) => setName(e.target.value)} />
      <Label htmlFor="agency-invite-email">Yetkilinin e-postası</Label>
      <Input id="agency-invite-email" required type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <p className="text-xs text-slate-500">Kişi 24 saat geçerli bağlantıyla kendi şifresini belirler. Aynı bekleyen hesaba yeniden davet, eski bağlantıyı iptal eder. Aktif hesabın şifresi değiştirilmez.</p>
      <Button type="submit" disabled={sending || agency.status !== 'active'}>{sending ? 'Gönderiliyor…' : 'Davet gönder / yenile'}</Button>
      {message && <p role="status" className="text-sm">{message}</p>}
    </form>
    <div className="grid grid-cols-2 gap-2">
      <div><Label htmlFor="ready-in">Kontrol giriş tarihi</Label><Input id="ready-in" type="date" value={dates.check_in} onChange={(e) => setDates({ ...dates, check_in: e.target.value })} /></div>
      <div><Label htmlFor="ready-out">Kontrol çıkış tarihi</Label><Input id="ready-out" type="date" value={dates.check_out} onChange={(e) => setDates({ ...dates, check_out: e.target.value })} /></div>
    </div>
    <Button type="button" variant="outline" disabled={loading} onClick={() => setRevision((value) => value + 1)}>Hazırlık durumunu yenile</Button>
    {loading && <p role="status">Hazırlık kontrol ediliyor…</p>}
    {error && <p role="alert">{error}</p>}
    {report && <div className="space-y-2" aria-live="polite">
      <p className="font-semibold">{report.ready ? 'Satışa hazır — seçilen tarihler için' : 'Satışa hazır değil'}</p>
      <ul className="space-y-1 text-sm">{Object.entries(steps).map(([key, label]) => <li key={key}>{report.checks[key] ? '✓' : '○'} {label}</li>)}</ul>
      <p className="text-sm">Aktif kullanıcı: {report.active_users} · Geçerli sözleşme: {report.contract_count}</p>
      {report.invitations.map((invite) => <p className="text-xs" key={invite.user_id}>Bekleyen davet: {invite.email || invite.user_id} — {invite.expired ? 'Süresi dolmuş; yeniden davet edin' : invite.delivery === 'sent' ? 'E-posta sağlayıcısına iletildi; kabul bekleniyor' : 'E-posta gönderimi doğrulanamadı; yeniden davet edin'}</p>)}
      {!report.checks.contract_approved && <p className="text-sm">Acente portalındaki sözleşme akışından tesisle bağlantı kurun. Tesis yetkilisi PMS → Gelen acente sözleşmeleri ekranında onaylamalıdır. Bu kontrol sözleşmeyi otomatik onaylamaz.</p>}
      {!report.checks.sellable_offer && <p className="text-sm">Tesisin satışa açık olduğunu, sözleşmedeki oda tiplerini, paylaşılan fiyatları ve kontenjanı kontrol edin; farklı tarihlerle tekrar deneyin.</p>}
      {report.check_error && <p role="alert">Satış kontrolü tamamlanamadı; hazır olarak işaretlenmedi. Yeniden deneyin.</p>}
      {report.offers.slice(0, 5).map((offer) => <p className="text-sm" key={`${offer.tenant_id}-${offer.room_type}`}>{offer.hotel_name} · {offer.room_type}: {offer.total_price} {offer.currency} · {offer.available_rooms} oda</p>)}
      <p className="text-xs text-slate-500">{report.scope} Son kontrol: {new Date(report.checked_at).toLocaleString('tr-TR')}. Rezervasyon anında tekrar doğrulanır.</p>
    </div>}
  </section>;
}
