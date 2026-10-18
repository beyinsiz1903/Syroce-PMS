import { AlertTriangle, ArrowRight, Clock3, Inbox } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { money } from '@/components/statements/StatementsWorkspace';

// Pending Agency Extranet work for one party (core.pending_actions on the
// server): what this side must do, and what it waits for from the other.

const TEXT = {
  contract_request: { yours: 'Sözleşme talebi onayınızı bekliyor', theirs: 'Sözleşme talebiniz otelin onayında' },
  contract_amendment: { yours: 'Sözleşme değişikliği teklifi kararınızı bekliyor', theirs: 'Değişiklik teklifiniz karşı tarafın kararında' },
  statement_approval: { yours: 'Ekstre onayınızı bekliyor', theirs: 'Ekstre karşı tarafın onayında' },
  dispute: { yours: 'Ekstreye itiraz edildi; yanıtınız bekleniyor', theirs: 'İtirazınız karşı tarafın yanıtında' },
  payment_notice: { yours: 'Ödeme bildirimi doğrulamanızı bekliyor', theirs: 'Ödeme bildiriminiz doğrulama bekliyor' },
  payment: { yours: 'Ödemeniz bekleniyor', theirs: 'Karşı taraftan ödeme bekleniyor' },
};

const day = (value) => (value ? String(value).slice(0, 10) : null);

function Row({ item, onOpen }) {
  const text = TEXT[item.kind]?.[item.owner] || item.kind;
  const detail = [
    item.party_name,
    item.ref,
    item.period?.[0] && `${item.period[0]} – ${item.period[1]}`,
    item.amount != null && money(item.amount, item.currency || 'TRY'),
    item.payment_ref && `Ref. ${item.payment_ref}`,
  ].filter(Boolean).join(' · ');
  return (
    <li className="flex flex-wrap items-center gap-3 border-t py-2.5 first:border-t-0" data-testid={`pending-${item.kind}-${item.owner}`}>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{text}</p>
        <p className="truncate text-xs text-slate-500">{detail}</p>
        {item.reason && <p className="text-xs text-slate-600">İtiraz: {item.reason}</p>}
      </div>
      {item.due_date && (
        <span className={`flex items-center gap-1 text-xs ${item.overdue ? 'font-semibold text-red-700' : 'text-slate-500'}`}>
          {item.overdue ? <AlertTriangle size={13} /> : <Clock3 size={13} />}
          {item.overdue ? 'Vadesi geçti' : 'Vade'} {item.due_date}
        </span>
      )}
      {!item.due_date && item.since && <span className="text-xs text-slate-400">{day(item.since)}</span>}
      {onOpen && (
        <Button size="sm" variant={item.owner === 'yours' ? 'default' : 'outline'} onClick={() => onOpen(item)}>
          {item.owner === 'yours' ? 'İşleme al' : 'Görüntüle'} <ArrowRight size={14} className="ml-1" />
        </Button>
      )}
    </li>
  );
}

export default function PendingActionsList({ data, onOpen, compact = false }) {
  const yours = Array.isArray(data?.yours) ? data.yours : [];
  const theirs = Array.isArray(data?.theirs) ? data.theirs : [];
  if (!yours.length && !theirs.length) {
    return <p className="flex items-center gap-2 text-sm text-slate-500" data-testid="pending-empty"><Inbox size={16} /> Bekleyen iş yok.</p>;
  }
  return (
    <div className="space-y-4" data-testid="pending-actions">
      <section>
        <h3 className="text-sm font-semibold">Sizin işiniz ({yours.length}){data?.counts?.overdue ? <span className="ml-2 text-red-700">· {data.counts.overdue} vadesi geçmiş</span> : null}</h3>
        {yours.length ? <ul>{yours.map((item) => <Row key={`${item.kind}-${item.record_id}-${item.notice_id || ''}`} item={item} onOpen={onOpen} />)}</ul>
          : <p className="text-xs text-slate-500">Sizden beklenen bir işlem yok.</p>}
      </section>
      {!compact && (
        <section>
          <h3 className="text-sm font-semibold text-slate-600">Karşı tarafta bekleyen ({theirs.length})</h3>
          {theirs.length ? <ul>{theirs.map((item) => <Row key={`${item.kind}-${item.record_id}-${item.notice_id || ''}`} item={item} onOpen={onOpen} />)}</ul>
            : <p className="text-xs text-slate-500">Karşı tarafta bekleyen bir işlem yok.</p>}
        </section>
      )}
    </div>
  );
}
