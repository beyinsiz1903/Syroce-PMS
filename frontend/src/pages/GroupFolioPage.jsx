import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Merge, Users, DollarSign, FileText, Check, AlertTriangle,
  RefreshCw, ArrowRight, Lock, Search, ChevronDown, ChevronRight,
  CreditCard, Banknote, TrendingUp, Layers, Clock
} from 'lucide-react';

const API = "";
const fmtTL = (v) => (v || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2 });

// ─── Summary Stats Card ────────────────────────────
const StatCard = ({ icon: Icon, label, value, sub, color }) => (
  <Card data-testid={`stat-${label.toLowerCase().replace(/\s/g, '-')}`}>
    <CardContent className="p-4 flex items-center gap-3">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <div className="text-xs text-gray-500">{label}</div>
        <div className="text-lg font-bold text-gray-900">{value}</div>
        {sub && <div className="text-[11px] text-gray-400">{sub}</div>}
      </div>
    </CardContent>
  </Card>
);

// ─── Booking Folio Detail (expandable) ─────────────
const BookingFolioDetail = ({ groupId, bookingId }) => {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await axios.get(`/pms/group-folio/${groupId}/booking/${bookingId}`);
        setDetail(res.data);
      } catch {
        toast.error('Folio detayı yüklenemedi');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [groupId, bookingId]);

  if (loading) return <div className="py-3 text-center text-sm text-gray-400">Yükleniyor...</div>;
  if (!detail) return <div className="py-3 text-center text-sm text-gray-400">Veri bulunamadı</div>;

  const allItems = [
    ...(detail.charges || []).map(c => ({
      type: 'charge', desc: c.description || c.category || 'Masraf', amount: c.total || c.amount || 0, date: c.created_at, voided: c.voided
    })),
    ...(detail.folios || []).map(f => ({
      type: f.type === 'payment' ? 'payment' : 'folio', desc: f.description || f.category || 'Folio', amount: f.amount || 0, date: f.created_at, voided: f.voided
    })),
    ...(detail.extra_charges || []).map(ec => ({
      type: 'extra', desc: ec.description || ec.category || 'Ekstra', amount: ec.charge_amount || ec.amount || 0, date: ec.created_at, voided: ec.voided
    })),
    ...(detail.payments || []).map(p => ({
      type: 'payment', desc: `${p.method || 'Ödeme'} - ${p.reference || ''}`.trim(), amount: -(p.amount || 0), date: p.created_at, voided: p.voided
    })),
  ].sort((a, b) => (a.date || '').localeCompare(b.date || ''));

  if (allItems.length === 0) {
    return (
      <div className="py-4 px-3 text-center text-sm text-gray-400 bg-gray-50/50 rounded-lg">
        Henuz folio girisi yok
      </div>
    );
  }

  return (
    <div className="bg-gray-50/80 rounded-lg border border-gray-100 overflow-hidden" data-testid={`folio-detail-${bookingId}`}>
      <div className="grid grid-cols-[1fr_auto_auto] gap-2 px-3 py-2 text-[11px] font-semibold text-gray-500 uppercase border-b bg-gray-100/50">
        <span>Açıklama</span>
        <span>Tarih</span>
        <span className="text-right">Tutar</span>
      </div>
      {allItems.map((item, i) => (
        <div key={i} className={`grid grid-cols-[1fr_auto_auto] gap-2 px-3 py-2 text-sm border-b border-gray-100 last:border-0 ${item.voided ? 'opacity-40 line-through' : ''}`}>
          <span className="flex items-center gap-1.5">
            {item.type === 'payment' ? (
              <CreditCard className="w-3 h-3 text-emerald-500 shrink-0" />
            ) : item.type === 'extra' ? (
              <TrendingUp className="w-3 h-3 text-amber-500 shrink-0" />
            ) : (
              <FileText className="w-3 h-3 text-blue-500 shrink-0" />
            )}
            <span className="truncate">{item.desc}</span>
          </span>
          <span className="text-xs text-gray-400 whitespace-nowrap">
            {item.date ? item.date.slice(0, 10) : '-'}
          </span>
          <span className={`text-right font-medium whitespace-nowrap ${item.amount < 0 ? 'text-emerald-600' : 'text-gray-700'}`}>
            {item.amount < 0 ? '-' : ''}{fmtTL(Math.abs(item.amount))} TL
          </span>
        </div>
      ))}
    </div>
  );
};

