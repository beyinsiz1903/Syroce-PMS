import { useEffect, useMemo, useState, useCallback } from 'react';
import api from '@/api/axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Loader2, Map as MapIcon, Crown, Calendar, RefreshCw, Info, X as XIcon, Search } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import EmptyState from '@/components/EmptyState';

const today = () => new Date().toISOString().slice(0, 10);

const STATUS_META = {
  occupied:     { color: 'bg-rose-100 border-rose-300 text-rose-900',       dotCls: 'bg-rose-500',     label: 'Dolu' },
  dirty:        { color: 'bg-amber-50 border-amber-300 text-amber-900',     dotCls: 'bg-amber-500',    label: 'Kirli' },
  clean:        { color: 'bg-emerald-50 border-emerald-200 text-emerald-900', dotCls: 'bg-emerald-500', label: 'Temiz' },
  available:    { color: 'bg-white border-slate-200 text-slate-700',         dotCls: 'bg-slate-300',   label: 'Müsait' },
  out_of_order: { color: 'bg-slate-200 border-slate-400 text-slate-700',     dotCls: 'bg-slate-500',   label: 'Engelli' },
  maintenance:  { color: 'bg-slate-100 border-slate-300 text-slate-600',     dotCls: 'bg-slate-400',   label: 'Bakımda' },
};

function statusMeta(status, occupied) {
  if (occupied) return STATUS_META.occupied;
  return STATUS_META[status] || STATUS_META.available;
}

