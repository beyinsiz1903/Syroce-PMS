import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Alert, AlertDescription } from './ui/alert';
import { Textarea } from './ui/textarea';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Building2, CreditCard, Users, DollarSign, Plus, Link2 } from 'lucide-react';

const OTAReservationDetails = ({ bookingId }) => {
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showAddCharge, setShowAddCharge] = useState(false);
  const [chargeData, setChargeData] = useState({ charge_name: '', charge_amount: '', notes: '' });

  useEffect(() => {
    if (bookingId) {
      fetchOTADetails();
    }
  }, [bookingId]);

  const fetchOTADetails = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${import.meta.env.VITE_BACKEND_URL}/api/reservations/${bookingId}/ota-details`,
        {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setDetails(data);
      }
    } catch (error) {
      console.error('Error fetching OTA details:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddExtraCharge = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${import.meta.env.VITE_BACKEND_URL}/api/reservations/${bookingId}/extra-charges`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(chargeData)
        }
      );

      if (response.ok) {
        setShowAddCharge(false);
        setChargeData({ charge_name: '', charge_amount: '', notes: '' });
        fetchOTADetails();
      }
    } catch (error) {
      console.error('Error adding extra charge:', error);
    }
  };

  const getSourceBadgeColor = (source) => {
    const colors = {
      ota: 'bg-blue-500',
      website: 'bg-green-500',
      corporate: 'bg-purple-500',
      walk_in: 'bg-orange-500',
      phone: 'bg-yellow-500'
    };
    return colors[source] || 'bg-gray-500';
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="animate-pulse space-y-4">
            <div className="h-4 bg-gray-200 rounded w-3/4"></div>
            <div className="h-4 bg-gray-200 rounded w-1/2"></div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!details) return null;

  return (
    <div className="space-y-4">
      {/* Source of Booking */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Building2 className="w-5 h-5" />
            Booking Source
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2">
            <Badge className={getSourceBadgeColor(details.source_of_booking)}>
              {details.source_of_booking?.toUpperCase()}
            </Badge>
            {details.ota_channel && (
              <span className="text-sm text-gray-600">
                Channel: {details.ota_channel}
              </span>
            )}
            {details.ota_confirmation && (
              <span className="text-sm text-gray-600">
                Confirmation: {details.ota_confirmation}
              </span>
            )}
          </div>
          {details.commission_pct && (
            <div className="mt-2 text-sm text-gray-600">
              Commission: {details.commission_pct}%
            </div>
          )}
        </CardContent>
      </Card>

      {/* Special Requests & Remarks */}
      <Card>
        <CardHeader>
          <CardTitle>Special Requests & Remarks</CardTitle>
        </CardHeader>
        <CardContent>
          <Textarea
            value={details.special_requests || 'No special requests'}
            readOnly
            className="min-h-[100px] bg-gray-50"
          />
          {details.remarks && (
            <div className="mt-3">
              <Label>Additional Remarks:</Label>
              <Textarea
                value={details.remarks}
                readOnly
                className="mt-1 bg-gray-50"
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Extra Charges */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <DollarSign className="w-5 h-5" />
              Extra Charges
            </CardTitle>
            <Button
              onClick={() => setShowAddCharge(!showAddCharge)}
              size="sm"
              variant="outline"
            >
              <Plus className="w-4 h-4 mr-2" />
              Add Charge
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {showAddCharge && (
            <div className="mb-4 p-4 border rounded-lg space-y-3">
              <div>
                <Label>Charge Name</Label>
                <Input
                  value={chargeData.charge_name}
                  onChange={(e) => setChargeData({ ...chargeData, charge_name: e.target.value })}
                  placeholder="e.g., Airport Transfer"
                />
              </div>
              <div>
                <Label>Amount</Label>
                <Input
                  type="number"
                  value={chargeData.charge_amount}
                  onChange={(e) => setChargeData({ ...chargeData, charge_amount: e.target.value })}
                  placeholder="0.00"
                />
              </div>
              <div>
                <Label>Notes</Label>
                <Input
                  value={chargeData.notes}
                  onChange={(e) => setChargeData({ ...chargeData, notes: e.target.value })}
                  placeholder="Optional notes"
                />
              </div>
              <div className="flex gap-2">
                <Button onClick={handleAddExtraCharge}>Add</Button>
                <Button variant="outline" onClick={() => setShowAddCharge(false)}>Cancel</Button>
              </div>
            </div>
          )}

          {details.extra_charges && details.extra_charges.length > 0 ? (
            <div className="space-y-2">
              {details.extra_charges.map((charge, idx) => (
                <div key={idx} className="flex items-center justify-between p-3 bg-gray-50 rounded">
                  <div>
                    <div className="font-medium">{charge.charge_name}</div>
                    {charge.notes && <div className="text-sm text-gray-600">{charge.notes}</div>}
                  </div>
                  <div className="font-semibold">${charge.charge_amount}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center text-gray-500 py-4">No extra charges</div>
          )}
        </CardContent>
      </Card>

      {/* Multi-Room Information */}
      {details.multi_room_info && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Link2 className="w-5 h-5" />
              Multi-Room Reservation
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div>
                <Label>Group Name:</Label>
                <div className="font-medium">{details.multi_room_info.group_name}</div>
              </div>
              <div>
                <Label>Total Rooms:</Label>
                <div className="font-medium">{details.multi_room_info.total_rooms}</div>
              </div>
              <div>
                <Label>Related Bookings:</Label>
                <div className="mt-2 space-y-2">
                  {details.multi_room_info.related_bookings?.map((booking, idx) => (
                    <div key={idx} className="flex items-center justify-between p-2 bg-gray-50 rounded">
                      <span>{booking.room_number}</span>
                      <span className="text-sm text-gray-600">{booking.guest_name}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default OTAReservationDetails;