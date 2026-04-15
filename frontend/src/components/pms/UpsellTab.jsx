import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  TrendingUp, Search, CheckCircle, XCircle, RefreshCw, Sparkles,
  ArrowUpRight, Clock, Car, LogIn, LogOut, BedDouble, BarChart3,
  DollarSign, Target, Percent, Building2
} from 'lucide-react';

const TYPE_LABELS = {
  room_upgrade: { label: 'Oda Yukseltme', icon: ArrowUpRight, color: 'bg-blue-100 text-blue-800' },
  early_checkin: { label: 'Erken Check-in', icon: LogIn, color: 'bg-green-100 text-green-800' },
  late_checkout: { label: 'Gec Check-out', icon: LogOut, color: 'bg-purple-100 text-purple-800' },
  airport_transfer: { label: 'Transfer', icon: Car, color: 'bg-orange-100 text-orange-800' },
};

const INSIGHT_STYLES = {
  success: 'bg-emerald-50 border-emerald-200',
  warning: 'bg-amber-50 border-amber-200',
  info: 'bg-blue-50 border-blue-200',
};
const INSIGHT_DOT = {
  success: 'bg-emerald-500',
  warning: 'bg-amber-500',
  info: 'bg-blue-500',
};
const INSIGHT_TITLE_COLOR = {
  success: 'text-emerald-800',
  warning: 'text-amber-800',
  info: 'text-blue-800',
};
const INSIGHT_TEXT_COLOR = {
  success: 'text-emerald-700',
  warning: 'text-amber-700',
  info: 'text-blue-700',
};

