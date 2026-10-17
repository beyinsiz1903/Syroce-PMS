import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import StatementsWorkspace, { money } from '@/components/statements/StatementsWorkspace';
import apiErrorText from '@/utils/apiErrorText';

// One entry per global agency, scoped by the hotel's contracts/history.
// Do not send a marketplace ID to the legacy agency_transactions endpoints.
export default function ExtranetFinanceDirectory({ searchTerm = '', onChanged }) {
  const [directory, setDirectory] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const latest = useRef(0);
  const load = useCallback(async () => {
    const request = ++latest.current;
    setLoading(true);
    setError('');
    try {
      const { data } = await axios.get('/agent-arap/extranet-agencies');
      if (!Array.isArray(data?.agencies)) throw new Error('Invalid directory');
      if (request === latest.current) setDirectory(data);
    } catch (err) {
      if (request === latest.current) {
        setDirectory(null);
        setError(apiErrorText(err, 'Extranet cari kayıtları yüklenemedi.'));
      }
    } finally {
      if (request === latest.current) setLoading(false);
    }
  }, []);
  useEffect(() => { load(); return () => { latest.current += 1; }; }, [load]);
  const agencies = (directory?.agencies || []).filter(row =>
    `${row.name || ''} ${row.contact_email || ''}`.toLocaleLowerCase('tr').includes(searchTerm.toLocaleLowerCase('tr')));

  return <section className="min-w-0 space-y-3" aria-label="Extranet acenteleri" aria-busy={loading}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="text-lg font-semibold">Extranet acenteleri</h2>
      <Button variant="outline" size="sm" disabled={loading} onClick={load}>Extranet bakiyelerini yenile</Button>
    </div>
    <p className="text-sm text-muted-foreground">Seçili tesisin sözleşmeli acenteleri ve finans geçmişi. Ödemeler, dekontlar ve onaylar acenteyle aynı ekstreye işlenir; bakiye satış tarihinden bağımsızdır.</p>
    {error && <p role="alert" className="rounded-lg border border-red-200 p-4 text-red-700">{error}</p>}
    {!directory && !error && <p role="status">Extranet kayıtları yükleniyor…</p>}
    {directory && agencies.length === 0 && <p className="rounded-lg border p-4 text-sm text-muted-foreground">Bu tesis ve arama için Extranet acentesi yok. Diğer tesislerin sözleşmeleri burada gösterilmez.</p>}
    {agencies.map(agency => <Card key={agency.id} data-testid={`extranet-finance-${agency.id}`}>
      <CardContent className="min-w-0 space-y-4 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0"><h3 className="break-words font-semibold">{agency.name || agency.id}</h3>
            <p className="break-all text-xs text-muted-foreground">{agency.contact_email}</p>
            <Badge variant="secondary">Extranet · {agency.approved ? 'Sözleşmeli' : 'Finans geçmişi'}</Badge>
          </div>
          <Button variant="outline" onClick={() => setSelected(selected === agency.id ? null : agency.id)}>Mutabakat ve ödeme{selected === agency.id ? ' · Kapat' : ''}</Button>
        </div>
        {agency.currencies.length === 0 && <p className="text-sm text-muted-foreground">{agency.has_financial_history
          ? 'Finans geçmişi var; açık bakiye veya gelecek rezervasyon bulunmuyor. Geçmiş ekstreleri Mutabakat ve ödeme bölümünde inceleyebilirsiniz.'
          : agency.approved ? 'Henüz satış veya ekstre kaydı yok. Acente onaylı sözleşmesiyle listeleniyor.'
            : 'Geçmiş sözleşme kaydı. Varsa önceki ekstreleri Mutabakat ve ödeme bölümünde inceleyebilirsiniz.'}</p>}
        {agency.currencies.map(row => <div key={row.currency} className="grid min-w-0 gap-3 rounded-lg border p-3 sm:grid-cols-2 xl:grid-cols-4">
          <div><p className="text-xs text-muted-foreground">Açık: acente → otel</p><p className="break-words font-semibold tabular-nums">{money(row.receivables.agency_owes_hotel, row.currency)}</p></div>
          <div><p className="text-xs text-muted-foreground">Açık: otel → acente</p><p className="break-words font-semibold tabular-nums">{money(row.receivables.hotel_owes_agency, row.currency)}</p></div>
          <div className="text-sm"><p className="text-xs text-muted-foreground">Henüz ekstreye alınmamış</p><p>Acente → otel: {money(row.unbilled.agency_owes_hotel, row.currency)}</p><p>Otel → acente: {money(row.unbilled.hotel_owes_agency, row.currency)}</p></div>
          <div><p className="text-xs text-muted-foreground">Gelecek 90 gün · satış tutarı, bakiye değil</p><p className="font-semibold tabular-nums">{row.forward['90']?.bookings || 0} rezervasyon</p><p className="text-sm">{money(row.forward['90']?.gross, row.currency)}</p></div>
          {row.receivables.pending_notices?.count > 0 && <p className="text-sm text-amber-700 sm:col-span-2 xl:col-span-4">{row.receivables.pending_notices.count} ödeme bildirimi doğrulama bekliyor. Doğrulanana kadar bakiyeden düşülmez.</p>}
        </div>)}
        {selected === agency.id && <StatementsWorkspace key={agency.id} side="hotel" api={axios}
          base="/marketplace/hotel/statements" partiesPath="/marketplace/hotel/statements/agencies"
          fixedPartyId={agency.id} initialCurrency={agency.currencies.length === 1 ? agency.currencies[0].currency : ''}
          onChanged={() => { load(); onChanged?.(); }} title={`${agency.name || agency.id} · Ortak mutabakat`}
          description="Tahsilatı ilgili ekstreye kaydedin; otele ait ödemeyi bildirin. İki taraf aynı ödeme ve bakiye kaydını görür. Birden fazla para biriminde işlem varsa ekstre para birimini ayrıca seçin." />}
      </CardContent>
    </Card>)}
  </section>;
}
