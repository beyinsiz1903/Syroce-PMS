import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { ListTodo, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import PendingActionsContent from '@/components/pending/PendingActionsContent';
import usePendingActions from '@/components/pending/usePendingActions';

// Hotel side: everything waiting in the Agency Extranet, in one list, each
// with the screen that handles it.
const PATHS = { contracts: '/app/incoming-agency-contracts', statements: '/app/agency-statements' };

export default function AgencyPendingActions({ user, tenant }) {
  const navigate = useNavigate();
  const pending = usePendingActions({
    api: axios, path: '/marketplace/hotel/pending-actions',
    sessionKey: JSON.stringify([user?.id || user?.user_id, tenant?.id || tenant?._id || user?.tenant_id]),
  });
  const open = item => {
    const path = PATHS[item.target] || PATHS.statements;
    navigate(item.kind === 'contract_amendment' ? `${path}?tab=active` : path);
  };

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold"><ListTodo size={22} /> Bekleyen İşler</h1>
          <p className="text-sm text-slate-500">Acente Extranet'te onay, yanıt ya da ödeme bekleyen her şey: sözleşme talepleri ve değişiklik teklifleri, ekstreler, itirazlar, ödeme bildirimleri ve vadesi gelen ödemeler.</p>
        </div>
        <Button variant="outline" onClick={pending.reload} disabled={pending.loading}><RefreshCw size={14} className="mr-2" />Yenile</Button>
      </div>
      <Card>
        <CardContent className="pt-6">
          <PendingActionsContent {...pending} onRetry={pending.reload} onOpen={open} />
        </CardContent>
      </Card>
    </div>
  );
}
