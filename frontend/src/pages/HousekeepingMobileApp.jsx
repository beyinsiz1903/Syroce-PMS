import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { CheckCircle, Clock, Camera, MessageSquare, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const HousekeepingMobileApp = ({ user }) => {
  const { t } = useTranslation();
  const [rooms, setRooms] = useState([]);
  const [selectedRoom, setSelectedRoom] = useState(null);
  const [checklistItems, setChecklistItems] = useState([]);
  const [filter, setFilter] = useState('dirty'); // dirty, clean, inspected
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadRooms();
  }, [filter]);

  const loadRooms = async () => {
    try {
      const response = await axios.get(`/housekeeping/rooms?status=${filter}`);
      setRooms(response.data.rooms || []);
    } catch (error) {
      console.error('Failed to load rooms:', error);
    }
  };

  const handleStartCleaning = async (room) => {
    try {
      await axios.post(`/housekeeping/rooms/${room.id}/start`);
      setSelectedRoom(room);
      const checklistRes = await axios.get('/housekeeping/checklist');
      setChecklistItems(checklistRes.data.items || []);
      toast.success(`Started cleaning Room ${room.room_number}`);
    } catch (error) {
      toast.error('Temizlik başlatılamadı');
    }
  };

  const handleCompleteTask = async (roomId, itemId) => {
    const updatedChecklist = checklistItems.map(item =>
      item.id === itemId ? { ...item, completed: !item.completed } : item
    );
    setChecklistItems(updatedChecklist);
  };

  const handleFinishCleaning = async () => {
    if (!selectedRoom) return;

    setLoading(true);
    try {
      // Update room status to 'inspected' via quick update endpoint
      await axios.put(`/housekeeping/room/${selectedRoom.id}/status?new_status=inspected`);
      
      // Complete the cleaning task
      await axios.post(`/housekeeping/rooms/${selectedRoom.id}/complete`, {
        checklist: checklistItems,
        cleaned_by: user?.id,
        cleaned_at: new Date().toISOString()
      });

      toast.success(`✅ Room ${selectedRoom.room_number} cleaned & marked as inspected!`);
      setSelectedRoom(null);
      setChecklistItems([]);
      loadRooms();
    } catch (error) {
      toast.error('Temizlik tamamlanamadı');
    } finally {
      setLoading(false);
    }
  };

  const handleQuickStatusUpdate = async (roomId, roomNumber, newStatus) => {
    try {
      await axios.put(`/housekeeping/room/${roomId}/status?new_status=${newStatus}`);
      toast.success(`Room ${roomNumber} status updated to ${newStatus}!`);
      loadRooms();
    } catch (error) {
      toast.error('Oda durumu güncellenemedi');
    }
  };

  const getRoomStatusBadge = (status) => {
    const colors = {
      dirty: 'bg-red-100 text-red-700',
      clean: 'bg-green-100 text-green-700',
      inspected: 'bg-blue-100 text-blue-700',
      occupied: 'bg-yellow-100 text-yellow-700'
    };
    return colors[status] || 'bg-gray-100 text-gray-700';
  };

  if (selectedRoom) {
    return (
      <div className="max-w-md mx-auto bg-gray-50 min-h-screen">
        {/* Header */}
        <div className="bg-blue-600 text-white p-4 sticky top-0 z-10">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold">Room {selectedRoom.room_number}</h1>
              <p className="text-sm text-blue-100">{selectedRoom.room_type}</p>
            </div>
            <Badge className="bg-white text-blue-600">Cleaning</Badge>
          </div>
        </div>

        {/* Checklist */}
        <div className="p-4 space-y-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Cleaning Checklist</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {checklistItems.map((item) => (
                <div key={item.id} className="flex items-center gap-3 p-3 bg-gray-50 rounded">
                  <Checkbox
                    checked={item.completed}
                    onCheckedChange={() => handleCompleteTask(selectedRoom.id, item.id)}
                  />
                  <div className="flex-1">
                    <div className={item.completed ? 'line-through text-gray-500' : ''}>
                      {item.task}
                    </div>
                    {item.area && (
                      <div className="text-xs text-gray-500">{item.area}</div>
                    )}
                  </div>
                  {item.completed && <CheckCircle className="w-5 h-5 text-green-500" />}
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Actions */}
          <div className="grid grid-cols-2 gap-3">
            <Button variant="outline" onClick={() => {
              setSelectedRoom(null);
              setChecklistItems([]);
            }}>
              Cancel
            </Button>
            <Button
              onClick={handleFinishCleaning}
              disabled={loading || !checklistItems.every(item => item.completed)}
              className="bg-green-600 hover:bg-green-700"
            >
              Finish Cleaning
            </Button>
          </div>

          {/* Quick Actions */}
          <div className="grid grid-cols-2 gap-3">
            <Button variant="outline" className="w-full">
              <Camera className="w-4 h-4 mr-2" />
              Take Photo
            </Button>
            <Button variant="outline" className="w-full">
              <MessageSquare className="w-4 h-4 mr-2" />
              Report Issue
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto bg-gray-50 min-h-screen">
      {/* Header */}
      <div className="bg-blue-600 text-white p-4 sticky top-0 z-10">
        <h1 className="text-xl font-bold">Housekeeping</h1>
        <p className="text-sm text-blue-100">{user?.name || 'Staff Member'}</p>
      </div>

      {/* Filter Tabs */}
      <div className="bg-white border-b p-2 sticky top-16 z-10">
        <div className="flex gap-2">
          <button
            onClick={() => setFilter('dirty')}
            className={`px-4 py-2 rounded-full text-sm font-semibold ${
              filter === 'dirty' ? 'bg-red-600 text-white' : 'bg-gray-100 text-gray-600'
            }`}
          >
            To Clean ({rooms.filter(r => r.hk_status === 'dirty').length})
          </button>
          <button
            onClick={() => setFilter('clean')}
            className={`px-4 py-2 rounded-full text-sm font-semibold ${
              filter === 'clean' ? 'bg-green-600 text-white' : 'bg-gray-100 text-gray-600'
            }`}
          >
            Cleaned
          </button>
          <button
            onClick={() => setFilter('inspected')}
            className={`px-4 py-2 rounded-full text-sm font-semibold ${
              filter === 'inspected' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600'
            }`}
          >
            Inspected
          </button>
        </div>
      </div>

      {/* Rooms List */}
      <div className="p-4 space-y-3">
        {rooms.map((room) => (
          <Card key={room.id} className="hover:shadow-md transition">
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h3 className="text-2xl font-bold">Room {room.room_number}</h3>
                  <p className="text-sm text-gray-600">{room.room_type} - Floor {room.floor}</p>
                </div>
                <Badge className={getRoomStatusBadge(room.hk_status)}>
                  {room.hk_status}
                </Badge>
              </div>

              {room.priority === 'urgent' && (
                <div className="bg-red-50 text-red-700 text-sm p-2 rounded mb-3">
                  ⚡ Priority: Guest checking in soon
                </div>
              )}

              {room.notes && (
                <div className="bg-yellow-50 text-yellow-800 text-sm p-2 rounded mb-3">
                  📝 {room.notes}
                </div>
              )}

              <div className="flex gap-2">
                {room.hk_status === 'dirty' && (
                  <>
                    <Button
                      size="sm"
                      onClick={() => handleStartCleaning(room)}
                      className="flex-1 bg-blue-600 hover:bg-blue-700"
                    >
                      Start Cleaning
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleQuickStatusUpdate(room.id, room.room_number, 'cleaning')}
                      className="px-3"
                      title="Mark as cleaning without checklist"
                    >
                      ⚡
                    </Button>
                  </>
                )}
                {room.hk_status === 'cleaning' && (
                  <Button
                    size="sm"
                    onClick={() => handleQuickStatusUpdate(room.id, room.room_number, 'inspected')}
                    className="flex-1 bg-green-600 hover:bg-green-700"
                  >
                    ✓ Mark as Clean
                  </Button>
                )}
                {room.hk_status === 'inspected' && (
                  <Button
                    size="sm"
                    onClick={() => handleQuickStatusUpdate(room.id, room.room_number, 'available')}
                    className="flex-1 bg-green-600 hover:bg-green-700"
                  >
                    ✓ Mark as Ready
                  </Button>
                )}
              </div>

              {room.last_cleaned_at && (
                <div className="text-xs text-gray-500 mt-2">
                  Last cleaned: {new Date(room.last_cleaned_at).toLocaleString()}
                </div>
              )}
            </CardContent>
          </Card>
        ))}

        {rooms.length === 0 && (
          <Card>
            <CardContent className="text-center py-12">
              <Sparkles className="w-16 h-16 mx-auto text-gray-400 mb-4" />
              <p className="text-gray-600">All rooms are {filter}!</p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
};

export default HousekeepingMobileApp;