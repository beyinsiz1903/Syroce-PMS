import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Award, ChevronLeft, ChevronRight, Crown, Gift, Loader2, Plus, RefreshCw,
  Search, ShieldCheck, Star, TrendingDown, TrendingUp, UserPlus, Users,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

const PAGE_SIZE = 48;
const MEMBER_PAGE_SIZE = 24;

const TIER_META = {
  bronze: { label: 'Bronz', icon: Star, className: 'border-amber-300 bg-amber-50 text-amber-800' },
  silver: { label: 'Gümüş', icon: Gift, className: 'border-slate-300 bg-slate-50 text-slate-700' },
  gold: { label: 'Altın', icon: Award, className: 'border-yellow-300 bg-yellow-50 text-yellow-800' },
  platinum: { label: 'Platin', icon: Crown, className: 'border-indigo-300 bg-indigo-50 text-indigo-800' },
};

const TIER_BENEFITS = {
  bronze: ['Konaklamalarda %5 indirim', 'Doğum günü bonusu', 'Karşılama ikramı'],
  silver: ['Konaklamalarda %10 indirim', 'Saat 14.00’e kadar geç çıkış', 'Oda servisi indirimi'],
  gold: ['Konaklamalarda %15 indirim', 'Ücretsiz kahvaltı', 'Müsaitliğe göre oda yükseltme'],
  platinum: ['Konaklamalarda %20 indirim', 'Garantili oda yükseltme', 'VIP danışmanlık ve transfer avantajı'],
};

const uniqueById = rows => Array.from(new Map(rows.filter(Boolean).map(row => [row.id, row])).values());
const guestContact = value => value || 'Bilgi yok veya görüntüleme yetkiniz sınırlı';

function TierBadge({ tier = 'bronze' }) {
  const meta = TIER_META[tier] || TIER_META.bronze;
  const Icon = meta.icon;
  return <Badge variant="outline" className={meta.className}><Icon className="mr-1 h-3.5 w-3.5" />{meta.label}</Badge>;
}

function Pagination({ page, totalPages, onPageChange }) {
  if (totalPages <= 1) return null;
  return (
    <div className="flex items-center justify-center gap-3 pt-2">
      <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
        <ChevronLeft className="mr-1 h-4 w-4" /> Önceki
      </Button>
      <span className="text-sm text-muted-foreground">{page} / {totalPages}</span>
      <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
        Sonraki <ChevronRight className="ml-1 h-4 w-4" />
      </Button>
    </div>
  );
}

