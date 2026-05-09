import { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { confirmDialog } from '@/lib/dialogs';
import { formatCurrency } from '@/lib/currency';
import {
  MapPin, Car, Utensils, Ticket, Clock, Plus, CheckCircle,
  AlertCircle, Package, Key, Coffee, Bell, Search, RefreshCw,
  Pencil, Trash2, XCircle, ListChecks, Hourglass, PlayCircle,
  CheckCircle2, Wallet, Loader2, ConciergeBell,
} from 'lucide-react';

const TYPE_ICONS = {
  restaurant: Utensils, transfer: Car, tour: MapPin, ticket: Ticket,
  spa: Coffee, valet: Car, parcel: Package, deposit_box: Key,
  wakeup: Bell, other: AlertCircle,
};

const TYPE_KEYS = ['restaurant', 'transfer', 'tour', 'ticket', 'spa', 'valet', 'parcel', 'depositBox', 'wakeup', 'other'];
const TYPE_VALUES = ['restaurant', 'transfer', 'tour', 'ticket', 'spa', 'valet', 'parcel', 'deposit_box', 'wakeup', 'other'];

const STATUS_INTENT = {
  pending: 'warning',
  in_progress: 'info',
  completed: 'success',
  confirmed: 'success',
  cancelled: 'danger',
};

const STATUS_MAP = {
  pending: 'statusPending', in_progress: 'statusInProgress', completed: 'statusCompleted',
  confirmed: 'statusConfirmed', cancelled: 'statusCancelled',
};

const CURRENCY_OPTIONS = ['TRY', 'EUR', 'USD', 'GBP'];

const PAGE_SIZE = 50;
const POLL_INTERVAL_MS = 60_000;

const EMPTY_FORM = {
  type: '', room_number: '', guest_name: '', details: '',
  date: '', time: '', pax: '1', notes: '', priority: 'normal',
  amount: '', currency: 'TRY', charge_to_folio: false,
  booking_id: '', folio_id: '',
};

const formatDateTime = (date, time) => {
  if (!date && !time) return '—';
  if (!date) return time;
  try {
    const isoLike = time ? `${date}T${time}` : date;
    const d = new Date(isoLike);
    if (Number.isNaN(d.getTime())) return time ? `${date} ${time}` : date;
    return d.toLocaleString('tr-TR', {
      day: '2-digit', month: 'short', year: 'numeric',
      ...(time ? { hour: '2-digit', minute: '2-digit' } : {}),
    });
  } catch {
    return time ? `${date} ${time}` : date;
  }
};

const errMsg = (err, fallback) => err?.response?.data?.detail || err?.message || fallback;

const ConciergeDesk = () => {
  const { t } = useTranslation();
  const tc = useCallback((k, opts) => t(`pmsComponents.concierge.${k}`, opts), [t]);

  const [requests, setRequests] = useState([]);
  const [counts, setCounts] = useState({ total: 0, pending: 0, in_progress: 0, completed: 0, cancelled: 0 });
  const [totalForFilter, setTotalForFilter] = useState(0);
  const [showNew, setShowNew] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [activeType, setActiveType] = useState('all');
  const [activeStatus, setActiveStatus] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [page, setPage] = useState(0);
  const [form, setForm] = useState(EMPTY_FORM);
  const [roomLookupBusy, setRoomLookupBusy] = useState(false);
  const [roomLookupHint, setRoomLookupHint] = useState(null);
  const lookupTimerRef = useRef(null);

  const loadRequests = useCallback(async ({ append = false, silent = false } = {}) => {
    if (!silent) {
      if (append) setLoading(true); else setRefreshing(true);
    }
    try {
      const params = { skip: append ? page * PAGE_SIZE : 0, limit: PAGE_SIZE };
      if (activeStatus !== 'all') params.status = activeStatus;
      const res = await axios.get('/concierge/requests', { params });
      const next = res.data.requests || [];
      setRequests(prev => append ? [...prev, ...next] : next);
      setCounts(res.data.counts || { total: 0, pending: 0, in_progress: 0, completed: 0, cancelled: 0 });
      setTotalForFilter(res.data.total || 0);
      if (!append) setPage(0);
    } catch (err) {
      toast.error(errMsg(err, tc('loadError')));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [activeStatus, page, tc]);

  useEffect(() => {
    loadRequests();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeStatus]);

  // Auto-refresh every minute (silent — preserves user state)
  useEffect(() => {
    const id = setInterval(() => { loadRequests({ silent: true }); }, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [loadRequests]);

  const lookupRoom = useCallback(async (roomNo) => {
    const room = (roomNo || '').trim();
    if (!room) {
      setRoomLookupHint(null);
      return;
    }
    setRoomLookupBusy(true);
    try {
      const res = await axios.get(`/concierge/active-room/${encodeURIComponent(room)}`);
      if (res.data?.found) {
        setForm(prev => ({
          ...prev,
          guest_name: prev.guest_name?.trim() ? prev.guest_name : (res.data.guest_name || ''),
          booking_id: res.data.booking_id || '',
          folio_id: res.data.folio_id || '',
        }));
        setRoomLookupHint({ ok: true, name: res.data.guest_name || '—', folio: !!res.data.folio_id });
      } else {
        setRoomLookupHint({ ok: false });
        setForm(prev => ({ ...prev, booking_id: '', folio_id: '' }));
      }
    } catch {
      setRoomLookupHint(null);
    } finally {
      setRoomLookupBusy(false);
    }
  }, []);

  const onRoomChange = (val) => {
    setForm(prev => ({ ...prev, room_number: val }));
    if (lookupTimerRef.current) clearTimeout(lookupTimerRef.current);
    lookupTimerRef.current = setTimeout(() => lookupRoom(val), 500);
  };

  const validate = () => {
    if (!form.type) { toast.error(tc('validationType')); return false; }
    if (!form.room_number?.trim()) { toast.error(tc('validationRoom')); return false; }
    const amt = Number(form.amount || 0);
    if (Number.isNaN(amt) || amt < 0) { toast.error(tc('validationAmount')); return false; }
    return true;
  };

  const buildPayload = () => ({
    type: form.type,
    room_number: form.room_number.trim(),
    guest_name: form.guest_name.trim(),
    details: form.details.trim(),
    date: form.date,
    time: form.time,
    pax: parseInt(form.pax, 10) || 1,
    notes: form.notes.trim(),
    priority: form.priority,
    amount: Number(form.amount || 0),
    currency: form.currency || 'TRY',
    charge_to_folio: !!form.charge_to_folio,
    booking_id: form.booking_id || '',
    folio_id: form.folio_id || '',
  });

  const createRequest = async () => {
    if (!validate()) return;
    setSubmitting(true);
    try {
      const res = await axios.post('/concierge/requests', buildPayload());
      setRequests(prev => [res.data, ...prev]);
      toast.success(tc('requestCreated'));
      setForm(EMPTY_FORM);
      setRoomLookupHint(null);
      setShowNew(false);
      loadRequests({ silent: true });
    } catch (err) {
      toast.error(errMsg(err, tc('createError')));
    } finally {
      setSubmitting(false);
    }
  };

  const startEdit = (req) => {
    setEditingId(req.id);
    setForm({
      type: req.type || '',
      room_number: req.room_number || '',
      guest_name: req.guest_name || '',
      details: req.details || '',
      date: req.date || '',
      time: req.time || '',
      pax: String(req.pax ?? 1),
      notes: req.notes || '',
      priority: req.priority || 'normal',
      amount: req.amount ? String(req.amount) : '',
      currency: req.currency || 'TRY',
      charge_to_folio: !!req.charge_to_folio,
      booking_id: req.booking_id || '',
      folio_id: req.folio_id || '',
    });
    setRoomLookupHint(null);
    setShowNew(true);
  };

  const saveEdit = async () => {
    if (!validate()) return;
    setSubmitting(true);
    try {
      const res = await axios.patch(`/concierge/requests/${editingId}`, buildPayload());
      setRequests(prev => prev.map(r => r.id === editingId ? { ...r, ...res.data } : r));
      toast.success(tc('requestUpdated'));
      setForm(EMPTY_FORM);
      setEditingId(null);
      setRoomLookupHint(null);
      setShowNew(false);
      loadRequests({ silent: true });
    } catch (err) {
      toast.error(errMsg(err, tc('createError')));
    } finally {
      setSubmitting(false);
    }
  };

  const updateStatus = async (id, status, confirmKey = null) => {
    if (confirmKey) {
      const ok = await confirmDialog({ message: tc(confirmKey) });
      if (!ok) return;
    }
    setBusyId(id);
    try {
      const res = await axios.patch(`/concierge/requests/${id}`, { status });
      setRequests(prev => prev.map(r => r.id === id ? { ...r, ...res.data } : r));
      loadRequests({ silent: true });
    } catch (err) {
      toast.error(errMsg(err, tc('statusUpdateError')));
    } finally {
      setBusyId(null);
    }
  };

  const deleteRequest = async (id) => {
    const ok = await confirmDialog({ message: tc('deleteConfirm') });
    if (!ok) return;
    setBusyId(id);
    try {
      await axios.delete(`/concierge/requests/${id}`);
      setRequests(prev => prev.filter(r => r.id !== id));
      toast.success(tc('requestDeleted'));
      loadRequests({ silent: true });
    } catch (err) {
      toast.error(errMsg(err, tc('deleteError')));
    } finally {
      setBusyId(null);
    }
  };

  const closeDialog = () => {
    setShowNew(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
    setRoomLookupHint(null);
  };

  const filtered = requests.filter(r => {
    if (activeType !== 'all' && r.type !== activeType) return false;
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      const inGuest = r.guest_name?.toLowerCase().includes(q);
      const inRoom = String(r.room_number || '').includes(searchTerm);
      if (!inGuest && !inRoom) return false;
    }
    return true;
  });

  const getTypeLabel = (value) => {
    const idx = TYPE_VALUES.indexOf(value);
    return idx >= 0 ? tc(TYPE_KEYS[idx]) : value;
  };

  const handleLoadMore = () => {
    setPage(p => p + 1);
    loadRequests({ append: true });
  };

  const hasMore = requests.length < totalForFilter;

  return (
    <div className="space-y-4">
      {/* Header (hub child — icon box pattern, no PageHeader) */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center">
            <ConciergeBell className="w-5 h-5 text-slate-700" />
          </div>
          <div>
            <h2 className="text-xl font-semibold text-slate-900">{tc('title')}</h2>
            <p className="text-xs text-slate-500">{tc('subtitle')}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => loadRequests()} disabled={refreshing}>
            <RefreshCw className={`w-4 h-4 mr-1.5 ${refreshing ? 'animate-spin' : ''}`} />
            {tc('refresh')}
          </Button>
          <Button onClick={() => { setEditingId(null); setForm(EMPTY_FORM); setRoomLookupHint(null); setShowNew(true); }}>
            <Plus className="w-4 h-4 mr-1" /> {tc('newRequest')}
          </Button>
        </div>
      </div>

      {/* KPI cards (clickable status filter) */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard
          icon={ListChecks} label={tc('total')} value={counts.total}
          intent="info" active={activeStatus === 'all'}
          onClick={() => setActiveStatus('all')}
        />
        <KpiCard
          icon={Hourglass} label={tc('pending')} value={counts.pending}
          intent="warning" active={activeStatus === 'pending'}
          onClick={() => setActiveStatus('pending')}
        />
        <KpiCard
          icon={PlayCircle} label={tc('inProgress')} value={counts.in_progress}
          intent="info" active={activeStatus === 'in_progress'}
          onClick={() => setActiveStatus('in_progress')}
        />
        <KpiCard
          icon={CheckCircle2} label={tc('completed')} value={counts.completed}
          intent="success" active={activeStatus === 'completed'}
          onClick={() => setActiveStatus('completed')}
        />
      </div>

      {/* Type filter chips */}
      <div className="flex gap-2 flex-wrap">
        <Button size="sm" variant={activeType === 'all' ? 'default' : 'outline'} onClick={() => setActiveType('all')}>
          {tc('all')}
        </Button>
        {TYPE_VALUES.map((val, i) => {
          const Icon = TYPE_ICONS[val] || AlertCircle;
          return (
            <Button key={val} size="sm" variant={activeType === val ? 'default' : 'outline'} onClick={() => setActiveType(val)}>
              <Icon className="h-3 w-3 mr-1" />{tc(TYPE_KEYS[i])}
            </Button>
          );
        })}
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
        <Input className="pl-9" placeholder={tc('searchPlaceholder')} value={searchTerm} onChange={e => setSearchTerm(e.target.value)} />
      </div>

      {/* List */}
      <div className="space-y-2">
        {loading && requests.length === 0 && (
          <div className="text-center text-slate-500 py-6">
            <Loader2 className="w-5 h-5 animate-spin inline mr-2" />{tc('loading')}
          </div>
        )}
        {!loading && filtered.length === 0 && (
          <Card>
            <CardContent className="p-8 text-center space-y-3">
              <ConciergeBell className="w-10 h-10 text-slate-300 mx-auto" />
              <p className="text-slate-500">{tc('emptyHint')}</p>
              <Button onClick={() => { setEditingId(null); setForm(EMPTY_FORM); setShowNew(true); }}>
                <Plus className="w-4 h-4 mr-1" /> {tc('createCta')}
              </Button>
            </CardContent>
          </Card>
        )}
        {filtered.map(req => {
          const Icon = TYPE_ICONS[req.type] || AlertCircle;
          const intent = STATUS_INTENT[req.status] || 'neutral';
          const isBusy = busyId === req.id;
          return (
            <Card key={req.id}>
              <CardContent className="p-3">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="flex items-start gap-3 min-w-0 flex-1">
                    <div className="p-2 rounded-lg bg-slate-100 shrink-0">
                      <Icon className="h-4 w-4 text-slate-700" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-slate-900">{req.guest_name || '—'}</span>
                        <StatusBadge intent="neutral">{tc('room')} {req.room_number || '—'}</StatusBadge>
                        {req.priority === 'vip' && <StatusBadge intent="info">{tc('vip')}</StatusBadge>}
                        {req.priority === 'high' && <StatusBadge intent="danger">{tc('highPriority')}</StatusBadge>}
                        {req.amount > 0 && (
                          <StatusBadge intent={req.folio_charge_id ? 'success' : 'warning'} icon={Wallet}>
                            {formatCurrency(req.amount, req.currency || 'TRY')}
                            {req.folio_charge_id ? ' · ' + tc('folioCharged') : (req.charge_to_folio ? ' · ' + tc('folioPending') : '')}
                          </StatusBadge>
                        )}
                      </div>
                      <p className="text-sm text-slate-600 mt-0.5">
                        {getTypeLabel(req.type)}
                        {req.details ? `: ${req.details}` : ''}
                      </p>
                      <div className="flex items-center gap-2 text-xs text-slate-500 mt-1 flex-wrap">
                        <Clock className="h-3 w-3" />{formatDateTime(req.date, req.time)}
                        {req.pax > 1 && <span>• {req.pax} {tc('persons')}</span>}
                        {req.notes && <span className="text-slate-400">• {req.notes}</span>}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <StatusBadge intent={intent}>{tc(STATUS_MAP[req.status] || 'statusPending')}</StatusBadge>
                    {req.status === 'pending' && (
                      <Button size="sm" variant="outline" disabled={isBusy} onClick={() => updateStatus(req.id, 'in_progress')}>
                        {tc('startBtn')}
                      </Button>
                    )}
                    {(req.status === 'pending' || req.status === 'in_progress') && (
                      <>
                        <Button size="sm" disabled={isBusy} onClick={() => updateStatus(req.id, 'completed')}>
                          <CheckCircle className="h-3 w-3 mr-1" />{tc('doneBtn')}
                        </Button>
                        <Button size="sm" variant="outline"
                          className="text-rose-600 border-rose-200 hover:bg-rose-50 hover:text-rose-700"
                          disabled={isBusy}
                          onClick={() => updateStatus(req.id, 'cancelled', 'cancelConfirm')}>
                          <XCircle className="h-3 w-3 mr-1" />{tc('cancelBtn')}
                        </Button>
                      </>
                    )}
                    <Button size="sm" variant="ghost" disabled={isBusy} onClick={() => startEdit(req)} aria-label={tc('editBtn')}>
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button size="sm" variant="ghost"
                      className="text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                      disabled={isBusy} onClick={() => deleteRequest(req.id)} aria-label={tc('deleteBtn')}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}

        {filtered.length > 0 && (
          <div className="flex items-center justify-between text-xs text-slate-500 pt-1">
            <span>{tc('ofTotal', { shown: requests.length, total: totalForFilter })}</span>
            {hasMore && (
              <Button size="sm" variant="outline" onClick={handleLoadMore} disabled={loading}>
                {loading ? tc('loading') : tc('showMore')}
              </Button>
            )}
          </div>
        )}
      </div>

      {/* Create/Edit dialog */}
      <Dialog open={showNew} onOpenChange={(open) => { if (!open) closeDialog(); }}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingId ? tc('editBtn') : tc('newRequestTitle')}</DialogTitle>
          </DialogHeader>

          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>{tc('requestType')} *</Label>
                <Select value={form.type} onValueChange={v => setForm(p => ({ ...p, type: v }))}>
                  <SelectTrigger><SelectValue placeholder={tc('typePlaceholder')} /></SelectTrigger>
                  <SelectContent>
                    {TYPE_VALUES.map((val, i) => <SelectItem key={val} value={val}>{tc(TYPE_KEYS[i])}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>{tc('priorityLabel')}</Label>
                <Select value={form.priority} onValueChange={v => setForm(p => ({ ...p, priority: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="normal">{tc('normal')}</SelectItem>
                    <SelectItem value="high">{tc('high')}</SelectItem>
                    <SelectItem value="vip">{tc('vip')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>{tc('roomNo')} *</Label>
                <Input value={form.room_number}
                  onChange={e => onRoomChange(e.target.value)}
                  onBlur={() => lookupRoom(form.room_number)}
                  inputMode="numeric"
                  placeholder="101" />
                {roomLookupBusy && <p className="text-xs text-slate-500 mt-1"><Loader2 className="w-3 h-3 animate-spin inline mr-1" />{tc('lookingUp')}</p>}
                {!roomLookupBusy && roomLookupHint?.ok && (
                  <p className="text-xs text-emerald-700 mt-1">
                    <CheckCircle2 className="w-3 h-3 inline mr-1" />
                    {tc('roomMatched', { name: roomLookupHint.name })}
                    {roomLookupHint.folio
                      ? <span className="ml-1 text-slate-500">· {tc('linkedFolio')}</span>
                      : <span className="ml-1 text-amber-700">· {tc('noOpenFolio')}</span>}
                  </p>
                )}
                {!roomLookupBusy && roomLookupHint && !roomLookupHint.ok && (
                  <p className="text-xs text-amber-700 mt-1">
                    <AlertCircle className="w-3 h-3 inline mr-1" />{tc('roomNotFound')}
                  </p>
                )}
              </div>
              <div>
                <Label>{tc('guestName')}</Label>
                <Input value={form.guest_name}
                  onChange={e => setForm(p => ({ ...p, guest_name: e.target.value }))} />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label>{tc('dateLabel')}</Label>
                <Input type="date" value={form.date}
                  onChange={e => setForm(p => ({ ...p, date: e.target.value }))} />
              </div>
              <div>
                <Label>{tc('timeLabel')}</Label>
                <Input type="time" value={form.time}
                  onChange={e => setForm(p => ({ ...p, time: e.target.value }))} />
              </div>
              <div>
                <Label>{tc('paxLabel')}</Label>
                <Input type="number" min="1" step="1" value={form.pax}
                  onChange={e => setForm(p => ({ ...p, pax: e.target.value.replace(/\D/g, '') }))} />
              </div>
            </div>

            {/* Folio integration */}
            <div className="rounded-lg border border-slate-200 p-3 space-y-2">
              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <Label>{tc('amountLabel')}</Label>
                  <Input type="number" min="0" step="0.01" value={form.amount}
                    onChange={e => setForm(p => ({ ...p, amount: e.target.value }))}
                    placeholder="0.00" inputMode="decimal" />
                </div>
                <div>
                  <Label>{tc('currencyLabel')}</Label>
                  <Select value={form.currency} onValueChange={v => setForm(p => ({ ...p, currency: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {CURRENCY_OPTIONS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <label className="flex items-start gap-2 text-sm cursor-pointer select-none">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-500"
                  checked={form.charge_to_folio}
                  disabled={!form.folio_id}
                  onChange={e => setForm(p => ({ ...p, charge_to_folio: e.target.checked }))}
                />
                <span>
                  <span className="font-medium text-slate-900">{tc('chargeToFolio')}</span>
                  <span className="block text-xs text-slate-500">{tc('chargeToFolioHint')}</span>
                  {!form.folio_id && form.room_number && (
                    <span className="block text-xs text-amber-700 mt-1">{tc('noOpenFolio')}</span>
                  )}
                </span>
              </label>
            </div>

            <div>
              <Label>{tc('detailsLabel')}</Label>
              <Textarea value={form.details}
                onChange={e => setForm(p => ({ ...p, details: e.target.value }))}
                placeholder={tc('detailsPlaceholder')} rows={2} />
            </div>
            <div>
              <Label>{tc('notesLabel')}</Label>
              <Input value={form.notes}
                onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
                placeholder={tc('notesPlaceholder')} />
            </div>

            <div className="flex gap-2 pt-1">
              <Button className="flex-1" onClick={editingId ? saveEdit : createRequest} disabled={submitting}>
                {submitting
                  ? (editingId ? tc('saving') : tc('creating'))
                  : (editingId ? tc('saveBtn') : tc('createRequest'))}
              </Button>
              <Button variant="ghost" onClick={closeDialog} disabled={submitting}>
                {tc('cancelBtn')}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ConciergeDesk;
