import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const STATES = { draft: 'Hazırlık', reviewed: 'Canlı devir incelendi', awaiting_finance: 'Muhasebe onayı / kayıt bekleniyor', activating: 'Canlı devir sürüyor', complete: 'Canlı devir tamamlandı', failed: 'Kısmi devir durdu · devam edilebilir' };
const message = e => typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : 'İşlem tamamlanamadı. Durumu yenileyip kontrol edin.';
const textClass = 'min-h-24 w-full rounded-md border border-input bg-background p-3 text-sm font-mono';

export default function DataMigrationCutover({ batchId }) {
  const root = `/data-migration/batches/${batchId}/cutover`;
  const [job, setJob] = useState(null);
  const [date, setDate] = useState('');
  const [frozen, setFrozen] = useState('');
  const [links, setLinks] = useState('{"rooms":{},"companies":{},"agencies":{}}');
  const [accounts, setAccounts] = useState('{"receivable":"120","payable":"320","deposit":"340","clearing":"500"}');
  const [rates, setRates] = useState('{"TRY":"1"}');
  const [stopped, setStopped] = useState(false);
  const [exclude, setExclude] = useState(false);
  const [confirmation, setConfirmation] = useState('');
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const stop = useRef(false);
  useEffect(() => () => { stop.current = true; }, []);
  const editable = !job || ['draft', 'reviewed'].includes(job.state);
  function receive(data) {
    setJob(data); setConfirmation('');
    if (data?.config) {
      setDate(data.config.cutover_date); setFrozen(data.config.source_frozen_at);
      setLinks(JSON.stringify(data.config.target_links, null, 2)); setAccounts(JSON.stringify(data.config.accounts, null, 2));
      setRates(JSON.stringify(data.config.exchange_rates, null, 2)); setStopped(data.config.source_writes_stopped); setExclude(data.config.balances_exclude_folios);
    }
    setDirty(false);
  }
  useEffect(() => {
    let current = true;
    axios.get(root).then(({ data }) => { if (current) receive(data); }).catch(e => { if (current) setError(message(e)); });
    return () => { current = false; };
  }, [root]);
  async function action(fn) {
    setBusy(true); setError('');
    try { await fn(); } catch (e) { setError(e instanceof SyntaxError ? 'JSON alanı geçersiz.' : message(e)); } finally { setBusy(false); }
  }
  const approved = !dirty && confirmation === 'CANLI DEVRI ONAYLIYORUM' && job?.review_token && !job?.report?.error_count;
  const body = () => ({ review_token: job.review_token, confirmation });
  async function activate() {
    stop.current = false;
    await action(async () => {
      let current = job;
      do {
        const { data } = await axios.post(`${root}/activate`, { review_token: current.review_token, confirmation }, { timeout: 110000 });
        current = data; setJob(data);
      } while (current.state === 'activating' && !stop.current);
      setConfirmation('');
    });
  }
  return <Card><CardHeader><CardTitle role="heading" aria-level={3} className="text-base">5. Ayrı onaylı canlı devir</CardTitle></CardHeader><CardContent className="space-y-4">
    <p className="text-sm text-muted-foreground">Arşiv tamamlanması canlı devir değildir. Önce kaynakta yazmayı durdurun, son fark dosyasını aktarın ve bağımsız sayım/tutarları uzlaştırın. İş günü ile kesim günü aynı olmalı. Mevcut odalar/şirketler/acenteler açıkça eşleştirilir; anlaşma veya tarifeler tahmin edilmez.</p>
    <p className="text-sm text-muted-foreground">Aktif rezervasyonlarda her gecenin brüt fiyatını günlük fiyat dosyasıyla ve 1–8 folyonun charged_amount / paid_amount / balance kesim dökümüyle verin. Geçmiş geceler tekrar ücretlendirilmez. KBS, eski tahsilat, fatura ve mesajlar yeniden gönderilmez; KBS devri ayrıca işletme tarafından uzlaştırılır.</p>
    <p className="text-sm text-muted-foreground">Otomatik canlı devir şu aşamada doğrudan misafir ödemeli rezervasyonlar içindir. Şirket/acente bağlantılı aktif rezervasyonlar; ödeyen, komisyon ve alt defter devir sözleşmesi doğrulanmadan engellenir. Bu kayıtların geçmişi arşive alınabilir.</p>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    {job && <p role="status" className="text-sm font-medium">{STATES[job.state] || job.state} · {job.cursor || 0} / {job.report?.bookings || 0} rezervasyon</p>}
    {editable && <form className="space-y-3" onChange={() => { setDirty(true); setConfirmation(''); }} onSubmit={e => { e.preventDefault(); action(async () => receive((await axios.put(root, { cutover_date: date, source_frozen_at: frozen, target_links: JSON.parse(links), accounts: JSON.parse(accounts), exchange_rates: JSON.parse(rates), source_writes_stopped: stopped, balances_exclude_folios: exclude })).data)); }}>
      <div className="grid gap-3 sm:grid-cols-2"><div><Label htmlFor="cutover-date">Kesim / açık iş günü</Label><Input id="cutover-date" type="date" value={date} required disabled={busy} onChange={e => setDate(e.target.value)} /></div><div><Label htmlFor="cutover-frozen">Kaynak yazmasının durduğu an (saat dilimiyle)</Label><Input id="cutover-frozen" value={frozen} required disabled={busy} onChange={e => setFrozen(e.target.value)} placeholder="2026-10-21T18:30:00+03:00" /></div></div>
      <div><Label htmlFor="cutover-links">Eski kaynak no → mevcut hedef ID (JSON)</Label><textarea id="cutover-links" className={textClass} value={links} disabled={busy} onChange={e => setLinks(e.target.value)} /><p className="text-xs text-muted-foreground">Örnek: {'{"rooms":{"eski-101":"syroce-oda-id"},"companies":{},"agencies":{}}'}. Misafir bağlantıları önce arşiv/yayınlama adımında yapılır.</p></div>
      <div className="grid gap-3 sm:grid-cols-2"><div><Label htmlFor="cutover-accounts">Mevcut bilanço hesapları (JSON, öneriyi muhasebeci doğrular)</Label><textarea id="cutover-accounts" className={textClass} value={accounts} disabled={busy} onChange={e => setAccounts(e.target.value)} /></div><div><Label htmlFor="cutover-rates">Kesim anı TL karşılık kurları (JSON)</Label><textarea id="cutover-rates" className={textClass} value={rates} disabled={busy} onChange={e => setRates(e.target.value)} /><p className="text-xs text-muted-foreground">Kur tahmin edilmez. Örnek: {'{"TRY":"1","EUR":"40.123456"}'}. GL iki ondalıkla çalışır; daha hassas döviz otomatik devredilmez.</p></div></div>
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={stopped} required disabled={busy} onChange={e => setStopped(e.target.checked)} />Kaynakta yeni işlem girişi durduruldu; kesim anı ve son fark aktarımı doğrulandı.</label>
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={exclude} disabled={busy} onChange={e => setExclude(e.target.checked)} />Bağımsız cari bakiye dosyası aktif folyo bakiyelerini içermiyor; kaynak raporundan kontrol ettim.</label>
      <Button type="submit" disabled={busy || !stopped}>Canlı devir ayarlarını kaydet</Button>
    </form>}
    {job && editable && <Button variant="outline" disabled={busy || dirty} onClick={() => action(async () => receive((await axios.post(`${root}/review`, {}, { timeout: 110000 })).data))}>Canlı devir denemesi ve çakışma kontrolü</Button>}
    {job?.report && <div className="space-y-2 rounded-md border p-3 text-sm"><p>{job.report.bookings} rezervasyon · {job.report.folios} folyo · {job.report.balances} cari bakiye · {job.report.error_count} hata</p><p className="break-words">{Object.entries(job.report.totals || {}).map(([key, value]) => `${key}: ${value}`).join(' · ') || 'Sıfır açılış'}</p>{job.report.errors?.map((item, i) => <p key={i} className="text-destructive">{item.message}</p>)}<p className="text-muted-foreground">Devir parçalarda ilerler; hata halinde kısmi kayıtlar korunur ve aynı planla devam edilir. Canlı kayıtlar otomatik silinmez.</p></div>}
    {job?.voucher_id && <p className="break-all text-sm">Muhasebe → Açılış fişi: {job.voucher_id}. Fişi mevcut muhasebe onay/kayıt akışında tamamladıktan sonra burada devam edin. Fişin kayıt tarihi ve satırları değişirse aktivasyon engellenir.</p>}
    {job?.review_token && job.state !== 'complete' && <div className="space-y-3">
      <Label htmlFor="cutover-confirm">CANLI DEVRI ONAYLIYORUM yazın</Label><Input id="cutover-confirm" value={confirmation} disabled={busy || dirty} onChange={e => setConfirmation(e.target.value)} />
      <div className="flex flex-wrap gap-2">{job.report?.voucher_required && ['reviewed', 'awaiting_finance'].includes(job.state) && <Button variant="outline" disabled={busy || !approved} onClick={() => action(async () => receive((await axios.post(`${root}/voucher`, body(), { timeout: 110000 })).data))}>Açılış fişini taslak oluştur · para göndermez</Button>}<Button disabled={busy || !approved || (job.report?.voucher_required && !job.voucher_id)} onClick={activate}>Onaylı canlı devri başlat / sürdür</Button>{busy && <Button variant="outline" onClick={() => { stop.current = true; }}>Bu parçadan sonra duraklat</Button>}</div>
    </div>}
    <Button size="sm" variant="outline" disabled={busy || dirty} onClick={() => action(async () => receive((await axios.get(root)).data))}>Canlı devir durumunu yenile</Button>
  </CardContent></Card>;
}
