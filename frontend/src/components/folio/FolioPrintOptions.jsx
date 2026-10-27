import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { formatCurrency } from '@/lib/currency';
import { buildFolioStatement, folioPayorLabel, serviceTimingLabel } from '@/lib/folioPresentation';
import PrintableFolio from '@/components/PrintableFolio';

export default function FolioPrintOptions({ folios, charges, extraCharges, payments, booking, property, guest, room, currentFolioId, onClose }) {
  const current = folios.find(folio => folio.id === currentFolioId);
  const [audience, setAudience] = useState('guest');
  const [scope, setScope] = useState(current && folioPayorLabel(current) === 'Misafir' ? current.id : 'guest');
  const [category, setCategory] = useState('all');
  const [selectedIds, setSelectedIds] = useState(null);
  const [preview, setPreview] = useState(false);
  useEffect(() => { setSelectedIds(null); }, [scope, category, audience]);
  const input = { folios, charges, extraCharges, payments, booking, property, scope, category, audience };
  const candidates = buildFolioStatement(input);
  const statement = useMemo(() => buildFolioStatement({ folios, charges, extraCharges, payments, booking, property, scope, category, audience, selectedIds }), [folios, charges, extraCharges, payments, booking, property, scope, category, audience, selectedIds]);
  const hasContents = statement.charges.length > 0 || (!statement.statement_only && (statement.payments.length > 0 || statement.opening_balance !== 0));
  return <section className="rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-4" aria-label="Folyo çıktı seçenekleri">
    <div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="font-semibold text-slate-900">Yazdırılacak hesabı ve hizmetleri seçin</h3><p className="mt-1 text-xs text-slate-600">Bu seçim hesapları taşımaz veya bakiyeyi değiştirmez; yalnız çıktı kapsamını belirler.</p></div><Button size="sm" variant="ghost" onClick={onClose}>Seçenekleri kapat</Button></div>
    <div className="grid gap-3 md:grid-cols-3">
      <label className="text-sm">Çıktı alıcısı<select className="mt-1 block w-full rounded-md border bg-white p-2" value={audience} onChange={event => { setAudience(event.target.value); setScope(event.target.value === 'guest' ? 'guest' : 'all'); }}><option value="guest">Misafir — acente/şirket hesabını gizle</option><option value="internal">İç kullanım — tüm ödeyenler</option></select></label>
      <label className="text-sm">Yazdırılacak hesap<select className="mt-1 block w-full rounded-md border bg-white p-2" value={scope} onChange={event => setScope(event.target.value)}><option value="guest">Misafir hesapları</option>{audience === 'internal' && <option value="all">Tüm hesaplar (acente/şirket dahil)</option>}{folios.filter(folio => audience === 'internal' || folioPayorLabel(folio) === 'Misafir').map(folio => <option key={folio.id} value={folio.id}>{folio.folio_number} · {folioPayorLabel(folio)}</option>)}</select></label>
      <label className="text-sm">Hizmet kapsamı<select className="mt-1 block w-full rounded-md border bg-white p-2" value={category} onChange={event => setCategory(event.target.value)}><option value="all">Hesaptaki tüm hizmetler</option><option value="food_beverage">Yalnız yiyecek ve içecek</option><option value="spa">Yalnız spa</option><option value="minibar">Yalnız minibar</option><option value="accommodation">Yalnız konaklama</option></select></label>
    </div>
    {audience === 'internal' && <p role="alert" className="text-sm font-medium text-rose-700">İç kullanım çıktısı acente/şirket tutarlarını içerebilir. Misafire vermeden önce alıcı seçimini kontrol edin.</p>}
    {statement.excluded_unassigned > 0 && <p className="text-xs text-amber-800">{statement.excluded_unassigned} kalemin hangi hesaba ait olduğu belirsiz; yanlış ödeyene gösterilmemesi için bu çıktıya eklenmedi.</p>}
    <div className="max-h-60 overflow-y-auto rounded-lg border bg-white divide-y">
      {candidates.charges.map((item, index) => <label key={item.id || index} className="flex items-start gap-3 p-3 text-sm"><input type="checkbox" className="mt-1" checked={!selectedIds || selectedIds.includes(item.id || item.charge_id)} disabled={!(item.id || item.charge_id)} onChange={event => { const ids = selectedIds || candidates.charges.map(row => row.id || row.charge_id); setSelectedIds(event.target.checked ? [...ids, item.id || item.charge_id] : ids.filter(id => id !== (item.id || item.charge_id))); }} /><span className="min-w-0 flex-1"><span className="block font-medium">{item.description || item.charge_name || 'Hizmet'}</span><span className="text-xs text-slate-500">{serviceTimingLabel(item)}</span></span><span className="shrink-0 tabular-nums">{formatCurrency(item.total ?? item.charge_amount ?? item.amount, item.currency || statement.currency, { locale: 'tr-TR', decimals: 2 })}</span></label>)}
      {!candidates.charges.length && <p className="p-4 text-sm text-slate-500">Bu kapsamda yazdırılabilecek hizmet bulunmuyor.</p>}
    </div>
    <div className="flex flex-wrap items-center justify-between gap-3"><p className="max-w-xl text-xs text-slate-600">{statement.selection_note}</p><Button size="sm" disabled={!hasContents || statement.mixedCurrency} onClick={() => setPreview(true)}>Çıktıyı önizle</Button></div>
    {statement.mixedCurrency && <p role="alert" className="text-sm text-rose-700">Farklı para birimleri tek toplamda yazdırılamaz. Tek para birimli bir hesap seçin.</p>}
    {preview && <PrintableFolio folioData={statement} guest={guest} room={room} onClose={() => setPreview(false)} />}
  </section>;
}
