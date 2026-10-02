import React, { useCallback, useEffect, useMemo, useState } from 'react';
import api from '@/api/axios';
import { toast } from 'sonner';
import { ArrowDownLeft, ArrowUpRight, BedDouble, ClipboardCheck, Handshake, RefreshCw, Send, ShieldCheck, WalletCards } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { formatCurrency, cachedTenantCurrency } from '@/lib/currency';

const money = (value, currency) => formatCurrency(value, currency || cachedTenantCurrency());
const summaryMoney = (summary, key) => Object.entries(summary?.totals_by_currency || {})
  .filter(([, totals]) => Math.abs(Number(totals?.[key] || 0)) > 0.001)
  .map(([currency, totals]) => money(totals[key], currency))
  .join(' · ') || money(0);
const statusText = {
  pending: 'Bekliyor', active: 'Aktif', accepted: 'Kabul edildi', rejected: 'Reddedildi', open: 'Açık',
  needs_review: 'İnceleme gerekli', settlement_pending: 'Mahsuplaşma onayı bekliyor', settled: 'Mahsuplaşıldı',
};
const blankListing = { room_type: '', date_start: '', date_end: '', nightly_rate: '', allotment: 1, visibility: 'network', approval_mode: 'manual', amenities: [], meal_plan: '', notes: '' };
const blankRequest = { check_in: '', check_out: '', guest_name: '', guest_email: '', guest_phone: '', adults: 2, children: 0, child_ages_text: '', collect_by: 'target_hotel', note: '', source_booking_id: '' };

