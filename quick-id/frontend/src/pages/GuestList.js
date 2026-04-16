import { useState, useEffect, useCallback } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';

import { Skeleton } from '../components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '../components/ui/tabs';
import { StatusBadge, DocTypeBadge, GenderBadge } from '../components/StatusBadges';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../components/ui/dropdown-menu';
import { api } from '../lib/api';
import {
  Search,
  MoreHorizontal,
  Eye,
  LogIn,
  LogOut,
  Trash2,
  ChevronLeft,
  ChevronRight,
  Users,
  FileDown,
} from 'lucide-react';

export default function GuestList() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [guests, setGuests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState(searchParams.get('search') || '');
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') || 'all');
  const limit = 15;

  const loadGuests = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, limit };
      if (search) params.search = search;
      if (statusFilter && statusFilter !== 'all') params.status = statusFilter;
      
      const data = await api.getGuests(params);
      setGuests(data.guests || []);
      setTotal(data.total || 0);
    } catch (err) {
      console.error('Failed to load guests:', err);
      toast.error('Misafirler yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter]);

  useEffect(() => {
    loadGuests();
  }, [loadGuests]);

  useEffect(() => {
    setPage(1);
  }, [search, statusFilter]);

  const handleCheckin = async (id) => {
    try {
      await api.checkinGuest(id);
      toast.success('Check-in yapıldı!');
      loadGuests();
    } catch (err) {
      toast.error('Check-in hatası');
    }
  };

  const handleCheckout = async (id) => {
    try {
      await api.checkoutGuest(id);
      toast.success('Check-out yapıldı!');
      loadGuests();
    } catch (err) {
      toast.error('Check-out hatası');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Bu misafiri silmek istediğinize emin misiniz?')) return;
    try {
      await api.deleteGuest(id);
      toast.success('Misafir silindi');
      loadGuests();
    } catch (err) {
      toast.error('Silme hatası');
    }
  };

  const totalPages = Math.ceil(total / limit);

  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    try {
      return new Date(dateStr).toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric' });
    } catch { return dateStr; }
  };

  return (
    <div className="space-y-4" data-testid="guest-list-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-[var(--brand-ink)]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            Misafirler
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {total} misafir kaydı
          </p>
        </div>
        <div className="flex gap-2">
          <a href={api.getExportCsvUrl(statusFilter !== 'all' ? { status: statusFilter } : {})} download>
            <Button variant="outline" size="sm">
              <FileDown className="w-4 h-4 mr-2" />
              CSV İndir
            </Button>
          </a>
        </div>
      </div>

      {/* Filters */}
      <Card className="bg-white">
        <CardContent className="p-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Ad, soyad veya kimlik no ara..."
                className="pl-9"
                data-testid="guest-search-input"
              />
            </div>
            <Tabs value={statusFilter} onValueChange={setStatusFilter} data-testid="status-filter-tabs">
              <TabsList className="h-9">
                <TabsTrigger value="all" className="text-xs px-3">Tümü</TabsTrigger>
                <TabsTrigger value="pending" className="text-xs px-3">Bekleyen</TabsTrigger>
                <TabsTrigger value="checked_in" className="text-xs px-3">Giriş</TabsTrigger>
                <TabsTrigger value="checked_out" className="text-xs px-3">Çıkış</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card className="bg-white overflow-hidden">
        <div className="overflow-x-auto">
          <Table data-testid="guest-table">
            <TableHeader>
              <TableRow className="bg-[hsl(var(--secondary))]">
                <TableHead className="font-medium">Ad Soyad</TableHead>
                <TableHead className="font-medium">Kimlik No</TableHead>
                <TableHead className="font-medium hidden md:table-cell">Belge</TableHead>
                <TableHead className="font-medium hidden md:table-cell">Uyruk</TableHead>
                <TableHead className="font-medium hidden lg:table-cell">Cinsiyet</TableHead>
                <TableHead className="font-medium">Durum</TableHead>
                <TableHead className="font-medium hidden lg:table-cell">Tarih</TableHead>
                <TableHead className="font-medium w-12">İşlem</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 8 }).map((_, j) => (
                      <TableCell key={j}><Skeleton className="h-5 w-full" /></TableCell>
                    ))}
                  </TableRow>
                ))
              ) : guests.length > 0 ? (
                guests.map((guest) => (
                  <TableRow key={guest.id} className="guest-row h-12">
                    <TableCell>
                      <Link to={`/guests/${guest.id}`} className="font-medium text-sm hover:text-[var(--brand-sky)] transition-colors">
                        {guest.first_name} {guest.last_name}
                      </Link>
                    </TableCell>
                    <TableCell className="text-sm font-mono">
                      {guest.id_number || '—'}
                    </TableCell>
                    <TableCell className="hidden md:table-cell">
                      <DocTypeBadge type={guest.document_type} />
                    </TableCell>
                    <TableCell className="text-sm hidden md:table-cell">
                      {guest.nationality || '—'}
                    </TableCell>
                    <TableCell className="hidden lg:table-cell">
                      <GenderBadge gender={guest.gender} />
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={guest.status} />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground hidden lg:table-cell">
                      {formatDate(guest.created_at)}
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8" data-testid="guest-row-actions-menu">
                            <MoreHorizontal className="w-4 h-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem asChild>
                            <Link to={`/guests/${guest.id}`}>
                              <Eye className="w-4 h-4 mr-2" /> Detay
                            </Link>
                          </DropdownMenuItem>
                          {guest.status !== 'checked_in' && (
                            <DropdownMenuItem onClick={() => handleCheckin(guest.id)}>
                              <LogIn className="w-4 h-4 mr-2" /> Check-in
                            </DropdownMenuItem>
                          )}
                          {guest.status === 'checked_in' && (
                            <DropdownMenuItem onClick={() => handleCheckout(guest.id)}>
                              <LogOut className="w-4 h-4 mr-2" /> Check-out
                            </DropdownMenuItem>
                          )}
                          <DropdownMenuItem onClick={() => handleDelete(guest.id)} className="text-[var(--brand-danger)]">
                            <Trash2 className="w-4 h-4 mr-2" /> Sil
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-12">
                    <Users className="w-12 h-12 text-muted-foreground/30 mx-auto mb-3" />
                    <p className="text-sm text-muted-foreground">Misafir bulunamadı</p>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between p-3 border-t border-[hsl(var(--border))]">
            <p className="text-xs text-muted-foreground">
              {(page - 1) * limit + 1}-{Math.min(page * limit, total)} / {total}
            </p>
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                disabled={page === 1}
                onClick={() => setPage(p => p - 1)}
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="text-sm px-2">{page} / {totalPages}</span>
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                disabled={page === totalPages}
                onClick={() => setPage(p => p + 1)}
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
