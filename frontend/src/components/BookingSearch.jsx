import React, { useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Search, Calendar } from 'lucide-react';
import { toast } from 'sonner';

const BookingSearch = ({ onSelectBooking }) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    if (!query.trim()) {
      toast.error('⚠️ Arama terimi girin');
      return;
    }

    setLoading(true);
    try {
      const response = await axios.get('/frontdesk/search-bookings', {
        params: { query }
      });
      setResults(response.data.bookings || []);
      if (response.data.count === 0) {
        toast.info('🔍 Sonuç bulunamadı');
      }
    } catch (error) {
      toast.error('✗ Arama başarısız');
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'confirmed': return 'bg-blue-500';
      case 'checked_in': return 'bg-green-500';
      case 'checked_out': return 'bg-gray-500';
      case 'cancelled': return 'bg-red-500';
      default: return 'bg-gray-400';
    }
  };

  const getStatusLabel = (status) => {
    const labels = {
      confirmed: 'Onaylandı',
      guaranteed: 'Garantili',
      checked_in: 'Giriş Yapıldı',
      checked_out: 'Çıkış Yapıldı',
      cancelled: 'İptal'
    };
    return labels[status] || status;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center text-lg">
          <Search className="w-5 h-5 mr-2" />
          Rezervasyon Arama
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex space-x-2 mb-4">
          <input
            type="text"
            className="flex-1 p-2 border rounded-lg text-sm"
            placeholder="Rezervasyon no veya misafir adı..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
          />
          <Button
            size="sm"
            className="bg-blue-600 hover:bg-blue-700"
            onClick={handleSearch}
            disabled={loading}
          >
            <Search className="w-4 h-4" />
          </Button>
        </div>

        <div className="space-y-2 max-h-96 overflow-y-auto">
          {results.map((booking) => (
            <div
              key={booking.id}
              className="p-3 bg-gray-50 rounded-lg cursor-pointer hover:bg-gray-100"
              onClick={() => onSelectBooking && onSelectBooking(booking)}
            >
              <div className="flex items-center justify-between mb-2">
                <div>
                  <div className="font-bold text-sm">{booking.booking_number}</div>
                  <div className="text-xs text-gray-600">{booking.guest_name}</div>
                </div>
                <Badge className={getStatusColor(booking.status)}>
                  {getStatusLabel(booking.status)}
                </Badge>
              </div>
              <div className="flex items-center text-xs text-gray-500">
                <Calendar className="w-3 h-3 mr-1" />
                {booking.check_in} → {booking.check_out}
              </div>
              <div className="flex items-center justify-between mt-2">
                <span className="text-xs text-gray-500">Oda: {booking.room_number || 'Atanmadı'}</span>
                <span className="text-sm font-bold text-green-600">₺{booking.total_amount}</span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

export default BookingSearch;
