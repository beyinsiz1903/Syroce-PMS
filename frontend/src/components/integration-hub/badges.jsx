import React from 'react';
import { Badge } from '@/components/ui/badge';
import { CheckCircle, AlertTriangle, XCircle, Clock, MailCheck, MailX } from 'lucide-react';

export const HealthBadge = ({ health }) => {
  const colors = {
    green: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    yellow: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    red: 'bg-red-500/15 text-red-400 border-red-500/30',
  };
  return (
    <Badge data-testid="health-badge" className={`${colors[health] || colors.yellow} border`}>
      {health === 'green' && <CheckCircle className="w-3 h-3 mr-1" />}
      {health === 'yellow' && <AlertTriangle className="w-3 h-3 mr-1" />}
      {health === 'red' && <XCircle className="w-3 h-3 mr-1" />}
      {health?.toUpperCase()}
    </Badge>
  );
};

export const StatusBadge = ({ status }) => {
  const map = {
    active: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    draft: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
    paused: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    error: 'bg-red-500/15 text-red-400 border-red-500/30',
    disabled: 'bg-red-500/15 text-red-300 border-red-500/30',
    completed: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    succeeded: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    failed: 'bg-red-500/15 text-red-400 border-red-500/30',
    open: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    queued: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
    pending: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
    batched: 'bg-violet-500/15 text-violet-400 border-violet-500/30',
    dispatched: 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30',
    retrying: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
    manual_review: 'bg-rose-500/15 text-rose-400 border-rose-500/30',
    in_progress: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
    created: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    modified: 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30',
    cancelled: 'bg-red-500/15 text-red-400 border-red-500/30',
    duplicate: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
    duplicate_cancel: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
    conflict: 'bg-rose-500/15 text-rose-400 border-rose-500/30',
    review: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    dismissed: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
    resolved: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    out_of_order: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  };
  return (
    <Badge data-testid={`status-${status}`} className={`${map[status] || map.draft} border text-xs`}>
      {status?.replace(/_/g, ' ')}
    </Badge>
  );
};

export const AckBadge = ({ ackStatus }) => {
  const map = {
    ack_pending: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    ack_sent: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    ack_failed: 'bg-red-500/15 text-red-400 border-red-500/30',
    not_required: 'bg-slate-500/15 text-slate-500 border-slate-700',
  };
  if (!ackStatus || ackStatus === 'not_required') return null;
  return (
    <Badge data-testid={`ack-${ackStatus}`} className={`${map[ackStatus] || ''} border text-[10px]`}>
      {ackStatus === 'ack_pending' && <Clock className="w-2.5 h-2.5 mr-0.5" />}
      {ackStatus === 'ack_sent' && <MailCheck className="w-2.5 h-2.5 mr-0.5" />}
      {ackStatus === 'ack_failed' && <MailX className="w-2.5 h-2.5 mr-0.5" />}
      {ackStatus.replace('ack_', '').replace('_', ' ')}
    </Badge>
  );
};
