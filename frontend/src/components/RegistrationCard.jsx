import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { FileText, Printer, Download, User, Calendar, CreditCard, MapPin, Phone, Mail } from 'lucide-react';

const RegistrationCard = ({ bookingId, onClose }) => {
  const [cardData, setCardData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (bookingId) {
      fetchRegistrationData();
    }
  }, [bookingId]);

  const fetchRegistrationData = async () => {
    try {
      const token = localStorage.getItem('token');
      
      // Fetch booking details
      const bookingResponse = await fetch(
        `/api/bookings/${bookingId}`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );
      const bookingData = await bookingResponse.json();
      
      // Fetch guest details
      const guestResponse = await fetch(
        `/api/guests/${bookingData.booking.guest_id}`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );
      const guestData = await guestResponse.json();
      
      // Fetch room details
      const roomsResponse = await fetch(
        `/api/rooms`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );
      const roomsData = await roomsResponse.json();
      const room = roomsData.rooms.find(r => r.id === bookingData.booking.room_id);
      
      setCardData({
        booking: bookingData.booking,
        guest: guestData.guest,
        room: room
      });
    } catch (error) {
      console.error('Error fetching registration data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  const handleDownloadPDF = async () => {
    alert('PDF download functionality - integrate with PDF library');
  };

  const formatDate = (date) => {
    if (!date) return 'N/A';
    try {
      return new Date(date).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      });
    } catch {
      return date;
    }
  };

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <Card className="w-full max-w-4xl max-h-[90vh] overflow-auto">
          <CardContent className="p-6">
            <div className="animate-pulse space-y-4">
              <div className="h-4 bg-gray-200 rounded w-3/4"></div>
              <div className="h-4 bg-gray-200 rounded w-1/2"></div>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!cardData) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <Card className="w-full max-w-4xl">
          <CardContent className="p-6">
            <p>Error loading registration card</p>
            <Button onClick={onClose} className="mt-4">Close</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const { booking, guest, room } = cardData;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <Card className="w-full max-w-4xl max-h-[90vh] overflow-auto bg-white">
        <CardHeader className="border-b print:border-black">
          <div className="flex justify-between items-start">
            <div>
              <CardTitle className="text-2xl mb-2">GUEST REGISTRATION CARD</CardTitle>
              <div className="text-sm text-gray-600">
                Registration No: <span className="font-semibold">{booking.id?.slice(0, 8).toUpperCase()}</span>
              </div>
            </div>
            <div className="flex gap-2 print:hidden">
              <Button onClick={handlePrint} variant="outline" size="sm">
                <Printer className="w-4 h-4 mr-2" />
                Print
              </Button>
              <Button onClick={handleDownloadPDF} variant="outline" size="sm">
                <Download className="w-4 h-4 mr-2" />
                PDF
              </Button>
              <Button onClick={onClose} variant="outline" size="sm">
                Close
              </Button>
            </div>
          </div>
        </CardHeader>

        <CardContent className="p-6 space-y-6">
          {/* Guest Information */}
          <div>
            <div className="flex items-center gap-2 mb-4 pb-2 border-b-2 border-gray-300">
              <User className="w-5 h-5 text-blue-600" />
              <h2 className="text-xl font-bold">GUEST INFORMATION</h2>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-semibold text-gray-600">Full Name:</label>
                <p className="text-lg font-medium">{guest.name}</p>
              </div>
              <div>
                <label className="text-sm font-semibold text-gray-600">Nationality:</label>
                <p className="text-lg">{guest.nationality || 'N/A'}</p>
              </div>
              <div>
                <label className="text-sm font-semibold text-gray-600">ID/Passport Number:</label>
                <p className="text-lg">{guest.id_number || 'N/A'}</p>
              </div>
              <div>
                <label className="text-sm font-semibold text-gray-600">Date of Birth:</label>
                <p className="text-lg">{guest.date_of_birth ? formatDate(guest.date_of_birth) : 'N/A'}</p>
              </div>
              <div className="flex items-center gap-2">
                <Phone className="w-4 h-4 text-gray-600" />
                <div>
                  <label className="text-sm font-semibold text-gray-600">Phone:</label>
                  <p className="text-lg">{guest.phone}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Mail className="w-4 h-4 text-gray-600" />
                <div>
                  <label className="text-sm font-semibold text-gray-600">Email:</label>
                  <p className="text-lg">{guest.email}</p>
                </div>
              </div>
            </div>
            {guest.address && (
              <div className="mt-4 flex items-start gap-2">
                <MapPin className="w-4 h-4 text-gray-600 mt-1" />
                <div className="flex-1">
                  <label className="text-sm font-semibold text-gray-600">Address:</label>
                  <p className="text-lg">{guest.address}</p>
                </div>
              </div>
            )}
          </div>

          {/* Stay Information */}
          <div>
            <div className="flex items-center gap-2 mb-4 pb-2 border-b-2 border-gray-300">
              <Calendar className="w-5 h-5 text-blue-600" />
              <h2 className="text-xl font-bold">STAY INFORMATION</h2>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-semibold text-gray-600">Check-in Date:</label>
                <p className="text-lg font-medium">{formatDate(booking.check_in)}</p>
              </div>
              <div>
                <label className="text-sm font-semibold text-gray-600">Check-out Date:</label>
                <p className="text-lg font-medium">{formatDate(booking.check_out)}</p>
              </div>
              <div>
                <label className="text-sm font-semibold text-gray-600">Number of Nights:</label>
                <p className="text-lg">
                  {(() => {
                    try {
                      const checkin = new Date(booking.check_in);
                      const checkout = new Date(booking.check_out);
                      const nights = Math.ceil((checkout - checkin) / (1000 * 60 * 60 * 24));
                      return nights;
                    } catch {
                      return 'N/A';
                    }
                  })()}
                </p>
              </div>
              <div>
                <label className="text-sm font-semibold text-gray-600">Number of Guests:</label>
                <p className="text-lg">
                  {booking.adults || 0} Adult(s)
                  {booking.children > 0 && `, ${booking.children} Child(ren)`}
                </p>
              </div>
            </div>
          </div>

          {/* Room Information */}
          <div>
            <div className="flex items-center gap-2 mb-4 pb-2 border-b-2 border-gray-300">
              <FileText className="w-5 h-5 text-blue-600" />
              <h2 className="text-xl font-bold">ROOM DETAILS</h2>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-semibold text-gray-600">Room Number:</label>
                <p className="text-2xl font-bold text-blue-600">{room?.room_number || 'N/A'}</p>
              </div>
              <div>
                <label className="text-sm font-semibold text-gray-600">Room Type:</label>
                <p className="text-lg">{room?.room_type || 'N/A'}</p>
              </div>
              <div>
                <label className="text-sm font-semibold text-gray-600">Floor:</label>
                <p className="text-lg">{room?.floor || 'N/A'}</p>
              </div>
              <div>
                <label className="text-sm font-semibold text-gray-600">Room Rate:</label>
                <p className="text-lg font-semibold">${booking.base_rate || 0} / night</p>
              </div>
            </div>
          </div>

          {/* Payment Information */}
          <div>
            <div className="flex items-center gap-2 mb-4 pb-2 border-b-2 border-gray-300">
              <CreditCard className="w-5 h-5 text-blue-600" />
              <h2 className="text-xl font-bold">PAYMENT INFORMATION</h2>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-semibold text-gray-600">Total Amount:</label>
                <p className="text-2xl font-bold text-green-600">${booking.total_amount || 0}</p>
              </div>
              <div>
                <label className="text-sm font-semibold text-gray-600">Payment Status:</label>
                <Badge className={booking.paid_amount >= booking.total_amount ? 'bg-green-500' : 'bg-yellow-500'}>
                  {booking.paid_amount >= booking.total_amount ? 'Paid' : 'Pending'}
                </Badge>
              </div>
            </div>
          </div>

          {/* Special Requests */}
          {booking.special_requests && (
            <div>
              <div className="mb-2 pb-2 border-b-2 border-gray-300">
                <h2 className="text-xl font-bold">SPECIAL REQUESTS</h2>
              </div>
              <p className="text-lg p-4 bg-yellow-50 border-l-4 border-yellow-400 rounded">
                {booking.special_requests}
              </p>
            </div>
          )}

          {/* Signatures */}
          <div className="mt-8 pt-6 border-t-2 border-gray-300">
            <div className="grid grid-cols-2 gap-8">
              <div>
                <div className="border-t-2 border-gray-400 pt-2 mt-16">
                  <p className="text-center font-semibold">Guest Signature</p>
                  <p className="text-center text-sm text-gray-600">Date: {formatDate(new Date())}</p>
                </div>
              </div>
              <div>
                <div className="border-t-2 border-gray-400 pt-2 mt-16">
                  <p className="text-center font-semibold">Hotel Representative</p>
                  <p className="text-center text-sm text-gray-600">Date: {formatDate(new Date())}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Terms and Conditions */}
          <div className="text-xs text-gray-600 mt-6 p-4 bg-gray-50 rounded">
            <p className="font-semibold mb-2">Terms & Conditions:</p>
            <ul className="list-disc list-inside space-y-1">
              <li>Check-in time: 2:00 PM | Check-out time: 12:00 PM</li>
              <li>Late check-out subject to availability and additional charges</li>
              <li>Damage to hotel property will be charged to guest's account</li>
              <li>Guest is responsible for all charges incurred during the stay</li>
              <li>Hotel is not responsible for valuables left in the room</li>
            </ul>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default RegistrationCard;