import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import {
  Package, Plus, Search, RefreshCw, Trash2, UserCheck,
  MapPin, Calendar, Tag, Archive, CheckCircle, Clock, Send,
  PackageSearch, Boxes, UserCog, PackageCheck, Ban
} from 'lucide-react';

const STATUS_INTENT = {
  found: 'info',
  stored: 'warning',
  claimed: 'neutral',
  returned: 'success',
  disposed: 'default',
};
const STATUS_ICONS = {
  found: PackageSearch,
  stored: Boxes,
  claimed: UserCog,
  returned: PackageCheck,
  disposed: Ban,
};

const STATUS_CONFIG = {
  found: { label: 'Bulundu', color: 'bg-blue-100 text-blue-700 border-blue-200' },
  stored: { label: 'Depolandı', color: 'bg-amber-100 text-amber-700 border-amber-200' },
  claimed: { label: 'Sahiplenildi', color: 'bg-indigo-100 text-indigo-700 border-indigo-200' },
  returned: { label: 'Teslim Edildi', color: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  disposed: { label: 'İmha Edildi', color: 'bg-gray-100 text-gray-600 border-gray-200' },
};

const CATEGORY_CONFIG = {
  electronics: { label: 'Elektronik', icon: '📱' },
  clothing: { label: 'Giyim', icon: '👔' },
  jewelry: { label: 'Mücevher', icon: '💍' },
  documents: { label: 'Belge', icon: '📄' },
  bags: { label: 'Çanta/Bavul', icon: '👜' },
  other: { label: 'Diğer', icon: '📦' },
};

const LostFoundPage = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [search, setSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [showDetail, setShowDetail] = useState(null);
  const [showMatch, setShowMatch] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [form, setForm] = useState({
    item_name: '', description: '', category: 'other', found_location: '',
    found_date: new Date().toISOString().split('T')[0], found_by: '',
    room_number: '', guest_name: '', guest_contact: '', storage_location: '',
  });
  const [matchForm, setMatchForm] = useState({ guest_name: '', guest_contact: '', booking_id: '' });

  const loadItems = useCallback(async () => {
    try {
      const params = {};
      if (filterStatus) params.status = filterStatus;
      if (filterCategory) params.category = filterCategory;
      if (search) params.search = search;
      const res = await axios.get(`/pms/lost-found`, { params });
      setItems(res.data?.items || []);
      setStats(res.data?.stats || {});
    } catch (e) {
      console.error('Load items error', e);
    } finally {
      setLoading(false);
    }
  }, [filterStatus, filterCategory, search]);

  useEffect(() => { loadItems(); }, [loadItems]);

  const handleCreate = async () => {
    if (!form.item_name || !form.found_location) {
      toast.error('Eşya adı ve bulunduğu yer zorunlu'); return;
    }
    try {
      await axios.post(`/pms/lost-found`, form);
      toast.success('Kayıp eşya kaydedildi');
      setShowCreate(false);
      setForm({
        item_name: '', description: '', category: 'other', found_location: '',
        found_date: new Date().toISOString().split('T')[0], found_by: '',
        room_number: '', guest_name: '', guest_contact: '', storage_location: '',
      });
      loadItems();
    } catch (e) {
      toast.error('Hata: ' + (e.response?.data?.detail || e.message));
    }
  };

  const handleStatusUpdate = async (itemId, newStatus) => {
    try {
      await axios.put(`/pms/lost-found/${itemId}`, { status: newStatus });
      toast.success(`Durum "${STATUS_CONFIG[newStatus]?.label}" olarak güncellendi`);
      loadItems();
      if (showDetail?.id === itemId) {
        setShowDetail(prev => ({ ...prev, status: newStatus }));
      }
    } catch (e) {
      toast.error('Güncelleme hatası');
    }
  };

  const handleMatchGuest = async () => {
    if (!showMatch) return;
    try {
      const params = new URLSearchParams();
      if (matchForm.guest_name) params.append('guest_name', matchForm.guest_name);
      if (matchForm.guest_contact) params.append('guest_contact', matchForm.guest_contact);
      if (matchForm.booking_id) params.append('booking_id', matchForm.booking_id);

      await axios.post(`/pms/lost-found/${showMatch.id}/match-guest?${params.toString()}`);
      toast.success('Misafir eşleştirmesi yapıldı');
      setShowMatch(null);
      loadItems();
    } catch (e) {
      toast.error('Eşleştirme hatası');
    }
  };

  const handleDelete = async (itemId) => {
    try {
      await axios.delete(`/pms/lost-found/${itemId}`);
      toast.success('Kayıt silindi');
      setShowDetail(null);
      setDeleteConfirm(null);
      loadItems();
    } catch (e) {
      toast.error('Silme hatası');
    }
  };

  return (
    <>
      <div className="p-4 md:p-6 space-y-5 max-w-6xl mx-auto" data-testid="lost-found-page">
        <PageHeader
          icon={Package}
          iconClassName="text-amber-600"
          title="Kayıp & Bulunan Eşyalar"
          subtitle="Bulunan eşyaları kaydedin ve misafirlerle eşleştirin"
          actions={
            <>
              <Button variant="outline" size="sm" onClick={() => { setLoading(true); loadItems(); }}>
                <RefreshCw className="w-4 h-4 mr-1.5" /> Yenile
              </Button>
              <Button size="sm" onClick={() => setShowCreate(true)} data-testid="create-lostfound-btn">
                <Plus className="w-4 h-4 mr-1.5" /> Yeni Kayıt
              </Button>
            </>
          }
        />

        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {Object.entries(STATUS_CONFIG).map(([key, cfg]) => (
            <KpiCard
              key={key}
              icon={STATUS_ICONS[key] || Package}
              label={cfg.label}
              value={stats[key] || 0}
              intent={STATUS_INTENT[key] || 'default'}
              active={filterStatus === key}
              onClick={() => setFilterStatus(filterStatus === key ? '' : key)}
            />
          ))}
        </div>

        <div className="flex flex-wrap gap-3 items-end">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Eşya, misafir veya açıklama ara..."
              className="pl-9 h-9"
              data-testid="search-lostfound"
            />
          </div>
          <div>
            <select
              value={filterCategory}
              onChange={e => setFilterCategory(e.target.value)}
              className="h-9 border rounded-md px-3 text-sm"
            >
              <option value="">Tüm Kategoriler</option>
              {Object.entries(CATEGORY_CONFIG).map(([k, v]) => (
                <option key={k} value={k}>{v.icon} {v.label}</option>
              ))}
            </select>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-12 text-gray-400">Yükleniyor...</div>
        ) : items.length === 0 ? (
          <Card className="p-12 text-center">
            <Package className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500 mb-4">Kayıt bulunamadı</p>
            <Button size="sm" onClick={() => setShowCreate(true)}>
              <Plus className="w-4 h-4 mr-1.5" /> Yeni Kayıt Ekle
            </Button>
          </Card>
        ) : (
          <div className="grid gap-3">
            {items.map(item => {
              const cat = CATEGORY_CONFIG[item.category] || CATEGORY_CONFIG.other;
              const st = STATUS_CONFIG[item.status] || STATUS_CONFIG.found;
              return (
                <Card
                  key={item.id}
                  className="hover:shadow-sm transition cursor-pointer"
                  onClick={() => setShowDetail(item)}
                  data-testid={`item-card-${item.id}`}
                >
                  <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="flex items-center gap-4">
                      <div className="text-3xl">{cat.icon}</div>
                      <div>
                        <div className="font-semibold">{item.item_name}</div>
                        <div className="text-xs text-gray-500 flex flex-wrap gap-2 mt-1">
                          <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{item.found_location}</span>
                          <span className="flex items-center gap-1"><Calendar className="w-3 h-3" />{item.found_date}</span>
                          {item.room_number && <span className="flex items-center gap-1">Oda: {item.room_number}</span>}
                          <span className="flex items-center gap-1"><Tag className="w-3 h-3" />{cat.label}</span>
                        </div>
                        {item.guest_name && (
                          <div className="text-xs text-blue-600 mt-1 flex items-center gap-1">
                            <UserCheck className="w-3 h-3" /> {item.guest_name}
                            {item.guest_contact && <span className="text-gray-400">({item.guest_contact})</span>}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <Badge className={`text-xs ${st.color}`}>{st.label}</Badge>
                      {item.status === 'found' && (
                        <Button size="sm" variant="outline" className="h-7 text-xs"
                          onClick={(e) => { e.stopPropagation(); setShowMatch(item); setMatchForm({ guest_name: item.guest_name || '', guest_contact: item.guest_contact || '', booking_id: '' }); }}
                        >
                          <UserCheck className="w-3 h-3 mr-1" /> Eşleştir
                        </Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}

        <Dialog open={showCreate} onOpenChange={setShowCreate}>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2"><Package className="w-5 h-5" /> Yeni Kayıp Eşya Kaydı</DialogTitle>
            </DialogHeader>
            <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Eşya Adı *</Label>
                  <Input value={form.item_name} onChange={e => setForm(f => ({ ...f, item_name: e.target.value }))} placeholder="Siyah cüzdan" data-testid="lf-item-name" />
                </div>
                <div>
                  <Label>Kategori</Label>
                  <select value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))} className="w-full border rounded-md px-3 py-2 text-sm">
                    {Object.entries(CATEGORY_CONFIG).map(([k, v]) => (
                      <option key={k} value={k}>{v.icon} {v.label}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div>
                <Label>Açıklama</Label>
                <Input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder="Detaylı açıklama..." />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Bulunduğu Yer *</Label>
                  <Input value={form.found_location} onChange={e => setForm(f => ({ ...f, found_location: e.target.value }))} placeholder="Lobi, Oda 205..." data-testid="lf-location" />
                </div>
                <div>
                  <Label>Bulunma Tarihi</Label>
                  <Input type="date" value={form.found_date} onChange={e => setForm(f => ({ ...f, found_date: e.target.value }))} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Bulan Kişi</Label>
                  <Input value={form.found_by} onChange={e => setForm(f => ({ ...f, found_by: e.target.value }))} placeholder="Personel adı" />
                </div>
                <div>
                  <Label>Oda No</Label>
                  <Input value={form.room_number} onChange={e => setForm(f => ({ ...f, room_number: e.target.value }))} placeholder={t('common.relatedRoom')} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Misafir Adı</Label>
                  <Input value={form.guest_name} onChange={e => setForm(f => ({ ...f, guest_name: e.target.value }))} placeholder="Muhtemel sahip" />
                </div>
                <div>
                  <Label>Misafir İletişim</Label>
                  <Input value={form.guest_contact} onChange={e => setForm(f => ({ ...f, guest_contact: e.target.value }))} placeholder="Telefon/e-posta" />
                </div>
              </div>
              <div>
                <Label>Depolama Yeri</Label>
                <Input value={form.storage_location} onChange={e => setForm(f => ({ ...f, storage_location: e.target.value }))} placeholder="Depo, Kasa, Resepsiyon..." />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowCreate(false)}>İptal</Button>
                <Button onClick={handleCreate} data-testid="save-lostfound-btn">Kaydet</Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        <Dialog open={!!showDetail} onOpenChange={() => setShowDetail(null)}>
          <DialogContent className="max-w-lg">
            {showDetail && (
              <>
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2">
                    <span className="text-2xl">{(CATEGORY_CONFIG[showDetail.category] || CATEGORY_CONFIG.other).icon}</span>
                    {showDetail.item_name}
                  </DialogTitle>
                </DialogHeader>
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div><span className="text-gray-500">Durum:</span> <Badge className={STATUS_CONFIG[showDetail.status]?.color}>{STATUS_CONFIG[showDetail.status]?.label}</Badge></div>
                    <div><span className="text-gray-500">Kategori:</span> {(CATEGORY_CONFIG[showDetail.category] || CATEGORY_CONFIG.other).label}</div>
                    <div><span className="text-gray-500">Bulunduğu Yer:</span> {showDetail.found_location}</div>
                    <div><span className="text-gray-500">Tarih:</span> {showDetail.found_date}</div>
                    <div><span className="text-gray-500">Bulan Kişi:</span> {showDetail.found_by || '-'}</div>
                    <div><span className="text-gray-500">Oda:</span> {showDetail.room_number || '-'}</div>
                    <div><span className="text-gray-500">Depo Yeri:</span> {showDetail.storage_location || '-'}</div>
                    <div><span className="text-gray-500">Kaydeden:</span> {showDetail.created_by || '-'}</div>
                  </div>
                  {showDetail.description && (
                    <div className="text-sm bg-gray-50 rounded-lg p-3">
                      <span className="text-gray-500">Açıklama:</span> {showDetail.description}
                    </div>
                  )}
                  {showDetail.guest_name && (
                    <div className="text-sm bg-blue-50 rounded-lg p-3 border border-blue-200">
                      <div className="font-medium text-blue-700 flex items-center gap-1"><UserCheck className="w-4 h-4" /> Eşleşen Misafir</div>
                      <div>{showDetail.guest_name} {showDetail.guest_contact && `(${showDetail.guest_contact})`}</div>
                    </div>
                  )}

                  <div className="flex flex-wrap gap-2 pt-2 border-t">
                    {showDetail.status !== 'returned' && (
                      <>
                        {showDetail.status === 'found' && (
                          <Button size="sm" variant="outline" onClick={() => handleStatusUpdate(showDetail.id, 'stored')}>
                            <Archive className="w-3 h-3 mr-1" /> Depola
                          </Button>
                        )}
                        {(showDetail.status === 'found' || showDetail.status === 'stored') && (
                          <Button size="sm" variant="outline" onClick={() => handleStatusUpdate(showDetail.id, 'claimed')}>
                            <UserCheck className="w-3 h-3 mr-1" /> Sahiplenildi
                          </Button>
                        )}
                        {showDetail.status === 'claimed' && (
                          <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700 text-white" onClick={() => handleStatusUpdate(showDetail.id, 'returned')}>
                            <Send className="w-3 h-3 mr-1" /> Teslim Edildi
                          </Button>
                        )}
                        {(showDetail.status === 'found' || showDetail.status === 'stored') && (
                          <Button size="sm" variant="outline" className="text-amber-600 border-amber-200"
                            onClick={() => { setShowMatch(showDetail); setMatchForm({ guest_name: showDetail.guest_name || '', guest_contact: showDetail.guest_contact || '', booking_id: '' }); setShowDetail(null); }}
                          >
                            <UserCheck className="w-3 h-3 mr-1" /> Misafir Eşleştir
                          </Button>
                        )}
                      </>
                    )}
                    <Button size="sm" variant="ghost" className="text-red-500 ml-auto" onClick={() => { setDeleteConfirm(showDetail); setShowDetail(null); }}>
                      <Trash2 className="w-3 h-3 mr-1" /> Sil
                    </Button>
                  </div>
                </div>
              </>
            )}
          </DialogContent>
        </Dialog>

        <Dialog open={!!showMatch} onOpenChange={() => setShowMatch(null)}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2"><UserCheck className="w-5 h-5 text-blue-600" /> Misafir Eşleştir</DialogTitle>
            </DialogHeader>
            {showMatch && (
              <div className="space-y-3">
                <div className="bg-gray-50 rounded-lg p-3 text-sm">
                  <span className="text-gray-500">Eşya:</span> <strong>{showMatch.item_name}</strong>
                </div>
                <div>
                  <Label>Misafir Adı</Label>
                  <Input value={matchForm.guest_name} onChange={e => setMatchForm(f => ({ ...f, guest_name: e.target.value }))} placeholder="Ad Soyad" />
                </div>
                <div>
                  <Label>İletişim</Label>
                  <Input value={matchForm.guest_contact} onChange={e => setMatchForm(f => ({ ...f, guest_contact: e.target.value }))} placeholder="Telefon veya e-posta" />
                </div>
                <div>
                  <Label>Rezervasyon ID (opsiyonel)</Label>
                  <Input value={matchForm.booking_id} onChange={e => setMatchForm(f => ({ ...f, booking_id: e.target.value }))} placeholder="Otomatik eşleştirme" />
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="outline" onClick={() => setShowMatch(null)}>İptal</Button>
                  <Button onClick={handleMatchGuest} data-testid="match-guest-btn">Eşleştir</Button>
                </div>
              </div>
            )}
          </DialogContent>
        </Dialog>

        <Dialog open={!!deleteConfirm} onOpenChange={o => { if (!o) setDeleteConfirm(null); }}>
          <DialogContent className="max-w-sm">
            <DialogHeader>
              <DialogTitle>Silme Onayı</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-gray-600">
              Bu kaydı silmek istediğinize emin misiniz?
              {deleteConfirm && <span className="font-medium"> ({deleteConfirm.item_name})</span>}
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setDeleteConfirm(null)}>İptal</Button>
              <Button variant="destructive" onClick={() => handleDelete(deleteConfirm?.id)}>Sil</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </>
  );
};

export default LostFoundPage;