// ─── Main Page Component ───────────────────────────
const GroupFolioPage = ({ user, tenant, onLogout }) => {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);
  const [selectedGroup, setSelectedGroup] = useState(null);
  const [groupDetail, setGroupDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedBooking, setExpandedBooking] = useState(null);

  // Merge dialog state
  const [showMerge, setShowMerge] = useState(false);
  const [masterBookingId, setMasterBookingId] = useState('');
  const [mergePayments, setMergePayments] = useState(true);
  const [merging, setMerging] = useState(false);

  // Payment dialog state
  const [showPayment, setShowPayment] = useState(false);
  const [paymentBookingId, setPaymentBookingId] = useState('');
  const [paymentAmount, setPaymentAmount] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('cash');
  const [paymentRef, setPaymentRef] = useState('');
  const [paying, setPaying] = useState(false);

  // Bulk payment dialog state
  const [showBulkPayment, setShowBulkPayment] = useState(false);
  const [bulkAmount, setBulkAmount] = useState('');
  const [bulkMethod, setBulkMethod] = useState('cash');
  const [bulkRef, setBulkRef] = useState('');
  const [bulkDistribution, setBulkDistribution] = useState('proportional');
  const [bulkPaying, setBulkPaying] = useState(false);

  const loadGroups = useCallback(async () => {
    try {
      const res = await axios.get(`/pms/group-bookings`);
      setGroups(res.data?.groups || res.data || []);
    } catch (e) {
      console.error('Load groups error', e);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadSummary = useCallback(async () => {
    try {
      const res = await axios.get(`/pms/group-folio-summary`);
      setSummary(res.data);
    } catch (e) {
      console.error('Summary error', e);
    }
  }, []);

  useEffect(() => {
    loadGroups();
    loadSummary();
  }, [loadGroups, loadSummary]);

  const loadGroupDetail = async (groupId) => {
    setDetailLoading(true);
    setExpandedBooking(null);
    try {
      const res = await axios.get(`/pms/group-folio/${groupId}`);
      setGroupDetail(res.data);
    } catch {
      toast.error('Grup detay yüklenemedi');
    } finally {
      setDetailLoading(false);
    }
  };

  const handleSelectGroup = (group) => {
    setSelectedGroup(group);
    loadGroupDetail(group.id);
  };

  const handleRefresh = () => {
    setLoading(true);
    loadGroups();
    loadSummary();
    if (selectedGroup) loadGroupDetail(selectedGroup.id);
  };

  const handleMerge = async () => {
    if (!masterBookingId || !groupDetail) {
      toast.error('Ana rezervasyon seçiniz');
      return;
    }

    const mergeIds = groupDetail.bookings
      .filter(b => b.booking_id !== masterBookingId && !b.folio_merged_to)
      .map(b => b.booking_id);

    if (mergeIds.length === 0) {
      toast.error('Birleştirilebilecek folio yok');
      return;
    }

    setMerging(true);
    try {
      const res = await axios.post(`/pms/group-folio/merge`, {
        group_id: selectedGroup.id,
        master_booking_id: masterBookingId,
        merge_booking_ids: mergeIds,
        merge_payments: mergePayments,
      });
      toast.success(`${res.data?.merged_entries_count || 0} folio girişi ve ${res.data?.merged_payments_count || 0} ödeme birleştirildi`);
      setShowMerge(false);
      loadGroupDetail(selectedGroup.id);
      loadSummary();
    } catch (e) {
      toast.error('Birleştirme hatası: ' + (e.response?.data?.detail || e.message));
    } finally {
      setMerging(false);
    }
  };

  const handlePayment = async () => {
    const amt = parseFloat(paymentAmount);
    if (!amt || amt <= 0) {
      toast.error('Geçerli bir tutar giriniz');
      return;
    }

    setPaying(true);
    try {
      await axios.post(`/pms/group-folio/payment`, {
        group_id: selectedGroup.id,
        booking_id: paymentBookingId,
        amount: amt,
        method: paymentMethod,
        reference: paymentRef,
      });
      toast.success('Ödeme başarıyla kaydedildi');
      setShowPayment(false);
      setPaymentAmount('');
      setPaymentRef('');
      loadGroupDetail(selectedGroup.id);
      loadSummary();
    } catch (e) {
      toast.error('Ödeme hatası: ' + (e.response?.data?.detail || e.message));
    } finally {
      setPaying(false);
    }
  };

  const handleBulkPayment = async () => {
    const amt = parseFloat(bulkAmount);
    if (!amt || amt <= 0) {
      toast.error('Geçerli bir tutar giriniz');
      return;
    }

    setBulkPaying(true);
    try {
      const res = await axios.post(`/pms/group-folio/bulk-payment`, {
        group_id: selectedGroup.id,
        total_amount: amt,
        method: bulkMethod,
        reference: bulkRef,
        distribution: bulkDistribution,
      });
      toast.success(`${res.data?.payments_count || 0} rezervasyona toplam ${fmtTL(res.data?.total_distributed || 0)} TL dağıtıldı`);
      setShowBulkPayment(false);
      setBulkAmount('');
      setBulkRef('');
      loadGroupDetail(selectedGroup.id);
      loadSummary();
    } catch (e) {
      toast.error('Toplu ödeme hatası: ' + (e.response?.data?.detail || e.message));
    } finally {
      setBulkPaying(false);
    }
  };

  const filteredGroups = groups.filter(g =>
    !searchTerm || (g.group_name || '').toLowerCase().includes(searchTerm.toLowerCase())
  );

  const groupBalance = (groupDetail?.bookings || []).reduce((s, b) => s + (b.balance || 0), 0);
  const unmergedCount = (groupDetail?.bookings || []).filter(b => !b.folio_merged_to).length;

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="group_folio">
      <div className="p-4 md:p-6 space-y-5 max-w-7xl mx-auto" data-testid="group-folio-page">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Layers className="w-6 h-6 text-violet-600" />
              Grup Folio Yönetimi
            </h1>
            <p className="text-sm text-gray-500 mt-1">Grup rezervasyonlarının folio işlemlerini yönetin ve birleştirin</p>
          </div>
          <Button variant="outline" size="sm" onClick={handleRefresh} data-testid="refresh-btn">
            <RefreshCw className="w-4 h-4 mr-1" /> Yenile
          </Button>
        </div>

        {/* Summary Stats */}
        {summary && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="summary-stats">
            <StatCard icon={Users} label="Toplam Grup" value={summary.total_groups} sub={`${summary.active_groups} aktif`} color="bg-violet-100 text-violet-600" />
            <StatCard icon={FileText} label="Toplam Rez." value={summary.total_bookings} color="bg-blue-100 text-blue-600" />
            <StatCard icon={DollarSign} label="Toplam Bakiye" value={`${fmtTL(summary.total_balance)} TL`} color={summary.total_balance > 0 ? 'bg-red-100 text-red-600' : 'bg-emerald-100 text-emerald-600'} />
            <StatCard icon={Merge} label="Birlestirmeler" value={summary.merge_operations} sub={`${summary.merged_folios} folio`} color="bg-amber-100 text-amber-600" />
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Groups List Panel */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-gray-600 uppercase flex-1">Grup Rezervasyonlari</h2>
              <Badge variant="outline" className="text-xs">{filteredGroups.length}</Badge>
            </div>

            {/* Search */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <Input
                placeholder="Grup ara..."
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                className="pl-9 h-9 text-sm"
                data-testid="group-search-input"
              />
            </div>

            {loading ? (
              <div className="text-center py-8 text-gray-400">Yükleniyor...</div>
            ) : filteredGroups.length === 0 ? (
              <Card className="p-8 text-center">
                <Users className="w-10 h-10 text-gray-300 mx-auto mb-2" />
                <p className="text-sm text-gray-500">
                  {searchTerm ? 'Aramayla eşleşen grup yok' : 'Henüz grup rezervasyonu yok'}
                </p>
              </Card>
            ) : (
              <div className="space-y-2 max-h-[calc(100vh-340px)] overflow-y-auto pr-1">
                {filteredGroups.map(group => {
                  const bookingCount = (group.booking_ids || []).length;
                  const isSelected = selectedGroup?.id === group.id;
                  return (
                    <Card
                      key={group.id}
                      className={`cursor-pointer transition-all hover:shadow-md ${
                        isSelected ? 'ring-2 ring-violet-400 bg-violet-50/30' : ''
                      }`}
                      onClick={() => handleSelectGroup(group)}
                      data-testid={`group-card-${group.id}`}
                    >
                      <CardContent className="p-3">
                        <div className="flex items-center justify-between">
                          <div className="font-semibold text-sm truncate flex-1">{group.group_name}</div>
                          <Badge
                            className={`text-[10px] ml-2 ${
                              group.status === 'active'
                                ? 'bg-emerald-100 text-emerald-700 border-emerald-200'
                                : 'bg-gray-100 text-gray-600 border-gray-200'
                            }`}
                          >
                            {group.status === 'active' ? 'Aktif' : group.status || '-'}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-500">
                          <span className="flex items-center gap-1">
                            <Users className="w-3 h-3" /> {bookingCount} rez.
                          </span>
                          {group.total_rooms && (
                            <span className="flex items-center gap-1">
                              <Layers className="w-3 h-3" /> {group.total_rooms} oda
                            </span>
                          )}
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" /> {(group.created_at || '').slice(0, 10)}
                          </span>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </div>

          {/* Group Detail Panel */}
          <div className="lg:col-span-2 space-y-4">
            {!selectedGroup ? (
              <Card className="p-12 text-center">
                <Layers className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                <p className="text-gray-500">Soldaki listeden bir grup seçin</p>
                <p className="text-xs text-gray-400 mt-1">Folio detaylarını ve birleştirme işlemlerini görüntüleyebilirsiniz</p>
              </Card>
            ) : detailLoading ? (
              <Card className="p-12 text-center text-gray-400">Yükleniyor...</Card>
            ) : groupDetail ? (
              <>
                {/* Group header with actions */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold">{selectedGroup.group_name}</h2>
                    <p className="text-xs text-gray-500">
                      {unmergedCount} aktif folio / {(groupDetail.bookings || []).length} toplam
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setShowBulkPayment(true)}
                      disabled={!groupDetail.bookings || unmergedCount === 0}
                      className="border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                      data-testid="bulk-payment-btn"
                    >
                      <Users className="w-4 h-4 mr-1" /> Toplu Ödeme
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        const firstUnmerged = groupDetail.bookings?.find(b => !b.folio_merged_to);
                        if (firstUnmerged) {
                          setPaymentBookingId(firstUnmerged.booking_id);
                          setShowPayment(true);
                        }
                      }}
                      disabled={!groupDetail.bookings || groupDetail.bookings.length === 0}
                      data-testid="add-payment-btn"
                    >
                      <Banknote className="w-4 h-4 mr-1" /> Ödeme Ekle
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => {
                        setShowMerge(true);
                        setMasterBookingId(groupDetail.bookings?.find(b => !b.folio_merged_to)?.booking_id || '');
                      }}
                      disabled={!groupDetail.bookings || unmergedCount < 2}
                      className="bg-violet-600 hover:bg-violet-700"
                      data-testid="merge-btn"
                    >
                      <Merge className="w-4 h-4 mr-1" /> Folioları Birleştir
                    </Button>
                  </div>
                </div>

                {/* Bookings in Group */}
                <div className="space-y-2">
                  {(groupDetail.bookings || []).map((b) => {
                    const isExpanded = expandedBooking === b.booking_id;
                    const isMerged = !!b.folio_merged_to;
                    return (
                      <div key={b.booking_id} data-testid={`booking-folio-${b.booking_id}`}>
                        <Card className={isMerged ? 'opacity-70' : ''}>
                          <CardContent className="p-0">
                            <div
                              className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 cursor-pointer hover:bg-gray-50/50 transition-colors"
                              onClick={() => setExpandedBooking(isExpanded ? null : b.booking_id)}
                              data-testid={`booking-row-${b.booking_id}`}
                            >
                              <div className="flex items-center gap-3">
                                {isExpanded ? (
                                  <ChevronDown className="w-4 h-4 text-gray-400 shrink-0" />
                                ) : (
                                  <ChevronRight className="w-4 h-4 text-gray-400 shrink-0" />
                                )}
                                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-violet-100 to-violet-200 flex items-center justify-center text-sm font-bold text-violet-700">
                                  {b.room_number || '?'}
                                </div>
                                <div>
                                  <div className="font-semibold text-sm">{b.guest_name}</div>
                                  <div className="text-xs text-gray-500">Oda: {b.room_number}</div>
                                </div>
                              </div>
                              <div className="flex items-center gap-4">
                                <div className="grid grid-cols-3 gap-4 text-center">
                                  <div>
                                    <div className="text-[11px] text-gray-500">Konaklama</div>
                                    <div className="text-sm font-semibold">{fmtTL(b.accommodation_total)} TL</div>
                                  </div>
                                  <div>
                                    <div className="text-[11px] text-gray-500">Ödeme</div>
                                    <div className="text-sm font-semibold text-emerald-600">{fmtTL(b.payments)} TL</div>
                                  </div>
                                  <div>
                                    <div className="text-[11px] text-gray-500">Bakiye</div>
                                    <div className={`text-sm font-bold ${b.balance > 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                                      {fmtTL(b.balance)} TL
                                    </div>
                                  </div>
                                </div>
                                <div className="shrink-0">
                                  {isMerged ? (
                                    <Badge className="bg-purple-100 text-purple-700 border-purple-200 text-[10px]">
                                      <Lock className="w-3 h-3 mr-1" /> Birlestirildi
                                    </Badge>
                                  ) : (
                                    <Badge className="bg-blue-100 text-blue-700 border-blue-200 text-[10px]">Aktif</Badge>
                                  )}
                                </div>
                              </div>
                            </div>
                            {/* Expanded folio detail */}
                            {isExpanded && (
                              <div className="px-4 pb-4 border-t border-gray-100">
                                <div className="flex items-center justify-between pt-3 pb-2">
                                  <span className="text-xs font-semibold text-gray-500 uppercase">Folio Detayları</span>
                                  {!isMerged && (
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      className="text-xs h-7"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        setPaymentBookingId(b.booking_id);
                                        setShowPayment(true);
                                      }}
                                      data-testid={`pay-btn-${b.booking_id}`}
                                    >
                                      <CreditCard className="w-3 h-3 mr-1" /> Ödeme Yap
                                    </Button>
                                  )}
                                </div>
                                <BookingFolioDetail groupId={selectedGroup.id} bookingId={b.booking_id} />
                              </div>
                            )}
                          </CardContent>
                        </Card>
                      </div>
                    );
                  })}
                </div>

                {/* Grand Total */}
                <Card className="bg-gradient-to-r from-violet-50 to-indigo-50 border-violet-200" data-testid="group-total-card">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-violet-700">Grup Toplam Bakiye</span>
                      <span className={`text-xl font-bold ${groupBalance > 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                        {fmtTL(groupBalance)} TL
                      </span>
                    </div>
                  </CardContent>
                </Card>

                {/* Merge Logs */}
                {groupDetail.merge_logs?.length > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold text-gray-600 mb-2">Birleştirme Geçmişi</h3>
                    {groupDetail.merge_logs.map(log => (
                      <Card key={log.id} className="mb-2">
                        <CardContent className="p-3 text-xs text-gray-600">
                          <div className="flex items-center gap-2">
                            <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                            <span>{log.merged_by} - {log.total_entries_merged} giriş, {log.total_payments_merged} ödeme birleştirildi</span>
                            <span className="ml-auto text-gray-400 whitespace-nowrap">{(log.created_at || '').slice(0, 16).replace('T', ' ')}</span>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}
              </>
            ) : null}
          </div>
        </div>

        {/* ─── Merge Dialog ─── */}
        <Dialog open={showMerge} onOpenChange={setShowMerge}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Merge className="w-5 h-5 text-violet-600" /> Folioları Birleştir
              </DialogTitle>
              <DialogDescription>
                Grup içerisindeki folio girişlerini tek bir ana folioda toplayın.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-700 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>Bu işlem diğer odaların folio girişlerini seçilen ana folioya taşıyacaktır. Bu işlem geri alınamaz.</span>
              </div>

              <div>
                <Label>Ana Rezervasyon (Master Folio)</Label>
                <select
                  value={masterBookingId}
                  onChange={e => setMasterBookingId(e.target.value)}
                  className="w-full border rounded-md px-3 py-2 text-sm mt-1"
                  data-testid="master-booking-select"
                >
                  {(groupDetail?.bookings || []).filter(b => !b.folio_merged_to).map(b => (
                    <option key={b.booking_id} value={b.booking_id}>
                      Oda {b.room_number} - {b.guest_name} (Bakiye: {fmtTL(b.balance)} TL)
                    </option>
                  ))}
                </select>
              </div>

              <div className="text-sm text-gray-600">
                <div className="font-medium mb-2">Birleştirilecek Foliolar:</div>
                {(groupDetail?.bookings || []).filter(b => b.booking_id !== masterBookingId && !b.folio_merged_to).map(b => (
                  <div key={b.booking_id} className="flex items-center gap-2 py-1">
                    <ArrowRight className="w-3 h-3 text-violet-500" />
                    Oda {b.room_number} - {b.guest_name} ({fmtTL(b.balance)} TL)
                  </div>
                ))}
              </div>

              <div className="flex items-center gap-2">
                <input type="checkbox" checked={mergePayments} onChange={e => setMergePayments(e.target.checked)} className="w-4 h-4 rounded" id="merge-payments" />
                <Label htmlFor="merge-payments" className="cursor-pointer text-sm">Ödemeleri de birleştir</Label>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowMerge(false)}>İptal</Button>
                <Button onClick={handleMerge} disabled={merging} className="bg-violet-600 hover:bg-violet-700" data-testid="confirm-merge-btn">
                  {merging ? 'Birleştiriliyor...' : 'Birleştir'}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        {/* ─── Payment Dialog ─── */}
        <Dialog open={showPayment} onOpenChange={setShowPayment}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <CreditCard className="w-5 h-5 text-emerald-600" /> Ödeme Kaydet
              </DialogTitle>
              <DialogDescription>
                Seçilen rezervasyon için ödeme girişi yapın.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label>Rezervasyon</Label>
                <select
                  value={paymentBookingId}
                  onChange={e => setPaymentBookingId(e.target.value)}
                  className="w-full border rounded-md px-3 py-2 text-sm mt-1"
                  data-testid="payment-booking-select"
                >
                  {(groupDetail?.bookings || []).filter(b => !b.folio_merged_to).map(b => (
                    <option key={b.booking_id} value={b.booking_id}>
                      Oda {b.room_number} - {b.guest_name} (Bakiye: {fmtTL(b.balance)} TL)
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <Label>Tutar (TL)</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={paymentAmount}
                  onChange={e => setPaymentAmount(e.target.value)}
                  placeholder="0.00"
                  className="mt-1"
                  data-testid="payment-amount-input"
                />
              </div>

              <div>
                <Label>Ödeme Yöntemi</Label>
                <Select value={paymentMethod} onValueChange={setPaymentMethod}>
                  <SelectTrigger className="mt-1" data-testid="payment-method-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Nakit</SelectItem>
                    <SelectItem value="credit_card">Kredi Kartı</SelectItem>
                    <SelectItem value="bank_transfer">Banka Havale</SelectItem>
                    <SelectItem value="agency">Acenta</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label>Referans / Açıklama</Label>
                <Input
                  value={paymentRef}
                  onChange={e => setPaymentRef(e.target.value)}
                  placeholder="Opsiyonel"
                  className="mt-1"
                  data-testid="payment-ref-input"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowPayment(false)}>İptal</Button>
                <Button onClick={handlePayment} disabled={paying} className="bg-emerald-600 hover:bg-emerald-700" data-testid="confirm-payment-btn">
                  {paying ? 'Kaydediliyor...' : 'Ödemeyi Kaydet'}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        {/* ─── Bulk Payment Dialog ─── */}
        <Dialog open={showBulkPayment} onOpenChange={setShowBulkPayment}>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Users className="w-5 h-5 text-emerald-600" /> Tüm Grup İçin Toplu Ödeme
              </DialogTitle>
              <DialogDescription>
                Girdiğiniz tutar gruptaki aktif rezervasyonlara otomatik dağıtılır.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              {/* Summary info */}
              <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-700">
                <div className="font-medium mb-1">Grup: {selectedGroup?.group_name}</div>
                <div className="flex gap-4 text-xs">
                  <span>{unmergedCount} aktif rezervasyon</span>
                  <span>Toplam bakiye: <strong>{fmtTL(groupBalance)} TL</strong></span>
                </div>
              </div>

              <div>
                <Label>Toplam Tutar (TL)</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={bulkAmount}
                  onChange={e => setBulkAmount(e.target.value)}
                  placeholder={groupBalance > 0 ? fmtTL(groupBalance) : '0.00'}
                  className="mt-1"
                  data-testid="bulk-amount-input"
                />
                {groupBalance > 0 && (
                  <Button
                    variant="link"
                    size="sm"
                    className="text-xs text-blue-600 p-0 h-auto mt-1"
                    onClick={() => setBulkAmount(String(groupBalance > 0 ? groupBalance : 0))}
                    data-testid="fill-balance-btn"
                  >
                    Bakiye tutarını doldur ({fmtTL(groupBalance)} TL)
                  </Button>
                )}
              </div>

              <div>
                <Label>Dağıtım Yöntemi</Label>
                <Select value={bulkDistribution} onValueChange={setBulkDistribution}>
                  <SelectTrigger className="mt-1" data-testid="bulk-distribution-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="proportional">Oransal (bakiyeye göre)</SelectItem>
                    <SelectItem value="equal">Eşit (her rezervasyona eşit)</SelectItem>
                    <SelectItem value="balance_only">Sadece bakiyesi olan</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label>Ödeme Yöntemi</Label>
                <Select value={bulkMethod} onValueChange={setBulkMethod}>
                  <SelectTrigger className="mt-1" data-testid="bulk-method-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Nakit</SelectItem>
                    <SelectItem value="credit_card">Kredi Kartı</SelectItem>
                    <SelectItem value="bank_transfer">Banka Havale</SelectItem>
                    <SelectItem value="agency">Acenta</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label>Referans / Açıklama</Label>
                <Input
                  value={bulkRef}
                  onChange={e => setBulkRef(e.target.value)}
                  placeholder="Opsiyonel"
                  className="mt-1"
                  data-testid="bulk-ref-input"
                />
              </div>

              {/* Preview distribution */}
              {bulkAmount && parseFloat(bulkAmount) > 0 && (
                <div className="border rounded-lg p-3 bg-gray-50">
                  <div className="text-xs font-semibold text-gray-500 uppercase mb-2">Dağıtım Önizleme</div>
                  {(groupDetail?.bookings || []).filter(b => !b.folio_merged_to).map(b => {
                    const amt = parseFloat(bulkAmount) || 0;
                    const totalPos = (groupDetail?.bookings || []).filter(x => !x.folio_merged_to && x.balance > 0).reduce((s, x) => s + x.balance, 0);
                    let share = 0;
                    if (bulkDistribution === 'equal') {
                      share = amt / unmergedCount;
                    } else if (bulkDistribution === 'balance_only') {
                      share = b.balance > 0 ? Math.min(b.balance, amt * (b.balance / Math.max(totalPos, 1))) : 0;
                    } else {
                      share = totalPos > 0 && b.balance > 0 ? amt * (b.balance / totalPos) : amt / unmergedCount;
                    }
                    return (
                      <div key={b.booking_id} className="flex items-center justify-between text-sm py-1 border-b border-gray-100 last:border-0">
                        <span className="text-gray-600">Oda {b.room_number} - {b.guest_name}</span>
                        <span className="font-medium text-emerald-600">{fmtTL(share)} TL</span>
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowBulkPayment(false)}>İptal</Button>
                <Button
                  onClick={handleBulkPayment}
                  disabled={bulkPaying || !bulkAmount || parseFloat(bulkAmount) <= 0}
                  className="bg-emerald-600 hover:bg-emerald-700"
                  data-testid="confirm-bulk-payment-btn"
                >
                  {bulkPaying ? 'Dağıtılıyor...' : 'Toplu Ödemeyi Kaydet'}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
};

export default GroupFolioPage;
