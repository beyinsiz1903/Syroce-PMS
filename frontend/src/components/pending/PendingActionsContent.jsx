import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import apiErrorText from '@/utils/apiErrorText';
import PendingActionsList from './PendingActionsList';

export default function PendingActionsContent({ data, loading, error, onRetry, onOpen }) {
  return <div className="space-y-3">
    {error && <div role="alert" data-testid="pending-load-error" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200">
      <p>Bekleyen işler yüklenemedi. {apiErrorText(error, 'Lütfen yeniden deneyin.')}</p>
      {data && <p className="mt-1">Aşağıda son yüklenen liste gösteriliyor; güncel olmayabilir.</p>}
      <Button size="sm" variant="outline" className="mt-2" onClick={onRetry} disabled={loading}>Yeniden dene</Button>
    </div>}
    {loading && !data ? <div role="status" aria-label="Bekleyen işler yükleniyor" className="py-6 text-center"><Loader2 className="mx-auto animate-spin" /></div>
      : (data || !error) && <PendingActionsList data={data} onOpen={onOpen} />}
  </div>;
}
