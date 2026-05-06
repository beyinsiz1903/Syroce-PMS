import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  MapPin, Car, Utensils, Ticket, Clock, Plus, CheckCircle,
  AlertCircle, Package, Key, Coffee, Bell, Search
} from 'lucide-react';

const TYPE_ICONS = {
  restaurant: Utensils, transfer: Car, tour: MapPin, ticket: Ticket,
  spa: Coffee, valet: Car, parcel: Package, deposit_box: Key,
  wakeup: Bell, other: AlertCircle,
};

const TYPE_KEYS = ['restaurant', 'transfer', 'tour', 'ticket', 'spa', 'valet', 'parcel', 'depositBox', 'wakeup', 'other'];
const TYPE_VALUES = ['restaurant', 'transfer', 'tour', 'ticket', 'spa', 'valet', 'parcel', 'deposit_box', 'wakeup', 'other'];

const STATUS_COLORS = {
  pending: 'bg-yellow-100 text-yellow-800',
  in_progress: 'bg-blue-100 text-blue-800',
  completed: 'bg-green-100 text-green-800',
  confirmed: 'bg-emerald-100 text-emerald-800',
  cancelled: 'bg-red-100 text-red-800',
};

const STATUS_MAP = {
  pending: 'statusPending', in_progress: 'statusInProgress', completed: 'statusCompleted',
  confirmed: 'statusConfirmed', cancelled: 'statusCancelled',
};

