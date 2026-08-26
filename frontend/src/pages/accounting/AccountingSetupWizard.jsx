import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { CheckCircle2, CircleAlert, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';

const currentYear = new Date().getFullYear();
const emptyProfile = {
  legal_name: '', taxpayer_id: '', tax_office: '', address: '', city: '', country: 'Türkiye',
  currency: 'TRY', fiscal_year: currentYear, migration_date: `${currentYear}-01-01`,
  opening_balance_required: false, branch_code: '', cost_center_code: '', accountant_name: '', accountant_email: '',
};

const stepLabels = ['Şirket', 'Hesap planı', 'PMS/POS', 'Açılış', 'Kontrol'];

export const AccountingSetupWizard = ({ onAccountsChanged }) => {
  const [state, setState] = useState(null);
  const [profile, setProfile] = useState(emptyProfile);
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState('');
  const [openingText, setOpeningText] = useState('');
  const openingKey = useRef('');

  const load = async () => {
    const response = await axios.get('/gl/setup');
    setState(response.data);
    if (response.data.profile) setProfile({ ...emptyProfile, ...response.data.profile });
  };

  useEffect(() => { load().catch(() => toast.error('Muhasebe kurulum durumu yüklenemedi.')); }, []);

  const update = (key, value) => setProfile(current => ({ ...current, [key]: value }));
  const run = async (key, request, success) => {
    setBusy(key);
    try {
      const response = await request();
      setState(response.data);
      if (response.data.profile) setProfile({ ...emptyProfile, ...response.data.profile });
      toast.success(success);
      return true;
    } catch (error) {
      toast.error(error.response?.data?.detail || 'İşlem tamamlanamadı.');
      return false;
    } finally { setBusy(''); }
  };

  const saveProfile = async () => {
    const ok = await run('profile', () => axios.put('/gl/setup/profile', {
      ...profile,
      fiscal_year: Number(profile.fiscal_year),
      currency: profile.currency.toUpperCase(),
      branch_code: profile.branch_code || null,
      cost_center_code: profile.cost_center_code || null,
      accountant_name: profile.accountant_name || null,
      accountant_email: profile.accountant_email || null,
    }), 'Şirket ve mali yıl bilgileri kaydedildi.');
    if (ok) setStep(2);
  };

  const initialize = async () => {
    const ok = await run('initialize', () => axios.post('/gl/setup/initialize'), 'Hesap planı ve 12 mali dönem hazırlandı.');
    if (ok) { onAccountsChanged?.(); setStep(3); }
  };

  const enableBridge = async () => {
    const ok = await run('mapping', () => axios.put('/gl/integrations/operational/mapping', {
      enabled: true, auto_night_audit: true, auto_pos: true,
      receivable_account_code: '120', revenue_account_code: '600', tax_account_code: '391',
      cash_account_code: '100', card_account_code: '108', bank_account_code: '102',
    }).then(async () => axios.get('/gl/setup')), 'PMS/POS muhasebe köprüsü etkinleştirildi.');
    if (ok) setStep(4);
  };

  const saveOpening = async () => {
    let lines;
    try {
      lines = openingText.split('\n').map(line => line.trim()).filter(Boolean).map((line, index) => {
        const [account_code, debit, credit, memo] = line.split(',').map(value => value.trim());
        if (!account_code || Number.isNaN(Number(debit)) || Number.isNaN(Number(credit))) throw new Error(`${index + 1}. satır geçersiz`);
        return { account_code, debit: Number(debit), credit: Number(credit), memo: memo || null };
      });
    } catch (error) { toast.error(error.message); return; }
    if (!openingKey.current) openingKey.current = globalThis.crypto?.randomUUID?.() || `setup-${Date.now()}`;
    const ok = await run('opening', () => axios.post('/gl/setup/opening-balances', {
      date: profile.migration_date,
      memo: `Muhasebe açılış bakiyeleri - ${profile.migration_date}`,
      lines,
      idempotency_key: openingKey.current,
    }), 'Açılış fişi taslak olarak oluşturuldu; onaylanmadan yevmiyeye geçmez.');
    if (ok) { openingKey.current = ''; setStep(5); }
  };

  if (!state) return <Card><CardContent className="flex items-center gap-2 p-8 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin" /> Kurulum durumu yükleniyor…</CardContent></Card>;

  return <div className="space-y-4" data-testid="accounting-setup-wizard">
    <Card>
      <CardHeader>
        <CardTitle>Otel Muhasebe Kurulumu</CardTitle>
        <p className="text-sm text-slate-500">Her otelin vergi kimliği, mali yılı ve açılış bakiyesi ayrıdır. Hesap şablonu ortaktır; kayıtlar otel bazında saklanır.</p>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-5 gap-1">
          {stepLabels.map((label, index) => <button key={label} type="button" onClick={() => setStep(index + 1)} className={`rounded-lg px-2 py-2 text-xs font-semibold ${step === index + 1 ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600'}`}><span className="block text-[10px] opacity-70">{index + 1}</span>{label}</button>)}
        </div>
      </CardContent>
    </Card>

    {step === 1 && <Card><CardHeader><CardTitle>1. Yasal şirket ve mali yıl</CardTitle></CardHeader><CardContent className="grid gap-3 sm:grid-cols-2">
      {[
        ['legal_name', 'Yasal unvan'], ['taxpayer_id', 'VKN / TCKN'], ['tax_office', 'Vergi dairesi'], ['city', 'Şehir'],
        ['address', 'Yasal adres'], ['country', 'Ülke'], ['currency', 'Defter para birimi'], ['fiscal_year', 'Mali yıl'],
        ['migration_date', 'Geçiş / açılış tarihi'], ['branch_code', 'Şube kodu'], ['cost_center_code', 'Masraf merkezi'], ['accountant_name', 'Mali müşavir'], ['accountant_email', 'Mali müşavir e-posta'],
      ].map(([key, label]) => <label key={key} className={key === 'address' ? 'sm:col-span-2' : ''}><span className="mb-1 block text-xs font-medium text-slate-600">{label}</span><Input type={key === 'fiscal_year' ? 'number' : key === 'migration_date' ? 'date' : key === 'accountant_email' ? 'email' : 'text'} value={profile[key] ?? ''} onChange={event => update(key, event.target.value)} /></label>)}
      <label className="flex items-center gap-2 text-sm sm:col-span-2"><Checkbox checked={profile.opening_balance_required} onCheckedChange={value => update('opening_balance_required', Boolean(value))} /> Eski sistemden açılış bakiyesi aktarılacak</label>
      <div className="sm:col-span-2 flex justify-end"><Button onClick={saveProfile} disabled={busy === 'profile'}>{busy === 'profile' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Kaydet ve devam et</Button></div>
    </CardContent></Card>}

    {step === 2 && <Card><CardHeader><CardTitle>2. Hesap planı ve dönemler</CardTitle></CardHeader><CardContent className="space-y-4"><p className="text-sm text-slate-600">Standart TDHP hesapları mevcut özel hesapları silmeden tamamlanır ve seçilen yıl için 12 mali dönem oluşturulur.</p><div className="rounded-lg bg-slate-50 p-3 text-sm">Aktif hesap: <b>{state.account_count}</b> · Mali dönem: <b>{state.period_count}/12</b></div><Button onClick={initialize} disabled={!state.profile || busy === 'initialize'}>Standart yapıyı hazırla</Button></CardContent></Card>}

    {step === 3 && <Card><CardHeader><CardTitle>3. PMS/POS otomatik muhasebe</CardTitle></CardHeader><CardContent className="space-y-4"><p className="text-sm text-slate-600">Oda geliri, KDV, nakit, kredi kartı ve alacak hareketlerinin doğru hesaplara taslak/kayıt üretmesini sağlar.</p><div className="rounded-lg border p-3 text-sm">Durum: <b>{state.operational_mapping?.enabled ? 'Etkin' : 'Kapalı'}</b><div className="mt-1 text-xs text-slate-500">120 Alıcılar · 600 Satışlar · 391 KDV · 100 Kasa · 108 Kredi Kartı · 102 Banka</div></div><Button onClick={enableBridge} disabled={state.account_count === 0 || busy === 'mapping'}>Varsayılan eşlemeyi etkinleştir</Button></CardContent></Card>}

    {step === 4 && <Card><CardHeader><CardTitle>4. Açılış bakiyeleri</CardTitle></CardHeader><CardContent className="space-y-3"><p className="text-sm text-slate-600">Her satırı <code>hesap,borç,alacak,açıklama</code> biçiminde girin. Borç ve alacak toplamı eşit olmalıdır. Oluşturulan fiş yalnız taslaktır.</p><textarea className="min-h-40 w-full rounded-md border p-3 font-mono text-sm" value={openingText} onChange={event => setOpeningText(event.target.value)} placeholder={'100,10000,0,Açılış kasa bakiyesi\n570,0,10000,Geçmiş yıl kârı'} /><Button onClick={saveOpening} disabled={!profile.opening_balance_required || busy === 'opening'}>Açılış taslağını oluştur</Button>{!profile.opening_balance_required && <div className="flex items-center justify-between gap-3"><p className="text-xs text-slate-500">Yeni otel olarak işaretlendiği için açılış bakiyesi zorunlu değil.</p><Button variant="outline" onClick={() => setStep(5)}>Bu adımı geç</Button></div>}</CardContent></Card>}

    {step === 5 && <Card><CardHeader><CardTitle>5. Hazırlık kontrolü</CardTitle></CardHeader><CardContent className="space-y-3">{state.checks.map(check => <div key={check.code} className="flex items-center gap-2 rounded-lg border p-3 text-sm">{check.ready ? <CheckCircle2 className="h-5 w-5 text-emerald-600" /> : <CircleAlert className={`h-5 w-5 ${check.required ? 'text-red-600' : 'text-amber-500'}`} />}<span className="flex-1">{check.label}</span><span className="text-xs text-slate-500">{check.ready ? 'Hazır' : check.required ? 'Zorunlu' : 'İsteğe bağlı'}</span></div>)}<Button disabled={!state.ready || busy === 'complete'} onClick={() => run('complete', () => axios.post('/gl/setup/complete'), 'Muhasebe kurulumu tamamlandı.')}>Kurulumu tamamla</Button>{!state.ready && <p className="text-xs text-red-600">Zorunlu adımlar tamamlanmadan otomatik muhasebe hazır kabul edilmez.</p>}</CardContent></Card>}
  </div>;
};

export default AccountingSetupWizard;
