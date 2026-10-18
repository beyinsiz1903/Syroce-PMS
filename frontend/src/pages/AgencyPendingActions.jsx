import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ListTodo, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import PendingActionsList from '@/components/pending/PendingActionsList';
import apiErrorText from '@/utils/apiErrorText';

// Hotel side: everything waiting in the Agency Extranet, in one list, each
// with the screen that handles it.
const PATHS = { contracts: '/app/incoming-agency-contracts', statements: '/app/agency-statements' };

export default function AgencyPendingActions() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try { setData((await axios.get('/marketplace/hotel/pending-actions')).data); }
    catch (err) { toast.error(apiErrorText(err, 'Bekleyen işler yüklenemedi.')); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold"><ListTodo size={22} /> Bekleyen İşler</h1>
          <p className="text-sm text-slate-500">Acente Extranet'te onay, yanıt ya da ödeme bekleyen her şey: sözleşme talepleri ve değişiklik teklifleri, ekstreler, itirazlar, ödeme bildirimleri ve vadesi gelen ödemeler.</p>
        </div>
        <Button variant="outline" onClick={load} disabled={loading}><RefreshCw size={14} className="mr-2" />Yenile</Button>
      </div>
      <Card>
        <CardContent className="pt-6">
          {loading && !data ? <div className="py-10 text-center"><Loader2 className="mx-auto animate-spin" /></div>
            : <PendingActionsList data={data} onOpen={(item) => navigate(PATHS[item.target] || '/app/agency-statements')} />}
        </CardContent>
      </Card>
    </div>
  );
}
