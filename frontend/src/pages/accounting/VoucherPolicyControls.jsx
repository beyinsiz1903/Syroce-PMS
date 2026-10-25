import { useEffect, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export const VOUCHER_POLICY_ENDPOINT = '/gl/voucher-policy';

export function VoucherPolicyControls({ onChange }) {
  const [data, setData] = useState(null);
  const [mode, setMode] = useState('authorized_self');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    onChange(null);
    setError('');
    axios.get(VOUCHER_POLICY_ENDPOINT).then(({ data: response }) => {
      if (!active) return;
      if (!['authorized_self', 'dual_control'].includes(response?.policy?.mode)) throw new Error('Politika alınamadı');
      setData(response);
      setMode(response.policy.mode);
      onChange(response);
    }).catch(() => { if (active) setError('Fiş onay politikası yüklenemedi. İşlem yapmadan önce yenileyin.'); });
    return () => { active = false; };
  }, [onChange, reload]);

  const save = async () => {
    setBusy(true);
    setError('');
    try {
      const { data: response } = await axios.put(VOUCHER_POLICY_ENDPOINT, { mode, version: data.policy.version, reason: reason.trim() });
      setData(response);
      setMode(response.policy.mode);
      setReason('');
      onChange(response);
    } catch (e) {
      setError(e.response?.data?.detail || 'Politika kaydedilemedi. Yenileyip tekrar deneyin.');
    } finally { setBusy(false); }
  };

  return <section className="mb-4 rounded-lg border bg-white p-4 space-y-3" aria-label="Fiş onay politikası">
    <h3 className="font-semibold">Fiş onay politikası</h3>
    <p className="text-sm text-slate-600">{!data ? 'Politika yükleniyor…' : data.policy.mode === 'dual_control'
      ? 'İkinci kişi onayı: hazırlayan dışında bir muhasebe yetkilisi onaylar.'
      : 'Yetkili kullanıcı kendi fişini gerekçesiyle kesinleştirebilir. İkinci kullanıcı zorunlu değildir.'}</p>
    <p className="text-xs text-slate-500">Yetki, borç/alacak dengesi, açık dönem, kaynak bakiye ve işlem geçmişi kontrolleri her iki modda da korunur. Bu ayar yalnız bu tesisi etkiler.</p>
    {data?.can_manage && <div className="flex flex-wrap items-end gap-3">
      <label className="text-sm">Onay yöntemi
        <select className="block h-10 rounded border px-2" aria-label="Onay yöntemi" value={mode} onChange={e => setMode(e.target.value)} disabled={busy}>
          <option value="authorized_self">Yetkili kendisi kesinleştirebilir</option>
          <option value="dual_control">İkinci kişi onayı zorunlu</option>
        </select>
      </label>
      <label className="text-sm">Politika değişikliği gerekçesi
        <Input value={reason} onChange={e => setReason(e.target.value)} disabled={busy} maxLength={500} />
      </label>
      <Button onClick={save} disabled={busy || mode === data.policy.mode || reason.trim().length < 3}>Politikayı Kaydet</Button>
    </div>}
    {error && <div role="alert" className="text-sm text-red-700">{error} <Button variant="outline" onClick={() => { setData(null); setReload(value => value + 1); }} disabled={busy}>Politikayı Yenile</Button></div>}
  </section>;
}
