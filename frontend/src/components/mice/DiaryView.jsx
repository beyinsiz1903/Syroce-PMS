import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { CalendarDays } from 'lucide-react';

const STATUS = {
  lead: { label: 'Lead', cls: 'bg-slate-100 text-slate-700' },
  tentative: { label: 'Beklemede', cls: 'bg-amber-100 text-amber-800' },
  definite: { label: 'Kesinleşmiş', cls: 'bg-sky-100 text-sky-800' },
  confirmed: { label: 'Onaylı', cls: 'bg-emerald-100 text-emerald-800' },
  completed: { label: 'Tamamlandı', cls: 'bg-indigo-100 text-indigo-800' },
  cancelled: { label: 'İptal', cls: 'bg-red-100 text-red-800' },
};

const DAYS_TR = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz'];
const MONTHS_TR = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
                   'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];

const DiaryView = ({ spaceById, spaces }) => {
  const today = new Date();
  const [view, setView] = useState('calendar');
  const [calMonth, setCalMonth] = useState({ year: today.getFullYear(), month: today.getMonth() });
  const [selectedDate, setSelectedDate] = useState(null);
  const [items, setItems] = useState([]);

  const monthRange = useMemo(() => {
    const { year, month } = calMonth;
    const from = `${year}-${String(month + 1).padStart(2, '0')}-01`;
    const lastDay = new Date(year, month + 1, 0).getDate();
    const to = `${year}-${String(month + 1).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`;
    return { from, to, lastDay };
  }, [calMonth]);

  useEffect(() => {
    axios.get('/mice/diary', { params: { date_from: monthRange.from, date_to: monthRange.to } })
      .then((r) => setItems(r.data.events || []))
      .catch(() => toast.error('Takvim yüklenemedi'));
  }, [monthRange.from, monthRange.to]);

  const eventsByDate = useMemo(() => {
    const map = {};
    items.forEach((ev) => {
      const start = new Date(ev.start_date);
      const end = new Date(ev.end_date || ev.start_date);
      for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
        const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
        if (!map[key]) map[key] = [];
        if (!map[key].find((e) => e.id === ev.id)) map[key].push(ev);
      }
    });
    return map;
  }, [items]);

  const calendarDays = useMemo(() => {
    const { year, month } = calMonth;
    let startWeekday = new Date(year, month, 1).getDay() - 1;
    if (startWeekday < 0) startWeekday = 6;
    const days = [];
    for (let i = 0; i < startWeekday; i++) days.push(null);
    for (let d = 1; d <= monthRange.lastDay; d++) {
      const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      const dayEvents = eventsByDate[dateStr] || [];
      const bookedSpaceIds = new Set();
      dayEvents.forEach((ev) => (ev.space_bookings || []).forEach((sb) => bookedSpaceIds.add(sb.space_id)));
      days.push({
        day: d, dateStr, events: dayEvents,
        bookedCount: bookedSpaceIds.size,
        freeCount: Math.max(0, (spaces?.length || 0) - bookedSpaceIds.size),
      });
    }
    return days;
  }, [calMonth, eventsByDate, spaces, monthRange.lastDay]);

  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const prevMonth = () => setCalMonth((p) => p.month === 0 ? { year: p.year - 1, month: 11 } : { ...p, month: p.month - 1 });
  const nextMonth = () => setCalMonth((p) => p.month === 11 ? { year: p.year + 1, month: 0 } : { ...p, month: p.month + 1 });
  const goToday = () => { setCalMonth({ year: today.getFullYear(), month: today.getMonth() }); setSelectedDate(todayStr); };

  const selectedDayEvents = selectedDate ? (eventsByDate[selectedDate] || []) : [];
  const selectedDayBookedIds = new Set();
  selectedDayEvents.forEach((ev) => (ev.space_bookings || []).forEach((sb) => selectedDayBookedIds.add(sb.space_id)));
  const selectedDayFreeSpaces = (spaces || []).filter((s) => !selectedDayBookedIds.has(s.id));
  const selectedDayBookedSpaces = (spaces || []).filter((s) => selectedDayBookedIds.has(s.id));

  return (
    <Card><CardContent className="p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={prevMonth}>‹</Button>
          <div className="font-semibold min-w-[140px] text-center">
            {MONTHS_TR[calMonth.month]} {calMonth.year}
          </div>
          <Button variant="outline" size="sm" onClick={nextMonth}>›</Button>
          <Button variant="outline" size="sm" onClick={goToday}>Bugün</Button>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 text-xs">
            <span className="inline-block w-3 h-3 rounded bg-indigo-100 border border-indigo-300" /> Etkinlik
            <span className="inline-block w-3 h-3 rounded bg-emerald-100 border border-emerald-300 ml-2" /> Müsait
          </div>
          <Button variant={view === 'calendar' ? 'default' : 'outline'} size="sm" onClick={() => setView('calendar')}>Takvim</Button>
          <Button variant={view === 'list' ? 'default' : 'outline'} size="sm" onClick={() => setView('list')}>Liste</Button>
        </div>
      </div>

      {view === 'calendar' ? (
        <div className="grid md:grid-cols-[1fr_320px] gap-3">
          <div>
            <div className="grid grid-cols-7 gap-1 mb-1">
              {DAYS_TR.map((d) => (
                <div key={d} className="text-center text-xs font-semibold text-gray-500 py-1">{d}</div>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-1">
              {calendarDays.map((cell, idx) => {
                if (!cell) return <div key={`empty-${idx}`} className="h-20 bg-slate-50/40 rounded" />;
                const isToday = cell.dateStr === todayStr;
                const isSelected = cell.dateStr === selectedDate;
                const hasEvents = cell.events.length > 0;
                return (
                  <button
                    key={cell.dateStr}
                    onClick={() => setSelectedDate(cell.dateStr)}
                    className={`h-20 rounded border p-1 text-left transition hover:border-indigo-400 hover:shadow-sm ${
                      isSelected ? 'border-indigo-500 ring-2 ring-indigo-200 bg-indigo-50/60'
                        : isToday ? 'border-indigo-300 bg-indigo-50/30'
                        : hasEvents ? 'border-slate-200 bg-white'
                        : 'border-slate-100 bg-white'
                    }`}
                  >
                    <div className={`text-xs font-semibold ${isToday ? 'text-indigo-700' : 'text-gray-700'}`}>{cell.day}</div>
                    {hasEvents && (
                      <div className="mt-0.5">
                        <div className="text-[10px] inline-flex items-center gap-1 px-1 py-0.5 rounded bg-indigo-100 text-indigo-700">
                          <CalendarDays className="w-2.5 h-2.5" /> {cell.events.length}
                        </div>
                      </div>
                    )}
                    {(spaces?.length || 0) > 0 && (
                      <div className="mt-0.5 text-[10px] text-emerald-700">
                        {cell.freeCount}/{spaces.length} müsait
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="border rounded-lg p-3 bg-slate-50/50">
            {selectedDate ? (
              <>
                <div className="font-semibold text-sm mb-2 flex items-center gap-2">
                  <CalendarDays className="w-4 h-4 text-indigo-600" />
                  {selectedDate}
                </div>
                <div className="text-xs text-gray-600 mb-2">
                  {selectedDayEvents.length} etkinlik • {selectedDayFreeSpaces.length} müsait mekan
                </div>
                {selectedDayEvents.length > 0 && (
                  <div className="space-y-1.5 mb-3">
                    <div className="text-[11px] font-semibold text-gray-500 uppercase">Etkinlikler</div>
                    {selectedDayEvents.map((ev) => (
                      <div key={ev.id} className="bg-white rounded border p-2">
                        <div className="flex items-start justify-between gap-1">
                          <div className="font-semibold text-xs">{ev.name}</div>
                          <Badge className={`${STATUS[ev.status]?.cls || ''} border-0 text-[10px]`}>{STATUS[ev.status]?.label}</Badge>
                        </div>
                        <div className="text-[11px] text-gray-500 mt-0.5">
                          {ev.client_name} • {ev.expected_pax} pax
                        </div>
                        <div className="text-[11px] text-gray-600 mt-0.5">
                          {(ev.space_bookings || []).map((sb) => spaceById[sb.space_id]?.name).filter(Boolean).join(', ')}
                        </div>
                        <div className="text-[11px] font-semibold mt-0.5">
                          ₺{(ev.totals?.grand_total || 0).toLocaleString('tr-TR')}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {selectedDayBookedSpaces.length > 0 && (
                  <div className="space-y-1 mb-3">
                    <div className="text-[11px] font-semibold text-gray-500 uppercase">Dolu Mekanlar</div>
                    <div className="flex flex-wrap gap-1">
                      {selectedDayBookedSpaces.map((s) => (
                        <Badge key={s.id} variant="outline" className="text-[10px] bg-rose-50 border-rose-200 text-rose-700">{s.name}</Badge>
                      ))}
                    </div>
                  </div>
                )}
                {selectedDayFreeSpaces.length > 0 && (
                  <div className="space-y-1">
                    <div className="text-[11px] font-semibold text-gray-500 uppercase">Müsait Mekanlar</div>
                    <div className="flex flex-wrap gap-1">
                      {selectedDayFreeSpaces.map((s) => (
                        <Badge key={s.id} variant="outline" className="text-[10px] bg-emerald-50 border-emerald-200 text-emerald-700">{s.name}</Badge>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="text-xs text-gray-500 text-center py-8">
                Detay için bir gün seçin
              </div>
            )}
          </div>
        </div>
      ) : (
        items.length === 0 ? (
          <p className="text-sm text-gray-500 p-4 text-center">Bu ayda etkinlik yok.</p>
        ) : (
          <div className="space-y-1">
            {items.map((ev) => (
              <div key={ev.id} className="flex items-center gap-2 p-2 border rounded hover:bg-slate-50">
                <CalendarDays className="w-4 h-4 text-indigo-600" />
                <div className="font-mono text-xs w-44">{ev.start_date} → {ev.end_date}</div>
                <div className="flex-1">
                  <div className="font-semibold text-sm">{ev.name}</div>
                  <div className="text-xs text-gray-500">
                    {ev.client_name} • {ev.expected_pax} pax •{' '}
                    {(ev.space_bookings || []).map((sb) => spaceById[sb.space_id]?.name).filter(Boolean).join(', ')}
                  </div>
                </div>
                <Badge className={`${STATUS[ev.status]?.cls || ''} border-0`}>{STATUS[ev.status]?.label}</Badge>
                <div className="font-semibold text-sm w-28 text-right">
                  ₺{(ev.totals?.grand_total || 0).toLocaleString('tr-TR')}
                </div>
              </div>
            ))}
          </div>
        )
      )}
    </CardContent></Card>
  );
};

export default DiaryView;
