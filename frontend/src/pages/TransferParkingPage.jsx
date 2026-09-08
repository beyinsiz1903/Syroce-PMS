import { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useEntitlements } from '@/context/EntitlementContext';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { PageHeader } from '@/components/ui/page-header';
import { confirmDialog } from '@/lib/dialogs';
import {
  Car, ParkingSquare, Plus, RefreshCw, Trash2, Receipt, AlertTriangle,
  KeyRound, ScanLine, BarChart3, CheckCircle2,
} from 'lucide-react';

const KIND_OPTIONS = [
  { value: 'transfer_vehicle', label: 'Transfer Aracı', icon: Car },
  { value: 'parking_spot', label: 'Otopark Yeri', icon: ParkingSquare },
];
const KIND_LABELS = Object.fromEntries(KIND_OPTIONS.map((k) => [k.value, k.label]));

const EMPTY_RESOURCE = { name: '', kind: 'transfer_vehicle', price: '', capacity: 1, active: true };
const EMPTY_BOOKING = {
  resource_id: '', room_number: '', guest_name: '', booking_id: '',
  start_date: '', num_days: 1, pickup_at: '', note: '',
};
const EMPTY_VALET = { plate: '', guest_name: '', room_number: '', vehicle_info: '', parking_spot: '', note: '' };
const EMPTY_LPR = { plate: '', direction: 'in', camera: '', confidence: '' };

const STATUS_VARIANTS = {
  reserved: 'default',
  cancelled: 'outline',
};

