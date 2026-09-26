import React, { useCallback, useEffect, useState } from 'react';
import api from '@/api/axios';
import { toast } from 'sonner';
import { ArrowDownLeft, ArrowUpRight, BedDouble, Handshake, RefreshCw, WalletCards } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

const money = value => new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY' }).format(Number(value || 0));
const statusText = { pending: 'Bekliyor', active: 'Aktif', accepted: 'Kabul edildi', rejected: 'Reddedildi', open: 'Açık' };
const blankListing = { room_type: '', date_start: '', date_end: '', nightly_rate: '', allotment: 1, visibility: 'network', approval_mode: 'manual', amenities: [], meal_plan: '', notes: '' };

export default function HotelNetwork() {
  const [data, setData] = useState({ feed: [], mine: [], requests: [], contracts: [], ledger: [], summary: {} });
  const [loading, setLoading] = useState(true);
  const [listing, setListing] = useState(blankListing);
  const [contract, setContract] = useState({ partner_tenant_id: '', valid_from: '', valid_to: '', approval_mode: 'automatic', settlement_model: 'net_rate', commission_pct: 0, payment_terms_days: 15, allowed_room_types: [], special_terms: '' });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [feed, mine, requests, contracts, ledger] = await Promise.all([
        api.get('/hotel-network/feed'), api.get('/hotel-network/listings/mine'),
        api.get('/hotel-network/requests'), api.get('/hotel-network/contracts'), api.get('/hotel-network/ledger'),
      ]);
      setData({ feed: feed.data.listings || [], mine: mine.data.listings || [], requests: requests.data.requests || [], contracts: contracts.data.contracts || [], ledger: ledger.data.entries || [], summary: ledger.data.summary || {} });
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

  return <div className="mx-auto max-w-7xl space-y-6 p-4 md:p-6">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h1 className="text-2xl font-semibold">Otel Ağı</h1><p className="text-sm text-muted-foreground">Anlaşmalı tesislerle sürekli paylaşım, spot yönlendirme ve tesisler arası cari hesap.</p></div><Button variant="outline" onClick={load} disabled={loading}><RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />Yenile</Button></div>
    <div className="grid gap-3 md:grid-cols-3"><Card><CardContent className="pt-5"><div className="text-sm text-muted-foreground">Açık alacak</div><div className="text-xl font-semibold text-emerald-700">{money(data.summary.open_receivable)}</div></CardContent></Card><Card><CardContent className="pt-5"><div className="text-sm text-muted-foreground">Açık borç</div><div className="text-xl font-semibold text-rose-700">{money(data.summary.open_payable)}</div></CardContent></Card><Card><CardContent className="pt-5"><div className="text-sm text-muted-foreground">Net bakiye</div><div className="text-xl font-semibold">{money(data.summary.net)}</div></CardContent></Card></div>
    <Tabs defaultValue="feed"><TabsList className="h-auto flex-wrap"><TabsTrigger value="feed">Kapalı devre pazar</TabsTrigger><TabsTrigger value="share">Kontenjan paylaş</TabsTrigger><TabsTrigger value="requests">Talepler</TabsTrigger><TabsTrigger value="contracts">Anlaşmalar</TabsTrigger><TabsTrigger value="ledger">Cari hesap</TabsTrigger></TabsList>
      <TabsContent value="feed" className="space-y-3">{data.feed.length === 0 ? <Empty text="Şu anda erişebildiğiniz aktif paylaşım yok." /> : data.feed.map(row => <Card key={row.id}><CardContent className="flex flex-wrap items-center justify-between gap-4 pt-5"><div><div className="flex items-center gap-2 font-medium"><BedDouble className="h-4 w-4" />{row.room_type}<Badge variant="secondary">{row.relationship === 'contracted' ? 'Anlaşmalı' : 'Spot'}</Badge></div><p className="mt-1 text-sm text-muted-foreground">{row.seller_name} · {row.date_start} – {row.date_end} · {row.available} oda müsait</p></div><div className="text-right"><div className="font-semibold">{money(row.nightly_rate)} / gece</div><div className="text-xs text-muted-foreground">{row.automatic_confirmation ? 'Anında onay' : 'Tesis onayı gerekir'}</div></div></CardContent></Card>)}</TabsContent>
      <TabsContent value="share"><Card><CardHeader><CardTitle>Fiyat ve kontenjan paylaş</CardTitle></CardHeader><CardContent><form onSubmit={publish} className="grid gap-4 md:grid-cols-2"><Field label="Oda tipi"><Input required value={listing.room_type} onChange={e => setListing({ ...listing, room_type: e.target.value })} /></Field><Field label="Gecelik fiyat"><Input required min="0.01" step="0.01" type="number" value={listing.nightly_rate} onChange={e => setListing({ ...listing, nightly_rate: e.target.value })} /></Field><Field label="Başlangıç"><Input required type="date" value={listing.date_start} onChange={e => setListing({ ...listing, date_start: e.target.value })} /></Field><Field label="Bitiş"><Input required type="date" value={listing.date_end} onChange={e => setListing({ ...listing, date_end: e.target.value })} /></Field><Field label="Kontenjan"><Input required min="1" type="number" value={listing.allotment} onChange={e => setListing({ ...listing, allotment: e.target.value })} /></Field><label className="space-y-2 text-sm font-medium">Görünürlük<select className="h-10 w-full rounded-md border bg-background px-3" value={listing.visibility} onChange={e => setListing({ ...listing, visibility: e.target.value })}><option value="network">Tüm otel ağı</option><option value="contracts_only">Yalnız anlaşmalı tesisler</option></select></label><Button type="submit" className="md:col-span-2">Paylaşımı yayınla</Button></form></CardContent></Card>{data.mine.map(row => <div key={row.id} className="rounded-lg border p-3 text-sm">{row.room_type} · {row.available}/{row.allotment} müsait · {money(row.nightly_rate)}</div>)}</TabsContent>
      <TabsContent value="requests" className="space-y-3">{data.requests.length === 0 ? <Empty text="Henüz gelen veya gönderilen talep yok." /> : data.requests.map(row => <Card key={row.id}><CardContent className="flex flex-wrap items-center justify-between gap-3 pt-5"><div><div className="flex items-center gap-2 font-medium">{row.direction === 'incoming' ? <ArrowDownLeft className="h-4 w-4" /> : <ArrowUpRight className="h-4 w-4" />}{row.room_type} · {row.guest_name}</div><p className="text-sm text-muted-foreground">{row.source_hotel_name} → {row.target_hotel_name} · {row.check_in} – {row.check_out}</p><Badge className="mt-2" variant="outline">{statusText[row.status] || row.status}</Badge></div>{row.direction === 'incoming' && row.status === 'pending' && <div className="flex gap-2"><Button variant="outline" onClick={() => decide('requests', row.id, false)}>Reddet</Button><Button onClick={() => decide('requests', row.id, true)}>Kabul et</Button></div>}</CardContent></Card>)}</TabsContent>
      <TabsContent value="contracts" className="space-y-4"><Card><CardHeader><CardTitle>İkili anlaşma teklif et</CardTitle></CardHeader><CardContent><form onSubmit={propose} className="grid gap-4 md:grid-cols-2"><Field label="Karşı tesis kimliği"><Input required value={contract.partner_tenant_id} onChange={e => setContract({ ...contract, partner_tenant_id: e.target.value })} /></Field><Field label="Komisyon (%)"><Input min="0" max="100" step="0.01" type="number" value={contract.commission_pct} onChange={e => setContract({ ...contract, commission_pct: e.target.value })} /></Field><Field label="Başlangıç"><Input required type="date" value={contract.valid_from} onChange={e => setContract({ ...contract, valid_from: e.target.value })} /></Field><Field label="Bitiş"><Input required type="date" value={contract.valid_to} onChange={e => setContract({ ...contract, valid_to: e.target.value })} /></Field><Button type="submit" className="md:col-span-2"><Handshake className="mr-2 h-4 w-4" />Teklif gönder</Button></form></CardContent></Card>{data.contracts.map(row => <Card key={row.id}><CardContent className="flex items-center justify-between gap-3 pt-5"><div><div className="font-medium">{row.partner_name}</div><Badge variant="outline">{statusText[row.status] || row.status}</Badge></div>{row.direction === 'incoming' && row.status === 'pending' && <div className="flex gap-2"><Button variant="outline" onClick={() => decide('contracts', row.id, false)}>Reddet</Button><Button onClick={() => decide('contracts', row.id, true)}>Onayla</Button></div>}</CardContent></Card>)}</TabsContent>
      <TabsContent value="ledger" className="space-y-3">{data.ledger.length === 0 ? <Empty text="Henüz tesisler arası cari hareket yok." /> : data.ledger.map(row => <Card key={row.id}><CardContent className="flex items-center justify-between gap-3 pt-5"><div className="flex items-center gap-2"><WalletCards className="h-4 w-4" /><div><div className="font-medium">{row.counterparty_name}</div><div className="text-xs text-muted-foreground">{row.transfer_reference} · {row.reason}</div></div></div><div className={row.entry_type === 'receivable' ? 'font-semibold text-emerald-700' : 'font-semibold text-rose-700'}>{row.entry_type === 'receivable' ? '+' : '-'}{money(row.amount)}</div></CardContent></Card>)}</TabsContent>
    </Tabs>
  </div>;
}

function Field({ label, children }) { return <div className="space-y-2"><Label>{label}</Label>{children}</div>; }
function Empty({ text }) { return <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">{text}</div>; }
