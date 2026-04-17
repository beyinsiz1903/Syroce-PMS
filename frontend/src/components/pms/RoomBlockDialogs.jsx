import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';

export const RoomBlockCreateDialog = ({ open, onClose, rooms, selectedRoom, setSelectedRoom, newRoomBlock, setNewRoomBlock, onSubmit, loading }) => {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Block Room</DialogTitle>
          <DialogDescription>Create an Out of Order, Out of Service, or Maintenance block</DialogDescription>
        </DialogHeader>
        <form onSubmit={(e) => { e.preventDefault(); onSubmit(); }} className="space-y-4">
          <div>
            <Label>{t('common.room')} *</Label>
            <Select value={selectedRoom?.id || ''} onValueChange={(v) => setSelectedRoom((rooms || []).find(r => r.id === v))}>
              <SelectTrigger><SelectValue placeholder="Select room" /></SelectTrigger>
              <SelectContent>{(rooms || []).map(r => <SelectItem key={r.id} value={r.id}>Room {r.room_number} ({r.room_type})</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label>Block Type *</Label>
            <Select value={newRoomBlock.type} onValueChange={(v) => setNewRoomBlock({...newRoomBlock, type: v})}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="out_of_order">Out of Order</SelectItem>
                <SelectItem value="out_of_service">Out of Service</SelectItem>
                <SelectItem value="maintenance">{t('maintenance.title')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Reason *</Label>
            <Input value={newRoomBlock.reason} onChange={(e) => setNewRoomBlock({...newRoomBlock, reason: e.target.value})} placeholder="e.g., Plumbing issue" maxLength={200} />
          </div>
          <div>
            <Label>Details</Label>
            <Textarea value={newRoomBlock.details} onChange={(e) => setNewRoomBlock({...newRoomBlock, details: e.target.value})} rows={3} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>{t('common.startDate')} *</Label><Input type="date" value={newRoomBlock.start_date} onChange={(e) => setNewRoomBlock({...newRoomBlock, start_date: e.target.value})} /></div>
            <div><Label>{t('common.endDate')}</Label><Input type="date" value={newRoomBlock.end_date} onChange={(e) => setNewRoomBlock({...newRoomBlock, end_date: e.target.value})} /></div>
          </div>
          <div className="flex items-center space-x-2">
            <input type="checkbox" id="allow_sell" checked={newRoomBlock.allow_sell} onChange={(e) => setNewRoomBlock({...newRoomBlock, allow_sell: e.target.checked})} className="h-4 w-4" />
            <Label htmlFor="allow_sell" className="cursor-pointer">Allow room to be sold during block</Label>
          </div>
          <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Olusturuluyor...' : t('common.create')}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export const RoomBlockViewDialog = ({ open, onClose, selectedRoom, roomBlocks, onCancelBlock }) => {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Room Blocks - Room {selectedRoom?.room_number}</DialogTitle>
          <DialogDescription>All blocks for this room</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 max-h-96 overflow-y-auto">
          {selectedRoom && roomBlocks.filter(b => b.room_id === selectedRoom.id).length === 0 && (
            <div className="text-center text-gray-400 py-8">No blocks for this room</div>
          )}
          {selectedRoom && (roomBlocks || []).filter(b => b.room_id === selectedRoom.id).map((block) => (
            <Card key={block.id} className={block.status === 'cancelled' ? 'bg-gray-50' : block.type === 'out_of_order' ? 'border-red-400' : block.type === 'out_of_service' ? 'border-orange-400' : 'border-yellow-400'}>
              <CardContent className="pt-4">
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`px-2 py-1 text-xs font-bold rounded ${block.type === 'out_of_order' ? 'bg-red-600 text-white' : block.type === 'out_of_service' ? 'bg-orange-500 text-white' : 'bg-yellow-600 text-white'}`}>
                        {block.type === 'out_of_order' ? 'OUT OF ORDER' : block.type === 'out_of_service' ? 'OUT OF SERVICE' : 'MAINTENANCE'}
                      </span>
                      <span className={`px-2 py-1 text-xs font-semibold rounded ${block.status === 'active' ? 'bg-green-100 text-green-700' : block.status === 'cancelled' ? 'bg-gray-200 text-gray-600' : 'bg-yellow-100 text-yellow-700'}`}>
                        {block.status}
                      </span>
                    </div>
                    <div className="text-sm font-medium text-gray-900 mb-1">{block.reason}</div>
                    {block.details && <div className="text-xs text-gray-600 mb-2">{block.details}</div>}
                    <div className="text-xs text-gray-500">{new Date(block.start_date).toLocaleDateString()} - {block.end_date ? new Date(block.end_date).toLocaleDateString() : 'Open-ended'}</div>
                  </div>
                  {block.status === 'active' && (
                    <Button size="sm" variant="destructive" onClick={() => onCancelBlock(block.id)}>Cancel</Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
};
