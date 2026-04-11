import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Download, RefreshCw, Eye, CheckCircle2, XCircle, AlertTriangle,
  Clock, Package, RotateCcw, ChevronDown, ChevronUp, Filter,
  FileText, Send, Ban, Loader2, ArrowUpDown
} from 'lucide-react';
import { API, MetricCard, SeverityBadge } from '../shared';

const API_BASE = import.meta.env.VITE_BACKEND_URL;

const fetchAPI = async (path) => {
  const token = localStorage.getItem('token');
  const res = await fetch(`${API_BASE}/api${API}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
};

const postAPI = async (path, body = {}) => {
  const token = localStorage.getItem('token');
  const res = await fetch(`${API_BASE}/api${API}${path}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
};

const STATUS_COLORS = {
  created: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  modified: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  cancelled: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
  duplicate: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  duplicate_cancel: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
  conflict: 'bg-red-500/15 text-red-400 border-red-500/30',
  review: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  failed: 'bg-red-500/15 text-red-400 border-red-500/30',
  out_of_order: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
  dismissed: 'bg-slate-600/15 text-slate-500 border-slate-600/30',
  pending: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
  acknowledged: 'bg-teal-500/15 text-teal-400 border-teal-500/30',
};

const ACK_COLORS = {
  ack_pending: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  ack_sent: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  ack_failed: 'bg-red-500/15 text-red-400 border-red-500/30',
  ack_retrying: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  not_required: 'bg-slate-600/15 text-slate-500 border-slate-600/30',
};

const StatusBadge = ({ status }) => (
  <Badge data-testid={`status-${status}`} className={`${STATUS_COLORS[status] || STATUS_COLORS.pending} border text-[10px] px-1.5 py-0`}>
    {status?.replace(/_/g, ' ')}
  </Badge>
);

const AckBadge = ({ status }) => (
  <Badge data-testid={`ack-${status}`} className={`${ACK_COLORS[status] || ACK_COLORS.not_required} border text-[10px] px-1.5 py-0`}>
    {status?.replace(/_/g, ' ')}
  </Badge>
);

/* ─── Batch Summary Card ────────────────────────────────────── */
const BatchCard = ({ batch, onExpand }) => {
  const total = batch.total_reservations || 0;
  const isCompleted = batch.status === 'completed';
  return (
    <Card data-testid={`batch-${batch.id?.slice(0,8)}`} className="bg-slate-800/40 border-slate-700/50 hover:border-slate-600 transition-colors cursor-pointer" onClick={() => onExpand(batch.id)}>
      <CardContent className="p-3">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Package className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-xs font-mono text-slate-300">{batch.id?.slice(0, 8)}</span>
            <Badge className={`${isCompleted ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' : 'bg-red-500/15 text-red-400 border-red-500/30'} border text-[10px]`}>
              {batch.status}
            </Badge>
          </div>
          <span className="text-[10px] text-slate-500">{batch.duration_ms ? `${batch.duration_ms}ms` : ''}</span>
        </div>
        <div className="grid grid-cols-5 gap-1 text-[10px]">
          <StatPill label="New" value={batch.new_count} color="text-emerald-400" />
          <StatPill label="Mod" value={batch.modified_count} color="text-blue-400" />
          <StatPill label="Cancel" value={batch.cancelled_count} color="text-slate-300" />
          <StatPill label="Dup" value={batch.duplicate_count} color="text-amber-400" />
          <StatPill label="Fail" value={batch.failed_count} color="text-red-400" />
        </div>
        {(batch.review_count > 0 || batch.conflict_count > 0 || batch.out_of_order_count > 0) && (
          <div className="flex gap-2 mt-1.5">
            {batch.review_count > 0 && <span className="text-[10px] text-orange-400">Review: {batch.review_count}</span>}
            {batch.conflict_count > 0 && <span className="text-[10px] text-red-400">Conflict: {batch.conflict_count}</span>}
            {batch.out_of_order_count > 0 && <span className="text-[10px] text-purple-400">OOO: {batch.out_of_order_count}</span>}
          </div>
        )}
        <div className="flex items-center justify-between mt-1.5">
          <span className="text-[10px] text-slate-500">
            {new Date(batch.started_at).toLocaleString('tr-TR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
          </span>
          <div className="flex gap-1">
            {batch.ack_sent_count > 0 && <span className="text-[10px] text-emerald-400">ACK: {batch.ack_sent_count}</span>}
            {batch.ack_failed_count > 0 && <span className="text-[10px] text-red-400">ACK Fail: {batch.ack_failed_count}</span>}
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

const StatPill = ({ label, value, color }) => (
  <div className="text-center">
    <span className={`block font-semibold ${color}`}>{value || 0}</span>
    <span className="text-slate-500">{label}</span>
  </div>
);

/* ─── Reservation Detail Dialog ─────────────────────────────── */
const ReservationDetailDialog = ({ reservation, onClose, onReprocess, onDismiss }) => {
  if (!reservation) return null;
  const r = reservation;
  const isReviewable = ['review', 'conflict', 'out_of_order'].includes(r.import_status);

  return (
    <div data-testid="reservation-detail-dialog" className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-700 rounded-lg max-w-2xl w-full max-h-[85vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="p-4 border-b border-slate-700 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-white">Reservation Detail</h3>
            <span className="text-[10px] font-mono text-slate-400">{r.id}</span>
          </div>
          <button data-testid="close-detail-btn" onClick={onClose} className="text-slate-400 hover:text-white"><XCircle className="w-4 h-4" /></button>
        </div>
        <div className="p-4 space-y-3 text-xs">
          {/* Status Row */}
          <div className="flex gap-2 flex-wrap">
            <StatusBadge status={r.import_status} />
            <AckBadge status={r.ack_status} />
            {r.is_modification && <Badge className="bg-blue-500/15 text-blue-400 border-blue-500/30 border text-[10px]">Modification</Badge>}
            {r.is_cancellation && <Badge className="bg-slate-500/15 text-slate-300 border-slate-500/30 border text-[10px]">Cancellation</Badge>}
          </div>

          {/* Guest Info */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Guest" value={r.guest_name} />
            <Field label="Email" value={r.guest_email} />
            <Field label="Phone" value={r.guest_phone} />
            <Field label="Channel" value={r.channel_name} />
          </div>

          {/* Stay Info */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Arrival" value={r.arrival_date} />
            <Field label="Departure" value={r.departure_date} />
            <Field label="Adults" value={r.adult_count} />
            <Field label="Children" value={r.child_count} />
            <Field label="Amount" value={`${r.total_amount} ${r.currency}`} />
            <Field label="Payment" value={r.payment_type} />
          </div>

          {/* Mapping Info */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Room Type (External)" value={r.room_type_external_id} />
            <Field label="Room Type (PMS)" value={r.room_type_mapped_id || 'Not mapped'} />
            <Field label="Rate Plan (External)" value={r.rate_plan_external_id} />
            <Field label="Rate Plan (PMS)" value={r.rate_plan_mapped_id || 'Not mapped'} />
            <Field label="PMS Booking" value={r.pms_booking_id || 'N/A'} />
            <Field label="External ID" value={r.external_reservation_id} />
          </div>

          {/* Review Info */}
          {(r.review_reason || r.conflict_reason) && (
            <div className="bg-orange-500/10 border border-orange-500/20 rounded p-2.5">
              <p className="text-[10px] text-orange-400 font-medium mb-1">Review Info</p>
              {r.review_reason_code && <p className="text-[10px] text-slate-300">Code: <span className="text-orange-300">{r.review_reason_code}</span></p>}
              {r.review_reason && <p className="text-[10px] text-slate-300">{r.review_reason}</p>}
              {r.conflict_reason && <p className="text-[10px] text-red-300">{r.conflict_reason}</p>}
              {r.suggested_action && <p className="text-[10px] text-amber-300 mt-1">Suggested: {r.suggested_action}</p>}
            </div>
          )}

          {/* Error Info */}
          {r.error_message && (
            <div className="bg-red-500/10 border border-red-500/20 rounded p-2.5">
              <p className="text-[10px] text-red-400">{r.error_message}</p>
            </div>
          )}

          {/* ACK Info */}
          {r.ack_failed_reason && (
            <div className="bg-red-500/10 border border-red-500/20 rounded p-2.5">
              <p className="text-[10px] text-red-400 font-medium">ACK Failed: {r.ack_failed_reason}</p>
            </div>
          )}

          {/* Timestamps */}
          <div className="grid grid-cols-2 gap-3 text-slate-500">
            <Field label="Created" value={r.created_at ? new Date(r.created_at).toLocaleString('tr-TR') : ''} />
            <Field label="Updated" value={r.updated_at ? new Date(r.updated_at).toLocaleString('tr-TR') : ''} />
            {r.reviewed_at && <Field label="Reviewed" value={new Date(r.reviewed_at).toLocaleString('tr-TR')} />}
            {r.reprocessed_at && <Field label="Reprocessed" value={new Date(r.reprocessed_at).toLocaleString('tr-TR')} />}
          </div>

          {/* Actions */}
          {isReviewable && (
            <div className="flex gap-2 pt-2 border-t border-slate-700">
              <Button data-testid="reprocess-btn" size="sm" className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs" onClick={() => onReprocess(r.id)}>
                <RotateCcw className="w-3 h-3 mr-1" /> Reprocess
              </Button>
              <Button data-testid="dismiss-btn" size="sm" variant="outline" className="border-slate-600 text-slate-300 text-xs" onClick={() => onDismiss(r.id)}>
                <Ban className="w-3 h-3 mr-1" /> Dismiss
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const Field = ({ label, value }) => (
  <div>
    <span className="text-slate-500 block">{label}</span>
    <span className="text-slate-200">{value || '-'}</span>
  </div>
);

/* ─── Audit Trail Timeline ──────────────────────────────────── */
const AuditTimeline = ({ logs }) => {
  if (!logs?.length) return <p className="text-xs text-slate-500 text-center py-4">No audit logs yet</p>;
  return (
    <div data-testid="audit-timeline" className="space-y-1.5 max-h-80 overflow-y-auto">
      {logs.slice(0, 50).map((log, i) => (
        <div key={log.id || i} className="flex items-start gap-2 text-[10px]">
          <div className="w-1.5 h-1.5 rounded-full bg-slate-500 mt-1 shrink-0" />
          <div className="flex-1 min-w-0">
            <span className="text-slate-300 font-medium">{log.action?.replace(/_/g, ' ')}</span>
            {log.metadata?.external_id && <span className="text-slate-500 ml-1">[{log.metadata.external_id.slice(0, 8)}]</span>}
            <span className="text-slate-600 ml-2">{new Date(log.created_at).toLocaleString('tr-TR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
          </div>
        </div>
      ))}
    </div>
  );
};

/* ─── Main Tab Component ────────────────────────────────────── */
const ReservationsTab = () => {
  const [stats, setStats] = useState(null);
  const [reservations, setReservations] = useState([]);
  const [reviewQueue, setReviewQueue] = useState([]);
  const [batches, setBatches] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedRes, setSelectedRes] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [activeSection, setActiveSection] = useState('overview');
  const [actionLoading, setActionLoading] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [statsData, resData, reviewData, batchData, auditData] = await Promise.all([
        fetchAPI('/reservations/stats'),
        fetchAPI(`/reservations/imported?limit=100${statusFilter ? `&status=${statusFilter}` : ''}`),
        fetchAPI('/reservations/review-queue'),
        fetchAPI('/reservations/batches'),
        fetchAPI('/reservations/audit-trail?limit=50'),
      ]);
      setStats(statsData);
      setReservations(resData.reservations || []);
      setReviewQueue(reviewData.queue || []);
      setBatches(batchData.batches || []);
      setAuditLogs(auditData.audit_logs || []);
    } catch (e) {
      console.error('Failed to load reservation data:', e);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleReprocess = async (reservationId) => {
    setActionLoading(reservationId);
    try {
      await postAPI(`/reservations/review-queue/${reservationId}/reprocess`);
      loadData();
    } catch (e) {
      console.error('Reprocess failed:', e);
    } finally {
      setActionLoading(null);
      setSelectedRes(null);
    }
  };

  const handleDismiss = async (reservationId) => {
    setActionLoading(reservationId);
    try {
      await postAPI(`/reservations/review-queue/${reservationId}/dismiss`);
      loadData();
    } catch (e) {
      console.error('Dismiss failed:', e);
    } finally {
      setActionLoading(null);
      setSelectedRes(null);
    }
  };

  const handleRetryAcks = async (connectorId) => {
    setActionLoading('retry-acks');
    try {
      await postAPI('/reservations/retry-acks', { connector_id: connectorId });
      loadData();
    } catch (e) {
      console.error('Retry ACKs failed:', e);
    } finally {
      setActionLoading(null);
    }
  };

  const handleViewDetail = async (reservationId) => {
    try {
      const detail = await fetchAPI(`/reservations/imported/${reservationId}`);
      setSelectedRes(detail);
    } catch (e) {
      console.error('Failed to load reservation detail:', e);
    }
  };

  if (loading) {
    return <div className="flex justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;
  }

  const byStatus = stats?.by_status || {};
  const byAck = stats?.by_ack_status || {};

  return (
    <div data-testid="reservations-tab" className="space-y-4">
      {/* Section Tabs */}
      <div className="flex gap-1 mb-1">
        {['overview', 'reservations', 'review', 'batches', 'audit'].map(sec => (
          <button
            key={sec}
            data-testid={`section-${sec}`}
            onClick={() => setActiveSection(sec)}
            className={`px-3 py-1.5 text-xs rounded-md transition-all ${
              activeSection === sec ? 'bg-blue-600 text-white' : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800'
            }`}
          >
            {sec.charAt(0).toUpperCase() + sec.slice(1)}
          </button>
        ))}
        <div className="flex-1" />
        <Button data-testid="refresh-reservations" size="sm" variant="ghost" onClick={loadData} className="text-slate-400 hover:text-white text-xs">
          <RefreshCw className="w-3 h-3 mr-1" /> Refresh
        </Button>
      </div>

      {/* ─── OVERVIEW ─────────────────────────────────────────── */}
      {activeSection === 'overview' && (
        <div className="space-y-4">
          {/* Metric Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard title="Total Imports" value={stats?.total_reservations || 0} icon={Package} color="text-blue-400" />
            <MetricCard title="Success Rate" value={`${stats?.success_rate || 0}%`} icon={CheckCircle2}
              color={stats?.success_rate >= 80 ? 'text-emerald-400' : 'text-amber-400'} />
            <MetricCard title="Review Queue" value={stats?.review_queue_count || 0} icon={AlertTriangle}
              color={stats?.review_queue_count > 0 ? 'text-orange-400' : 'text-slate-400'} />
            <MetricCard title="ACK Failed" value={stats?.ack_failed_count || 0} icon={XCircle}
              color={stats?.ack_failed_count > 0 ? 'text-red-400' : 'text-slate-400'} />
          </div>

          {/* Status Breakdown */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card className="bg-slate-800/40 border-slate-700/50">
              <CardContent className="p-4">
                <h3 className="text-xs font-medium text-slate-300 mb-3">Import Status Breakdown</h3>
                <div className="space-y-1.5">
                  {Object.entries(byStatus).length > 0 ? Object.entries(byStatus).sort((a, b) => b[1] - a[1]).map(([status, count]) => (
                    <div key={status} className="flex items-center justify-between">
                      <StatusBadge status={status} />
                      <span className="text-xs text-slate-300 font-mono">{count}</span>
                    </div>
                  )) : <p className="text-xs text-slate-500">No data yet</p>}
                </div>
              </CardContent>
            </Card>

            <Card className="bg-slate-800/40 border-slate-700/50">
              <CardContent className="p-4">
                <h3 className="text-xs font-medium text-slate-300 mb-3">ACK Status Breakdown</h3>
                <div className="space-y-1.5">
                  {Object.entries(byAck).length > 0 ? Object.entries(byAck).sort((a, b) => b[1] - a[1]).map(([status, count]) => (
                    <div key={status} className="flex items-center justify-between">
                      <AckBadge status={status} />
                      <span className="text-xs text-slate-300 font-mono">{count}</span>
                    </div>
                  )) : <p className="text-xs text-slate-500">No data yet</p>}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Recent Batches */}
          <Card className="bg-slate-800/40 border-slate-700/50">
            <CardContent className="p-4">
              <h3 className="text-xs font-medium text-slate-300 mb-3">Recent Import Batches</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                {(stats?.recent_batches || []).map(b => (
                  <BatchCard key={b.id} batch={b} onExpand={() => setActiveSection('batches')} />
                ))}
                {(!stats?.recent_batches?.length) && <p className="text-xs text-slate-500">No batches yet</p>}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ─── RESERVATIONS LIST ────────────────────────────────── */}
      {activeSection === 'reservations' && (
        <div className="space-y-3">
          {/* Filter Bar */}
          <div className="flex items-center gap-2">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <select
              data-testid="status-filter"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-slate-800 border border-slate-700 text-xs text-slate-300 rounded px-2 py-1"
            >
              <option value="">All Statuses</option>
              {['created', 'modified', 'cancelled', 'duplicate', 'conflict', 'review', 'failed', 'out_of_order', 'dismissed'].map(s => (
                <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
              ))}
            </select>
            <span className="text-[10px] text-slate-500">{reservations.length} reservation(s)</span>
          </div>

          {/* Reservation Table */}
          <Card className="bg-slate-800/40 border-slate-700/50">
            <div className="overflow-x-auto">
              <table data-testid="reservations-table" className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-700 text-slate-400">
                    <th className="text-left p-2.5 font-medium">Guest</th>
                    <th className="text-left p-2.5 font-medium">Channel</th>
                    <th className="text-left p-2.5 font-medium">Status</th>
                    <th className="text-left p-2.5 font-medium">ACK</th>
                    <th className="text-left p-2.5 font-medium">Dates</th>
                    <th className="text-left p-2.5 font-medium">Amount</th>
                    <th className="text-right p-2.5 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {reservations.map(r => (
                    <tr key={r.id} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                      <td className="p-2.5">
                        <span className="text-slate-200 block">{r.guest_name || 'Unknown'}</span>
                        <span className="text-[10px] text-slate-500 font-mono">{r.external_reservation_id?.slice(0, 12)}</span>
                      </td>
                      <td className="p-2.5 text-slate-300">{r.channel_name || '-'}</td>
                      <td className="p-2.5"><StatusBadge status={r.import_status} /></td>
                      <td className="p-2.5"><AckBadge status={r.ack_status} /></td>
                      <td className="p-2.5 text-slate-400">{r.arrival_date} → {r.departure_date}</td>
                      <td className="p-2.5 text-slate-300">{r.total_amount} {r.currency}</td>
                      <td className="p-2.5 text-right">
                        <button data-testid={`view-${r.id?.slice(0,8)}`} onClick={() => handleViewDetail(r.id)} className="text-blue-400 hover:text-blue-300 p-1">
                          <Eye className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                  {reservations.length === 0 && (
                    <tr><td colSpan={7} className="text-center py-8 text-slate-500">No reservations found</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {/* ─── REVIEW QUEUE ─────────────────────────────────────── */}
      {activeSection === 'review' && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-medium text-slate-300">
              Manual Review Queue ({reviewQueue.length})
            </h3>
          </div>

          {reviewQueue.length === 0 ? (
            <Card className="bg-slate-800/40 border-slate-700/50">
              <CardContent className="py-8 text-center text-xs text-slate-500">
                <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-400/50" />
                No items pending review
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-2">
              {reviewQueue.map(r => (
                <Card key={r.id} data-testid={`review-${r.id?.slice(0,8)}`} className="bg-slate-800/40 border-slate-700/50">
                  <CardContent className="p-3">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1.5">
                          <StatusBadge status={r.import_status} />
                          {r.review_reason_code && (
                            <Badge className="bg-orange-500/10 text-orange-400 border-orange-500/30 border text-[10px]">
                              {r.review_reason_code.replace(/_/g, ' ')}
                            </Badge>
                          )}
                          {r.is_cancellation && <Badge className="bg-slate-500/15 text-slate-300 border text-[10px]">Cancellation</Badge>}
                        </div>
                        <p className="text-xs text-slate-200">{r.guest_name || 'Unknown Guest'}</p>
                        <p className="text-[10px] text-slate-400 mt-0.5">
                          {r.arrival_date} → {r.departure_date} | {r.channel_name} | {r.total_amount} {r.currency}
                        </p>
                        {r.review_reason && <p className="text-[10px] text-orange-300 mt-1">{r.review_reason}</p>}
                        {r.conflict_reason && <p className="text-[10px] text-red-300 mt-1">{r.conflict_reason}</p>}
                        {r.suggested_action && <p className="text-[10px] text-amber-300 mt-0.5">Suggested: {r.suggested_action}</p>}
                      </div>
                      <div className="flex gap-1.5 ml-3">
                        <Button
                          data-testid={`reprocess-review-${r.id?.slice(0,8)}`}
                          size="sm"
                          className="bg-emerald-600 hover:bg-emerald-700 text-white text-[10px] h-7 px-2"
                          onClick={() => handleReprocess(r.id)}
                          disabled={actionLoading === r.id}
                        >
                          {actionLoading === r.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <><RotateCcw className="w-3 h-3 mr-1" />Reprocess</>}
                        </Button>
                        <Button
                          data-testid={`dismiss-review-${r.id?.slice(0,8)}`}
                          size="sm"
                          variant="outline"
                          className="border-slate-600 text-slate-300 text-[10px] h-7 px-2"
                          onClick={() => handleDismiss(r.id)}
                          disabled={actionLoading === r.id}
                        >
                          <Ban className="w-3 h-3 mr-1" />Dismiss
                        </Button>
                        <button onClick={() => handleViewDetail(r.id)} className="text-blue-400 hover:text-blue-300 p-1.5">
                          <Eye className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ─── BATCHES ──────────────────────────────────────────── */}
      {activeSection === 'batches' && (
        <div className="space-y-3">
          <h3 className="text-xs font-medium text-slate-300">Import Batches ({batches.length})</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
            {batches.map(b => (
              <BatchCard key={b.id} batch={b} onExpand={() => {}} />
            ))}
            {batches.length === 0 && (
              <p className="text-xs text-slate-500 col-span-3 text-center py-8">No import batches yet</p>
            )}
          </div>
        </div>
      )}

      {/* ─── AUDIT TRAIL ──────────────────────────────────────── */}
      {activeSection === 'audit' && (
        <Card className="bg-slate-800/40 border-slate-700/50">
          <CardContent className="p-4">
            <h3 className="text-xs font-medium text-slate-300 mb-3">Import Audit Trail</h3>
            <AuditTimeline logs={auditLogs} />
          </CardContent>
        </Card>
      )}

      {/* Reservation Detail Dialog */}
      {selectedRes && (
        <ReservationDetailDialog
          reservation={selectedRes}
          onClose={() => setSelectedRes(null)}
          onReprocess={handleReprocess}
          onDismiss={handleDismiss}
        />
      )}
    </div>
  );
};

export default ReservationsTab;
