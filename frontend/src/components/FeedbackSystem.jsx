import { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Star, MessageCircle, RefreshCw, Send, TrendingUp, Mail, Globe,
  Building2, ClipboardList, Inbox, Search, ExternalLink, CheckCircle2
} from 'lucide-react';

const SOURCE_META = {
  internal: { label: 'Otel İçi', color: 'bg-indigo-100 text-indigo-700 border-indigo-200', icon: Inbox },
  external: { label: 'Dış Platform', color: 'bg-blue-100 text-blue-700 border-blue-200', icon: Globe },
  survey: { label: 'Anket', color: 'bg-amber-100 text-amber-700 border-amber-200', icon: ClipboardList },
  department: { label: 'Departman', color: 'bg-emerald-100 text-emerald-700 border-emerald-200', icon: Building2 },
};

const PLATFORM_LABEL = {
  booking: 'Booking.com',
  google: 'Google',
  tripadvisor: 'TripAdvisor',
  expedia: 'Expedia',
  hotels: 'Hotels.com',
};

const safe = (p) => p.catch(() => ({ data: null }));

const renderStars = (rating, size = 'w-4 h-4') => (
  <div className="flex gap-0.5">
    {Array.from({ length: 5 }, (_, i) => (
      <Star key={i} className={`${size} ${i < (rating || 0) ? 'text-yellow-400 fill-yellow-400' : 'text-gray-300'}`} />
    ))}
  </div>
);