export default function HotelNetwork() {
  const [data, setData] = useState({ feed: [], mine: [], requests: [], contracts: [], ledger: [], summary: {} });
  const [loading, setLoading] = useState(true);
  const [listing, setListing] = useState(blankListing);
  const [contract, setContract] = useState({ partner_tenant_id: '', valid_from: '', valid_to: '', approval_mode: 'automatic', settlement_model: 'net_rate', commission_pct: 0, payment_terms_days: 15, allowed_room_types: [], special_terms: '' });
  const [partners, setPartners] = useState([]);
  const [audit, setAudit] = useState([]);
  const [bookingCandidates, setBookingCandidates] = useState([]);
  const [requestListing, setRequestListing] = useState(null);
  const [request, setRequest] = useState(blankRequest);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [feed, mine, requests, contracts, ledger, partnerResult, auditResult, candidateResult] = await Promise.all([
        api.get('/hotel-network/feed'), api.get('/hotel-network/listings/mine'),
        api.get('/hotel-network/requests'), api.get('/hotel-network/contracts'), api.get('/hotel-network/ledger'),
        api.get('/hotel-network/partners'), api.get('/hotel-network/audit'), api.get('/hotel-network/booking-candidates'),
      ]);
      setData({ feed: feed.data.listings || [], mine: mine.data.listings || [], requests: requests.data.requests || [], contracts: contracts.data.contracts || [], ledger: ledger.data.entries || [], summary: ledger.data.summary || {} });
      setPartners(partnerResult.data.partners || []); setAudit(auditResult.data.events || []); setBookingCandidates(candidateResult.data.bookings || []);
    } catch (error) { toast.error(error.response?.data?.detail || 'Otel ağı verileri alınamadı'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const publish = async event => {
    event.preventDefault();
    try {
      await api.post('/hotel-network/listings', { ...listing, nightly_rate: Number(listing.nightly_rate), allotment: Number(listing.allotment) });
      toast.success('Kontenjan otel ağına açıldı'); setListing(blankListing); load();
    } catch (error) { toast.error(error.response?.data?.detail || 'Paylaşım oluşturulamadı'); }
  };
  const propose = async event => {
    event.preventDefault();
    try { await api.post('/hotel-network/contracts', { ...contract, commission_pct: Number(contract.commission_pct), payment_terms_days: Number(contract.payment_terms_days) }); toast.success('Anlaşma teklifi gönderildi'); load(); }
    catch (error) { toast.error(error.response?.data?.detail || 'Teklif gönderilemedi'); }
  };
  const decide = async (kind, id, accept) => {
    const reason = accept ? '' : window.prompt('Ret nedenini yazın') || '';
    if (!accept && reason.trim().length < 3) return;
    try { await api.post(`/hotel-network/${kind}/${id}/decision`, kind === 'requests' ? { accept, reason } : { accept, note: reason }); toast.success(accept ? 'Talep kabul edildi' : 'Talep reddedildi'); load(); }
    catch (error) { toast.error(error.response?.data?.detail || 'İşlem tamamlanamadı'); }
  };
  const submitRequest = async event => {
    event.preventDefault();
    if (!requestListing) return;
    setSubmitting(true);
    try {
      const { child_ages_text, ...payload } = request;
      const childAges = child_ages_text.trim() ? child_ages_text.split(',').map(value => Number(value.trim())) : [];
      await api.post('/hotel-network/requests', { ...payload, listing_id: requestListing.id, adults: Number(request.adults), children: Number(request.children), child_ages: childAges });
      toast.success('Yönlendirme talebi gönderildi; hedef tesis bildirildi.');
      setRequestListing(null); setRequest(blankRequest); load();
    } catch (error) { toast.error(error.response?.data?.detail || 'Talep gönderilemedi'); }
    finally { setSubmitting(false); }
  };
  const settle = async (entry, accept = null) => {
    setSubmitting(true);
    try {
      if (accept === null) await api.post(`/hotel-network/ledger/${entry.id}/settlements`);
      else await api.post(`/hotel-network/ledger/${entry.id}/settlements/decision`, { accept, note: accept ? '' : (window.prompt('İade nedenini yazın') || '') });
      toast.success(accept === null ? 'Mahsuplaşma onaya gönderildi.' : accept ? 'Cari kayıt kapatıldı.' : 'Cari kayıt tekrar açık duruma alındı.'); load();
    } catch (error) { toast.error(error.response?.data?.detail || 'Mahsuplaşma işlemi tamamlanamadı'); }
    finally { setSubmitting(false); }
  };
  const pendingIncoming = useMemo(() => data.requests.filter(row => row.direction === 'incoming' && row.status === 'pending').length, [data.requests]);
  const selectSourceBooking = bookingId => {
    const booking = bookingCandidates.find(item => item.id === bookingId);
    if (!booking) { setRequest(blankRequest); return; }
    setRequest({
      ...request, source_booking_id: booking.id, guest_name: booking.guest_name || '', guest_email: booking.guest_email || '', guest_phone: booking.guest_phone || '',
      check_in: String(booking.check_in || '').slice(0, 10), check_out: String(booking.check_out || '').slice(0, 10), adults: booking.adults || 2,
      children: booking.children || 0, child_ages_text: (booking.child_ages || []).join(', '),
    });
  };

  return <div className="mx-auto max-w-7xl space-y-6 p-4 md:p-6">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h1 className="text-2xl font-semibold">Otel Ağı</h1><p className="text-sm text-muted-foreground">Anlaşmalı tesislerle sürekli paylaşım, spot yönlendirme ve tesisler arası cari hesap.</p></div><Button variant="outline" onClick={load} disabled={loading}><RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />Yenile</Button></div>
    <div className="grid gap-3 md:grid-cols-4"><Kpi label="Açık alacak" value={summaryMoney(data.summary, 'open_receivable')} tone="text-emerald-700" /><Kpi label="Açık borç" value={summaryMoney(data.summary, 'open_payable')} tone="text-rose-700" /><Kpi label="Net bakiye" value={summaryMoney(data.summary, 'net')} /><Kpi label="Onay bekleyen talep" value={String(pendingIncoming)} sub="Hedef tesiste işlem bekliyor" tone={pendingIncoming ? 'text-amber-700' : ''} /></div>
    <Tabs defaultValue="feed"><TabsList className="h-auto flex-wrap"><TabsTrigger value="feed">Kapalı devre pazar</TabsTrigger><TabsTrigger value="share">Kontenjan paylaş</TabsTrigger><TabsTrigger value="requests">Talepler{pendingIncoming ? ` (${pendingIncoming})` : ''}</TabsTrigger><TabsTrigger value="contracts">Anlaşmalar</TabsTrigger><TabsTrigger value="ledger">Cari hesap</TabsTrigger><TabsTrigger value="audit">İşlem geçmişi</TabsTrigger></TabsList>
      <TabsContent value="feed" className="space-y-3">{data.feed.length === 0 ? <Empty text="Erişiminize açık aktif paylaşım yok. Anlaşma oluşturun veya karşı tesisin kontenjan paylaşmasını isteyin." /> : data.feed.map(row => <Card key={row.id}><CardContent className="flex flex-wrap items-center justify-between gap-4 pt-5"><div><div className="flex items-center gap-2 font-medium"><BedDouble className="h-4 w-4" />{row.room_type}<Badge variant="secondary">{row.relationship === 'contracted' ? 'Anlaşmalı' : 'Spot'}</Badge></div><p className="mt-1 text-sm text-muted-foreground">{row.seller_name} · {row.date_start} – {row.date_end} · {row.available} oda müsait</p></div><div className="flex items-center gap-3"><div className="text-right"><div className="font-semibold">{money(row.nightly_rate, row.currency)} / gece</div><div className="text-xs text-muted-foreground">{row.automatic_confirmation ? 'Anında onay' : 'Tesis onayı gerekir'}</div></div><Button size="sm" onClick={() => setRequestListing(row)}><Send className="mr-2 h-4 w-4" />Talep oluştur</Button></div></CardContent></Card>)}</TabsContent>
      <TabsContent value="share" className="space-y-4"><Card><CardHeader><CardTitle>Fiyat ve kontenjan paylaş</CardTitle><p className="text-sm text-muted-foreground">Paylaşım anında hedef tesislere görünür; onay modu rezervasyonun nasıl kesinleşeceğini belirler.</p></CardHeader><CardContent><form onSubmit={publish} className="grid gap-4 md:grid-cols-2"><Field label="Oda tipi"><Input required value={listing.room_type} onChange={e => setListing({ ...listing, room_type: e.target.value })} /></Field><Field label="Gecelik net fiyat"><Input required min="0.01" step="0.01" type="number" value={listing.nightly_rate} onChange={e => setListing({ ...listing, nightly_rate: e.target.value })} /></Field><Field label="Başlangıç"><Input required type="date" value={listing.date_start} onChange={e => setListing({ ...listing, date_start: e.target.value })} /></Field><Field label="Bitiş"><Input required type="date" value={listing.date_end} onChange={e => setListing({ ...listing, date_end: e.target.value })} /></Field><Field label="Kontenjan"><Input required min="1" type="number" value={listing.allotment} onChange={e => setListing({ ...listing, allotment: e.target.value })} /></Field><label className="space-y-2 text-sm font-medium">Görünürlük<select className="h-10 w-full rounded-md border bg-background px-3" value={listing.visibility} onChange={e => setListing({ ...listing, visibility: e.target.value })}><option value="network">Tüm otel ağı</option><option value="contracts_only">Yalnız anlaşmalı tesisler</option></select></label><label className="space-y-2 text-sm font-medium">Onay modu<select className="h-10 w-full rounded-md border bg-background px-3" value={listing.approval_mode} onChange={e => setListing({ ...listing, approval_mode: e.target.value })}><option value="manual">Tesis onayı gerekli</option><option value="automatic">Anında onay (yalnız çift taraflı anlaşmada)</option></select></label><Field label="Not / dahil olanlar"><Input value={listing.notes} maxLength={1000} onChange={e => setListing({ ...listing, notes: e.target.value })} placeholder="Örn. kahvaltı dahil, iptal koşulu" /></Field><Button type="submit" className="md:col-span-2">Paylaşımı yayınla</Button></form></CardContent></Card>{data.mine.length === 0 ? <Empty text="Henüz kontenjan paylaşmadınız." /> : data.mine.map(row => <Card key={row.id}><CardContent className="flex flex-wrap justify-between gap-2 pt-5 text-sm"><span>{row.room_type} · {row.date_start} – {row.date_end}</span><span>{row.available}/{row.allotment} müsait · {money(row.nightly_rate, row.currency)}</span></CardContent></Card>)}</TabsContent>
      <TabsContent value="requests" className="space-y-3">{data.requests.length === 0 ? <Empty text="Henüz gelen veya gönderilen talep yok." /> : data.requests.map(row => <Card key={row.id}><CardContent className="flex flex-wrap items-center justify-between gap-3 pt-5"><div><div className="flex items-center gap-2 font-medium">{row.direction === 'incoming' ? <ArrowDownLeft className="h-4 w-4" /> : <ArrowUpRight className="h-4 w-4" />}{row.room_type} · {row.guest_name}</div><p className="text-sm text-muted-foreground">{row.source_hotel_name} → {row.target_hotel_name} · {row.check_in} – {row.check_out}</p><Badge className="mt-2" variant="outline">{statusText[row.status] || row.status}</Badge></div>{row.direction === 'incoming' && row.status === 'pending' && <div className="flex gap-2"><Button variant="outline" onClick={() => decide('requests', row.id, false)}>Reddet</Button><Button onClick={() => decide('requests', row.id, true)}>Kabul et</Button></div>}</CardContent></Card>)}</TabsContent>
      <TabsContent value="contracts" className="space-y-4"><Card><CardHeader><CardTitle>İkili anlaşma teklif et</CardTitle><p className="text-sm text-muted-foreground">Komisyon, onay yöntemi ve vade iki tarafça kabul edildiğinde geçerli olur.</p></CardHeader><CardContent><form onSubmit={propose} className="grid gap-4 md:grid-cols-2"><label className="space-y-2 text-sm font-medium">Karşı tesis<select required className="h-10 w-full rounded-md border bg-background px-3" value={contract.partner_tenant_id} onChange={e => setContract({ ...contract, partner_tenant_id: e.target.value })}><option value="">Tesis seçin</option>{partners.map(partner => <option key={partner.id} value={partner.id}>{partner.name}</option>)}</select></label><Field label="Komisyon (%)"><Input min="0" max="100" step="0.01" type="number" value={contract.commission_pct} onChange={e => setContract({ ...contract, commission_pct: e.target.value })} /></Field><Field label="Başlangıç"><Input required type="date" value={contract.valid_from} onChange={e => setContract({ ...contract, valid_from: e.target.value })} /></Field><Field label="Bitiş"><Input required type="date" value={contract.valid_to} onChange={e => setContract({ ...contract, valid_to: e.target.value })} /></Field><label className="space-y-2 text-sm font-medium">Rezervasyon onayı<select className="h-10 w-full rounded-md border bg-background px-3" value={contract.approval_mode} onChange={e => setContract({ ...contract, approval_mode: e.target.value })}><option value="automatic">Otomatik</option><option value="manual">Manuel</option></select></label><Field label="Vade (gün)"><Input min="0" max="90" type="number" value={contract.payment_terms_days} onChange={e => setContract({ ...contract, payment_terms_days: e.target.value })} /></Field><Button type="submit" className="md:col-span-2"><Handshake className="mr-2 h-4 w-4" />Teklif gönder</Button></form></CardContent></Card>{data.contracts.length === 0 ? <Empty text="Henüz ikili anlaşma yok." /> : data.contracts.map(row => <Card key={row.id}><CardContent className="flex items-center justify-between gap-3 pt-5"><div><div className="font-medium">{row.partner_name}</div><p className="text-xs text-muted-foreground">%{row.commission_pct || 0} komisyon · {row.payment_terms_days} gün vade</p><Badge variant="outline">{statusText[row.status] || row.status}</Badge></div>{row.direction === 'incoming' && row.status === 'pending' && <div className="flex gap-2"><Button variant="outline" onClick={() => decide('contracts', row.id, false)}>Reddet</Button><Button onClick={() => decide('contracts', row.id, true)}>Onayla</Button></div>}</CardContent></Card>)}</TabsContent>
      <TabsContent value="ledger" className="space-y-3">{data.ledger.length === 0 ? <Empty text="Henüz tesisler arası cari hareket yok." /> : data.ledger.map(row => <Card key={row.id}><CardContent className="flex flex-wrap items-center justify-between gap-3 pt-5"><div className="flex items-center gap-2"><WalletCards className="h-4 w-4" /><div><div className="font-medium">{row.counterparty_name}</div><div className="text-xs text-muted-foreground">{row.transfer_reference} · {row.reason} · {row.status === 'settlement_pending' ? 'Onay bekleyen mahsuplaşma' : row.status === 'settled' ? 'Kapatıldı' : 'Açık'}</div></div></div><div className="flex items-center gap-3"><div className={row.entry_type === 'receivable' ? 'font-semibold text-emerald-700' : 'font-semibold text-rose-700'}>{row.entry_type === 'receivable' ? '+' : '-'}{money(row.amount, row.currency)}</div>{row.entry_type === 'payable' && row.status === 'open' && <Button disabled={submitting} size="sm" onClick={() => settle(row)}><Send className="mr-2 h-4 w-4" />Ödeme bildir</Button>}{row.entry_type === 'receivable' && row.status === 'settlement_pending' && <div className="flex gap-2"><Button disabled={submitting} variant="outline" size="sm" onClick={() => settle(row, false)}>İade et</Button><Button disabled={submitting} size="sm" onClick={() => settle(row, true)}><ShieldCheck className="mr-2 h-4 w-4" />Onayla</Button></div>}</div></CardContent></Card>)}</TabsContent>
      <TabsContent value="audit" className="space-y-3">{audit.length === 0 ? <Empty text="Henüz kayıtlı Otel Ağı işlemi yok." /> : audit.map(event => <Card key={event.id}><CardContent className="flex items-center gap-3 pt-4 text-sm"><ClipboardCheck className="h-4 w-4 text-muted-foreground" /><div><div className="font-medium">{event.action}</div><div className="text-xs text-muted-foreground">{new Date(event.created_at).toLocaleString('tr-TR')} · Referans: {event.entity_id}</div></div></CardContent></Card>)}</TabsContent>
    </Tabs>
    <Dialog open={Boolean(requestListing)} onOpenChange={open => !open && setRequestListing(null)}><DialogContent><DialogHeader><DialogTitle>Otel Ağı yönlendirme talebi</DialogTitle><DialogDescription>{requestListing?.seller_name} · {requestListing?.room_type} · {requestListing ? money(requestListing.nightly_rate, requestListing.currency) : ''} / gece. Hedef tesis, kabul edene kadar misafir iletişim bilgisini görmez.</DialogDescription></DialogHeader><form onSubmit={submitRequest} className="grid gap-3"><label className="space-y-2 text-sm font-medium">Mevcut rezervasyondan aktar (isteğe bağlı)<select className="h-10 w-full rounded-md border bg-background px-3" value={request.source_booking_id || ''} onChange={e => selectSourceBooking(e.target.value)}><option value="">Yeni talep / misafiri elle gir</option>{bookingCandidates.map(booking => <option key={booking.id} value={booking.id}>{booking.guest_name} · {String(booking.check_in).slice(0, 10)} – {String(booking.check_out).slice(0, 10)} · {booking.room_type || 'Oda'}</option>)}</select></label>{request.source_booking_id && <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">Kaynak rezervasyon seçildi: misafir ve tarih bilgileri güvenli olarak kaynak kayıttan alınır.</p>}<div className="grid grid-cols-2 gap-3"><Field label="Giriş"><Input required disabled={Boolean(request.source_booking_id)} type="date" min={requestListing?.date_start} max={requestListing?.date_end} value={request.check_in} onChange={e => setRequest({ ...request, check_in: e.target.value })} /></Field><Field label="Çıkış"><Input required disabled={Boolean(request.source_booking_id)} type="date" min={request.check_in || requestListing?.date_start} value={request.check_out} onChange={e => setRequest({ ...request, check_out: e.target.value })} /></Field></div><Field label="Misafir adı"><Input required disabled={Boolean(request.source_booking_id)} value={request.guest_name} onChange={e => setRequest({ ...request, guest_name: e.target.value })} /></Field><div className="grid grid-cols-2 gap-3"><Field label="Yetişkin"><Input required disabled={Boolean(request.source_booking_id)} min="1" max="20" type="number" value={request.adults} onChange={e => setRequest({ ...request, adults: e.target.value })} /></Field><Field label="Çocuk"><Input required disabled={Boolean(request.source_booking_id)} min="0" max="20" type="number" value={request.children} onChange={e => setRequest({ ...request, children: e.target.value })} /></Field></div>{Number(request.children) > 0 && <Field label="Çocuk yaşları"><Input required disabled={Boolean(request.source_booking_id)} placeholder="Örn. 4, 9" value={request.child_ages_text} onChange={e => setRequest({ ...request, child_ages_text: e.target.value })} /></Field>}<label className="space-y-2 text-sm font-medium">Tahsilatı kim alacak?<select className="h-10 w-full rounded-md border bg-background px-3" value={request.collect_by} onChange={e => setRequest({ ...request, collect_by: e.target.value })}><option value="target_hotel">Konaklayan tesis</option><option value="source_hotel">Yönlendiren tesis</option></select></label><Field label="Operasyon notu"><Input value={request.note} onChange={e => setRequest({ ...request, note: e.target.value })} /></Field><DialogFooter><Button type="button" variant="outline" onClick={() => setRequestListing(null)}>Vazgeç</Button><Button disabled={submitting} type="submit">Talebi gönder</Button></DialogFooter></form></DialogContent></Dialog>
  </div>;
}

function Field({ label, children }) { return <div className="space-y-2"><Label>{label}</Label>{children}</div>; }
function Empty({ text }) { return <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">{text}</div>; }
function Kpi({ label, value, sub, tone = '' }) { return <Card><CardContent className="pt-5"><div className="text-sm text-muted-foreground">{label}</div><div className={`text-xl font-semibold ${tone}`}>{value}</div>{sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}</CardContent></Card>; }
