import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Home, Search } from 'lucide-react';
import { toast } from 'sonner';

const RoomAssignment = ({ booking }) => {
  const [availableRooms, setAvailableRooms] = useState([]);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);

  const loadAvailableRooms = async () => {
    if (!booking) return;
    
    setLoading(true);
    try {
      const response = await axios.get('/frontdesk/available-rooms', {
        params: {
          check_in: booking.check_in,
          check_out: booking.check_out,
          room_type: booking.room_type
        }
      });
      setAvailableRooms(response.data.rooms || []);
    } catch (error) {
      toast.error('✗ Odalar yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  const handleAssignRoom = async (roomId, roomNumber) => {
    try {
      await axios.post('/frontdesk/assign-room', {
        booking_id: booking.id,
        room_id: roomId
      });
      toast.success(`✓ Oda ${roomNumber} atandı`);
      setDialogOpen(false);
    } catch (error) {
      toast.error('✗ Oda atanamadı');
    }
  };

  return (
    <>
      <Button
        size="sm"
        className="bg-blue-600 hover:bg-blue-700"
        onClick={() => {
          setDialogOpen(true);
          loadAvailableRooms();
        }}
      >
        <Home className="w-4 h-4 mr-1" />
        Oda Ata
      </Button>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-md max-h-[70vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Müsait Odalar</DialogTitle>
          </DialogHeader>
          
          {loading ? (
            <div className="text-center py-8">Yükleniyor...</div>
          ) : (
            <div className="space-y-2">
              {availableRooms.length === 0 ? (
                <p className="text-center text-gray-500 py-8">Müsait oda yok</p>
              ) : (
                availableRooms.map((room) => (
                  <div
                    key={room.id}
                    className="p-3 border rounded-lg hover:bg-gray-50 cursor-pointer"
                    onClick={() => handleAssignRoom(room.id, room.room_number)}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="font-bold">Oda {room.room_number}</div>
                        <div className="text-sm text-gray-600">{room.room_type}</div>
                        <div className="text-xs text-gray-500">
                          {room.bed_type} • Max {room.max_occupancy} kişi
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="font-bold text-green-600">₺{room.base_rate}</div>
                        <div className="text-xs text-gray-500">/ gece</div>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
};

export default RoomAssignment;
