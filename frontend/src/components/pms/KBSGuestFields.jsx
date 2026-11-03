import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { kbsFieldLabels } from '@/lib/kbsIdentity';

export default function KBSGuestFields({ value, onChange, missing = [], existingReady = false }) {
  const foreign = !['TR', 'TC', 'TUR', 'TURKIYE'].includes(value.nationality.trim().toUpperCase());
  const set = (key, v) => onChange({ ...value, [key]: v });
  return <section className="rounded-lg border p-3 space-y-3" aria-label="KBS kimlik bilgileri">
    <p className="font-medium">KBS için misafir bilgileri</p>
    {existingReady ? <p className="text-sm text-green-700">Kayıtlı misafirin zorunlu kimlik alanları doğrulandı.</p> : <>
      <p className="text-sm text-muted-foreground">Eksikleri rezervasyon sırasında tamamlayın. Her konaklayan ayrı kaydedilmelidir; girişte tamamı yeniden kontrol edilir.</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Label>Uyruk / ülke kodu<Input aria-label="KBS uyruk" value={value.nationality} onChange={e => onChange({ ...value, nationality: e.target.value.toUpperCase(), id_type: e.target.value.toUpperCase() === 'TR' ? 'tc_kimlik' : 'passport' })} /></Label>
        {foreign && <Label>Belge türü<select aria-label="KBS belge türü" className="w-full border rounded p-2" value={value.id_type} onChange={e => set('id_type', e.target.value)}><option value="passport">Pasaport</option><option value="foreign_identity_card">Yabancı kimlik (YKN)</option></select></Label>}
        {foreign && value.id_type !== 'foreign_identity_card'
          ? <Label>Pasaport numarası<Input aria-label="KBS pasaport numarası" value={value.passport_number} onChange={e => set('passport_number', e.target.value)} autoComplete="off" /></Label>
          : <Label>{foreign ? 'Yabancı kimlik numarası' : 'T.C. kimlik numarası'}<Input aria-label="KBS kimlik numarası" inputMode="numeric" maxLength={11} value={value.id_number} onChange={e => set('id_number', e.target.value)} autoComplete="off" /></Label>}
        {foreign && value.id_type !== 'foreign_identity_card' && <>
          <Label>Doğum tarihi<Input aria-label="KBS doğum tarihi" type="date" value={value.birth_date} onChange={e => set('birth_date', e.target.value)} /></Label>
          <Label>Cinsiyet<select aria-label="KBS cinsiyet" className="w-full border rounded p-2" value={value.gender} onChange={e => set('gender', e.target.value)}><option value="">Seçin</option><option value="F">Kadın</option><option value="M">Erkek</option></select></Label>
        </>}
      </div>
      {!!missing.length && <p className="text-sm text-amber-700" data-testid="kbs-identity-missing">Tamamlayın: {missing.map(f => kbsFieldLabels[f] || 'Misafir bilgisi').join(', ')}</p>}
    </>}
  </section>;
}