export default function LoyaltyModule() {
  const [programs, setPrograms] = useState([]);
  const [guests, setGuests] = useState([]);
  const [totalGuests, setTotalGuests] = useState(0);
  const [guestOffset, setGuestOffset] = useState(0);
  const [searchResults, setSearchResults] = useState([]);
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [activeTab, setActiveTab] = useState('unenrolled');
  const [memberPage, setMemberPage] = useState(1);
  const [busyGuestId, setBusyGuestId] = useState('');
  const [openDialog, setOpenDialog] = useState(null);
  const [selectedProgram, setSelectedProgram] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [newTransaction, setNewTransaction] = useState({
    guest_id: '', points: '', transaction_type: 'earned', description: '',
  });

  const loadGuestPage = useCallback(async ({ offset = 0, append = false } = {}) => {
    const response = await axios.get('/pms/guests', { params: { limit: PAGE_SIZE, offset } });
    const rows = Array.isArray(response.data) ? response.data : [];
    const total = Number(response.headers?.['x-total-count']);
    setGuests(current => uniqueById(append ? [...current, ...rows] : rows));
    setGuestOffset(offset + rows.length);
    if (Number.isFinite(total)) setTotalGuests(total);
    else if (!append) setTotalGuests(rows.length);
    return rows;
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      const [programResponse] = await Promise.all([
        axios.get('/loyalty/programs'), loadGuestPage({ offset: 0, append: false }),
      ]);
      setPrograms(Array.isArray(programResponse.data) ? programResponse.data : []);
    } catch (error) {
      setLoadError(error.response?.data?.detail || 'Sadakat verileri yüklenemedi.');
      toast.error('Sadakat verileri yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, [loadGuestPage]);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    const normalized = query.trim();
    if (normalized.length < 2) {
      setSearchResults([]);
      setSearching(false);
      return undefined;
    }
    setSearching(true);
    const timer = window.setTimeout(async () => {
      try {
        const response = await axios.get('/pms/guests/search', { params: { q: normalized, limit: 100 } });
        setSearchResults(Array.isArray(response.data) ? response.data : []);
      } catch (error) {
        toast.error(error.response?.data?.detail || 'Misafir araması yapılamadı');
      } finally {
        setSearching(false);
      }
    }, 350);
    return () => window.clearTimeout(timer);
  }, [query]);

  const programGuestIds = useMemo(() => new Set(programs.map(program => program.guest_id)), [programs]);
  const guestById = useMemo(() => new Map(guests.map(guest => [guest.id, guest])), [guests]);
  const searchActive = query.trim().length >= 2;
  const directoryGuests = searchActive ? searchResults : guests;
  const unenrolledGuests = useMemo(
    () => directoryGuests.filter(guest => !programGuestIds.has(guest.id)),
    [directoryGuests, programGuestIds],
  );
  const activeMemberCount = programs.filter(program => program.guest || guestById.has(program.guest_id)).length;
  const totalUnenrolled = Math.max(totalGuests - activeMemberCount, 0);
  const filteredPrograms = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('tr-TR');
    if (!normalized) return programs;
    return programs.filter(program => {
      const guest = program.guest || guestById.get(program.guest_id) || {};
      return [guest.name, guest.email, guest.phone, program.guest_id]
        .filter(Boolean)
        .some(value => String(value).toLocaleLowerCase('tr-TR').includes(normalized));
    });
  }, [guestById, programs, query]);
  const memberTotalPages = Math.max(1, Math.ceil(filteredPrograms.length / MEMBER_PAGE_SIZE));
  const visiblePrograms = filteredPrograms.slice((memberPage - 1) * MEMBER_PAGE_SIZE, memberPage * MEMBER_PAGE_SIZE);

  useEffect(() => { setMemberPage(1); }, [query]);

  const totalPoints = programs.reduce((sum, program) => sum + Number(program.points || 0), 0);
  const lifetimePoints = programs.reduce((sum, program) => sum + Number(program.lifetime_points || 0), 0);

  const loadMoreGuests = async () => {
    setLoadingMore(true);
    try { await loadGuestPage({ offset: guestOffset, append: true }); }
    catch (error) { toast.error(error.response?.data?.detail || 'Sonraki misafir sayfası yüklenemedi'); }
    finally { setLoadingMore(false); }
  };

  const enrollGuest = async guestId => {
    setBusyGuestId(guestId);
    try {
      await axios.post('/loyalty/programs', { guest_id: guestId, tier: 'bronze', points: 0, lifetime_points: 0 });
      toast.success('Misafir sadakat programına kaydedildi');
      await loadData();
      setActiveTab('enrolled');
    } catch (error) { toast.error(error.response?.data?.detail || 'Misafir kaydedilemedi'); }
    finally { setBusyGuestId(''); }
  };

  const loadTransactions = async guestId => {
    try {
      const response = await axios.get(`/loyalty/guest/${guestId}`);
      setTransactions(response.data?.transactions || []);
    } catch (error) {
      setTransactions([]);
      toast.error(error.response?.data?.detail || 'Puan hareketleri yüklenemedi');
    }
  };

  const openProgramDetails = async program => {
    setSelectedProgram(program);
    setOpenDialog('details');
    await loadTransactions(program.guest_id);
  };

  const openPointsDialog = program => {
    setNewTransaction(current => ({ ...current, guest_id: program?.guest_id || current.guest_id }));
    setOpenDialog('transaction');
  };

  const createTransaction = async event => {
    event.preventDefault();
    const points = Number(newTransaction.points);
    if (!newTransaction.guest_id || !Number.isInteger(points) || points <= 0 || !newTransaction.description.trim()) {
      toast.error('Misafir, pozitif tam puan ve açıklama zorunludur');
      return;
    }
    setSubmitting(true);
    try {
      await axios.post('/loyalty/transactions', { ...newTransaction, points, description: newTransaction.description.trim() });
      toast.success(newTransaction.transaction_type === 'earned' ? 'Puan eklendi' : 'Puan kullanıldı');
      setOpenDialog(null);
      setNewTransaction({ guest_id: '', points: '', transaction_type: 'earned', description: '' });
      await loadData();
    } catch (error) { toast.error(error.response?.data?.detail || 'Puan işlemi tamamlanamadı'); }
    finally { setSubmitting(false); }
  };

  if (loading) {
    return <div className="flex min-h-[420px] items-center justify-center gap-2 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /> Sadakat çalışma alanı yükleniyor…</div>;
  }

  return (
    <div className="space-y-6 p-4 md:p-6">
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
        <div><h1 className="text-3xl font-semibold tracking-tight">Misafir Sadakat Programı</h1><p className="mt-1 text-muted-foreground">Üyelikleri, seviyeleri, puan bakiyelerini ve hareketlerini tek yerden yönetin.</p></div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={loadData}><RefreshCw className="mr-2 h-4 w-4" />Yenile</Button>
          <Dialog open={openDialog === 'transaction'} onOpenChange={open => setOpenDialog(open ? 'transaction' : null)}>
            <DialogTrigger asChild><Button data-testid="add-points-btn"><Plus className="mr-2 h-4 w-4" />Puan işlemi</Button></DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Puan ekle veya kullandır</DialogTitle><DialogDescription>İşlem anında bakiyeye yansır ve denetim kaydına eklenir.</DialogDescription></DialogHeader>
              <form className="space-y-4" onSubmit={createTransaction}>
                <div className="space-y-2"><Label htmlFor="transaction-guest">Kayıtlı misafir</Label><Select value={newTransaction.guest_id} onValueChange={guest_id => setNewTransaction(current => ({ ...current, guest_id }))}><SelectTrigger id="transaction-guest" data-testid="transaction-guest-select"><SelectValue placeholder="Misafir seçin" /></SelectTrigger><SelectContent>{programs.map(program => { const guest = program.guest || guestById.get(program.guest_id) || {}; return <SelectItem key={program.guest_id} value={program.guest_id}>{guest.name || 'Gizli misafir'} · {program.points || 0} puan</SelectItem>; })}</SelectContent></Select></div>
                <div className="space-y-2"><Label htmlFor="transaction-type">İşlem türü</Label><Select value={newTransaction.transaction_type} onValueChange={transaction_type => setNewTransaction(current => ({ ...current, transaction_type }))}><SelectTrigger id="transaction-type"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="earned">Puan ekle</SelectItem><SelectItem value="redeemed">Puan kullandır</SelectItem></SelectContent></Select></div>
                <div className="space-y-2"><Label htmlFor="points">Puan</Label><Input id="points" type="number" min="1" step="1" max="10000000" value={newTransaction.points} onChange={event => setNewTransaction(current => ({ ...current, points: event.target.value }))} required /></div>
                <div className="space-y-2"><Label htmlFor="description">İşlem açıklaması</Label><Input id="description" maxLength={500} value={newTransaction.description} onChange={event => setNewTransaction(current => ({ ...current, description: event.target.value }))} placeholder="Örn. konaklama bonusu, restoran harcaması" required /></div>
                <Button className="w-full" type="submit" disabled={submitting} data-testid="submit-transaction-btn">{submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}İşlemi kaydet</Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {loadError && <Card className="border-destructive/40"><CardContent className="flex items-center justify-between gap-4 py-4"><span className="text-sm text-destructive">{loadError}</span><Button size="sm" variant="outline" onClick={loadData}>Tekrar dene</Button></CardContent></Card>}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm font-medium text-muted-foreground">Kayıtlı üye</CardTitle></CardHeader><CardContent><div className="text-2xl font-semibold">{programs.length.toLocaleString('tr-TR')}</div></CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm font-medium text-muted-foreground">Kayıt bekleyen misafir</CardTitle></CardHeader><CardContent><div className="text-2xl font-semibold">{totalUnenrolled.toLocaleString('tr-TR')}</div></CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm font-medium text-muted-foreground">Aktif puan</CardTitle></CardHeader><CardContent><div className="text-2xl font-semibold">{totalPoints.toLocaleString('tr-TR')}</div></CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm font-medium text-muted-foreground">Kazanılmış toplam puan</CardTitle></CardHeader><CardContent><div className="text-2xl font-semibold">{lifetimePoints.toLocaleString('tr-TR')}</div></CardContent></Card>
      </div>

      <Card><CardContent className="space-y-3 py-4"><div className="relative">{searching ? <Loader2 className="absolute left-3 top-3 h-4 w-4 animate-spin text-muted-foreground" /> : <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />}<Input value={query} onChange={event => setQuery(event.target.value)} className="pl-9" placeholder="Ad, e-posta, telefon veya kimlik bilgisiyle ara…" aria-label="Sadakat misafiri ara" /></div><div className="flex items-start gap-2 text-xs text-muted-foreground"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />İletişim bilgileri kullanıcı veri görünürlüğü politikanıza göre maskelenir. Liste {guests.length.toLocaleString('tr-TR')} / {totalGuests.toLocaleString('tr-TR')} aktif misafir kaydını yükledi.</div></CardContent></Card>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-3"><TabsTrigger value="enrolled">Kayıtlı üyeler ({programs.length})</TabsTrigger><TabsTrigger value="unenrolled">Kayıt bekleyenler ({totalUnenrolled})</TabsTrigger><TabsTrigger value="overview">Seviye dağılımı</TabsTrigger></TabsList>

        <TabsContent value="enrolled" className="space-y-4 pt-2">
          {visiblePrograms.length === 0 ? <Card><CardContent className="py-12 text-center text-muted-foreground"><Award className="mx-auto mb-3 h-10 w-10 opacity-40" /><p className="font-medium">Eşleşen kayıtlı üye bulunamadı</p><p className="mt-1 text-sm">Kayıt bekleyenler sekmesinden yeni üyelik başlatabilirsiniz.</p></CardContent></Card> : <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{visiblePrograms.map(program => { const guest = program.guest || guestById.get(program.guest_id) || {}; return <Card key={program.id || program.guest_id} className="transition-shadow hover:shadow-md"><CardHeader className="pb-3"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><CardTitle className="truncate text-lg">{guest.name || 'Gizli misafir'}</CardTitle><p className="mt-1 truncate text-sm text-muted-foreground">{guestContact(guest.email)}</p></div><TierBadge tier={program.tier} /></div></CardHeader><CardContent className="space-y-4"><div className="grid grid-cols-2 gap-3 rounded-lg border bg-muted/20 p-3 text-center"><div><div className="text-xl font-semibold">{Number(program.points || 0).toLocaleString('tr-TR')}</div><div className="text-xs text-muted-foreground">Kullanılabilir</div></div><div><div className="text-xl font-semibold">{Number(program.lifetime_points || 0).toLocaleString('tr-TR')}</div><div className="text-xs text-muted-foreground">Toplam kazanılan</div></div></div><div className="flex gap-2"><Button className="flex-1" variant="outline" onClick={() => openProgramDetails(program)}>Detay ve hareketler</Button><Button size="icon" aria-label="Puan işlemi" onClick={() => openPointsDialog(program)}><Plus className="h-4 w-4" /></Button></div></CardContent></Card>; })}</div>}
          <Pagination page={memberPage} totalPages={memberTotalPages} onPageChange={setMemberPage} />
        </TabsContent>

        <TabsContent value="unenrolled" className="space-y-4 pt-2">
          {unenrolledGuests.length === 0 ? <Card><CardContent className="py-12 text-center text-muted-foreground"><Users className="mx-auto mb-3 h-10 w-10 opacity-40" /><p className="font-medium">{searchActive ? 'Aramanızla eşleşen kayıt bekleyen misafir yok' : totalUnenrolled === 0 ? 'Tüm misafirler kayıtlı' : 'Bu sayfada kayıt bekleyen misafir yok'}</p>{!searchActive && guestOffset < totalGuests && <Button className="mt-4" variant="outline" onClick={loadMoreGuests}>Sonraki kayıtları yükle</Button>}</CardContent></Card> : <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{unenrolledGuests.map(guest => <Card key={guest.id}><CardContent className="flex items-start justify-between gap-3 pt-6"><div className="min-w-0"><div className="truncate font-semibold">{guest.name || 'Gizli misafir'}</div><div className="mt-1 truncate text-sm text-muted-foreground">{guestContact(guest.email)}</div><div className="truncate text-sm text-muted-foreground">{guestContact(guest.phone)}</div><div className="mt-2 text-xs text-muted-foreground">Toplam konaklama: {Number(guest.total_stays || 0)}</div></div><Button size="sm" disabled={busyGuestId === guest.id} onClick={() => enrollGuest(guest.id)}>{busyGuestId === guest.id ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <UserPlus className="mr-1 h-4 w-4" />}Kaydet</Button></CardContent></Card>)}</div>}
          {!searchActive && guestOffset < totalGuests && <div className="flex flex-col items-center gap-2 pt-2"><Button variant="outline" disabled={loadingMore} onClick={loadMoreGuests}>{loadingMore && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Daha fazla misafir yükle</Button><span className="text-xs text-muted-foreground">{guests.length} / {totalGuests} kayıt yüklendi</span></div>}
          {searchActive && searchResults.length >= 100 && <p className="text-center text-xs text-muted-foreground">İlk 100 eşleşme gösteriliyor. Daha dar bir arama yazın.</p>}
        </TabsContent>

        <TabsContent value="overview" className="pt-2"><Card><CardHeader><CardTitle>Üyelik seviyesi dağılımı</CardTitle></CardHeader><CardContent className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{Object.keys(TIER_META).map(tier => { const count = programs.filter(program => program.tier === tier).length; const percentage = programs.length ? Math.round((count / programs.length) * 100) : 0; return <div key={tier} className="rounded-lg border p-4"><div className="flex items-center justify-between"><TierBadge tier={tier} /><span className="text-2xl font-semibold">{count}</span></div><div className="mt-3 text-sm text-muted-foreground">Üyelerin %{percentage}’i</div><ul className="mt-3 space-y-1 text-xs text-muted-foreground">{TIER_BENEFITS[tier].map(benefit => <li key={benefit}>• {benefit}</li>)}</ul></div>; })}</CardContent></Card></TabsContent>
      </Tabs>

      <Dialog open={openDialog === 'details'} onOpenChange={open => !open && setOpenDialog(null)}>
        <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto"><DialogHeader><DialogTitle>Sadakat üyeliği detayı</DialogTitle><DialogDescription>Puan bakiyesi, üyelik seviyesi ve denetlenebilir hareket geçmişi.</DialogDescription></DialogHeader>{selectedProgram && (() => { const guest = selectedProgram.guest || guestById.get(selectedProgram.guest_id) || {}; return <div className="space-y-6"><div className="flex items-start justify-between gap-4"><div><h3 className="text-xl font-semibold">{guest.name || 'Gizli misafir'}</h3><p className="text-sm text-muted-foreground">{guestContact(guest.email)}</p></div><TierBadge tier={selectedProgram.tier} /></div><div className="grid grid-cols-2 gap-3"><Card><CardContent className="pt-5"><div className="text-2xl font-semibold">{Number(selectedProgram.points || 0).toLocaleString('tr-TR')}</div><div className="text-sm text-muted-foreground">Kullanılabilir puan</div></CardContent></Card><Card><CardContent className="pt-5"><div className="text-2xl font-semibold">{Number(selectedProgram.lifetime_points || 0).toLocaleString('tr-TR')}</div><div className="text-sm text-muted-foreground">Toplam kazanılan</div></CardContent></Card></div><div><div className="mb-3 flex items-center justify-between"><h4 className="font-semibold">Puan hareketleri</h4><Button size="sm" onClick={() => openPointsDialog(selectedProgram)}><Plus className="mr-1 h-4 w-4" />Yeni işlem</Button></div>{transactions.length === 0 ? <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">Henüz puan hareketi yok.</div> : <div className="divide-y rounded-lg border">{transactions.map(transaction => { const earned = transaction.transaction_type === 'earned'; return <div key={transaction.id} className="flex items-center justify-between gap-4 p-3"><div><div className="text-sm font-medium">{transaction.description || 'Puan işlemi'}</div><div className="text-xs text-muted-foreground">{transaction.created_at ? new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(transaction.created_at)) : 'Tarih yok'}</div></div><div className={`flex items-center font-semibold ${earned ? 'text-emerald-700' : 'text-red-700'}`}>{earned ? <TrendingUp className="mr-1 h-4 w-4" /> : <TrendingDown className="mr-1 h-4 w-4" />}{earned ? '+' : '-'}{Number(transaction.points || 0).toLocaleString('tr-TR')}</div></div>; })}</div>}</div></div>; })()}</DialogContent>
      </Dialog>
    </div>
  );
}