const formatDate = (raw) => {
  if (!raw) return '';
  try {
    return new Date(raw).toLocaleDateString('tr-TR', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch {
    return String(raw).slice(0, 10);
  }
};

const FeedbackSystem = () => {
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState('all');
  const [internal, setInternal] = useState([]);
  const [external, setExternal] = useState([]);
  const [surveys, setSurveys] = useState([]);
  const [department, setDepartment] = useState([]);

  const [respondDialog, setRespondDialog] = useState(null); // { id, source, guest_name }
  const [responseText, setResponseText] = useState('');
  const [sending, setSending] = useState(false);

  const [inviteOpen, setInviteOpen] = useState(false);
  const [bookings, setBookings] = useState([]);
  const [bookingsLoading, setBookingsLoading] = useState(false);
  const [bookingSearch, setBookingSearch] = useState('');
  const [sendingInvite, setSendingInvite] = useState(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [intRes, extRes, surveysRes, deptRes] = await Promise.all([
        safe(axios.get('/crm/reviews')),
        safe(axios.get('/feedback/external-reviews')),
        safe(axios.get('/feedback/surveys')),
        safe(axios.get('/feedback/department')),
      ]);

      setInternal(intRes.data?.reviews || []);
      setExternal(extRes.data?.reviews || []);
      setDepartment(deptRes.data?.feedback || []);

      const surveyList = surveysRes.data?.surveys || [];
      const responseAggregates = await Promise.all(
        surveyList.slice(0, 10).map(s =>
          safe(axios.get(`/feedback/surveys/${s.id}/responses`)).then(r => ({
            survey: s,
            responses: r.data?.responses || [],
          }))
        )
      );
      setSurveys(responseAggregates);
    } catch {
      toast.error('Geri bildirimler yüklenemedi');
    }
    setLoading(false);
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const respondToReview = async () => {
    if (!responseText.trim() || !respondDialog) return;
    setSending(true);
    try {
      const url = respondDialog.source === 'external'
        ? `/feedback/external-reviews/${respondDialog.id}/respond`
        : `/crm/reviews/${respondDialog.id}/respond`;
      await axios.post(url, { response: responseText });
      toast.success('Yanıt gönderildi');
      setRespondDialog(null);
      setResponseText('');
      loadAll();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Yanıt gönderilemedi');
    }
    setSending(false);
  };

  const openInvite = async () => {
    setInviteOpen(true);
    setBookingSearch('');
    setBookingsLoading(true);
    try {
      const res = await axios.get('/bookings');
      const list = res.data?.bookings || res.data || [];
      setBookings(Array.isArray(list) ? list.filter(b => b.guest_email).slice(0, 200) : []);
    } catch {
      toast.error('Rezervasyonlar yüklenemedi');
      setBookings([]);
    }
    setBookingsLoading(false);
  };

  const sendInvite = async (booking) => {
    setSendingInvite(booking.id);
    try {
      const res = await axios.post('/feedback/review-invite', {
        booking_id: booking.id,
        guest_email: booking.guest_email,
      });
      if (res.data?.sent === false) {
        toast.warning('E-posta sağlayıcısı yapılandırılmamış olabilir, davet kaydedildi (link: ' + (res.data?.link || '') + ')', { duration: 8000 });
      } else {
        toast.success(`Davet gönderildi: ${booking.guest_name || booking.guest_email}`);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Davet gönderilemedi');
    }
    setSendingInvite(null);
  };

  const combined = useMemo(() => {
    const items = [];
    internal.forEach(r => items.push({
      _key: `int-${r.id}`,
      _source: 'internal',
      id: r.id,
      guest_name: r.guest_name,
      rating: r.rating,
      comment: r.comment,
      response: r.response,
      created_at: r.created_at,
      category: r.category,
      sourceLabel: r.source === 'direct_invite' ? 'Davet ile' : null,
    }));
    external.forEach(r => items.push({
      _key: `ext-${r.id}`,
      _source: 'external',
      id: r.id,
      guest_name: r.reviewer_name,
      rating: r.rating,
      comment: r.review_text,
      response: r.response,
      created_at: r.review_date || r.received_at,
      sourceLabel: PLATFORM_LABEL[r.platform] || r.platform,
      sentiment: r.sentiment,
      external_url: r.review_url,
    }));
    surveys.forEach(({ survey, responses }) => {
      responses.forEach(resp => items.push({
        _key: `srv-${resp.id}`,
        _source: 'survey',
        id: resp.id,
        guest_name: resp.guest_name,
        rating: resp.overall_rating,
        comment: (resp.responses || []).filter(a => a.answer).map(a => a.answer).join(' • '),
        created_at: resp.submitted_at,
        sourceLabel: survey.survey_name,
      }));
    });
    department.forEach(f => items.push({
      _key: `dep-${f.id}`,
      _source: 'department',
      id: f.id,
      guest_name: f.guest_name,
      rating: f.rating,
      comment: f.comment,
      created_at: f.submitted_at,
      sourceLabel: f.department,
      staff: f.staff_member,
    }));
    return items.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
  }, [internal, external, surveys, department]);

  const stats = useMemo(() => {
    const all = combined.filter(c => typeof c.rating === 'number' && c.rating > 0);
    if (all.length === 0) return { avg: 0, total: 0, sat: 0, breakdown: {} };
    const avg = all.reduce((s, r) => s + r.rating, 0) / all.length;
    const sat = (all.filter(r => r.rating >= 4).length / all.length) * 100;
    const breakdown = { internal: 0, external: 0, survey: 0, department: 0 };
    combined.forEach(c => { breakdown[c._source] = (breakdown[c._source] || 0) + 1; });
    return { avg: avg.toFixed(1), total: combined.length, sat: sat.toFixed(0), breakdown };
  }, [combined]);

  const visible = useMemo(() => {
    if (view === 'all') return combined;
    return combined.filter(c => c._source === view);
  }, [combined, view]);

  const filteredBookings = useMemo(() => {
    const s = bookingSearch.trim().toLowerCase();
    if (!s) return bookings;
    return bookings.filter(b =>
      (b.guest_name || '').toLowerCase().includes(s) ||
      (b.guest_email || '').toLowerCase().includes(s) ||
      (b.room_number || '').toString().includes(s)
    );
  }, [bookings, bookingSearch]);

  const getRatingBadge = (rating) => {
    if (!rating) return <Badge variant="outline" className="text-gray-500">Puanlanmamış</Badge>;
    if (rating >= 4) return <Badge className="bg-green-100 text-green-700">Memnun</Badge>;
    if (rating >= 3) return <Badge className="bg-yellow-100 text-yellow-700">Orta</Badge>;
    return <Badge className="bg-red-100 text-red-700">Memnun değil</Badge>;
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center flex-wrap gap-3">
        <div>
          <h3 className="text-2xl font-bold flex items-center gap-2">
            <MessageCircle className="w-6 h-6" /> Misafir Geri Bildirimleri
          </h3>
          <p className="text-gray-600 text-sm">Tüm kaynaklardan gelen değerlendirmeleri tek yerden takip edin ve yanıtlayın</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={loadAll} disabled={loading} data-testid="btn-feedback-refresh">
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> Yenile
          </Button>
          <Button size="sm" onClick={openInvite} data-testid="btn-feedback-invite">
            <Mail className="w-4 h-4 mr-2" /> Değerlendirme İste
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="bg-yellow-50 border-yellow-200">
          <CardContent className="p-5 text-center">
            <Star className="w-6 h-6 mx-auto mb-1 text-yellow-500 fill-yellow-500" />
            <p className="text-xs text-yellow-600">Ortalama Puan</p>
            <p className="text-3xl font-bold text-yellow-700">{stats.avg}</p>
            <div className="flex justify-center mt-1">{renderStars(Math.round(stats.avg))}</div>
          </CardContent>
        </Card>
        <Card className="bg-blue-50 border-blue-200">
          <CardContent className="p-5 text-center">
            <MessageCircle className="w-6 h-6 mx-auto mb-1 text-blue-500" />
            <p className="text-xs text-blue-600">Toplam Değerlendirme</p>
            <p className="text-3xl font-bold text-blue-700">{stats.total}</p>
            <p className="text-xs text-blue-500 mt-1">
              {stats.breakdown.internal || 0} otel içi · {stats.breakdown.external || 0} dış · {stats.breakdown.survey || 0} anket · {stats.breakdown.department || 0} dep.
            </p>
          </CardContent>
        </Card>
        <Card className="bg-green-50 border-green-200">
          <CardContent className="p-5 text-center">
            <TrendingUp className="w-6 h-6 mx-auto mb-1 text-green-500" />
            <p className="text-xs text-green-600">Memnuniyet Oranı</p>
            <p className="text-3xl font-bold text-green-700">%{stats.sat}</p>
            <p className="text-xs text-green-500">(4+ yıldız)</p>
          </CardContent>
        </Card>
      </div>

      <Tabs value={view} onValueChange={setView}>
        <TabsList className="grid grid-cols-5 w-full max-w-3xl">
          <TabsTrigger value="all">Tümü ({combined.length})</TabsTrigger>
          <TabsTrigger value="internal">Otel İçi ({stats.breakdown.internal || 0})</TabsTrigger>
          <TabsTrigger value="external">Dış Platform ({stats.breakdown.external || 0})</TabsTrigger>
          <TabsTrigger value="survey">Anket ({stats.breakdown.survey || 0})</TabsTrigger>
          <TabsTrigger value="department">Departman ({stats.breakdown.department || 0})</TabsTrigger>
        </TabsList>

        <TabsContent value={view} className="mt-4">
          {visible.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center text-gray-500">
                <MessageCircle className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                <p className="font-medium">Bu kategoride değerlendirme yok</p>
                <p className="text-sm mt-1">"Değerlendirme İste" düğmesiyle misafirlerinize davet gönderebilirsiniz</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {visible.map((item) => {
                const meta = SOURCE_META[item._source] || SOURCE_META.internal;
                const SrcIcon = meta.icon;
                const canRespond = (item._source === 'internal' || item._source === 'external') && !item.response;
                return (
                  <Card key={item._key} className="hover:shadow-md transition">
                    <CardHeader className="pb-2">
                      <div className="flex justify-between items-start gap-2 flex-wrap">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <CardTitle className="text-base">{item.guest_name || 'Misafir'}</CardTitle>
                            <Badge variant="outline" className={`${meta.color} text-xs`}>
                              <SrcIcon className="w-3 h-3 mr-1" /> {meta.label}
                            </Badge>
                            {item.sourceLabel && (
                              <Badge variant="outline" className="text-xs">{item.sourceLabel}</Badge>
                            )}
                          </div>
                          <div className="flex items-center gap-2 mt-1.5">
                            {renderStars(item.rating)}
                            {getRatingBadge(item.rating)}
                          </div>
                        </div>
                        <span className="text-xs text-gray-500 whitespace-nowrap">{formatDate(item.created_at)}</span>
                      </div>
                    </CardHeader>
                    <CardContent>
                      {item.comment && <p className="text-sm text-gray-700 mb-3 whitespace-pre-wrap">{item.comment}</p>}
                      {item.staff && (
                        <p className="text-xs text-gray-500 mb-2">Personel: {item.staff}</p>
                      )}
                      {item.response ? (
                        <div className="bg-blue-50 border border-blue-200 p-3 rounded-lg">
                          <p className="text-xs font-semibold text-blue-700 mb-1">Yönetim Yanıtı</p>
                          <p className="text-sm text-gray-700">{item.response}</p>
                        </div>
                      ) : canRespond ? (
                        <div className="flex gap-2 flex-wrap">
                          <Button size="sm" variant="outline" onClick={() => { setRespondDialog({ id: item.id, source: item._source, guest_name: item.guest_name }); setResponseText(''); }}>
                            <Send className="w-4 h-4 mr-2" /> Yanıtla
                          </Button>
                          {item.external_url && (
                            <Button size="sm" variant="ghost" asChild>
                              <a href={item.external_url} target="_blank" rel="noreferrer">
                                <ExternalLink className="w-4 h-4 mr-1" /> Platformda görüntüle
                              </a>
                            </Button>
                          )}
                        </div>
                      ) : null}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Respond Dialog */}
      <Dialog open={!!respondDialog} onOpenChange={(o) => { if (!o) { setRespondDialog(null); setResponseText(''); } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Değerlendirmeye yanıt ver</DialogTitle>
            <DialogDescription>
              {respondDialog?.guest_name ? `${respondDialog.guest_name} adlı misafirin değerlendirmesine yanıt yazıyorsunuz.` : 'Yanıtınız panelde görünür olacak.'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <Textarea
              value={responseText}
              onChange={(e) => setResponseText(e.target.value)}
              rows={5}
              placeholder="Misafire teşekkür edin, geri bildirimini değerlendirin..."
              maxLength={2000}
            />
            <p className="text-xs text-gray-500">{responseText.length} / 2000 karakter</p>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => { setRespondDialog(null); setResponseText(''); }}>İptal</Button>
              <Button onClick={respondToReview} disabled={!responseText.trim() || sending}>
                <Send className="w-4 h-4 mr-2" /> {sending ? 'Gönderiliyor...' : 'Gönder'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Invite Dialog */}
      <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Misafire değerlendirme daveti gönder</DialogTitle>
            <DialogDescription>
              E-posta adresi kayıtlı olan misafirlerin listesi. Seçtiğiniz misafire değerlendirme bağlantısı içeren bir e-posta gönderilir.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <Input
                className="pl-9"
                placeholder="Misafir adı, e-posta veya oda numarası ara..."
                value={bookingSearch}
                onChange={(e) => setBookingSearch(e.target.value)}
              />
            </div>
            <ScrollArea className="h-[420px] pr-3">
              {bookingsLoading ? (
                <div className="py-8 text-center text-gray-500">Rezervasyonlar yükleniyor...</div>
              ) : filteredBookings.length === 0 ? (
                <div className="py-8 text-center text-gray-500">
                  <Mail className="w-10 h-10 mx-auto mb-2 text-gray-300" />
                  <p className="text-sm">E-postası kayıtlı misafir bulunamadı</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {filteredBookings.map((b) => (
                    <Card key={b.id} className="border">
                      <CardContent className="p-3 flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <p className="font-medium text-sm truncate">{b.guest_name || 'Misafir'}</p>
                          <p className="text-xs text-gray-500 truncate">{b.guest_email}</p>
                          <p className="text-xs text-gray-400 mt-0.5">
                            Oda {b.room_number || '-'} · {formatDate(b.check_in)} → {formatDate(b.check_out)}
                          </p>
                        </div>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => sendInvite(b)}
                          disabled={sendingInvite === b.id}
                        >
                          {sendingInvite === b.id ? (
                            <><RefreshCw className="w-4 h-4 mr-1 animate-spin" /> Gönderiliyor</>
                          ) : (
                            <><Send className="w-4 h-4 mr-1" /> Gönder</>
                          )}
                        </Button>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </ScrollArea>
            <div className="flex items-center gap-2 text-xs text-gray-500 pt-1 border-t">
              <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />
              <span>Bağlantı 30 gün geçerlidir ve tek kullanımlıktır</span>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default FeedbackSystem;
