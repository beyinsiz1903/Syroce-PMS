import { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Bed, CheckCircle, AlertTriangle, Wrench, Search as SearchIcon,
  Eye, Filter, RefreshCw, ChevronDown
} from 'lucide-react';

const HousekeepingRoomGrid = ({ embedded = false, onChange }) => {
  const { t } = useTranslation();
  const tg = (k) => t(`pmsComponents.housekeeping.roomGrid.${k}`);
  const ts = (k) => t(`pmsComponents.housekeeping.roomGrid.statuses.${k}`);

  const STATUS_CONFIG = useMemo(() => ({
    clean: { label: ts('clean'), color: 'bg-emerald-100 text-emerald-700 border-emerald-200', icon: CheckCircle, dot: 'bg-emerald-500' },
    dirty: { label: ts('dirty'), color: 'bg-red-100 text-red-700 border-red-200', icon: AlertTriangle, dot: 'bg-red-500' },
    inspected: { label: ts('inspected'), color: 'bg-blue-100 text-blue-700 border-blue-200', icon: Eye, dot: 'bg-blue-500' },
    maintenance: { label: ts('maintenance'), color: 'bg-amber-100 text-amber-700 border-amber-200', icon: Wrench, dot: 'bg-amber-500' },
    out_of_order: { label: ts('out_of_order'), color: 'bg-gray-200 text-gray-700 border-gray-300', icon: AlertTriangle, dot: 'bg-gray-500' },
  }), [t]);

  const [rooms, setRooms] = useState([]);
  const [summary, setSummary] = useState({});
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [selectedRooms, setSelectedRooms] = useState([]);
  const [bulkMenuOpen, setBulkMenuOpen] = useState(false);

  const loadRooms = useCallback(async () => {
    try {
      const params = {};
      if (filter !== 'all') params.status_filter = filter;
      const res = await axios.get(`/pms/housekeeping/rooms`, { params });
      setRooms(res.data?.rooms || []);
      setSummary(res.data?.summary || {});
    } catch (e) {
      console.error('Failed to load rooms', e);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { loadRooms(); }, [loadRooms]);

  const updateStatus = async (roomId, newStatus) => {
    try {
      await axios.put(`/pms/housekeeping/rooms/${roomId}/status`, { status: newStatus });
      toast.success(tg('statusUpdated').replace('{label}', STATUS_CONFIG[newStatus]?.label || newStatus));
      loadRooms();
      if (onChange) onChange();
    } catch (e) {
      toast.error(tg('updateFailed') + ': ' + (e.response?.data?.detail || e.message));
    }
  };

  const bulkUpdate = async (newStatus) => {
    if (selectedRooms.length === 0) { toast.error(tg('selectRoom')); return; }
    try {
      await axios.put(`/pms/housekeeping/rooms/bulk-status`, null, {
        params: { room_ids: selectedRooms, status: newStatus }
      });
      toast.success(
        tg('bulkUpdated')
          .replace('{count}', String(selectedRooms.length))
          .replace('{label}', STATUS_CONFIG[newStatus]?.label || newStatus)
      );
      setSelectedRooms([]);
      setBulkMenuOpen(false);
      loadRooms();
      if (onChange) onChange();
    } catch (e) {
      toast.error(tg('bulkFailed'));
    }
  };

  const toggleRoom = (id) => {
    setSelectedRooms(prev => prev.includes(id) ? prev.filter(r => r !== id) : [...prev, id]);
  };

  const filteredRooms = rooms.filter(r => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (r.room_number || '').toLowerCase().includes(s) ||
           (r.room_type || '').toLowerCase().includes(s) ||
           (r.current_booking?.guest_name || '').toLowerCase().includes(s);
  });

  return (
    <div className={embedded ? 'space-y-5' : 'p-4 md:p-6 space-y-5 max-w-7xl mx-auto'} data-testid="housekeeping-room-grid">
      {!embedded && (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Bed className="w-6 h-6 text-blue-600" />
              {tg('title')}
            </h1>
            <p className="text-sm text-gray-500 mt-1">{tg('subtitle')}</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => { setLoading(true); loadRooms(); }} data-testid="refresh-btn">
            <RefreshCw className="w-4 h-4 mr-1" /> {tg('refresh')}
          </Button>
        </div>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
        {Object.entries(STATUS_CONFIG).map(([key, cfg]) => {
          const count = summary[key] || 0;
          return (
            <Card
              key={key}
              className={`cursor-pointer transition-all hover:shadow-md ${filter === key ? 'ring-2 ring-blue-400' : ''}`}
              onClick={() => setFilter(filter === key ? 'all' : key)}
              data-testid={`filter-${key}`}
            >
              <CardContent className="p-3 flex items-center gap-3">
                <div className={`w-3 h-3 rounded-full ${cfg.dot}`} />
                <div>
                  <div className="text-xl font-bold">{count}</div>
                  <div className="text-xs text-gray-500">{cfg.label}</div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Actions Bar */}
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
        <div className="relative flex-1 max-w-sm">
          <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={tg('searchPlaceholder')}
            className="pl-9 h-9"
            data-testid="search-rooms"
          />
        </div>

        {embedded && (
          <Button variant="outline" size="sm" onClick={() => { setLoading(true); loadRooms(); }} data-testid="refresh-btn-embedded">
            <RefreshCw className="w-4 h-4 mr-1" /> {tg('refresh')}
          </Button>
        )}

        {selectedRooms.length > 0 && (
          <div className="relative">
            <Button size="sm" variant="outline" onClick={() => setBulkMenuOpen(!bulkMenuOpen)} data-testid="bulk-update-btn">
              <Filter className="w-4 h-4 mr-1" /> {tg('bulkUpdate')} ({selectedRooms.length})
              <ChevronDown className="w-3 h-3 ml-1" />
            </Button>
            {bulkMenuOpen && (
              <div className="absolute top-full left-0 mt-1 bg-white border rounded-lg shadow-lg z-20 min-w-[180px]">
                {Object.entries(STATUS_CONFIG).map(([key, cfg]) => (
                  <button
                    key={key}
                    onClick={() => bulkUpdate(key)}
                    className="w-full text-left px-4 py-2 text-sm hover:bg-gray-50 flex items-center gap-2"
                  >
                    <div className={`w-2 h-2 rounded-full ${cfg.dot}`} /> {cfg.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {filter !== 'all' && (
          <Button size="sm" variant="ghost" onClick={() => setFilter('all')}>
            {tg('clearFilter')}
          </Button>
        )}
      </div>

      {/* Room Grid */}
      {loading ? (
        <div className="text-center py-12 text-gray-400">{tg('loading')}</div>
      ) : filteredRooms.length === 0 ? (
        <div className="text-center py-12 text-gray-400">{tg('noRooms')}</div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
          {filteredRooms.map(room => {
            const st = room.housekeeping_status || 'clean';
            const cfg = STATUS_CONFIG[st] || STATUS_CONFIG.clean;
            const isSelected = selectedRooms.includes(room.id);
            const hasGuest = !!room.current_booking;

            return (
              <div
                key={room.id}
                data-testid={`room-card-${room.room_number}`}
                className={`relative border rounded-xl p-3 transition-all hover:shadow-md cursor-pointer ${
                  isSelected ? 'ring-2 ring-blue-500 bg-blue-50/30' : 'bg-white'
                }`}
              >
                <div className="absolute top-2 right-2">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleRoom(room.id)}
                    className="w-4 h-4 rounded border-gray-300"
                  />
                </div>

                <div className="flex items-center gap-2 mb-2">
                  <Bed className="w-4 h-4 text-gray-400" />
                  <span className="font-bold text-lg">{room.room_number}</span>
                </div>

                <div className="text-xs text-gray-500 mb-2">{room.room_type || tg('standardType')}</div>

                <Badge className={`text-xs ${cfg.color} mb-2`}>{cfg.label}</Badge>

                {hasGuest && (
                  <div className="text-xs text-gray-600 bg-gray-50 rounded p-1.5 mb-2 truncate">
                    {room.current_booking.guest_name}
                  </div>
                )}

                <div className="flex flex-wrap gap-1 mt-2">
                  {Object.entries(STATUS_CONFIG).filter(([k]) => k !== st).map(([key, c]) => (
                    <button
                      key={key}
                      onClick={(e) => { e.stopPropagation(); updateStatus(room.id, key); }}
                      className={`text-[10px] px-1.5 py-0.5 rounded border hover:opacity-80 transition ${c.color}`}
                      title={c.label}
                      data-testid={`status-btn-${room.room_number}-${key}`}
                    >
                      {c.label}
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default HousekeepingRoomGrid;
