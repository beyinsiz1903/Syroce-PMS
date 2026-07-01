import { useState, useMemo, useRef, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ChevronLeft, ChevronRight, Calendar, BedDouble, ZoomIn, ZoomOut } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const statusColors = {
  confirmed: { bg: '#3B82F6', text: '#fff' },
  checked_in: { bg: '#10B981', text: '#fff' },
  checked_out: { bg: '#6B7280', text: '#fff' },
  cancelled: { bg: '#EF4444', text: '#fff' },
  no_show: { bg: '#F59E0B', text: '#fff' },
  guaranteed: { bg: '#8B5CF6', text: '#fff' },
  tentative: { bg: '#F97316', text: '#fff' },
};

const RoomTimelineView = ({ rooms = [], bookings = [], onBookingClick }) => {
  const { t } = useTranslation();
  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    return d.toISOString().split('T')[0];
  });
  const [daysToShow, setDaysToShow] = useState(14);
  const [typeFilter, setTypeFilter] = useState('all');
  const scrollRef = useRef(null);

  const dates = useMemo(() => {
    const result = [];
    const start = new Date(startDate);
    for (let i = 0; i < daysToShow; i++) {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      result.push(d.toISOString().split('T')[0]);
    }
    return result;
  }, [startDate, daysToShow]);

  const today = new Date().toISOString().split('T')[0];

  const filteredRooms = useMemo(() => {
    if (typeFilter === 'all') return rooms;
    return rooms.filter(r => r.room_type === typeFilter);
  }, [rooms, typeFilter]);

  const roomTypes = useMemo(() => {
    const types = new Set(rooms.map(r => r.room_type).filter(Boolean));
    return Array.from(types);
  }, [rooms]);

  const roomBookingsMap = useMemo(() => {
    const map = {};
    for (const b of bookings) {
      const rn = String(b.room_number);
      if (!map[rn]) map[rn] = [];
      map[rn].push(b);
    }
    return map;
  }, [bookings]);

  const getBookingForCell = (roomNumber, date) => {
    const rBookings = roomBookingsMap[String(roomNumber)] || [];
    for (const b of rBookings) {
      const ci = (b.check_in || '').slice(0, 10);
      const co = (b.check_out || '').slice(0, 10);
      if (ci <= date && co > date) return b;
    }
    return null;
  };

  const getBookingSpan = (booking, dateIndex) => {
    if (!booking) return 0;
    const ci = (booking.check_in || '').slice(0, 10);
    const co = (booking.check_out || '').slice(0, 10);
    const startIdx = Math.max(0, dates.indexOf(ci));
    if (dateIndex !== startIdx && dates[dateIndex] !== ci) return -1;
    const endIdx = dates.indexOf(co);
    const actualEnd = endIdx >= 0 ? endIdx : daysToShow;
    return Math.max(1, actualEnd - startIdx);
  };

  const navigate = (dir) => {
    const d = new Date(startDate);
    d.setDate(d.getDate() + (dir * 7));
    setStartDate(d.toISOString().split('T')[0]);
  };

  const goToToday = () => {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    setStartDate(d.toISOString().split('T')[0]);
  };

  const cellWidth = 80;
  const roomColWidth = 120;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <Calendar className="w-5 h-5" /> {t('cm.components_pms_RoomTimelineView.oda_zaman_cizelgesi')}
        </h3>
        <div className="flex items-center gap-2">
          <Select value={typeFilter} onValueChange={setTypeFilter}>
            <SelectTrigger className="w-36 h-8 text-xs">
              <SelectValue placeholder={t('cm.components_pms_RoomTimelineView.oda_tipi')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('cm.components_pms_RoomTimelineView.tum_tipler')}</SelectItem>
              {roomTypes.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={() => setDaysToShow(Math.max(7, daysToShow - 7))}>
            <ZoomIn className="w-3.5 h-3.5" />
          </Button>
          <Button variant="outline" size="sm" onClick={() => setDaysToShow(Math.min(30, daysToShow + 7))}>
            <ZoomOut className="w-3.5 h-3.5" />
          </Button>
          <Button variant="outline" size="sm" onClick={() => navigate(-1)}>
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <Button variant="outline" size="sm" onClick={goToToday}>{t('cm.components_pms_RoomTimelineView.bugun')}</Button>
          <Button variant="outline" size="sm" onClick={() => navigate(1)}>
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="p-0 overflow-x-auto" ref={scrollRef}>
          <div style={{ minWidth: roomColWidth + (cellWidth * daysToShow) }}>
            <div className="flex border-b border-gray-200 sticky top-0 bg-white z-10">
              <div className="flex-shrink-0 border-r border-gray-200 bg-gray-50 p-2 font-medium text-xs text-gray-500"
                style={{ width: roomColWidth }}>
                {t('cm.components_pms_RoomTimelineView.oda')}
              </div>
              {dates.map((date, i) => {
                const d = new Date(date);
                const isToday = date === today;
                const isWeekend = d.getDay() === 0 || d.getDay() === 6;
                return (
                  <div key={date}
                    className={`flex-shrink-0 border-r border-gray-200 p-1 text-center text-[10px] ${isToday ? 'bg-blue-100 font-bold' : isWeekend ? 'bg-gray-50' : 'bg-white'}`}
                    style={{ width: cellWidth }}>
                    <div className="text-gray-400">{['Pzr', 'Pzt', 'Sal', 'Car', 'Per', 'Cum', 'Cmt'][d.getDay()]}</div>
                    <div className={isToday ? 'text-blue-700' : 'text-gray-700'}>{d.getDate()}</div>
                    <div className="text-gray-300">{['Oca', 'Sub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Agu', 'Eyl', 'Eki', 'Kas', 'Ara'][d.getMonth()]}</div>
                  </div>
                );
              })}
            </div>

            {filteredRooms.map(room => {
              const renderedBookings = new Set();
              return (
                <div key={room.id} className="flex border-b border-gray-100 hover:bg-gray-50/50">
                  <div className="flex-shrink-0 border-r border-gray-200 p-2 flex items-center gap-1.5"
                    style={{ width: roomColWidth }}>
                    <BedDouble className="w-3 h-3 text-gray-400" />
                    <span className="text-xs font-medium text-gray-700">{room.room_number}</span>
                    <Badge variant="outline" className="text-[8px] h-4">{room.room_type?.slice(0, 6)}</Badge>
                  </div>
                  <div className="flex relative" style={{ height: 36 }}>
                    {dates.map((date, dateIdx) => {
                      const booking = getBookingForCell(room.room_number, date);
                      const isToday = date === today;
                      const d = new Date(date);
                      const isWeekend = d.getDay() === 0 || d.getDay() === 6;

                      if (booking && !renderedBookings.has(booking.id)) {
                        renderedBookings.add(booking.id);
                        const ci = (booking.check_in || '').slice(0, 10);
                        const co = (booking.check_out || '').slice(0, 10);
                        const startIdx = Math.max(0, dates.indexOf(ci) >= 0 ? dates.indexOf(ci) : 0);
                        const endIdx = dates.indexOf(co);
                        const actualEnd = endIdx >= 0 ? endIdx : daysToShow;
                        const span = Math.max(1, actualEnd - startIdx);
                        const colors = statusColors[booking.status] || statusColors.confirmed;

                        return (
                          <div key={date} className="absolute top-1 flex-shrink-0"
                            style={{
                              left: dateIdx * cellWidth + 2,
                              width: span * cellWidth - 4,
                              zIndex: 5
                            }}>
                            <div
                              className="rounded-md px-2 py-1 cursor-pointer hover:opacity-90 transition-opacity shadow-sm"
                              style={{ backgroundColor: colors.bg, color: colors.text, height: 28 }}
                              onClick={() => onBookingClick?.(booking)}
                              title={`${booking.guest_name || 'Misafir'} | ${ci} - ${co} | ${booking.status}`}
                            >
                              <span className="text-[10px] font-medium truncate block leading-tight">
                                {booking.guest_name?.split(' ')[0] || 'Misafir'}
                              </span>
                              <span className="text-[8px] opacity-80 truncate block leading-tight">
                                {booking.status === 'checked_in' ? 'Konaklama' : booking.status === 'confirmed' ? 'Onaylandi' : booking.status}
                              </span>
                            </div>
                          </div>
                        );
                      }

                      if (booking) return <div key={date} style={{ width: cellWidth }} className="flex-shrink-0" />;

                      return (
                        <div key={date}
                          className={`flex-shrink-0 border-r border-gray-100 ${isToday ? 'bg-blue-50/30' : isWeekend ? 'bg-gray-50/30' : ''}`}
                          style={{ width: cellWidth, height: 36 }}
                        />
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-2">
        {Object.entries(statusColors).map(([status, colors]) => (
          <div key={status} className="flex items-center gap-1.5 text-xs">
            <div className="w-3 h-3 rounded" style={{ backgroundColor: colors.bg }} />
            <span className="text-gray-600 capitalize">{status.replace('_', ' ')}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default RoomTimelineView;