function RoomCell({ room, onDrop }) {
  const { t } = useTranslation();
  const [over, setOver] = useState(false);
  const occupied = !!room.booking;
  const meta = statusMeta(room.status, occupied);
  return (
    <div
      onDragOver={e => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={e => {
        e.preventDefault();
        setOver(false);
        const id = e.dataTransfer.getData('booking_id');
        const srcRoomId = e.dataTransfer.getData('source_room_id');
        if (!id) return;
        if (srcRoomId && String(srcRoomId) === String(room.id)) return; // aynı odaya geri bırakıldı, no-op
        onDrop(id, room.id);
      }}
      draggable={occupied}
      onDragStart={e => {
        if (occupied) {
          e.dataTransfer.setData('booking_id', room.booking.booking_id);
          e.dataTransfer.setData('source_room_id', String(room.id));
        }
      }}
      className={`border rounded-lg p-2 min-h-[92px] transition ${meta.color} ${over ? 'ring-2 ring-amber-400 ring-offset-1' : ''} ${occupied ? 'cursor-move' : ''}`}
      data-testid={`room-cell-${room.room_number}`}
    >
      <div className="flex items-center justify-between">
        <div className="font-bold text-sm">{room.room_number}</div>
        <span className={`w-2 h-2 rounded-full ${meta.dotCls}`} title={meta.label} />
      </div>
      {occupied ? (
        <div className="mt-1.5 text-xs">
          <div className="font-semibold flex items-center gap-1 truncate">
            {room.booking.vip && <Crown className="w-3 h-3 text-amber-600" />}
            {room.booking.guest_name}
          </div>
          <div className="text-[11px] opacity-75 mt-0.5">
            {room.booking.adults}+{room.booking.children} · {room.booking.check_out?.slice(5)} {t('cm.pages_RoomMapPage.cikis')}
          </div>
        </div>
      ) : (
        <div className="text-[11px] mt-2 opacity-70">{meta.label}{room.room_type ? ` · ${room.room_type}` : ''}</div>
      )}
    </div>
  );
}

function UnassignedItem({ b }) {
  return (
    <div
      draggable
      onDragStart={e => e.dataTransfer.setData('booking_id', b.booking_id)}
      className="border border-sky-300 bg-sky-50 rounded p-2 cursor-move text-xs hover:border-sky-400 transition"
    >
      <div className="font-semibold flex items-center gap-1 truncate">
        {b.vip && <Crown className="w-3 h-3 text-amber-600" />}
        {b.guest_name}
      </div>
      <div className="text-[10px] text-slate-600">{b.check_in?.slice(5)} → {b.check_out?.slice(5)} · {b.adults}+{b.children}</div>
    </div>
  );
}

export default function RoomMapPage({ user, tenant, onLogout }) {
  const { t } = useTranslation();
  const [date, setDate] = useState(today());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [hintOpen, setHintOpen] = useState(true);
  const [query, setQuery] = useState('');

  // İpucu otomatik kapansın
  useEffect(() => {
    const t = setTimeout(() => setHintOpen(false), 6000);
    return () => clearTimeout(t);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/pms/room-map', { params: { business_date: date } });
      setData(data);
    } catch (e) { toast.error('Yükleme hatası'); }
    finally { setLoading(false); }
  }, [date]);

  useEffect(() => { load(); }, [load]);

  const assign = async (booking_id, room_id) => {
    try {
      await api.post('/pms/room-map/assign', { booking_id, room_id, business_date: date });
      toast.success('Oda değiştirildi');
      load();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  // Arama: misafir adı veya oda numarasına göre filtrele (büyük/küçük harf
  // duyarsız). Boş sorguda tüm odalar gösterilir.
  const q = query.trim().toLowerCase();
  const matchRoom = useCallback((r) => {
    if (!q) return true;
    const roomNo = String(r.room_number ?? '').toLowerCase();
    const guest = (r.booking?.guest_name ?? '').toLowerCase();
    return roomNo.includes(q) || guest.includes(q);
  }, [q]);

  // Memoize: oda sayısı 200+ olabilen tesislerde her drag-hover render'ında
  // tekrar hesaplama gereksiz idi (RoomCell child state setOver tetikliyor).
  const byFloor = useMemo(() => {
    return (data?.rooms || []).filter(matchRoom).reduce((acc, r) => {
      const f = r.floor ?? '—';
      (acc[f] = acc[f] || []).push(r);
      return acc;
    }, {});
  }, [data, matchRoom]);

  // Atanmamış rezervasyonlar yalnızca misafir adıyla aranır (oda numarası yok).
  const filteredUnassigned = useMemo(() => {
    const list = data?.unassigned || [];
    if (!q) return list;
    return list.filter(b => (b.guest_name ?? '').toLowerCase().includes(q));
  }, [data, q]);

  const matchCount = useMemo(
    () => Object.values(byFloor).reduce((n, rooms) => n + rooms.length, 0),
    [byFloor]
  );

  return (
    <>
      <div className="p-4 md:p-6 space-y-4" data-testid="room-map-page">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2 text-slate-900">
              <MapIcon className="w-6 h-6 text-amber-600" /> {t('cm.pages_RoomMapPage.oda_haritasi')}
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              {new Date(date).toLocaleDateString('tr-TR', { day: '2-digit', month: 'long', year: 'numeric' })}
              {data?.rooms && <> · {data.rooms.length} oda</>}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              <Input
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Misafir adı veya oda no ara"
                data-testid="room-map-search"
                className="h-9 w-56 pl-8 pr-8"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700"
                  aria-label="Aramayı temizle"
                >
                  <XIcon className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
            <Calendar className="w-4 h-4 text-slate-500" />
            <Input type="date" value={date} onChange={e => setDate(e.target.value)} className="h-9 w-40" />
            <Button size="sm" variant="outline" onClick={load} className="border-slate-300">
              <RefreshCw className="w-3 h-3 mr-1" /> {t('cm.pages_RoomMapPage.yenile')}
            </Button>
          </div>
        </div>

        {/* Renk lejandı */}
        <div className="flex items-center gap-3 flex-wrap text-xs bg-white border border-slate-200 rounded-lg px-3 py-2">
          <span className="text-slate-500 font-medium uppercase tracking-wide text-[10px]">Lejant:</span>
          {[
            ['available', 'Müsait'],
            ['occupied', 'Dolu'],
            ['dirty', 'Kirli'],
            ['clean', 'Temiz'],
            ['out_of_order', 'Engelli'],
          ].map(([k, l]) => {
            const m = STATUS_META[k];
            return (
              <span key={k} className="inline-flex items-center gap-1.5 text-slate-700">
                <span className={`w-2.5 h-2.5 rounded-full ${m.dotCls}`} />
                {l}
              </span>
            );
          })}
        </div>

        {/* Sürükle-bırak ipucu */}
        {hintOpen && (
          <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg p-2.5 text-sm text-amber-900">
            <Info className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <div className="flex-1">{t('cm.pages_RoomMapPage.misafir_kartini_baska_odaya')} <b>{t('cm.pages_RoomMapPage.surukleyip_birakarak')}</b> {t('cm.pages_RoomMapPage.oda_degisikligi_yapabilirsiniz')}</div>
            <button onClick={() => setHintOpen(false)} className="text-amber-700 hover:text-amber-900" aria-label={t('cm.pages_RoomMapPage.kapat')}>
              <XIcon className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Atanmamış rezervasyonlar */}
        {filteredUnassigned.length > 0 && (
          <Card className="p-3 bg-sky-50/40 border-sky-200">
            <div className="font-semibold text-sm mb-2 text-sky-900">
              {t('cm.pages_RoomMapPage.atanmamis_rezervasyonlar')}{filteredUnassigned.length})
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
              {filteredUnassigned.map(b => <UnassignedItem key={b.booking_id} b={b} />)}
            </div>
          </Card>
        )}

        {loading && (
          <div className="text-center py-10">
            <Loader2 className="inline w-5 h-5 animate-spin text-slate-400" />
          </div>
        )}

        {data && !loading && q && matchCount === 0 && filteredUnassigned.length === 0 && (
          <div className="text-center py-10 text-sm text-slate-500" data-testid="room-map-no-results">
            "{query.trim()}" için eşleşen oda veya misafir bulunamadı.
          </div>
        )}

        {data && !loading && !q && (data?.rooms || []).length === 0 && (
          <EmptyState
            icon={MapIcon}
            setupRequired
            title={t('emptyStates.roomMap.title')}
            description={t('emptyStates.roomMap.desc')}
          />
        )}

        {data && Object.entries(byFloor).sort().map(([floor, rooms]) => (
          <Card key={floor} className="p-3 border-slate-200">
            <div className="flex items-center justify-between mb-2">
              <div className="text-sm font-semibold text-slate-700">Kat {floor}</div>
              <div className="text-xs text-slate-500">{rooms.length} oda</div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2">
              {rooms.map(r => <RoomCell key={r.id} room={r} onDrop={assign} />)}
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}