const ConciergeDesk = () => {
  const { t } = useTranslation();
  const tc = (k) => t(`pmsComponents.concierge.${k}`);

  const [requests, setRequests] = useState([]);
  const [showNew, setShowNew] = useState(false);
  const [activeType, setActiveType] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(false);
  const [newReq, setNewReq] = useState({
    type: '', room_number: '', guest_name: '', details: '',
    date: '', time: '', pax: '', notes: '', priority: 'normal'
  });

  useEffect(() => { loadRequests(); }, []);

  const loadRequests = async () => {
    setLoading(true);
    try {
      const res = await axios.get('/concierge/requests');
      setRequests(res.data.requests || []);
    } catch {
      toast.error(tc('loadError'));
    } finally {
      setLoading(false);
    }
  };

  const createRequest = async () => {
    if (!newReq.type || !newReq.room_number) return;
    try {
      const res = await axios.post('/concierge/requests', newReq);
      setRequests(prev => [res.data, ...prev]);
      toast.success(tc('requestCreated'));
      setNewReq({ type: '', room_number: '', guest_name: '', details: '', date: '', time: '', pax: '', notes: '', priority: 'normal' });
      setShowNew(false);
    } catch {
      toast.error(tc('createError'));
    }
  };

  const updateStatus = async (id, status) => {
    try {
      await axios.patch(`/concierge/requests/${id}`, { status });
      setRequests(prev => prev.map(r => r.id === id ? { ...r, status } : r));
    } catch {
      toast.error(tc('statusUpdateError'));
    }
  };

  const filtered = requests.filter(r => {
    if (activeType !== 'all' && r.type !== activeType) return false;
    if (searchTerm && !r.guest_name?.toLowerCase().includes(searchTerm.toLowerCase()) && !r.room_number?.includes(searchTerm)) return false;
    return true;
  });

  const stats = {
    total: requests.length,
    pending: requests.filter(r => r.status === 'pending').length,
    in_progress: requests.filter(r => r.status === 'in_progress').length,
    completed: requests.filter(r => r.status === 'completed').length,
  };

  const getTypeLabel = (value) => {
    const idx = TYPE_VALUES.indexOf(value);
    return idx >= 0 ? tc(TYPE_KEYS[idx]) : value;
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <MapPin className="h-5 w-5" /> {tc('title')}
        </h2>
        <Button onClick={() => setShowNew(true)}><Plus className="h-4 w-4 mr-1" /> {tc('newRequest')}</Button>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <Card className="cursor-pointer" onClick={() => setActiveType('all')}>
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold">{stats.total}</div>
            <div className="text-xs text-muted-foreground">{tc('total')}</div>
          </CardContent>
        </Card>
        <Card className="cursor-pointer border-yellow-200">
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold text-yellow-600">{stats.pending}</div>
            <div className="text-xs text-muted-foreground">{tc('pending')}</div>
          </CardContent>
        </Card>
        <Card className="cursor-pointer border-blue-200">
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold text-blue-600">{stats.in_progress}</div>
            <div className="text-xs text-muted-foreground">{tc('inProgress')}</div>
          </CardContent>
        </Card>
        <Card className="cursor-pointer border-green-200">
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold text-green-600">{stats.completed}</div>
            <div className="text-xs text-muted-foreground">{tc('completed')}</div>
          </CardContent>
        </Card>
      </div>

      <div className="flex gap-2 flex-wrap">
        <Button size="sm" variant={activeType === 'all' ? 'default' : 'outline'} onClick={() => setActiveType('all')}>{tc('all')}</Button>
        {TYPE_VALUES.map((val, i) => {
          const Icon = TYPE_ICONS[val] || AlertCircle;
          return (
            <Button key={val} size="sm" variant={activeType === val ? 'default' : 'outline'} onClick={() => setActiveType(val)}>
              <Icon className="h-3 w-3 mr-1" />{tc(TYPE_KEYS[i])}
            </Button>
          );
        })}
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input className="pl-9" placeholder={tc('searchPlaceholder')} value={searchTerm} onChange={e => setSearchTerm(e.target.value)} />
      </div>

      <div className="space-y-2">
        {loading && <p className="text-center text-muted-foreground py-4">{tc('loading')}</p>}
        {!loading && filtered.length === 0 && <p className="text-center text-muted-foreground py-8">{tc('noRequests')}</p>}
        {filtered.map(req => {
          const Icon = TYPE_ICONS[req.type] || AlertCircle;
          return (
            <Card key={req.id}>
              <CardContent className="p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-muted"><Icon className="h-4 w-4" /></div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{req.guest_name}</span>
                        <Badge variant="outline">{tc('room')} {req.room_number}</Badge>
                        {req.priority === 'vip' && <Badge className="bg-indigo-100 text-indigo-800">{tc('vip')}</Badge>}
                        {req.priority === 'high' && <Badge className="bg-red-100 text-red-800">{tc('highPriority')}</Badge>}
                      </div>
                      <p className="text-sm text-muted-foreground">{getTypeLabel(req.type)}: {req.details}</p>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground mt-1">
                        <Clock className="h-3 w-3" />{req.date} {req.time}
                        {req.pax > 1 && <span>• {req.pax} {tc('persons')}</span>}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge className={STATUS_COLORS[req.status] || ''}>
                      {tc(STATUS_MAP[req.status] || 'statusPending')}
                    </Badge>
                    {req.status === 'pending' && (
                      <Button size="sm" variant="outline" onClick={() => updateStatus(req.id, 'in_progress')}>{tc('startBtn')}</Button>
                    )}
                    {(req.status === 'pending' || req.status === 'in_progress') && (
                      <Button size="sm" onClick={() => updateStatus(req.id, 'completed')}>
                        <CheckCircle className="h-3 w-3 mr-1" />{tc('doneBtn')}
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Dialog open={showNew} onOpenChange={setShowNew}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>{tc('newRequestTitle')}</DialogTitle></DialogHeader>

          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>{tc('requestType')}</Label>
                <Select value={newReq.type} onValueChange={v => setNewReq(p => ({ ...p, type: v }))}>
                  <SelectTrigger><SelectValue placeholder={tc('typePlaceholder')} /></SelectTrigger>
                  <SelectContent>{TYPE_VALUES.map((val, i) => <SelectItem key={val} value={val}>{tc(TYPE_KEYS[i])}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div>
                <Label>{tc('priorityLabel')}</Label>
                <Select value={newReq.priority} onValueChange={v => setNewReq(p => ({ ...p, priority: v }))}>
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
              <div><Label>{tc('roomNo')}</Label><Input value={newReq.room_number} onChange={e => setNewReq(p => ({ ...p, room_number: e.target.value }))} /></div>
              <div><Label>{tc('guestName')}</Label><Input value={newReq.guest_name} onChange={e => setNewReq(p => ({ ...p, guest_name: e.target.value }))} /></div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div><Label>{tc('dateLabel')}</Label><Input type="date" value={newReq.date} onChange={e => setNewReq(p => ({ ...p, date: e.target.value }))} /></div>
              <div><Label>{tc('timeLabel')}</Label><Input type="time" value={newReq.time} onChange={e => setNewReq(p => ({ ...p, time: e.target.value }))} /></div>
              <div><Label>{tc('paxLabel')}</Label><Input type="number" min="1" value={newReq.pax} onChange={e => setNewReq(p => ({ ...p, pax: e.target.value }))} /></div>
            </div>
            <div><Label>{tc('detailsLabel')}</Label><Textarea value={newReq.details} onChange={e => setNewReq(p => ({ ...p, details: e.target.value }))} placeholder={tc('detailsPlaceholder')} /></div>
            <div><Label>{tc('notesLabel')}</Label><Input value={newReq.notes} onChange={e => setNewReq(p => ({ ...p, notes: e.target.value }))} placeholder={tc('notesPlaceholder')} /></div>
            <Button className="w-full" onClick={createRequest}>{tc('createRequest')}</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ConciergeDesk;
