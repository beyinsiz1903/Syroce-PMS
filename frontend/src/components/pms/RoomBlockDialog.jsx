import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { AlertTriangle, Ban, Wrench } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const blockLabels = {
  out_of_order: 'Arızalı / OOO',
  out_of_service: 'Hizmet dışı / OOS',
  maintenance: 'Planlı bakım',
};

const idempotencyKey = (scope) => globalThis.crypto?.randomUUID?.() || `${scope}-${Date.now()}-${Math.random()}`;
const nextDay = (date) => {
  const value = new Date(`${date}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() + 1);
  return value.toISOString().slice(0, 10);
};

export default function RoomBlockDialog({ open, onOpenChange, rooms = [], defaultRoomId = '', businessDate = '', onChanged }) {
  const today = useMemo(() => businessDate || new Date().toISOString().slice(0, 10), [businessDate]);
  const [roomId, setRoomId] = useState(defaultRoomId);
  const [type, setType] = useState('out_of_order');
  const [reason, setReason] = useState('');
  const [startDate, setStartDate] = useState(today);
  const [endDate, setEndDate] = useState(nextDay(today));
  const [activeBlocks, setActiveBlocks] = useState([]);
  const [saving, setSaving] = useState(false);

  const refreshBlocks = async () => {
    try {
      const response = await axios.get('/pms/room-blocks?status=active');
      setActiveBlocks(Array.isArray(response.data) ? response.data : response.data?.blocks || []);
    } catch {
      setActiveBlocks([]);
    }
  };

  useEffect(() => {
    if (!open) return;
    setRoomId(defaultRoomId || '');
    setStartDate(today);
    setEndDate(nextDay(today));
    setReason('');
    refreshBlocks();
  }, [open, defaultRoomId, today]);

  const selectedRoom = rooms.find((room) => room.id === roomId);
  const roomBlocks = activeBlocks.filter((block) => block.room_id === roomId);

  const createBlock = async (event) => {
    event.preventDefault();
    if (!roomId || !reason.trim() || !startDate || !endDate) {
      toast.error('Oda, neden ve başlangıç/bitiş tarihi zorunludur.');
      return;
    }
    if (endDate <= startDate) {
      toast.error('Bitiş tarihi başlangıçtan sonraki ilk satışa açılacak gün olmalıdır.');
      return;
    }
    setSaving(true);
    try {
      await axios.post('/pms/room-blocks', {
        room_id: roomId,
        type,
        reason: reason.trim(),
        start_date: startDate,
        end_date: endDate,
        allow_sell: false,
      }, { headers: { 'Idempotency-Key': idempotencyKey('room-block-create') } });
      toast.success(`Oda ${selectedRoom?.room_number || ''} satışa kapatıldı.`);
      await refreshBlocks();
      onChanged?.();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Oda bloklanamadı.');
    } finally {
      setSaving(false);
    }
  };

  const releaseBlock = async (block) => {
    setSaving(true);
    try {
      await axios.post(`/pms/room-blocks/${block.id}/cancel`, null, {
        params: { reason: 'Operatör tarafından blok kaldırıldı' },
        headers: { 'Idempotency-Key': idempotencyKey('room-block-release') },
      });
      toast.success('Oda bloğu kaldırıldı.');
      await refreshBlocks();
      onChanged?.();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Oda bloğu kaldırılamadı.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Wrench className="h-5 w-5 text-rose-600" /> Odayı satışa kapat</DialogTitle>
          <DialogDescription>Arıza, hizmet dışı veya planlı bakım için oda gecelerini bloke eder.</DialogDescription>
        </DialogHeader>
        <form onSubmit={createBlock} className="space-y-4">
          <div>
            <Label>Oda</Label>
            <Select value={roomId} onValueChange={setRoomId}>
              <SelectTrigger className="mt-1"><SelectValue placeholder="Oda seçin" /></SelectTrigger>
              <SelectContent>
                {rooms.map((room) => <SelectItem key={room.id} value={room.id}>{room.room_number} · {room.room_type}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Blok tipi</Label>
            <Select value={type} onValueChange={setType}>
              <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>{Object.entries(blockLabels).map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label>Neden</Label>
            <Input className="mt-1" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Örn. klima arızası" maxLength={200} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Başlangıç</Label><Input className="mt-1" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></div>
            <div><Label>Tekrar satışa açılma</Label><Input className="mt-1" type="date" value={endDate} min={nextDay(startDate)} onChange={(event) => setEndDate(event.target.value)} /></div>
          </div>
          <p className="flex gap-2 rounded-md bg-amber-50 p-2 text-xs text-amber-800"><AlertTriangle className="h-4 w-4 shrink-0" /> Oda başlangıçtan bu tarihe kadar satışa kapalıdır; seçilen tarihte yeniden satılabilir. Süre uzatılabilir.</p>
          <Button type="submit" className="w-full bg-rose-600 hover:bg-rose-700" disabled={saving}><Ban className="mr-1 h-4 w-4" /> {saving ? 'Kaydediliyor…' : 'Odayı Blokla'}</Button>
        </form>
        {roomBlocks.length > 0 && <div className="border-t pt-3 space-y-2">
          <p className="text-sm font-semibold">Açık bloklar</p>
          {roomBlocks.map((block) => <div key={block.id} className="flex items-center justify-between gap-2 rounded border p-2 text-xs"><span>{blockLabels[block.type] || block.type} · {block.start_date} – {block.end_date}<br />{block.reason}</span><Button type="button" size="sm" variant="outline" disabled={saving} onClick={() => releaseBlock(block)}>Kaldır</Button></div>)}
        </div>}
      </DialogContent>
    </Dialog>
  );
}
