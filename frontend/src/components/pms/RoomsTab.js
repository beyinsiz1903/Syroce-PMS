import React, { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { BedDouble, User } from 'lucide-react';

const RoomsTab = ({
  rooms,
  bookings = [],
}) => {
  const { t } = useTranslation();
  const [typeFilter, setTypeFilter] = useState('all');
  const [viewFilter, setViewFilter] = useState('all');
  const [amenityFilter, setAmenityFilter] = useState('all');

  // Build a map of room_number -> current guest info from active bookings
  const roomGuestMap = useMemo(() => {
    const map = {};
    const today = new Date().toISOString().split('T')[0];
    const activeStatuses = ['confirmed', 'checked_in', 'guaranteed'];
    for (const b of bookings) {
      if (!activeStatuses.includes(b.status)) continue;
      if (!b.room_number) continue;
      const ci = (b.check_in || '').slice(0, 10);
      const co = (b.check_out || '').slice(0, 10);
      if (ci <= today && co > today) {
        map[String(b.room_number)] = {
          guest_name: b.guest_name || 'Misafir',
          check_in: ci,
          check_out: co,
          status: b.status,
        };
      }
    }
    return map;
  }, [bookings]);

  const filteredRooms = useMemo(() => {
    return rooms.filter(r => {
      if (typeFilter !== 'all' && r.room_type !== typeFilter) return false;
      if (viewFilter !== 'all' && r.view !== viewFilter) return false;
      if (amenityFilter !== 'all' && !(r.amenities || []).includes(amenityFilter)) return false;
      return true;
    });
  }, [rooms, typeFilter, viewFilter, amenityFilter]);

  const allTypes = [...new Set(rooms.map(r => r.room_type).filter(Boolean))];
  const allViews = [...new Set(rooms.map(r => r.view).filter(Boolean))];
  const allAmenities = [...new Set(rooms.flatMap(r => r.amenities || []))];

  const statusColors = {
    available: 'bg-green-100 text-green-800',
    occupied: 'bg-blue-100 text-blue-800',
    dirty: 'bg-yellow-100 text-yellow-800',
    cleaning: 'bg-orange-100 text-orange-800',
    maintenance: 'bg-red-100 text-red-800',
    out_of_order: 'bg-gray-100 text-gray-800',
    inspected: 'bg-purple-100 text-purple-800',
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-semibold">{t('pms.rooms')} ({rooms.length})</h2>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-40"><SelectValue placeholder={t('pms.roomType')} /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('common.filter') || 'All Types'}</SelectItem>
            {allTypes.map(t2 => <SelectItem key={t2} value={t2}>{t2}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={viewFilter} onValueChange={setViewFilter}>
          <SelectTrigger className="w-40"><SelectValue placeholder={t('common.view')} /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('common.filter') || 'All Views'}</SelectItem>
            {allViews.map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={amenityFilter} onValueChange={setAmenityFilter}>
          <SelectTrigger className="w-40"><SelectValue placeholder="Amenity" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('common.filter') || 'All Amenities'}</SelectItem>
            {allAmenities.map(a => <SelectItem key={a} value={a}>{a}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {/* Room Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
        {filteredRooms.map(room => (
          <Card
            key={room.id}
            className="hover:shadow-md transition-all"
            data-testid={`room-card-${room.room_number}`}
          >
            <CardContent className="p-3">
              <div className="flex justify-between items-start mb-2">
                <span className="text-lg font-bold">{room.room_number}</span>
                <Badge className={statusColors[room.status] || 'bg-gray-100'}>{room.status}</Badge>
              </div>
              <p className="text-sm text-gray-600">{room.room_type}</p>
              <p className="text-xs text-gray-400">{t('pms.roomNumber') || 'Floor'} {room.floor} • {room.capacity} {t('common.guests') || 'guests'}</p>
              {roomGuestMap[String(room.room_number)] && (
                <div className="mt-2 p-2 bg-blue-50 rounded-md border border-blue-100" data-testid={`room-guest-${room.room_number}`}>
                  <div className="flex items-center gap-1.5">
                    <User className="w-3.5 h-3.5 text-blue-600 flex-shrink-0" />
                    <span className="text-sm font-medium text-blue-800 truncate">{roomGuestMap[String(room.room_number)].guest_name}</span>
                  </div>
                  <p className="text-[10px] text-blue-500 mt-0.5">
                    {roomGuestMap[String(room.room_number)].check_in} → {roomGuestMap[String(room.room_number)].check_out}
                  </p>
                </div>
              )}
              {room.base_price && <p className="text-sm font-semibold mt-1">€{room.base_price}</p>}
              <div className="flex gap-1 mt-2 flex-wrap">
                {room.view && <Badge variant="outline" className="text-[10px]">{room.view}</Badge>}
                {room.bed_type && <Badge variant="outline" className="text-[10px]"><BedDouble className="w-3 h-3 mr-0.5" />{room.bed_type}</Badge>}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};

export default RoomsTab;