const UpsellTab = ({ bookings = [] }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedBooking, setSelectedBooking] = useState(null);
  const [offers, setOffers] = useState([]);
  const [allOffers, setAllOffers] = useState([]);
  const [offerSummary, setOfferSummary] = useState(null);
  const [revenueInsights, setRevenueInsights] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingAction, setLoadingAction] = useState(null);
  const [filterStatus, setFilterStatus] = useState('all');

  const loadAllOffers = useCallback(async () => {
    try {
      const res = await axios.get('/ai/upsell/offers');
      setAllOffers(res.data.offers || []);
      setOfferSummary(res.data.summary || null);
    } catch {
      toast.error('Teklif gecmisi yuklenemedi');
    }
  }, []);

  const loadInsights = useCallback(async () => {
    try {
      const res = await axios.get('/ai/upsell/revenue-insights');
      setRevenueInsights(res.data);
    } catch {
      toast.error('Gelir analizi yuklenemedi');
    }
  }, []);

  useEffect(() => {
    loadAllOffers();
    loadInsights();
  }, [loadAllOffers, loadInsights]);

  const activeBookings = bookings.filter(b =>
    ['confirmed', 'guaranteed', 'checked_in'].includes(b.status)
  );

  const filteredBookings = activeBookings.filter(b => {
    const term = searchTerm.toLowerCase();
    if (!term) return true;
    return (
      (b.guest_name || '').toLowerCase().includes(term) ||
      (b.id || '').toLowerCase().includes(term) ||
      (b.room_number || '').toString().includes(term)
    );
  });

  const selectBooking = async (booking) => {
    setSelectedBooking(booking);
    setLoading(true);
    try {
      const existing = allOffers.filter(o => o.booking_id === booking.id);
      if (existing.length > 0) {
        setOffers(existing);
        setLoading(false);
        return;
      }
      const res = await axios.post(`/ai/upsell/generate?booking_id=${booking.id}`, {}, { timeout: 10000 });
      setOffers(res.data.offers || []);
      toast.success(`${res.data.total_offers} teklif uretildi`);
      loadAllOffers();
      loadInsights();
    } catch (err) {
      if (err.response?.status === 404) {
        toast.error('Rezervasyon bulunamadi');
      } else {
        toast.error(err.response?.data?.detail || 'Teklif uretme basarisiz');
      }
    }
    setLoading(false);
  };

  const regenerateOffers = async () => {
    if (!selectedBooking) return;
    setLoading(true);
    try {
      const res = await axios.post(`/ai/upsell/generate?booking_id=${selectedBooking.id}`, {}, { timeout: 10000 });
      setOffers(res.data.offers || []);
      toast.success(`${res.data.total_offers} yeni teklif uretildi`);
      loadAllOffers();
      loadInsights();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Teklif uretme basarisiz');
    }
    setLoading(false);
  };

  const handleOfferAction = async (offerId, action) => {
    setLoadingAction(offerId);
    try {
      await axios.put(`/ai/upsell/offers/${offerId}?action=${action}`);
      toast.success(action === 'accepted' ? 'Teklif kabul edildi ve folioya eklendi' : 'Teklif reddedildi');
      setOffers(prev => prev.map(o => o.id === offerId ? { ...o, status: action } : o));
      loadAllOffers();
      loadInsights();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Islem basarisiz');
    }
    setLoadingAction(null);
  };

  const displayOffers = filterStatus === 'all'
    ? allOffers
    : allOffers.filter(o => o.status === filterStatus);

  const kpis = revenueInsights?.kpis;
  const upsellSummary = revenueInsights?.upsell_summary;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-semibold">Upsell & Gelir Optimizasyonu</h2>
        <Button variant="outline" size="sm" onClick={() => { loadAllOffers(); loadInsights(); }}>
          <RefreshCw className="w-4 h-4 mr-2" /> Yenile
        </Button>
      </div>

      {kpis && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card className="border-l-4 border-l-blue-500">
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
                <Percent className="w-4 h-4" /> Doluluk
              </div>
              <p className="text-2xl font-bold">%{kpis.occupancy_rate}</p>
              <p className="text-xs text-gray-400">{kpis.occupied_rooms} / {kpis.total_rooms} oda</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-emerald-500">
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
                <DollarSign className="w-4 h-4" /> ADR
              </div>
              <p className="text-2xl font-bold">{kpis.adr?.toFixed(0)} TL</p>
              <p className="text-xs text-gray-400">Ortalama Gunluk Fiyat</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-purple-500">
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
                <BarChart3 className="w-4 h-4" /> RevPAR
              </div>
              <p className="text-2xl font-bold">{kpis.revpar?.toFixed(0)} TL</p>
              <p className="text-xs text-gray-400">Oda Basina Gelir</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-amber-500">
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
                <TrendingUp className="w-4 h-4" /> Upsell Geliri
              </div>
              <p className="text-2xl font-bold">{(upsellSummary?.revenue || 0).toFixed(0)} TL</p>
              <p className="text-xs text-gray-400">
                {upsellSummary?.accepted || 0} kabul / {upsellSummary?.total || 0} toplam
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Search className="w-4 h-4" /> Rezervasyon Sec
            </CardTitle>
            <CardDescription>Upsell teklifi uretmek icin bir rezervasyon secin</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Input
              placeholder="Misafir adi, oda no veya rez. ID..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="text-sm"
            />
            <div className="max-h-[400px] overflow-y-auto space-y-2">
              {filteredBookings.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-4">Aktif rezervasyon bulunamadi</p>
              ) : (
                filteredBookings.slice(0, 20).map(b => (
                  <div
                    key={b.id}
                    onClick={() => selectBooking(b)}
                    className={`border rounded-lg p-3 cursor-pointer transition-all hover:border-blue-400 hover:bg-blue-50/50 ${
                      selectedBooking?.id === b.id ? 'border-blue-500 bg-blue-50' : ''
                    }`}
                  >
                    <div className="flex justify-between items-start">
                      <div>
                        <p className="font-medium text-sm">{b.guest_name || 'Misafir'}</p>
                        <p className="text-xs text-gray-500">Oda {b.room_number} - {b.room_type}</p>
                      </div>
                      <Badge variant="outline" className="text-xs">
                        {b.status === 'checked_in' ? 'Konaklama' : 'Onaylanmis'}
                      </Badge>
                    </div>
                    <div className="flex gap-3 mt-1 text-xs text-gray-400">
                      <span>{b.check_in?.slice(0, 10)}</span>
                      <span>→</span>
                      <span>{b.check_out?.slice(0, 10)}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader className="pb-3">
            <div className="flex justify-between items-center">
              <div>
                <CardTitle className="text-base flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-amber-500" /> Upsell Teklifleri
                </CardTitle>
                <CardDescription>
                  {selectedBooking
                    ? `${selectedBooking.guest_name} - Oda ${selectedBooking.room_number}`
                    : 'Sol taraftan bir rezervasyon secin'}
                </CardDescription>
              </div>
              {selectedBooking && (
                <Button variant="outline" size="sm" onClick={regenerateOffers} disabled={loading} className="h-7 text-xs">
                  <Sparkles className="w-3 h-3 mr-1" /> Yeniden Uret
                </Button>
              )}
              {loading && <RefreshCw className="w-4 h-4 animate-spin text-blue-500" />}
            </div>
          </CardHeader>
          <CardContent>
            {!selectedBooking && offers.length === 0 ? (
              <div className="text-center py-12 text-gray-400">
                <Sparkles className="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p className="font-medium">Henuz teklif yok</p>
                <p className="text-sm">Bir rezervasyon sectiginizde AI otomatik teklif uretecek</p>
              </div>
            ) : (
              <div className="space-y-3">
                {offers.map(offer => {
                  const typeInfo = TYPE_LABELS[offer.type] || { label: offer.type, icon: TrendingUp, color: 'bg-gray-100 text-gray-800' };
                  const TypeIcon = typeInfo.icon;
                  const isPending = offer.status === 'pending';
                  return (
                    <div key={offer.id} className={`border rounded-lg p-4 transition-all ${
                      offer.status === 'accepted' ? 'border-emerald-300 bg-emerald-50/30' :
                      offer.status === 'rejected' ? 'border-red-200 bg-red-50/20 opacity-60' : ''
                    }`}>
                      <div className="flex justify-between items-start mb-2">
                        <div className="flex items-center gap-2">
                          <TypeIcon className="w-4 h-4 text-gray-600" />
                          <span className="font-medium text-sm">{typeInfo.label}</span>
                          <Badge className={`text-xs ${typeInfo.color}`}>{offer.type}</Badge>
                        </div>
                        <span className="font-bold text-lg">{offer.price?.toFixed(0)} TL</span>
                      </div>
                      <div className="text-sm text-gray-600 mb-2">
                        {offer.current_item && <span>{offer.current_item} → </span>}
                        <span className="font-medium">{offer.target_item}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3 text-xs text-gray-400">
                          <span className="flex items-center gap-1">
                            <Target className="w-3 h-3" /> %{(offer.confidence * 100).toFixed(0)} guven
                          </span>
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" /> {offer.valid_until?.slice(0, 10)}
                          </span>
                        </div>
                        {isPending ? (
                          <div className="flex gap-2">
                            <Button
                              size="sm"
                              variant="outline"
                              className="text-red-600 border-red-200 hover:bg-red-50 h-7 text-xs"
                              disabled={loadingAction === offer.id}
                              onClick={() => handleOfferAction(offer.id, 'rejected')}
                            >
                              <XCircle className="w-3 h-3 mr-1" /> Reddet
                            </Button>
                            <Button
                              size="sm"
                              className="bg-emerald-600 hover:bg-emerald-700 h-7 text-xs"
                              disabled={loadingAction === offer.id}
                              onClick={() => handleOfferAction(offer.id, 'accepted')}
                            >
                              {loadingAction === offer.id
                                ? <RefreshCw className="w-3 h-3 mr-1 animate-spin" />
                                : <CheckCircle className="w-3 h-3 mr-1" />
                              }
                              Kabul Et
                            </Button>
                          </div>
                        ) : (
                          <Badge variant={offer.status === 'accepted' ? 'default' : 'secondary'} className="text-xs">
                            {offer.status === 'accepted' ? 'Kabul Edildi' : 'Reddedildi'}
                          </Badge>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader className="pb-3">
            <div className="flex justify-between items-center">
              <CardTitle className="text-base flex items-center gap-2">
                <BarChart3 className="w-4 h-4" /> Teklif Gecmisi
              </CardTitle>
              <Select value={filterStatus} onValueChange={setFilterStatus}>
                <SelectTrigger className="w-[140px] h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Tumu ({offerSummary?.total || 0})</SelectItem>
                  <SelectItem value="pending">Bekleyen ({offerSummary?.pending || 0})</SelectItem>
                  <SelectItem value="accepted">Kabul ({offerSummary?.accepted || 0})</SelectItem>
                  <SelectItem value="rejected">Red ({offerSummary?.rejected || 0})</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardHeader>
          <CardContent>
            {displayOffers.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-6">Henuz teklif gecmisi yok</p>
            ) : (
              <div className="max-h-[350px] overflow-y-auto space-y-2">
                {displayOffers.slice(0, 50).map(offer => {
                  const typeInfo = TYPE_LABELS[offer.type] || { label: offer.type, color: 'bg-gray-100 text-gray-800' };
                  return (
                    <div key={offer.id} className="flex items-center justify-between border rounded-lg px-3 py-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <Badge className={`text-xs shrink-0 ${typeInfo.color}`}>{typeInfo.label}</Badge>
                        <span className="text-xs text-gray-500 truncate">{offer.booking_id?.slice(0, 8)}...</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-sm font-medium">{offer.price?.toFixed(0)} TL</span>
                        <Badge variant={
                          offer.status === 'accepted' ? 'default' :
                          offer.status === 'rejected' ? 'secondary' : 'outline'
                        } className="text-xs">
                          {offer.status === 'accepted' ? 'Kabul' :
                           offer.status === 'rejected' ? 'Red' : 'Bekliyor'}
                        </Badge>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Building2 className="w-4 h-4" /> Gelir Analizi
            </CardTitle>
            <CardDescription>Gercek verilere dayali oneriler</CardDescription>
          </CardHeader>
          <CardContent>
            {!revenueInsights?.insights?.length ? (
              <p className="text-sm text-gray-400 text-center py-6">Analiz icin yeterli veri yok</p>
            ) : (
              <div className="space-y-3">
                {revenueInsights.insights.map((insight, i) => (
                  <div key={i} className={`border rounded-lg p-4 ${INSIGHT_STYLES[insight.type] || 'bg-gray-50 border-gray-200'}`}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${INSIGHT_DOT[insight.type] || 'bg-gray-500'}`} />
                        <span className={`font-semibold text-sm ${INSIGHT_TITLE_COLOR[insight.type] || 'text-gray-800'}`}>
                          {insight.title}
                        </span>
                      </div>
                      {insight.metric && (
                        <Badge variant="outline" className="text-xs font-bold">{insight.metric}</Badge>
                      )}
                    </div>
                    <p className={`text-sm ${INSIGHT_TEXT_COLOR[insight.type] || 'text-gray-700'}`}>
                      {insight.text}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default UpsellTab;
