import { useState } from 'react';
import { Button } from '@/components/ui/button';

export default function ContractInitialOffer({ contract, busy, onAccept }) {
  const [consent, setConsent] = useState(false);
  if (contract.status !== 'pending' || contract.awaiting_party !== 'agency') return null;
  const policy = contract.cancellation_policy || {};
  const payment = {prepaid: 'Ön ödemeli', on_arrival: 'Girişte ödemeli', net_7: '7 gün vadeli', net_15: '15 gün vadeli', net_30: '30 gün vadeli'};
  return <section className="w-full rounded-lg border border-amber-300 p-4 space-y-2" aria-label="Otel karşı teklif şartları">
    <h3 className="font-semibold">Otelin karşı teklifi — onayınıza kadar satış kapalı</h3>
    <p>Geçerlilik: {contract.valid_from} – {contract.valid_to} · Para birimi: {contract.currency}</p>
    <p>Komisyon: %{contract.commission_pct} · Ödeme: {payment[contract.payment_terms] || contract.payment_terms} · Tür: {contract.contract_type === 'net_rate' ? 'Net fiyat' : 'Komisyonlu'}</p>
    <p>İptal: girişten {policy.free_until_days_before} gün öncesine kadar ücretsiz; ceza %{policy.penalty_pct}; no-show %{policy.no_show_penalty_pct}.</p>
    <p>Oda tipleri: {(contract.allowed_room_types || []).join(', ') || 'Sözleşme kapsamındaki tüm oda tipleri'}</p>
    <p>Otelin temel fiyatına dönüş: {contract.allow_base_rate_fallback ? 'Açık' : 'Kapalı'} · Kredi limiti: {contract.credit_limit ?? 'Tanımlanmadı'} {contract.credit_currency || ''}</p>
    {(contract.season_rates || []).map((season, index) => <p key={index}>{season.room_type_id}: {season.season_start} – {season.season_end} · {season.price} {contract.currency}</p>)}
    {contract.special_terms && <p className="whitespace-pre-wrap">Özel şartlar: {contract.special_terms}</p>}
    {contract.decision_notes && <p className="whitespace-pre-wrap">Otel notu: {contract.decision_notes}</p>}
    <label className="flex gap-2"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} />Bu karşı teklifin şartlarını okudum ve kabul ediyorum.</label>
    <Button disabled={!consent || busy} onClick={() => onAccept(contract)}>Karşı teklifi onayla</Button>
  </section>;
}