const TransferParkingPage = () => {
  useTranslation();
  const [tab, setTab] = useState('bookings');

  const [resources, setResources] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [lateCharges, setLateCharges] = useState([]);
  const [valetTickets, setValetTickets] = useState([]);
  const [lprEvents, setLprEvents] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);

  const [showResourceDialog, setShowResourceDialog] = useState(false);
  const [resourceForm, setResourceForm] = useState(EMPTY_RESOURCE);

  const [showBookingDialog, setShowBookingDialog] = useState(false);
  const [bookingForm, setBookingForm] = useState(EMPTY_BOOKING);
  const [submitting, setSubmitting] = useState(false);
  const [showValetDialog, setShowValetDialog] = useState(false);
  const [valetForm, setValetForm] = useState(EMPTY_VALET);
  const [showLprDialog, setShowLprDialog] = useState(false);
  const [lprForm, setLprForm] = useState(EMPTY_LPR);
  const pendingKeyRef = useRef(null);

  const activeResources = resources.filter((r) => r.active);
  const selectedResource = activeResources.find((r) => r.id === bookingForm.resource_id);
  const selectedKind = selectedResource?.kind;

  const { getLimit, hasFeature } = useEntitlements();
  const vehicleLimit = getLimit('parking', 'transfer_vehicles', 0);
  const spotLimit = getLimit('parking', 'parking_spots', 0);

  const vehicleCount = activeResources.filter((r) => r.kind === 'transfer_vehicle').length;
  const spotCount = activeResources.filter((r) => r.kind === 'parking_spot').length;

  // Backend treats a zero limit as no entitlement.  Fail closed in the UI too,
  // instead of opening a form that the server can only reject.
  const canAddVehicle = vehicleLimit > 0 && vehicleCount < vehicleLimit;
  const canAddSpot = spotLimit > 0 && spotCount < spotLimit;
  const canAddResource = canAddVehicle || canAddSpot;

  const loadResources = useCallback(async () => {
    try {
      const res = await axios.get('/transfer-parking/resources', {
        params: { include_inactive: true },
      });
      setResources(res.data.resources || []);
    } catch {
      toast.error('Kaynaklar yüklenemedi');
      setResources([]);
    }
  }, []);

  const loadBookings = useCallback(async () => {
    try {
      const res = await axios.get('/transfer-parking/bookings');
      setBookings(res.data.bookings || []);
    } catch {
      toast.error('Rezervasyonlar yüklenemedi');
      setBookings([]);
    }
  }, []);

  const loadLateCharges = useCallback(async () => {
    try {
      const res = await axios.get('/transfer-parking/late-charges');
      setLateCharges(res.data.late_charges || []);
    } catch {
      setLateCharges([]);
    }
  }, []);

  const loadValet = useCallback(async () => {
    try {
      const res = await axios.get('/transfer-parking/valet');
      setValetTickets(res.data.tickets || []);
    } catch { setValetTickets([]); }
  }, []);

  const loadLpr = useCallback(async () => {
    try {
      const res = await axios.get('/transfer-parking/lpr-events');
      setLprEvents(res.data.events || []);
    } catch { setLprEvents([]); }
  }, []);

  const loadAnalytics = useCallback(async () => {
    try {
      const res = await axios.get('/transfer-parking/analytics');
      setAnalytics(res.data);
    } catch { setAnalytics(null); }
  }, []);

  const refreshAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([loadResources(), loadBookings(), loadLateCharges()]);
    setLoading(false);
  }, [loadResources, loadBookings, loadLateCharges]);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    if (tab === 'valet') loadValet();
    if (tab === 'lpr') loadLpr();
    if (tab === 'analytics') loadAnalytics();
  }, [tab, loadValet, loadLpr, loadAnalytics]);

  const submitValet = async () => {
    if (!valetForm.plate.trim()) return toast.error('Plaka gerekli');
    setSubmitting(true);
    try {
      await axios.post('/transfer-parking/valet', valetForm);
      toast.success('Vale kaydı açıldı');
      setShowValetDialog(false); setValetForm(EMPTY_VALET); await loadValet();
    } catch (err) { toast.error(err?.response?.data?.detail || 'Vale kaydı açılamadı'); }
    finally { setSubmitting(false); }
  };

  const setValetStatus = async (ticket, status) => {
    try {
      await axios.patch(`/transfer-parking/valet/${ticket.id}`, { status });
      toast.success('Vale durumu güncellendi'); await loadValet();
    } catch (err) { toast.error(err?.response?.data?.detail || 'Vale durumu güncellenemedi'); }
  };

  const submitLpr = async () => {
    if (!lprForm.plate.trim()) return toast.error('Plaka gerekli');
    setSubmitting(true);
    try {
      await axios.post('/transfer-parking/lpr-events', {
        ...lprForm,
        confidence: lprForm.confidence === '' ? undefined : Number(lprForm.confidence),
      });
      toast.success('Plaka geçişi kaydedildi');
      setShowLprDialog(false); setLprForm(EMPTY_LPR); await loadLpr();
    } catch (err) { toast.error(err?.response?.data?.detail || 'Plaka geçişi kaydedilemedi'); }
    finally { setSubmitting(false); }
  };

  // ── Kaynak (katalog) ──
  const saveResource = async () => {
    if (!resourceForm.name.trim()) {
      toast.error('Kaynak adı gerekli');
      return;
    }
    const price = parseFloat(resourceForm.price);
    if (Number.isNaN(price) || price < 0) {
      toast.error('Geçerli bir fiyat girin');
      return;
    }
    try {
      await axios.post('/transfer-parking/resources', {
        name: resourceForm.name.trim(),
        kind: resourceForm.kind,
        price,
        capacity: parseInt(resourceForm.capacity, 10) || 1,
        active: true,
      });
      toast.success('Kaynak eklendi');
      setShowResourceDialog(false);
      setResourceForm(EMPTY_RESOURCE);
      await loadResources();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Kaynak kaydedilemedi');
    }
  };

  const deactivateResource = async (resource) => {
    const ok = await confirmDialog({
      title: 'Kaynağı pasifleştir',
      description: `"${resource.name}" pasifleştirilsin mi?`,
    });
    if (!ok) return;
    try {
      await axios.delete(`/transfer-parking/resources/${resource.id}`);
      toast.success('Kaynak pasifleştirildi');
      await loadResources();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'İşlem başarısız');
    }
  };

  // ── Rezervasyon ──
  const openBookingDialog = () => {
    setBookingForm(EMPTY_BOOKING);
    pendingKeyRef.current = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID()
      : `tp-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setShowBookingDialog(true);
  };

  const submitBooking = async () => {
    if (!bookingForm.resource_id) {
      toast.error('Kaynak seçin');
      return;
    }
    if (!bookingForm.room_number.trim()) {
      toast.error('Oda numarası gerekli');
      return;
    }
    const payload = {
      resource_id: bookingForm.resource_id,
      room_number: bookingForm.room_number.trim(),
      guest_name: bookingForm.guest_name.trim() || undefined,
      booking_id: bookingForm.booking_id.trim() || undefined,
      note: bookingForm.note.trim() || undefined,
      idempotency_key: pendingKeyRef.current,
    };
    if (selectedKind === 'parking_spot') {
      if (!bookingForm.start_date) {
        toast.error('Başlangıç günü gerekli');
        return;
      }
      payload.start_date = bookingForm.start_date;
      payload.num_days = parseInt(bookingForm.num_days, 10) || 1;
    } else {
      if (!bookingForm.pickup_at) {
        toast.error('Kalkış zamanı gerekli');
        return;
      }
      payload.pickup_at = new Date(bookingForm.pickup_at).toISOString();
    }
    setSubmitting(true);
    try {
      const res = await axios.post('/transfer-parking/bookings', payload);
      const fc = res.data.folio_charge;
      if (fc?.charged) {
        toast.success(`Rezervasyon oluşturuldu, folyoya ${fc.amount} işlendi`);
      } else if (fc?.reason === 'no_active_booking_or_folio') {
        toast.warning('Rezervasyon oluşturuldu ancak açık folyo yok — geç tahakkuk listesine eklendi');
      } else {
        toast.success('Rezervasyon oluşturuldu');
      }
      setShowBookingDialog(false);
      pendingKeyRef.current = null;
      await Promise.all([loadBookings(), loadLateCharges()]);
    } catch (err) {
      if (err?.response?.status === 409) {
        toast.error(err?.response?.data?.detail || 'Bu kaynak seçilen zaman diliminde dolu');
      } else {
        toast.error(err?.response?.data?.detail || 'Rezervasyon oluşturulamadı');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const cancelBooking = async (bk) => {
    const ok = await confirmDialog({
      title: 'Rezervasyonu iptal et',
      description: `${KIND_LABELS[bk.kind]} - ${bk.resource_name} rezervasyonu iptal edilsin mi?`,
    });
    if (!ok) return;
    try {
      await axios.delete(`/transfer-parking/bookings/${bk.id}`);
      toast.success('Rezervasyon iptal edildi');
      // Cancellation also closes a possible late-charge record. Refresh both
      // views together so the badge and table never expose stale receivables.
      await Promise.all([loadBookings(), loadLateCharges()]);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'İptal başarısız');
    }
  };

  const formatSchedule = (bk) => {
    const s = bk.schedule || {};
    if (bk.kind === 'parking_spot') {
      return `${s.start_date || '?'} → ${s.end_date || '?'} (${s.num_days || 0} gün)`;
    }
    if (s.pickup_at) {
      try {
        return new Date(s.pickup_at).toLocaleString('tr-TR');
      } catch {
        return s.pickup_at;
      }
    }
    return '-';
  };

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="Transfer & Otopark"
        description="Araç transferi ve otopark yeri rezervasyonu — çift-rezervasyon korumalı, folyoya otomatik işlenir."
        actions={(
          <Button variant="outline" onClick={refreshAll} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Yenile
          </Button>
        )}
      />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="bookings">Rezervasyonlar</TabsTrigger>
          <TabsTrigger value="resources">Kaynaklar</TabsTrigger>
          <TabsTrigger value="late">
            Geç Tahakkuk
            {lateCharges.length > 0 && (
              <Badge variant="destructive" className="ml-2">{lateCharges.length}</Badge>
            )}
          </TabsTrigger>
          {hasFeature('parking', 'valet_service') && <TabsTrigger value="valet">Vale</TabsTrigger>}
          {hasFeature('parking', 'lpr_integration') && <TabsTrigger value="lpr">Plaka Tanıma</TabsTrigger>}
          {hasFeature('parking', 'parking_analytics') && <TabsTrigger value="analytics">Analiz</TabsTrigger>}
        </TabsList>

        {/* ── Rezervasyonlar ── */}
        <TabsContent value="bookings" className="space-y-4">
          <div className="flex justify-end">
            <Button className="bg-black text-white" onClick={openBookingDialog}>
              <Plus className="h-4 w-4 mr-2" />
              Yeni Rezervasyon
            </Button>
          </div>
          <Card>
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40">
                  <tr className="text-left">
                    <th className="p-3">Tip</th>
                    <th className="p-3">Kaynak</th>
                    <th className="p-3">Oda</th>
                    <th className="p-3">Misafir</th>
                    <th className="p-3">Plan</th>
                    <th className="p-3 text-right">Tutar</th>
                    <th className="p-3">Folyo</th>
                    <th className="p-3">Durum</th>
                    <th className="p-3" />
                  </tr>
                </thead>
                <tbody>
                  {bookings.length === 0 && (
                    <tr><td colSpan={9} className="p-6 text-center text-muted-foreground">Rezervasyon yok</td></tr>
                  )}
                  {bookings.map((bk) => (
                    <tr key={bk.id} className="border-b last:border-0">
                      <td className="p-3">{KIND_LABELS[bk.kind] || bk.kind}</td>
                      <td className="p-3">{bk.resource_name}</td>
                      <td className="p-3">{bk.room_number || '-'}</td>
                      <td className="p-3">{bk.guest_name || '-'}</td>
                      <td className="p-3">{formatSchedule(bk)}</td>
                      <td className="p-3 text-right">{bk.total}</td>
                      <td className="p-3">
                        {bk.folio_charged
                          ? <Badge variant="default">İşlendi</Badge>
                          : <Badge variant="outline">Geç tahakkuk</Badge>}
                      </td>
                      <td className="p-3">
                        <Badge variant={STATUS_VARIANTS[bk.status] || 'outline'}>{bk.status}</Badge>
                      </td>
                      <td className="p-3 text-right">
                        {bk.status === 'reserved' && (
                          <Button size="sm" variant="ghost" onClick={() => cancelBooking(bk)}>
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Kaynaklar ── */}
        <TabsContent value="resources" className="space-y-4">
          <div className="flex justify-end">
            <Button
              className="bg-black text-white"
              onClick={() => { setResourceForm(EMPTY_RESOURCE); setShowResourceDialog(true); }}
              disabled={!canAddResource}
            >
              <Plus className="h-4 w-4 mr-2" />
              {canAddResource ? 'Yeni Kaynak' : 'Limit Doldu'}
            </Button>
          </div>
          <Card>
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40">
                  <tr className="text-left">
                    <th className="p-3">Ad</th>
                    <th className="p-3">Tip</th>
                    <th className="p-3 text-right">Fiyat</th>
                    <th className="p-3">Kapasite</th>
                    <th className="p-3">Durum</th>
                    <th className="p-3" />
                  </tr>
                </thead>
                <tbody>
                  {resources.length === 0 && (
                    <tr><td colSpan={6} className="p-6 text-center text-muted-foreground">Kaynak yok</td></tr>
                  )}
                  {resources.map((r) => (
                    <tr key={r.id} className="border-b last:border-0">
                      <td className="p-3">{r.name}</td>
                      <td className="p-3">{KIND_LABELS[r.kind] || r.kind}</td>
                      <td className="p-3 text-right">{r.price}{r.kind === 'parking_spot' ? ' /gün' : ' /sefer'}</td>
                      <td className="p-3">{r.capacity}</td>
                      <td className="p-3">
                        {r.active ? <Badge variant="default">Aktif</Badge> : <Badge variant="outline">Pasif</Badge>}
                      </td>
                      <td className="p-3 text-right">
                        {r.active && (
                          <Button size="sm" variant="ghost" onClick={() => deactivateResource(r)}>
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Geç Tahakkuk ── */}
        <TabsContent value="late" className="space-y-4">
          <Card>
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40">
                  <tr className="text-left">
                    <th className="p-3">Tip</th>
                    <th className="p-3">Kaynak</th>
                    <th className="p-3">Oda</th>
                    <th className="p-3 text-right">Tutar</th>
                    <th className="p-3">Durum</th>
                  </tr>
                </thead>
                <tbody>
                  {lateCharges.length === 0 && (
                    <tr><td colSpan={5} className="p-6 text-center text-muted-foreground">Geç tahakkuk yok</td></tr>
                  )}
                  {lateCharges.map((lc) => (
                    <tr key={lc.source_transport_booking_id} className="border-b last:border-0">
                      <td className="p-3">{KIND_LABELS[lc.kind] || lc.kind}</td>
                      <td className="p-3">{lc.resource_name || '-'}</td>
                      <td className="p-3">{lc.room_number || '-'}</td>
                      <td className="p-3 text-right">{lc.total}</td>
                      <td className="p-3">
                        <Badge variant="outline" className="gap-1">
                          <AlertTriangle className="h-3 w-3" />
                          {lc.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="valet" className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">Araç teslim alma, park etme ve geri getirme kuyruğu</p>
            <Button className="bg-black text-white" onClick={() => setShowValetDialog(true)}>
              <KeyRound className="h-4 w-4 mr-2" />Vale Kaydı Aç
            </Button>
          </div>
          <Card><CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40"><tr className="text-left">
                <th className="p-3">Plaka</th><th className="p-3">Misafir / Oda</th>
                <th className="p-3">Araç / Yer</th><th className="p-3">Durum</th><th className="p-3">İşlem</th>
              </tr></thead>
              <tbody>
                {valetTickets.length === 0 && <tr><td colSpan={5} className="p-6 text-center text-muted-foreground">Açık vale kaydı yok</td></tr>}
                {valetTickets.map(ticket => <tr key={ticket.id} className="border-b last:border-0">
                  <td className="p-3 font-semibold">{ticket.plate}</td>
                  <td className="p-3">{ticket.guest_name || '-'}{ticket.room_number ? ` · Oda ${ticket.room_number}` : ''}</td>
                  <td className="p-3">{ticket.vehicle_info || '-'}{ticket.parking_spot ? ` · ${ticket.parking_spot}` : ''}</td>
                  <td className="p-3"><Badge variant="outline">{ticket.status}</Badge></td>
                  <td className="p-3 flex flex-wrap gap-1">
                    {ticket.status === 'waiting' && <Button size="sm" variant="outline" onClick={() => setValetStatus(ticket, 'parked')}>Park Edildi</Button>}
                    {ticket.status === 'parked' && <Button size="sm" variant="outline" onClick={() => setValetStatus(ticket, 'requested')}>Araç İstendi</Button>}
                    {ticket.status === 'requested' && <Button size="sm" onClick={() => setValetStatus(ticket, 'delivered')}><CheckCircle2 className="h-4 w-4 mr-1" />Teslim Edildi</Button>}
                  </td>
                </tr>)}
              </tbody>
            </table>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="lpr" className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">Kamera veya manuel giriş/çıkış plaka olayları</p>
            <Button className="bg-black text-white" onClick={() => setShowLprDialog(true)}>
              <ScanLine className="h-4 w-4 mr-2" />Geçiş Kaydet
            </Button>
          </div>
          <Card><CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40"><tr className="text-left">
                <th className="p-3">Zaman</th><th className="p-3">Plaka</th><th className="p-3">Yön</th>
                <th className="p-3">Kamera</th><th className="p-3">Güven</th>
              </tr></thead>
              <tbody>
                {lprEvents.length === 0 && <tr><td colSpan={5} className="p-6 text-center text-muted-foreground">Plaka geçişi yok</td></tr>}
                {lprEvents.map(event => <tr key={event.id} className="border-b last:border-0">
                  <td className="p-3">{new Date(event.occurred_at).toLocaleString('tr-TR')}</td>
                  <td className="p-3 font-semibold">{event.plate}</td>
                  <td className="p-3"><Badge variant={event.direction === 'in' ? 'default' : 'outline'}>{event.direction === 'in' ? 'Giriş' : 'Çıkış'}</Badge></td>
                  <td className="p-3">{event.camera || 'Manuel'}</td>
                  <td className="p-3">{event.confidence == null ? '-' : `%${Math.round(event.confidence * 100)}`}</td>
                </tr>)}
              </tbody>
            </table>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="analytics" className="space-y-4">
          {!analytics ? <Card><CardContent className="p-8 text-center text-muted-foreground">Analiz verisi yüklenemedi</CardContent></Card> : <>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              {[
                ['Aktif Rezervasyon', analytics.bookings?.active || 0],
                ['Folyo Tahakkuku', analytics.bookings?.folio_charged || 0],
                ['Vale Kuyruğu', analytics.valet?.active || 0],
                ['Rezervasyon Geliri', `${Number(analytics.bookings?.revenue || 0).toLocaleString('tr-TR')} ₺`],
              ].map(([label, value]) => <Card key={label}><CardContent className="p-5">
                <div className="flex items-center gap-2 text-muted-foreground text-sm"><BarChart3 className="h-4 w-4" />{label}</div>
                <div className="text-2xl font-bold mt-2">{value}</div>
              </CardContent></Card>)}
            </div>
            <Card><CardContent className="p-5 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>Park yeri <strong>{analytics.resources?.parking_spots || 0}</strong></div>
              <div>Transfer aracı <strong>{analytics.resources?.transfer_vehicles || 0}</strong></div>
              <div>Plaka girişi <strong>{analytics.lpr?.entries || 0}</strong></div>
              <div>Plaka çıkışı <strong>{analytics.lpr?.exits || 0}</strong></div>
            </CardContent></Card>
          </>}
        </TabsContent>
      </Tabs>

      {/* ── Kaynak Dialog ── */}
      <Dialog open={showResourceDialog} onOpenChange={setShowResourceDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Yeni Kaynak</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Ad</Label>
              <Input
                value={resourceForm.name}
                onChange={(e) => setResourceForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="VIP Araç / Otopark A1"
              />
            </div>
            <div>
              <Label>Tip</Label>
              <Select value={resourceForm.kind} onValueChange={(v) => setResourceForm((f) => ({ ...f, kind: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {KIND_OPTIONS.map((k) => (
                    <SelectItem
                      key={k.value}
                      value={k.value}
                      disabled={
                        (k.value === 'transfer_vehicle' && !canAddVehicle) ||
                        (k.value === 'parking_spot' && !canAddSpot)
                      }
                    >
                      {k.label}
                      {k.value === 'transfer_vehicle' && !canAddVehicle && ' (Limit dolu)'}
                      {k.value === 'parking_spot' && !canAddSpot && ' (Limit dolu)'}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Fiyat ({resourceForm.kind === 'parking_spot' ? '/gün' : '/sefer'})</Label>
                <Input
                  type="number" min="0" step="0.01"
                  value={resourceForm.price}
                  onChange={(e) => setResourceForm((f) => ({ ...f, price: e.target.value }))}
                />
              </div>
              <div>
                <Label>Kapasite</Label>
                <Input
                  type="number" min="1"
                  value={resourceForm.capacity}
                  onChange={(e) => setResourceForm((f) => ({ ...f, capacity: e.target.value }))}
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowResourceDialog(false)}>İptal</Button>
            <Button className="bg-black text-white" onClick={saveResource}>Kaydet</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Rezervasyon Dialog ── */}
      <Dialog open={showBookingDialog} onOpenChange={setShowBookingDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Yeni Rezervasyon</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Kaynak</Label>
              <Select
                value={bookingForm.resource_id}
                onValueChange={(v) => setBookingForm((f) => ({ ...f, resource_id: v }))}
              >
                <SelectTrigger><SelectValue placeholder="Kaynak seçin" /></SelectTrigger>
                <SelectContent>
                  {activeResources.map((r) => (
                    <SelectItem key={r.id} value={r.id}>
                      {KIND_LABELS[r.kind]} - {r.name} ({r.price})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Oda No</Label>
                <Input
                  value={bookingForm.room_number}
                  onChange={(e) => setBookingForm((f) => ({ ...f, room_number: e.target.value }))}
                />
              </div>
              <div>
                <Label>Misafir (ops.)</Label>
                <Input
                  value={bookingForm.guest_name}
                  onChange={(e) => setBookingForm((f) => ({ ...f, guest_name: e.target.value }))}
                />
              </div>
            </div>

            {selectedKind === 'parking_spot' && (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Başlangıç Günü</Label>
                  <Input
                    type="date"
                    value={bookingForm.start_date}
                    onChange={(e) => setBookingForm((f) => ({ ...f, start_date: e.target.value }))}
                  />
                </div>
                <div>
                  <Label>Gün Sayısı</Label>
                  <Input
                    type="number" min="1"
                    value={bookingForm.num_days}
                    onChange={(e) => setBookingForm((f) => ({ ...f, num_days: e.target.value }))}
                  />
                </div>
              </div>
            )}

            {selectedKind === 'transfer_vehicle' && (
              <div>
                <Label>Kalkış Zamanı</Label>
                <Input
                  type="datetime-local"
                  value={bookingForm.pickup_at}
                  onChange={(e) => setBookingForm((f) => ({ ...f, pickup_at: e.target.value }))}
                />
              </div>
            )}

            <div>
              <Label>Not (ops.)</Label>
              <Input
                value={bookingForm.note}
                onChange={(e) => setBookingForm((f) => ({ ...f, note: e.target.value }))}
              />
            </div>

            {selectedResource && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Receipt className="h-4 w-4" />
                Tahmini tutar:{' '}
                <span className="font-medium text-foreground">
                  {selectedKind === 'parking_spot'
                    ? (selectedResource.price * (parseInt(bookingForm.num_days, 10) || 1)).toFixed(2)
                    : selectedResource.price.toFixed(2)}
                </span>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowBookingDialog(false)}>İptal</Button>
            <Button className="bg-black text-white" onClick={submitBooking} disabled={submitting}>
              {submitting ? 'Kaydediliyor...' : 'Rezervasyon Oluştur'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={showValetDialog} onOpenChange={setShowValetDialog}>
        <DialogContent>
          <DialogHeader><DialogTitle>Yeni Vale Kaydı</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-4">
            <div><Label>Plaka *</Label><Input value={valetForm.plate} onChange={(e) => setValetForm(f => ({ ...f, plate: e.target.value }))} placeholder="34ABC123" /></div>
            <div><Label>Oda No</Label><Input value={valetForm.room_number} onChange={(e) => setValetForm(f => ({ ...f, room_number: e.target.value }))} /></div>
            <div><Label>Misafir</Label><Input value={valetForm.guest_name} onChange={(e) => setValetForm(f => ({ ...f, guest_name: e.target.value }))} /></div>
            <div><Label>Araç Bilgisi</Label><Input value={valetForm.vehicle_info} onChange={(e) => setValetForm(f => ({ ...f, vehicle_info: e.target.value }))} placeholder="Marka / renk" /></div>
            <div><Label>Park Yeri</Label><Input value={valetForm.parking_spot} onChange={(e) => setValetForm(f => ({ ...f, parking_spot: e.target.value }))} /></div>
            <div><Label>Not</Label><Input value={valetForm.note} onChange={(e) => setValetForm(f => ({ ...f, note: e.target.value }))} /></div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setShowValetDialog(false)}>İptal</Button><Button onClick={submitValet} disabled={submitting}>Kaydı Aç</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={showLprDialog} onOpenChange={setShowLprDialog}>
        <DialogContent>
          <DialogHeader><DialogTitle>Plaka Geçişi Kaydet</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-4">
            <div><Label>Plaka *</Label><Input value={lprForm.plate} onChange={(e) => setLprForm(f => ({ ...f, plate: e.target.value }))} placeholder="34ABC123" /></div>
            <div><Label>Yön</Label><Select value={lprForm.direction} onValueChange={(v) => setLprForm(f => ({ ...f, direction: v }))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="in">Giriş</SelectItem><SelectItem value="out">Çıkış</SelectItem></SelectContent></Select></div>
            <div><Label>Kamera</Label><Input value={lprForm.camera} onChange={(e) => setLprForm(f => ({ ...f, camera: e.target.value }))} placeholder="Ana kapı" /></div>
            <div><Label>Güven (0-1)</Label><Input type="number" min="0" max="1" step="0.01" value={lprForm.confidence} onChange={(e) => setLprForm(f => ({ ...f, confidence: e.target.value }))} /></div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setShowLprDialog(false)}>İptal</Button><Button onClick={submitLpr} disabled={submitting}>Kaydet</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default TransferParkingPage;
