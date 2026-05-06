import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

const API_URL = import.meta.env.VITE_BACKEND_URL || '';

const EnhancedReservationCalendar = () => {
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [rooms, setRooms] = useState([]);
  const [adrData, setAdrData] = useState(null);
  const [aiPricing, setAiPricing] = useState(null);
  const [draggedBooking, setDraggedBooking] = useState(null);
  const [showRateOverride, setShowRateOverride] = useState(false);
  const [selectedBooking, setSelectedBooking] = useState(null);

  useEffect(() => {
    fetchRooms();
    fetchADR();
  }, [selectedDate]);

  const fetchRooms = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(`/rooms`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setRooms(response.data.rooms || []);
    } catch (error) {
      console.error('Error fetching rooms:', error);
    }
  };

  const fetchADR = async () => {
    try {
      const token = localStorage.getItem('token');
      const endDate = new Date(selectedDate);
      endDate.setDate(endDate.getDate() + 30);
      
      const response = await axios.get(
        `/reservations/adr-visibility?start_date=${selectedDate}&end_date=${endDate.toISOString().split('T')[0]}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setAdrData(response.data);
    } catch (error) {
      console.error('Error fetching ADR:', error);
    }
  };

  const fetchAIPricing = async () => {
    try {
      const token = localStorage.getItem('token');
      const endDate = new Date(selectedDate);
      endDate.setDate(endDate.getDate() + 30);
      
      const response = await axios.post(
        `/rms/ai-pricing/auto-publish-rates`,
        {
          start_date: selectedDate,
          end_date: endDate.toISOString().split('T')[0],
          strategy: 'revenue_optimization'
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setAiPricing(response.data);
      toast.success(`AI Fiyatlama: ${response.data.rates_published} fiyat yayınlandı`);
    } catch (error) {
      console.error('Error fetching AI pricing:', error);
    }
  };

  const handleRateOverride = async (bookingId, newRate, reason) => {
    try {
      const token = localStorage.getItem('token');
      // Bug CP fix — backend now expects query params (Query) not JSON body
      await axios.post(
        `/reservations/rate-override-panel`,
        null,
        {
          headers: { Authorization: `Bearer ${token}` },
          params: {
            booking_id: bookingId,
            new_rate: parseFloat(newRate),
            override_reason: reason,
          },
        }
      );
      toast.success('Fiyat geçersiz kılma başarılı');
      setShowRateOverride(false);
      fetchRooms();
    } catch (error) {
      console.error('Error overriding rate:', error);
      toast.error('Fiyat geçersiz kılınamadı');
    }
  };

  return (
    <div className="p-6 bg-white">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">Reservation Calendar</h1>
        <div className="flex gap-4">
          <button
            onClick={fetchAIPricing}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 flex items-center gap-2"
          >
            🤖 AI Price Suggestions
          </button>
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="px-4 py-2 border rounded-lg"
          />
        </div>
      </div>

      {/* ADR Summary */}
      {adrData && (
        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="bg-blue-50 p-4 rounded-lg">
            <div className="text-sm text-gray-600">Overall ADR</div>
            <div className="text-2xl font-bold text-blue-600">${adrData.overall_adr}</div>
          </div>
          <div className="bg-green-50 p-4 rounded-lg">
            <div className="text-sm text-gray-600">Total Revenue</div>
            <div className="text-2xl font-bold text-green-600">${adrData.total_room_revenue}</div>
          </div>
          <div className="bg-indigo-50 p-4 rounded-lg">
            <div className="text-sm text-gray-600">Room Nights</div>
            <div className="text-2xl font-bold text-indigo-600">{adrData.total_room_nights}</div>
          </div>
          <div className="bg-amber-50 p-4 rounded-lg">
            <div className="text-sm text-gray-600">Bookings</div>
            <div className="text-2xl font-bold text-amber-600">{adrData.total_bookings}</div>
          </div>
        </div>
      )}

      {/* Room Grid */}
      <div className="border rounded-lg overflow-hidden">
        <div className="bg-gray-100 p-4 font-semibold border-b">
          Availability Grid - {rooms.length} Rooms
        </div>
        <div className="max-h-[600px] overflow-y-auto">
          {rooms.map(room => (
            <div key={room.id} className="border-b p-4 hover:bg-gray-50">
              <div className="flex justify-between items-center">
                <div>
                  <span className="font-semibold">{room.room_number}</span>
                  <span className="ml-4 text-gray-600">{room.room_type}</span>
                  <span className={`ml-4 px-2 py-1 rounded text-sm ${
                    room.status === 'available' ? 'bg-green-100 text-green-800' :
                    room.status === 'occupied' ? 'bg-blue-100 text-blue-800' :
                    'bg-gray-100 text-gray-800'
                  }`}>
                    {room.status}
                  </span>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      setSelectedBooking(room);
                      setShowRateOverride(true);
                    }}
                    className="px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
                  >
                    Override Rate
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Rate Override Modal */}
      {showRateOverride && selectedBooking && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-[500px]">
            <h3 className="text-xl font-bold mb-4">Rate Override - Room {selectedBooking.room_number}</h3>
            <form onSubmit={(e) => {
              e.preventDefault();
              const formData = new FormData(e.target);
              handleRateOverride(
                selectedBooking.current_booking_id,
                formData.get('new_rate'),
                formData.get('reason')
              );
            }}>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-2">New Rate ($)</label>
                <input
                  type="number"
                  name="new_rate"
                  step="0.01"
                  required
                  className="w-full px-4 py-2 border rounded-lg"
                  placeholder="Enter new rate"
                />
              </div>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-2">Override Reason</label>
                <textarea
                  name="reason"
                  required
                  rows="3"
                  className="w-full px-4 py-2 border rounded-lg"
                  placeholder="Why are you overriding the rate?"
                />
              </div>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowRateOverride(false)}
                  className="px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  Override Rate
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default EnhancedReservationCalendar;