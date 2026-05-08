import React, { useState, useEffect, useMemo, lazy, Suspense } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { X, Calendar as CalendarIcon, User, MapPin, ArrowRight, Ban, ChevronDown } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';

import {
  CalendarHeader,
  CalendarOccupancy,
  CalendarGrid,
  NewBookingDialog,
  BookingDetailsDialog,
  MoveReasonDialog,
  FindRoomDialog,
  isBookingOnDate,
  toDateStringUTC,
  getDateRange,
  getSegmentColor,
  getStatusLabel,
  getRateTypeInfo,
  getUnassignedUrgency,
  sortByUrgency,
} from './calendar';

const ReservationSidebar = lazy(() => import('@/components/ReservationSidebar'));
const FolioDetailView = lazy(() => import('@/pages/FolioDetailView'));
const ReservationDetailModal = lazy(() => import('@/pages/ReservationDetailModal'));

const DEBUG_ROOMS = false;

const ReservationCalendar = ({ user, tenant, onLogout }) => {
  const navigate = useNavigate();

  // Core state
  const [rooms, setRooms] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [guests, setGuests] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [roomBlocks, setRoomBlocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [currentDate, setCurrentDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 3);
    return d;
  });
  const [daysToShow, setDaysToShow] = useState(14);
  const [calendarMeta, setCalendarMeta] = useState({});
  const [hotelBusinessDate, setHotelBusinessDate] = useState(null);

  // UI State
  const [selectedRoom, setSelectedRoom] = useState(null);
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedBooking, setSelectedBooking] = useState(null);
  const [selectedBookingFolio, setSelectedBookingFolio] = useState(null);
  const [showSidebar, setShowSidebar] = useState(false);
  const [showNewBookingDialog, setShowNewBookingDialog] = useState(false);
  const [showDetailsDialog, setShowDetailsDialog] = useState(false);
  const [showFindRoomDialog, setShowFindRoomDialog] = useState(false);
  const [showMoveReasonDialog, setShowMoveReasonDialog] = useState(false);
  const [showFolioPanel, setShowFolioPanel] = useState(false);
  const [folioPanelId, setFolioPanelId] = useState(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [detailModalBookingId, setDetailModalBookingId] = useState(null);
  const [showUnassignedPanel, setShowUnassignedPanel] = useState(false);
  const [unassignedFilter, setUnassignedFilter] = useState('all');

  // No-Show Reason Dialog
  const [showNoShowDialog, setShowNoShowDialog] = useState(false);
  const [noShowBookingId, setNoShowBookingId] = useState(null);
  const [noShowReason, setNoShowReason] = useState('misafir_gelmedi');
  const [noShowProcessing, setNoShowProcessing] = useState(false);

  // Drag & Drop
  const [draggingBooking, setDraggingBooking] = useState(null);
  const [dragOverCell, setDragOverCell] = useState(null);
  const [moveData, setMoveData] = useState(null);
  const [moveReason, setMoveReason] = useState('');

  // Enterprise / AI Mode
  const [showEnterprisePanel, setShowEnterprisePanel] = useState(false);
  const [rateLeakages, setRateLeakages] = useState([]);
  const [availabilityHeatmap, setAvailabilityHeatmap] = useState([]);
  const [showAIPanel, setShowAIPanel] = useState(false);
  const [aiOverbookingSolutions, setAiOverbookingSolutions] = useState([]);
  const [aiRoomMoves, setAiRoomMoves] = useState([]);
  const [aiRateRecommendations, setAiRateRecommendations] = useState([]);
  const [aiNoShowPredictions, setAiNoShowPredictions] = useState([]);
  const [showDeluxePanel, setShowDeluxePanel] = useState(false);
  const [groupBookings, setGroupBookings] = useState([]);
  const [oversellProtection, setOversellProtection] = useState([]);
  const [channelMixData, setChannelMixData] = useState(null);
  const [groupColorMap, setGroupColorMap] = useState({});

  // New booking form
  const [newBooking, setNewBooking] = useState({
    guest_id: '', room_id: '', check_in: '', check_out: '',
    guests_count: 2, adults: 2, children: 0, children_ages: [],
    total_amount: 0, status: 'confirmed'
  });

  // Find room
  const [findRoomCriteria, setFindRoomCriteria] = useState({
    check_in: '', check_out: '', room_type: 'all', guests_count: 2
  });
  const [availableRooms, setAvailableRooms] = useState([]);

  // Conflicts
  // conflicts: derived from bookings/rooms via useMemo (no state, no extra render).
  const [showConflictsModal, setShowConflictsModal] = useState(false);

  const dateRange = getDateRange(currentDate, daysToShow);

  // ─── Data Loading ─────────────────────────────────────────────
  // Race-safe: hızlı ok navigasyonunda eski fetch sonucu yeni state'i ezmesin.
  // useEffect cleanup ile cancelled flag set edilir; yarışı kaybeden response
  // setBookings çağırmaz.
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  useEffect(() => {
    let cancelled = false;
    loadCalendarData(() => cancelled);
    return () => { cancelled = true; };
  }, [currentDate, daysToShow]);

  // Fetch hotel business date once on mount
  useEffect(() => {
    axios.get('/night-audit/business-date')
      .then(res => {
        const bd = res.data?.business_date;
        if (bd) setHotelBusinessDate(bd);
      })
      .catch(() => {
        // Fallback: use today if business date endpoint fails
        setHotelBusinessDate(new Date().toISOString().split('T')[0]);
      });
  }, []);

  const loadCalendarData = async (isCancelled = () => false) => {
    // İlk yüklemede full-screen spinner; sonraki fetch'lerde mevcut takvimi
    // koru (boş ekran flash yok). bookings.length === 0 = ilk yükleme.
    const isInitialLoad = bookings.length === 0;
    if (isInitialLoad) setLoading(true);
    try {
      const startDate = new Date(currentDate);
      startDate.setDate(startDate.getDate() - 7);
      const endDate = new Date(currentDate);
      endDate.setDate(endDate.getDate() + daysToShow + 7);

      const [roomsRes, bookingsRes, guestsRes, companiesRes, blocksRes] = await Promise.all([
        axios.get('/pms/rooms'),
        axios.get(`/pms/bookings?start_date=${startDate.toISOString().split('T')[0]}&end_date=${endDate.toISOString().split('T')[0]}&limit=500`),
        axios.get('/pms/guests').catch(() => ({ data: [] })),
        axios.get('/companies').catch(() => ({ data: [] })),
        axios.get('/pms/room-blocks?status=active').catch(() => ({ data: { blocks: [] } }))
      ]);

      // Race guard: bu fetch tamamlanırken kullanıcı yeni navigasyon yaptıysa
      // eski response state'i ezmemeli.
      if (isCancelled()) return;

      setCalendarMeta({
        start_date: startDate.toISOString().split('T')[0],
        end_date: endDate.toISOString().split('T')[0],
        rooms: roomsRes.data?.length || 0,
        bookings: bookingsRes.data?.length || 0,
      });
      setRooms(roomsRes.data || []);
      setBookings(bookingsRes.data || []);
      setGuests(guestsRes.data || []);
      setCompanies(companiesRes.data || []);
      setRoomBlocks(blocksRes.data.blocks || []);

      // Build group bookings summary
      const rawBookings = bookingsRes.data || [];
      const groupMap = new Map();
      rawBookings.forEach(b => {
        if (!b.group_booking_id) return;
        if (!groupMap.has(b.group_booking_id)) groupMap.set(b.group_booking_id, []);
        groupMap.get(b.group_booking_id).push(b);
      });
      const groupSummary = Array.from(groupMap.entries()).map(([groupId, groupItems]) => {
        const master = groupItems[0];
        return {
          group_booking_id: groupId,
          totalRooms: groupItems.length,
          totalAmount: groupItems.reduce((sum, x) => sum + (x.total_amount || 0), 0),
          master,
          bookings: groupItems,
          guest_name: master.guest_name || guestsRes.data.find(g => g.id === master.guest_id)?.name || 'Group Guest'
        };
      });
      setGroupBookings(groupSummary);
    } catch (error) {
      console.error('Takvim verileri yüklenemedi:', error);
      toast.error('Takvim verileri yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  // Opens Reports tab Pickup Pace for a given arrival date
  const openPickupPaceForDate = (dateStr) => {
    if (!dateStr) return;
    try { localStorage.setItem('pickup_target_date', dateStr); } catch (e) { /* noop */ }
    window.open('/pms?tab=reports', '_blank');
  };

  // ─── Sync Reservations ──────────────────────────────────────
  const handleSyncReservations = async () => {
    setSyncing(true);
    try {
      let totalImported = 0, totalCancelled = 0, synced = false;

      try {
        const exelyRes = await axios.post('/channel-manager/exely/sync/reservations/pull');
        const d = exelyRes.data || {};
        totalImported += d.auto_imported || d.processed || 0;
        totalCancelled += d.cancelled || 0;
        synced = true;
      } catch (e) { if (e.response?.status !== 404) console.warn('Exely sync error:', e); }

      try {
        const connectorsRes = await axios.get('/channel-manager/v2/connectors');
        const connectors = Array.isArray(connectorsRes.data) ? connectorsRes.data : [];
        const sDate = new Date(); sDate.setDate(sDate.getDate() - 7);
        const eDate = new Date(); eDate.setMonth(eDate.getMonth() + 3);
        for (const conn of connectors) {
          try {
            const result = await axios.post('/channel-manager/v2/reservations/pull', {
              connector_id: conn.id,
              date_start: sDate.toISOString().split('T')[0],
              date_end: eDate.toISOString().split('T')[0],
            });
            totalImported += result.data?.imported || result.data?.new || 0;
            totalCancelled += result.data?.cancelled || 0;
            synced = true;
          } catch (e) { console.warn(`Sync failed for connector ${conn.id}:`, e); }
        }
      } catch (e) { if (e.response?.status !== 404) console.warn('v2 connector sync error:', e); }

      if (!synced) { toast.info('Aktif kanal bağlantısı bulunamadı'); setSyncing(false); return; }
      if (totalImported > 0 || totalCancelled > 0) {
        toast.success(`Senkronizasyon tamamlandi: ${totalImported} yeni, ${totalCancelled} iptal`);
      } else {
        toast.info('Yeni rezervasyon değişikliği bulunamadı');
      }
      await loadCalendarData();
    } catch (error) {
      console.error('Sync failed:', error);
      toast.error('Senkronizasyon başarısız');
    } finally { setSyncing(false); }
  };

  // ─── Enterprise / AI / Deluxe Data Loading ─────────────────
  const loadEnterpriseData = async ({ roomsCount } = {}) => {
    try {
      if (typeof roomsCount === 'number' && roomsCount === 0) { setRateLeakages([]); setAvailabilityHeatmap([]); return; }
      const sd = currentDate.toISOString().split('T')[0];
      const ed = new Date(currentDate.getTime() + daysToShow * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
      const [leakageRes, heatmapRes] = await Promise.all([
        axios.get(`/enterprise/rate-leakage?start_date=${sd}&end_date=${ed}`).catch(() => ({ data: { leakages: [] } })),
        axios.get(`/enterprise/availability-heatmap?start_date=${sd}&end_date=${ed}`).catch(() => ({ data: { heatmap: [] } }))
      ]);
      setRateLeakages(leakageRes.data.leakages || []);
      setAvailabilityHeatmap(heatmapRes.data.heatmap || []);
    } catch (error) { console.error('Failed to load enterprise data:', error); }
  };

  const loadAIRecommendations = async () => {
    try {
      const today = new Date().toISOString().split('T')[0];
      const sd = currentDate.toISOString().split('T')[0];
      const ed = new Date(currentDate.getTime() + daysToShow * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
      const [overbookingRes, roomMovesRes, ratesRes, noShowRes] = await Promise.all([
        axios.post('/ai/solve-overbooking', null, { params: { date: today } }).catch(() => ({ data: { solutions: [] } })),
        axios.post('/ai/recommend-room-moves', null, { params: { date: today } }).catch(() => ({ data: { recommendations: [] } })),
        axios.post('/ai/recommend-rates', null, { params: { start_date: sd, end_date: ed } }).catch(() => ({ data: { recommendations: [] } })),
        axios.post('/ai/predict-no-shows', null, { params: { date: today } }).catch(() => ({ data: { predictions: [] } }))
      ]);
      setAiOverbookingSolutions(overbookingRes.data.solutions || []);
      setAiRoomMoves(roomMovesRes.data.recommendations || []);
      setAiRateRecommendations(ratesRes.data.recommendations || []);
      setAiNoShowPredictions(noShowRes.data.predictions || []);
    } catch (error) { console.error('Failed to load AI recommendations:', error); }
  };

  const loadDeluxeFeatures = async () => {
    try {
      const sd = currentDate.toISOString().split('T')[0];
      const ed = new Date(currentDate.getTime() + daysToShow * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
      const [groupsRes, oversellRes, channelRes] = await Promise.all([
        axios.get(`/deluxe/group-bookings?start_date=${sd}&end_date=${ed}&min_rooms=5`).catch(() => ({ data: { groups: [] } })),
        axios.get(`/deluxe/oversell-protection?start_date=${sd}&end_date=${ed}`).catch(() => ({ data: { protection_map: [] } })),
        axios.post('/deluxe/optimize-channel-mix', { start_date: sd, end_date: ed }).catch(() => ({ data: null }))
      ]);
      setGroupBookings(groupsRes.data.groups || []);
      setOversellProtection(oversellRes.data.protection_map || []);
      setChannelMixData(channelRes.data);
    } catch (error) { console.error('Failed to load deluxe features:', error); }
  };

  // ─── Conflict Detection ────────────────────────────────────
  // Bookings group is bucketed by room_id once (O(N)); the per-room O(k²)
  // overlap check then runs only on each room's small subset, instead of
  // the previous O(rooms × bookings²) double scan that re-ran on every
  // booking change. Result memoized so no setState/re-render churn.
  const conflicts = useMemo(() => {
    if (!bookings.length || !rooms.length) return [];
    const SKIPPED = new Set(['cancelled', 'checked_out', 'no_show']);
    const byRoom = new Map();
    for (const b of bookings) {
      if (SKIPPED.has(b.status) || !b.room_id) continue;
      let arr = byRoom.get(b.room_id);
      if (!arr) { arr = []; byRoom.set(b.room_id, arr); }
      arr.push(b);
    }
    const out = [];
    for (const room of rooms) {
      const roomBookings = byRoom.get(room.id);
      if (!roomBookings || roomBookings.length < 2) continue;
      for (let i = 0; i < roomBookings.length; i++) {
        const b1 = roomBookings[i];
        const s1 = new Date(b1.check_in).getTime();
        const e1 = new Date(b1.check_out).getTime();
        for (let j = i + 1; j < roomBookings.length; j++) {
          const b2 = roomBookings[j];
          const s2 = new Date(b2.check_in).getTime();
          const e2 = new Date(b2.check_out).getTime();
          if (s1 < e2 && s2 < e1) {
            out.push({
              type: 'overbooking', room_id: room.id, room_number: room.room_number,
              booking1_id: b1.id, booking2_id: b2.id,
              guest1: b1.guest_name, guest2: b2.guest_name,
              overlap_start: new Date(s1 > s2 ? s1 : s2),
              overlap_end: new Date(e1 < e2 ? e1 : e2)
            });
          }
        }
      }
    }
    return out;
  }, [bookings, rooms]);

  // ─── Occupancy ─────────────────────────────────────────────
  const getOccupancyForDate = (date) => {
    const activeStatuses = ['confirmed', 'guaranteed', 'checked_in'];
    const occupiedCount = bookings.filter(b =>
      isBookingOnDate(b, date) &&
      activeStatuses.includes(b.status) &&
      b.status !== 'cancelled' && b.status !== 'checked_out' && b.status !== 'no_show'
    ).length;
    return rooms.length > 0 ? Math.min(Math.round((occupiedCount / rooms.length) * 100), 100) : 0;
  };

  // ─── Event Handlers ────────────────────────────────────────
  const handleCellClick = (roomId, date) => {
    const room = rooms.find(r => r.id === roomId);
    if (!room) return;

    // Gecmis tarih kontrolu: PMS business date hala aktif is gunudur.
    // Gun sonu yapilmadiysa business_date takvim tarihinden geride kalir
    // (orn: business=05-May, takvim=06-May). Bu durumda 05-May'a hala
    // rezervasyon yapilabilmeli — min(business_date, today) kullaniyoruz.
    const today = new Date().toISOString().split('T')[0];
    const minDate = hotelBusinessDate && hotelBusinessDate < today ? hotelBusinessDate : today;
    const clickedDateStr = new Date(date).toISOString().split('T')[0];
    if (clickedDateStr < minDate) {
      toast.error(`Geçmiş tarihe rezervasyon yapilamaz (minimum: ${minDate})`);
      return;
    }

    setSelectedRoom(room);
    setSelectedDate(date);
    const checkInDate = new Date(date);
    const checkOutDate = new Date(date);
    checkOutDate.setDate(checkOutDate.getDate() + 1);
    setNewBooking({
      guest_id: '', room_id: roomId,
      check_in: checkInDate.toISOString().split('T')[0],
      check_out: checkOutDate.toISOString().split('T')[0],
      guests_count: 2, adults: 2, children: 0, children_ages: [],
      total_amount: room.base_price || 100, status: 'confirmed'
    });
    setShowNewBookingDialog(true);
  };

  const handleBookingDoubleClick = async (booking) => {
    setDetailModalBookingId(booking.id);
    setShowDetailModal(true);
  };

  const handleCreateBooking = async (e) => {
    e.preventDefault();

    // Gecmis tarih kontrolu: PMS business date hala aktif is gunudur
    // (gun sonu yapilmadiysa business_date takvim tarihinden geride olabilir).
    const today = new Date().toISOString().split('T')[0];
    const minDate = hotelBusinessDate && hotelBusinessDate < today ? hotelBusinessDate : today;
    if (newBooking.check_in < minDate) {
      toast.error(`Geçmiş tarihe rezervasyon yapilamaz (minimum: ${minDate})`);
      return;
    }

    let guestId = newBooking.guest_id;
    if (!guestId && newBooking.guest_name) {
      try {
        const newGuest = {
          id: `guest_${Date.now()}`, name: newBooking.guest_name,
          email: newBooking.guest_email || '', phone: newBooking.guest_phone || '',
          tenant_id: user.tenant_id, created_at: new Date().toISOString()
        };
        await axios.post('/pms/guests', newGuest);
        guestId = newGuest.id;
        toast.success('Yeni misafir oluşturuldu!');
      } catch (error) {
        toast.error('Misafir oluşturulamadı: ' + (error.response?.data?.detail || error.message));
        return;
      }
    }
    if (!guestId) { toast.error('Lutfen bir misafir seçin veya yeni misafir ekleyin'); return; }
    try {
      const idempotencyKey = globalThis.crypto?.randomUUID?.() || `booking-create-${Date.now()}-${Math.random()}`;
      await axios.post('/pms/bookings', { ...newBooking, guest_id: guestId }, {
        headers: { 'Idempotency-Key': idempotencyKey },
      });
      toast.success('Rezervasyon başarıyla oluşturuldu!');
      setShowNewBookingDialog(false);
      loadCalendarData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Rezervasyon oluşturulamadı');
    }
  };

  // ─── Drag & Drop ───────────────────────────────────────────
  const handleDragStart = (e, booking) => {
    setDraggingBooking(booking);
    e.dataTransfer.effectAllowed = 'move';
  };
  const handleDragOver = (e, roomId, date) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverCell({ roomId, date: date.toISOString() });
  };
  const handleDragLeave = () => { setDragOverCell(null); };
  const handleDragEnd = () => { setDraggingBooking(null); setDragOverCell(null); };

  const handleAssignRoom = async (booking, newRoomId) => {
    try {
      const idempotencyKey = globalThis.crypto?.randomUUID?.() || `room-assign-${Date.now()}`;
      await axios.put(`/pms/bookings/${booking.id}`, { room_id: newRoomId }, {
        headers: { 'Idempotency-Key': idempotencyKey },
      });
      const newRoom = rooms.find(r => r.id === newRoomId);
      toast.success(`Rezervasyon ${newRoom?.room_number || ''} numarali odaya atandi`);
      loadCalendarData();
    } catch (error) {
      toast.error('Oda ataması başarısız');
      console.error('Room assignment error:', error);
    }
  };

  const handleDrop = async (e, newRoomId, newDate) => {
    e.preventDefault();
    setDragOverCell(null);
    if (!draggingBooking) return;

    const { getRoomBlockForDate: getRBF } = await import('./calendar/calendarHelpers');
    const roomBlock = getRBF(newRoomId, newDate, roomBlocks);
    if (roomBlock && !roomBlock.allow_sell) {
      toast.error(`Cannot move booking: Room is ${roomBlock.type.replace('_', ' ')} (${roomBlock.reason})`);
      setDraggingBooking(null);
      return;
    }

    if (!draggingBooking.room_id) {
      setDraggingBooking(null);
      await handleAssignRoom(draggingBooking, newRoomId);
      return;
    }

    const oldRoomId = draggingBooking.room_id;
    const oldDate = new Date(draggingBooking.check_in);
    if (oldRoomId === newRoomId && oldDate.toDateString() === newDate.toDateString()) {
      setDraggingBooking(null);
      return;
    }

    const daysDiff = Math.ceil((new Date(draggingBooking.check_out) - new Date(draggingBooking.check_in)) / (1000 * 60 * 60 * 24));
    const newCheckIn = new Date(newDate);
    const newCheckOut = new Date(newDate);
    newCheckOut.setDate(newCheckOut.getDate() + daysDiff);

    const oldRoom = rooms.find(r => r.id === oldRoomId);
    const newRoom = rooms.find(r => r.id === newRoomId);

    setMoveData({
      booking: draggingBooking,
      oldRoom: oldRoom?.room_number, newRoom: newRoom?.room_number,
      oldCheckIn: draggingBooking.check_in,
      newCheckIn: newCheckIn.toISOString().split('T')[0],
      newCheckOut: newCheckOut.toISOString().split('T')[0],
      newRoomId
    });
    setShowMoveReasonDialog(true);
    setDraggingBooking(null);
  };

  const handleConfirmMove = async () => {
    if (!moveReason.trim()) { toast.error('Please provide a reason for the room move'); return; }
    try {
      const idempotencyKey = globalThis.crypto?.randomUUID?.() || `booking-move-${Date.now()}-${Math.random()}`;
      await axios.put(`/pms/bookings/${moveData.booking.id}`, {
        room_id: moveData.newRoomId,
        check_in: moveData.newCheckIn,
        check_out: moveData.newCheckOut
      }, { headers: { 'Idempotency-Key': idempotencyKey } });

      await axios.post('/pms/room-move-history', {
        booking_id: moveData.booking.id,
        old_room: moveData.oldRoom, new_room: moveData.newRoom,
        old_check_in: moveData.oldCheckIn, new_check_in: moveData.newCheckIn,
        reason: moveReason, moved_by: user.name,
        timestamp: new Date().toISOString()
      }).catch(() => { /* history logging best-effort, silent on failure */ });

      toast.success(`Rezervasyon ${moveData.newRoom} numarali odaya tasindi!`);
      setShowMoveReasonDialog(false);
      setMoveReason('');
      setMoveData(null);
      loadCalendarData();
    } catch (error) {
      toast.error('Rezervasyon taşınamadı');
      console.error('Move booking error:', error);
    }
  };

  // ─── Find Room ─────────────────────────────────────────────
  const handleFindRoom = async () => {
    if (!findRoomCriteria.check_in || !findRoomCriteria.check_out) {
      toast.error('Please select check-in and check-out dates');
      return;
    }
    const checkIn = new Date(findRoomCriteria.check_in);
    const checkOut = new Date(findRoomCriteria.check_out);
    const available = rooms.filter(room => {
      if (findRoomCriteria.room_type !== 'all' && room.room_type !== findRoomCriteria.room_type) return false;
      if (room.capacity < findRoomCriteria.guests_count) return false;
      const roomBookings = bookings.filter(b => b.room_id === room.id && b.status !== 'cancelled' && b.status !== 'checked_out' && b.status !== 'no_show');
      return !roomBookings.some(b => {
        const bStart = new Date(b.check_in);
        const bEnd = new Date(b.check_out);
        return checkIn < bEnd && checkOut > bStart;
      });
    });
    setAvailableRooms(available);
  };

  // ─── Folio / Sidebar ──────────────────────────────────────
  const handleViewFolio = async (bookingId) => {
    if (selectedBookingFolio && selectedBookingFolio.id) {
      setFolioPanelId(selectedBookingFolio.id);
      setShowFolioPanel(true);
      return;
    }
    try {
      const folioRes = await axios.get(`/folio/booking/${bookingId}`);
      if (folioRes.data && folioRes.data.length > 0) {
        setFolioPanelId(folioRes.data[0].id);
        setShowFolioPanel(true);
      } else {
        toast.info('Bu rezervasyon için henüz folyo olusturulmamis');
      }
    } catch (error) {
      toast.error('Folyo yüklenemedi');
    }
  };

  const handleEditReservation = (booking) => {
    setShowSidebar(false);
    setShowDetailsDialog(false);
    const target = booking || selectedBooking;
    const id = target?.id;
    // Persist the full booking object so PMSModule can open the detail
    // dialog even when the booking is outside its loaded date range.
    if (target && typeof window !== 'undefined' && window.sessionStorage) {
      try { window.sessionStorage.setItem('pms_edit_booking', JSON.stringify(target)); } catch { /* ignore */ }
    }
    if (id) {
      navigate(`/app/pms?edit=${id}#bookings`);
    } else {
      navigate('/app/pms#bookings');
    }
  };

  const handleSendConfirmation = async (booking) => {
    try {
      await axios.post(`/whatsapp/send-confirmation?booking_id=${booking.id}`);
      toast.success('Onay mesaji gonderildi!');
    } catch (error) {
      const detail = error.response?.data?.detail;
      if (detail && detail.includes('telefon')) {
        toast.error('Misafir telefon numarası bulunamadı');
      } else {
        toast.info('Onay mesaji gondermek için WhatsApp entegrasyonu gereklidir');
      }
    }
  };

  // ─── No-Show Handler ────────────────────────────────────────
  const handleNoShowConfirm = async () => {
    if (!noShowBookingId) return;
    setNoShowProcessing(true);
    try {
      await axios.post('/pms/bookings/no-show-virtual', {
        booking_id: noShowBookingId,
        charge_first_night: false,
        no_show_reason: noShowReason,
      });
      toast.success('No-show işlemi tamamlandi, sanal odaya atandi');
      setShowNoShowDialog(false);
      setNoShowBookingId(null);
      setNoShowReason('misafir_gelmedi');
      loadCalendarData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'No-show işlemi başarısız');
    } finally {
      setNoShowProcessing(false);
    }
  };

  // ─── Toggle Handlers ──────────────────────────────────────
  const toggleAIMode = () => {
    const newState = !showAIPanel;
    setShowAIPanel(newState);
    if (newState && (calendarMeta.rooms || 0) > 0) loadAIRecommendations();
  };

  const toggleDeluxeMode = () => {
    const newState = !showDeluxePanel;
    setShowDeluxePanel(newState);
    if (newState && (calendarMeta.rooms || 0) > 0) loadDeluxeFeatures();
  };

  const toggleEnterprise = () => {
    const newState = !showEnterprisePanel;
    setShowEnterprisePanel(newState);
    if (newState) loadEnterpriseData({ roomsCount: rooms.length });
  };

  // ─── Navigation ────────────────────────────────────────────
  const SCROLL_DAYS = Math.max(3, Math.floor(daysToShow / 3));
  const navigatePrevious = () => {
    const nd = new Date(currentDate);
    nd.setDate(nd.getDate() - SCROLL_DAYS);
    setCurrentDate(nd);
  };
  const navigateNext = () => {
    const nd = new Date(currentDate);
    nd.setDate(nd.getDate() + SCROLL_DAYS);
    setCurrentDate(nd);
  };
  const goToDate = (date) => { setCurrentDate(date); };

  // ─── Loading State ─────────────────────────────────────────
  if (loading) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="reservation_calendar">
        <div className="flex items-center justify-center h-screen">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600"></div>
        </div>
      </Layout>
    );
  }

  // ─── Render ────────────────────────────────────────────────
  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="calendar">
      <div className="flex flex-col h-[calc(100vh-72px)] overflow-hidden">
        <div className="flex-none p-4 pb-3 bg-gray-50 border-b border-gray-200 space-y-3" data-testid="calendar-sticky-header">
        <CalendarHeader
          dateRange={dateRange}
          daysToShow={daysToShow}
          setDaysToShow={setDaysToShow}
          bookings={bookings}
          conflicts={conflicts}
          syncing={syncing}
          showEnterprisePanel={showEnterprisePanel}
          showAIPanel={showAIPanel}
          onNavigatePrevious={navigatePrevious}
          onNavigateNext={navigateNext}
          onGoToDate={goToDate}
          onSyncReservations={handleSyncReservations}
          onToggleEnterprise={toggleEnterprise}
          onToggleAI={toggleAIMode}
          onShowFindRoomDialog={() => setShowFindRoomDialog(true)}
          onShowNewBookingDialog={() => {
            setSelectedRoom(null);
            setNewBooking({
              guest_id: '', room_id: '', check_in: '', check_out: '',
              guests_count: 2, adults: 2, children: 0, children_ages: [],
              total_amount: 0, status: 'confirmed'
            });
            setShowNewBookingDialog(true);
          }}
          onShowUnassigned={() => setShowUnassignedPanel(true)}
          onShowConflicts={() => setShowConflictsModal(true)}
        />
        </div>

        <div className="flex-1 overflow-auto p-4 pt-3 space-y-3">
        <CalendarOccupancy
          dateRange={dateRange}
          getOccupancyForDate={getOccupancyForDate}
          showDeluxePanel={showDeluxePanel}
          onToggleDeluxe={toggleDeluxeMode}
        />

        {/* Compact Legend */}
        <div className="bg-white border rounded-lg px-4 py-2" data-testid="calendar-legend">
          <div className="flex items-center justify-between text-xs text-gray-500">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded" style={{ backgroundColor: '#16a34a' }}></div>
                <span>Iceride (Check-in)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded" style={{ backgroundColor: '#f97316' }}></div>
                <span>Bugün Gelis</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded" style={{ backgroundColor: '#2563eb' }}></div>
                <span>Onaylanmis</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded" style={{ backgroundColor: '#f87171' }}></div>
                <span>Geçmiş / Check-out</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full bg-green-500"></div>
                <span>Müsait</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full bg-red-500"></div>
                <span>Dolu</span>
              </div>
            </div>
            <div className="flex items-center gap-3 text-gray-400">
              <span>Tıkla = Yeni rez.</span>
              <span>Çift tıkla = Detay</span>
              <span>Sürükle = Taşı</span>
            </div>
          </div>
        </div>

        <CalendarGrid
          rooms={rooms}
          bookings={bookings}
          roomBlocks={roomBlocks}
          dateRange={dateRange}
          daysToShow={daysToShow}
          currentDate={currentDate}
          conflicts={conflicts}
          draggingBooking={draggingBooking}
          dragOverCell={dragOverCell}
          showAIPanel={showAIPanel}
          showDeluxePanel={showDeluxePanel}
          groupColorMap={groupColorMap}
          setGroupColorMap={setGroupColorMap}
          rateLeakages={rateLeakages}
          aiRoomMoves={aiRoomMoves}
          aiOverbookingSolutions={aiOverbookingSolutions}
          aiNoShowPredictions={aiNoShowPredictions}
          groupBookings={groupBookings}
          onCellClick={handleCellClick}
          onDragStart={handleDragStart}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onDragEnd={handleDragEnd}
          onBookingDoubleClick={handleBookingDoubleClick}
        />

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="pt-6">
              <div className="text-sm text-gray-600">Total Rooms</div>
              <div className="text-3xl font-bold">{rooms.length}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-sm text-gray-600">Active Bookings</div>
              <div className="text-3xl font-bold text-blue-600">
                {bookings.filter(b => b.status === 'confirmed' || b.status === 'checked_in').length}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-sm text-gray-600">In-House</div>
              <div className="text-3xl font-bold text-green-600">
                {bookings.filter(b => b.status === 'checked_in').length}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-sm text-gray-600">Occupancy Today</div>
              <div className="text-3xl font-bold text-indigo-600">
                {rooms.length > 0
                  ? Math.round((bookings.filter(b => isBookingOnDate(b, new Date()) && b.status === 'checked_in').length / rooms.length) * 100)
                  : 0}%
              </div>
            </CardContent>
          </Card>
        </div>
        </div>
      </div>

      {/* Dialogs */}
      <NewBookingDialog
        open={showNewBookingDialog}
        onOpenChange={setShowNewBookingDialog}
        newBooking={newBooking}
        setNewBooking={setNewBooking}
        selectedRoom={selectedRoom}
        guests={guests}
        rooms={rooms}
        onSubmit={handleCreateBooking}
        minDate={(() => { const t = new Date().toISOString().split('T')[0]; return hotelBusinessDate && hotelBusinessDate < t ? hotelBusinessDate : t; })()}
      />

      <Dialog open={showConflictsModal} onOpenChange={setShowConflictsModal}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto" data-testid="conflicts-modal">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-600">
              <Ban className="w-5 h-5" />
              Çakışan Rezervasyonlar ({conflicts.length})
            </DialogTitle>
          </DialogHeader>
          {conflicts.length === 0 ? (
            <div className="py-6 text-center text-sm text-gray-500">Çakışma kalmadı.</div>
          ) : (
            <div className="space-y-3">
              <p className="text-xs text-gray-600">
                Aynı odaya aynı tarihlerde birden fazla rezervasyon atanmış. Sorunu çözmek için aşağıdaki rezervasyonlardan birini açıp odasını değiştirin veya iptal edin.
              </p>
              {conflicts.map((c, idx) => {
                const b1 = bookings.find(b => b.id === c.booking1_id);
                const b2 = bookings.find(b => b.id === c.booking2_id);
                const fmt = (d) => d instanceof Date ? d.toLocaleDateString('tr-TR') : new Date(d).toLocaleDateString('tr-TR');
                const openBooking = (booking) => {
                  if (!booking) return;
                  setSelectedBooking(booking);
                  setShowConflictsModal(false);
                  setShowDetailsDialog(true);
                };
                return (
                  <div key={idx} className="border border-red-200 rounded-lg p-3 bg-red-50/50" data-testid={`conflict-row-${idx}`}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="font-semibold text-sm text-red-700">
                        Oda {c.room_number || c.room_id}
                      </div>
                      <div className="text-xs text-gray-600">
                        Çakışma: {fmt(c.overlap_start)} – {fmt(c.overlap_end)}
                      </div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => openBooking(b1)}
                        disabled={!b1}
                        className="text-left p-2 bg-white border rounded hover:bg-amber-50 hover:border-amber-300 transition disabled:opacity-50 disabled:cursor-not-allowed"
                        data-testid={`conflict-open-b1-${idx}`}
                      >
                        <div className="text-xs text-gray-500">Rezervasyon 1</div>
                        <div className="text-sm font-medium truncate">{c.guest1 || '(misafir bilinmiyor)'}</div>
                        {b1 && <div className="text-xs text-gray-600">{fmt(b1.check_in)} → {fmt(b1.check_out)}</div>}
                        <div className="text-xs text-amber-600 mt-1">Aç ve düzenle →</div>
                      </button>
                      <button
                        type="button"
                        onClick={() => openBooking(b2)}
                        disabled={!b2}
                        className="text-left p-2 bg-white border rounded hover:bg-amber-50 hover:border-amber-300 transition disabled:opacity-50 disabled:cursor-not-allowed"
                        data-testid={`conflict-open-b2-${idx}`}
                      >
                        <div className="text-xs text-gray-500">Rezervasyon 2</div>
                        <div className="text-sm font-medium truncate">{c.guest2 || '(misafir bilinmiyor)'}</div>
                        {b2 && <div className="text-xs text-gray-600">{fmt(b2.check_in)} → {fmt(b2.check_out)}</div>}
                        <div className="text-xs text-amber-600 mt-1">Aç ve düzenle →</div>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowConflictsModal(false)}>Kapat</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <BookingDetailsDialog
        open={showDetailsDialog}
        onOpenChange={setShowDetailsDialog}
        selectedBooking={selectedBooking}
        rooms={rooms}
        onEdit={handleEditReservation}
        onMoved={loadCalendarData}
      />

      <MoveReasonDialog
        open={showMoveReasonDialog}
        onOpenChange={(open) => {
          setShowMoveReasonDialog(open);
          if (!open) { setMoveReason(''); setMoveData(null); }
        }}
        moveData={moveData}
        moveReason={moveReason}
        setMoveReason={setMoveReason}
        onConfirmMove={handleConfirmMove}
      />

      <FindRoomDialog
        open={showFindRoomDialog}
        onOpenChange={setShowFindRoomDialog}
        findRoomCriteria={findRoomCriteria}
        setFindRoomCriteria={setFindRoomCriteria}
        availableRooms={availableRooms}
        rooms={rooms}
        onFindRoom={handleFindRoom}
        onSelectRoom={(room) => {
          handleCellClick(room.id, new Date(findRoomCriteria.check_in));
          setShowFindRoomDialog(false);
        }}
      />

      {/* Reservation Details Sidebar */}
      {showSidebar && (
        <>
          <div className="fixed inset-0 bg-black bg-opacity-50 z-40" onClick={() => setShowSidebar(false)}></div>
          <ReservationSidebar
            booking={selectedBooking}
            folio={selectedBookingFolio}
            room={rooms.find(r => r.id === selectedBooking?.room_id)}
            onClose={() => setShowSidebar(false)}
            getSegmentColor={getSegmentColor}
            getStatusLabel={getStatusLabel}
            getRateTypeInfo={getRateTypeInfo}
            onViewFolio={handleViewFolio}
            onEditReservation={handleEditReservation}
            onSendConfirmation={handleSendConfirmation}
            onDataRefresh={loadCalendarData}
          />
        </>
      )}

      {/* Inline Folio Panel */}
      {showFolioPanel && folioPanelId && (
        <>
          <div
            className="fixed inset-0 bg-black/40 z-50 transition-opacity"
            onClick={() => setShowFolioPanel(false)}
            data-testid="folio-panel-backdrop"
          ></div>
          <div className="fixed top-0 right-0 h-full w-[700px] max-w-[90vw] bg-white z-50 shadow-2xl overflow-y-auto animate-in slide-in-from-right" data-testid="folio-inline-panel">
            <div className="sticky top-0 z-10 bg-white border-b px-4 py-3 flex items-center justify-between">
              <h3 className="font-semibold text-gray-800 text-sm">Folyo Detayi</h3>
              <Button variant="ghost" size="sm" onClick={() => setShowFolioPanel(false)} className="h-8 w-8 p-0" data-testid="close-folio-panel-btn">
                <X className="w-4 h-4" />
              </Button>
            </div>
            <Suspense fallback={<div className="p-8 text-center text-gray-400">Yükleniyor...</div>}>
              <FolioDetailView folioId={folioPanelId} onClose={() => setShowFolioPanel(false)} />
            </Suspense>
          </div>
        </>
      )}

      {/* Reservation Detail Modal */}
      {showDetailModal && detailModalBookingId && (
        <Suspense fallback={<div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"><div className="bg-white rounded-xl p-6 text-gray-500">Yükleniyor...</div></div>}>
          <ReservationDetailModal
            bookingId={detailModalBookingId}
            onClose={() => { setShowDetailModal(false); setDetailModalBookingId(null); loadCalendarData(); }}
            allBookings={bookings}
          />
        </Suspense>
      )}

      {/* Unassigned Bookings Panel — Enhanced with urgency + quick assign */}
      {showUnassignedPanel && (() => {
        const allUnassigned = bookings.filter(b => !b.room_id && b.status !== 'cancelled' && b.status !== 'checked_out' && b.status !== 'no_show');
        const overdueList = allUnassigned.filter(b => getUnassignedUrgency(b).level === 'overdue');
        const todayList = allUnassigned.filter(b => getUnassignedUrgency(b).level === 'today');
        const tomorrowList = allUnassigned.filter(b => getUnassignedUrgency(b).level === 'tomorrow');
        const futureList = allUnassigned.filter(b => getUnassignedUrgency(b).level === 'future');

        const activeFilter = unassignedFilter;
        const filteredList = activeFilter === 'all' ? allUnassigned
          : activeFilter === 'overdue' ? overdueList
          : activeFilter === 'today' ? todayList
          : activeFilter === 'tomorrow' ? tomorrowList
          : futureList;
        const sorted = sortByUrgency(filteredList);

        const urgencyBorderColors = {
          overdue: 'border-l-red-500',
          today: 'border-l-amber-500',
          tomorrow: 'border-l-amber-400',
          future: 'border-l-blue-400',
        };
        const urgencyBadgeColors = {
          overdue: 'bg-red-100 text-red-700',
          today: 'bg-amber-100 text-amber-700',
          tomorrow: 'bg-amber-100 text-amber-700',
          future: 'bg-blue-100 text-blue-700',
        };

        return (
          <>
            <div className="fixed inset-0 bg-black/40 z-50 transition-opacity" onClick={() => { setShowUnassignedPanel(false); setUnassignedFilter('all'); }} data-testid="unassigned-panel-backdrop" />
            <div className="fixed top-0 right-0 h-full w-[560px] max-w-[90vw] bg-white z-50 shadow-2xl overflow-y-auto animate-in slide-in-from-right" data-testid="unassigned-panel">
              <div className="sticky top-0 z-10 bg-white border-b">
                <div className="px-5 py-4 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${overdueList.length > 0 ? 'bg-red-100' : todayList.length > 0 ? 'bg-amber-100' : 'bg-blue-100'}`}>
                      <CalendarIcon className={`w-4 h-4 ${overdueList.length > 0 ? 'text-red-600' : todayList.length > 0 ? 'text-amber-600' : 'text-blue-600'}`} />
                    </div>
                    <div>
                      <h3 className="font-semibold text-gray-800 text-sm" data-testid="unassigned-panel-title">Atanmamış Rezervasyonlar</h3>
                      <p className="text-xs text-gray-500">{allUnassigned.length} aktif rezervasyon</p>
                    </div>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => { setShowUnassignedPanel(false); setUnassignedFilter('all'); }} className="h-8 w-8 p-0" data-testid="close-unassigned-panel-btn">
                    <X className="w-4 h-4" />
                  </Button>
                </div>

                {allUnassigned.length > 0 && (
                  <>
                    <div className="px-5 pb-3 grid grid-cols-4 gap-2">
                      <div className={`rounded-lg p-2 text-center cursor-pointer transition-colors ${overdueList.length > 0 ? 'bg-red-50 hover:bg-red-100' : 'bg-gray-50'}`} onClick={() => setUnassignedFilter('overdue')}>
                        <div className={`text-lg font-bold ${overdueList.length > 0 ? 'text-red-600' : 'text-gray-400'}`}>{overdueList.length}</div>
                        <div className="text-[10px] text-gray-500">Gecikmiş</div>
                      </div>
                      <div className={`rounded-lg p-2 text-center cursor-pointer transition-colors ${todayList.length > 0 ? 'bg-amber-50 hover:bg-amber-100' : 'bg-gray-50'}`} onClick={() => setUnassignedFilter('today')}>
                        <div className={`text-lg font-bold ${todayList.length > 0 ? 'text-amber-600' : 'text-gray-400'}`}>{todayList.length}</div>
                        <div className="text-[10px] text-gray-500">Bugün</div>
                      </div>
                      <div className={`rounded-lg p-2 text-center cursor-pointer transition-colors ${tomorrowList.length > 0 ? 'bg-amber-50 hover:bg-amber-100' : 'bg-gray-50'}`} onClick={() => setUnassignedFilter('tomorrow')}>
                        <div className={`text-lg font-bold ${tomorrowList.length > 0 ? 'text-amber-600' : 'text-gray-400'}`}>{tomorrowList.length}</div>
                        <div className="text-[10px] text-gray-500">Yarın</div>
                      </div>
                      <div className={`rounded-lg p-2 text-center cursor-pointer transition-colors bg-blue-50 hover:bg-blue-100`} onClick={() => setUnassignedFilter('future')}>
                        <div className="text-lg font-bold text-blue-600">{futureList.length}</div>
                        <div className="text-[10px] text-gray-500">Gelecek</div>
                      </div>
                    </div>

                    <div className="px-5 pb-3 flex gap-1.5">
                      {['all', 'overdue', 'today', 'tomorrow', 'future'].map((f) => {
                        const labels = { all: 'Tümü', overdue: 'Gecikmiş', today: 'Bugün', tomorrow: 'Yarın', future: 'Gelecek' };
                        return (
                          <button
                            key={f}
                            onClick={() => setUnassignedFilter(f)}
                            className={`text-[11px] px-2.5 py-1 rounded-full font-medium transition-colors ${
                              activeFilter === f ? 'bg-gray-800 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                            }`}
                          >
                            {labels[f]}
                          </button>
                        );
                      })}
                    </div>
                  </>
                )}
              </div>

              <div className="p-4 space-y-3">
                {sorted.length === 0 ? (
                  <div className="text-center py-12 text-gray-400" data-testid="no-unassigned-msg">
                    <CalendarIcon className="w-10 h-10 mx-auto mb-3 opacity-40" />
                    <p className="text-sm font-medium">{activeFilter === 'all' ? 'Atanmamış rezervasyon yok' : 'Bu filtrede sonuc yok'}</p>
                    <p className="text-xs mt-1">{activeFilter === 'all' ? 'Tüm rezervasyonlar odalara atanmis' : 'Diger filtreleri deneyin'}</p>
                  </div>
                ) : (
                  sorted.map((booking, idx) => {
                    const checkIn = booking.check_in ? new Date(booking.check_in).toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' }) : '-';
                    const checkOut = booking.check_out ? new Date(booking.check_out).toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' }) : '-';
                    const urgency = getUnassignedUrgency(booking);
                    const borderColor = urgencyBorderColors[urgency.level] || 'border-l-blue-400';
                    const badgeColor = urgencyBadgeColors[urgency.level] || 'bg-blue-100 text-blue-700';
                    const bCheckIn = new Date(booking.check_in);
                    const bCheckOut = new Date(booking.check_out);
                    const matchingRooms = rooms.filter(r =>
                      (r.room_type || '').toLowerCase() === (booking.room_type || '').toLowerCase() &&
                      !bookings.some(ob =>
                        ob.room_id === r.id &&
                        ob.id !== booking.id &&
                        ob.status !== 'cancelled' && ob.status !== 'checked_out' && ob.status !== 'no_show' &&
                        new Date(ob.check_in) < bCheckOut && new Date(ob.check_out) > bCheckIn
                      )
                    );
                    return (
                      <div
                        key={booking.id || idx}
                        className={`bg-white border rounded-lg p-4 hover:shadow-md transition-shadow border-l-4 ${borderColor} ${urgency.level === 'overdue' ? 'ring-1 ring-red-200' : ''}`}
                        data-testid={`unassigned-item-${idx}`}
                      >
                        <div className="flex items-start justify-between mb-2">
                          <div
                            className="flex items-center gap-2 cursor-pointer flex-1"
                            onClick={() => { if (booking.id) { setDetailModalBookingId(booking.id); setShowDetailModal(true); }}}
                          >
                            <div className="w-7 h-7 rounded-full bg-gray-100 flex items-center justify-center">
                              <User className="w-3.5 h-3.5 text-gray-500" />
                            </div>
                            <div>
                              <p className="text-sm font-semibold text-gray-800" data-testid={`unassigned-guest-${idx}`}>
                                {booking.guest_name || 'Bilinmeyen Misafir'}
                              </p>
                              <p className="text-xs text-gray-400">{booking.room_type || ''}</p>
                            </div>
                          </div>
                          <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${badgeColor}`}>
                            {urgency.label}
                          </span>
                        </div>
                        <div className="flex items-center gap-4 text-xs text-gray-500 mt-2">
                          <div className="flex items-center gap-1">
                            <CalendarIcon className="w-3 h-3" />
                            <span>{checkIn}</span>
                            <ArrowRight className="w-3 h-3 mx-0.5" />
                            <span>{checkOut}</span>
                          </div>
                          {booking.total_amount > 0 && (
                            <span className="font-medium text-gray-700">{booking.total_amount.toLocaleString('tr-TR')} TL</span>
                          )}
                        </div>

                        <div className="mt-3 flex items-center gap-2">
                          {matchingRooms.length > 0 ? (
                            <div className="flex items-center gap-1.5 flex-1">
                              <select
                                className="border rounded px-2 py-1 text-xs h-7 flex-1 max-w-[160px]"
                                defaultValue=""
                                data-testid={`quick-assign-select-${idx}`}
                                onChange={async (e) => {
                                  const roomId = e.target.value;
                                  if (!roomId) return;
                                  try {
                                    await axios.put(`/pms/bookings/${booking.id}`, { room_id: roomId });
                                    toast.success(`${booking.guest_name || 'Misafir'} odaya atandi`);
                                    loadCalendarData();
                                  } catch (err) {
                                    toast.error(err.response?.data?.detail || 'Atama başarısız');
                                  }
                                }}
                              >
                                <option value="">Oda sec...</option>
                                {matchingRooms.map(r => (
                                  <option key={r.id} value={r.id}>
                                    {r.room_number} - {r.room_type}
                                  </option>
                                ))}
                              </select>
                              <span className="text-[10px] text-green-600 font-medium">{matchingRooms.length} müsait</span>
                            </div>
                          ) : (
                            <span className="text-[10px] text-red-500 font-medium">Müsait oda yok</span>
                          )}
                          <Button
                            size="sm"
                            variant="outline"
                            className="text-xs h-7 border-amber-300 text-amber-700 hover:bg-amber-50"
                            data-testid={`no-show-btn-${idx}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              setNoShowBookingId(booking.id);
                              setNoShowReason('misafir_gelmedi');
                              setShowNoShowDialog(true);
                            }}
                          >
                            <Ban className="w-3 h-3 mr-1" />
                            No-Show
                          </Button>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </>
        );
      })()}

      {/* No-Show Reason Dialog */}
      <Dialog open={showNoShowDialog} onOpenChange={(open) => { if (!open) { setShowNoShowDialog(false); setNoShowBookingId(null); } }}>
        <DialogContent className="sm:max-w-md" data-testid="noshow-reason-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <Ban className="w-4 h-4 text-amber-600" />
              No-Show Sebebi
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <p className="text-sm text-gray-500">
              Rezervasyonu no-show olarak isaretlemek ve sanal odaya atamak için bir sebep seçin.
            </p>
            <div className="space-y-2">
              <Label className="text-sm font-medium">Sebep</Label>
              <Select value={noShowReason} onValueChange={setNoShowReason}>
                <SelectTrigger data-testid="noshow-reason-select">
                  <SelectValue placeholder="Sebep seçin..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="misafir_gelmedi">Misafir Gelmedi</SelectItem>
                  <SelectItem value="iptal_gec_islendi">İptal Edildi ama Gec Islendi</SelectItem>
                  <SelectItem value="overbooking">Overbooking</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" size="sm" onClick={() => { setShowNoShowDialog(false); setNoShowBookingId(null); }} data-testid="noshow-cancel-btn">
              Vazgec
            </Button>
            <Button
              size="sm"
              className="bg-amber-600 hover:bg-amber-700 text-white"
              onClick={handleNoShowConfirm}
              disabled={noShowProcessing}
              data-testid="noshow-confirm-btn"
            >
              {noShowProcessing ? 'Isleniyor...' : 'No-Show Onayla'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Layout>
  );
};

export default ReservationCalendar;
