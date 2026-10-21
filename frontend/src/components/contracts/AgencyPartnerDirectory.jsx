import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import apiErrorText from '@/utils/apiErrorText';

export default function AgencyPartnerDirectory() {
  const [agencies, setAgencies] = useState([]);
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { const { data } = await axios.get('/marketplace/incoming-requests/agency-candidates'); setAgencies(data.agencies || []); }
    catch { setError('Acente ağı yüklenemedi. Yeniden deneyin.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const invite = async agency => {
    setBusy(agency.id);
    try {
      await axios.post('/marketplace/incoming-requests/partnership-requests', {agency_id: agency.id});
      toast.success('Çalışma talebiniz iletildi. Sözleşme onaylanmadan fiyat ve müsaitlik paylaşılmaz.');
      await load();
    } catch (err) { toast.error(apiErrorText(err, 'Çalışma talebi gönderilemedi.')); }
    finally { setBusy(null); }
  };
  const withdraw = async agency => {
    setBusy(agency.id);
    try { await axios.post(`/marketplace/incoming-requests/partnership-requests/${encodeURIComponent(agency.partnership_request_id)}/withdraw`); await load(); }
    catch (err) { toast.error(apiErrorText(err, 'Talep geri çekilemedi.')); }
    finally { setBusy(null); }
  };
  return <Card data-testid="agency-partner-directory"><CardHeader><CardTitle>Syroce acente ağı</CardTitle>
    <p className="text-sm text-muted-foreground">Acenteleri keşfedin ve şartlarını isteyin. Bu talep satış yetkisi vermez; fiyat ve müsaitlik yalnız yürürlükteki sözleşmeyle paylaşılır. Kanal yöneticisi gerekmez.</p>
    <Input aria-label="Acente ağında ara" placeholder="Acente adı veya ülke ara" value={search} onChange={e => setSearch(e.target.value)} />
  </CardHeader><CardContent>
    {error ? <div role="alert">{error}<Button variant="outline" onClick={load}>Yeniden dene</Button></div>
      : loading ? <p>Acente ağı yükleniyor…</p> : <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {agencies.filter(a => `${a.name} ${a.country || ''} ${a.city || ''}`.toLocaleLowerCase('tr').includes(search.toLocaleLowerCase('tr'))).map(agency => {
          const unavailable = agency.contract_active || agency.proposal_pending || agency.request_pending;
          return <div className="rounded-lg border p-3 space-y-2" key={agency.id}>
            <h3 className="font-semibold">{agency.name}</h3><p className="text-sm text-muted-foreground">{[agency.city, agency.country].filter(Boolean).join(', ')}</p>
            <Button variant="outline" disabled={Boolean(unavailable || busy)} onClick={() => invite(agency)}>
              {agency.contract_active ? 'Sözleşme yürürlükte' : agency.proposal_pending ? 'Sözleşme onayı bekleniyor' : agency.request_pending ? 'Şartlar istendi' : busy === agency.id ? 'Gönderiliyor…' : 'Çalışmak istiyorum, şartlarınızı iletin'}
            </Button>
            {agency.request_pending && agency.partnership_request_id && <Button variant="ghost" disabled={Boolean(busy)} onClick={() => withdraw(agency)}>Çalışma talebini geri çek</Button>}
          </div>;
        })}
        {agencies.length === 0 && <p>Henüz aktif acente bulunmuyor.</p>}
      </div>}
  </CardContent></Card>;
}
