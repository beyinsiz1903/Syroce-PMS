import React, { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { UserPlus, Zap } from 'lucide-react';

/**
 * Walk-in Booking Quick Form
 * One-click fast booking for walk-in guests
 */
const WalkInBookingQuick = ({ onSuccess }) => {
  const [formData, setFormData] = useState({
    guest_name: '',
    guest_phone: '',
    guest_email: '',
    room_type: 'standard',
    nights: 1,
    adults: 1
  });
  const [loading, setLoading] = useState(false);

  const handleQuickBook = async () => {
    if (!formData.guest_name || !formData.guest_phone) {
      toast.error('Name and phone required');
      return;
    }

    setLoading(true);
    try {
      const response = await axios.post('/bookings/walk-in-quick', {
        ...formData,
        check_in: new Date().toISOString().split('T')[0],
        check_out: new Date(Date.now() + formData.nights * 86400000).toISOString().split('T')[0],
        source: 'walk-in',
        status: 'confirmed'
      });

      toast.success(`Walk-in booking created! Room: ${response.data.room_number}`);
      
      if (onSuccess) onSuccess(response.data);
      
      // Reset form
      setFormData({
        guest_name: '',
        guest_phone: '',
        guest_email: '',
        room_type: 'standard',
        nights: 1,
        adults: 1
      });
    } catch (error) {
      toast.error('Walk-in booking failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="border-2 border-green-300">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <UserPlus className="w-5 h-5 text-green-600" />
          Walk-in Booking (Quick)
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label className="text-xs">Guest Name*</Label>
            <Input
              value={formData.guest_name}
              onChange={(e) => setFormData({...formData, guest_name: e.target.value})}
              placeholder="John Doe"
              className="h-9"
            />
          </div>
          <div>
            <Label className="text-xs">Phone*</Label>
            <Input
              value={formData.guest_phone}
              onChange={(e) => setFormData({...formData, guest_phone: e.target.value})}
              placeholder="+1234567890"
              className="h-9"
            />
          </div>
        </div>

        <div>
          <Label className="text-xs">Email</Label>
          <Input
            value={formData.guest_email}
            onChange={(e) => setFormData({...formData, guest_email: e.target.value})}
            placeholder="john@email.com"
            className="h-9"
          />
        </div>

        <div className="grid grid-cols-3 gap-2">
          <div>
            <Label className="text-xs">Room Type</Label>
            <select
              value={formData.room_type}
              onChange={(e) => setFormData({...formData, room_type: e.target.value})}
              className="w-full h-9 border rounded px-2 text-sm"
            >
              <option value="standard">Standard</option>
              <option value="deluxe">Deluxe</option>
              <option value="suite">Suite</option>
            </select>
          </div>
          <div>
            <Label className="text-xs">Nights</Label>
            <Input
              type="number"
              value={formData.nights}
              onChange={(e) => setFormData({...formData, nights: parseInt(e.target.value)})}
              min={1}
              className="h-9"
            />
          </div>
          <div>
            <Label className="text-xs">Adults</Label>
            <Input
              type="number"
              value={formData.adults}
              onChange={(e) => setFormData({...formData, adults: parseInt(e.target.value)})}
              min={1}
              className="h-9"
            />
          </div>
        </div>

        <Button
          onClick={handleQuickBook}
          disabled={loading}
          className="w-full bg-green-600 hover:bg-green-700"
        >
          <Zap className="w-4 h-4 mr-2" />
          {loading ? 'Creating...' : 'Quick Book Walk-in'}
        </Button>
      </CardContent>
    </Card>
  );
};

export default WalkInBookingQuick;
