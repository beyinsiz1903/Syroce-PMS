import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Send, Save, Plus, Trash2, Loader2, Bed,
  Building2, CheckSquare, Square, RefreshCw, AlertTriangle, ImagePlus, X
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useTranslation } from 'react-i18next';

// Marketplace catalogue visibility. Sales access always comes from the
// approved contract; this only decides who sees photos and descriptions.
const MarketplaceContentTargeting = () => {
  const [state, setState] = useState(null);
  const [saving, setSaving] = useState(false);
  const load = useCallback(async () => {
    try { setState((await axios.get('/hotel-content/marketplace-distribution')).data); }
    catch { setState({ error: true }); }
  }, []);
  useEffect(() => { load(); }, [load]);
  if (!state) return null;
  if (state.error) return <p className="text-xs text-slate-400">Marketplace içerik dağıtımı yüklenemedi.</p>;
  const toggle = id => setState(current => ({
    ...current,
    agency_ids: current.agency_ids.includes(id) ? current.agency_ids.filter(x => x !== id) : [...current.agency_ids, id],
  }));
  const save = async () => {
    if (state.mode === 'selected' && state.agency_ids.length === 0) return toast.error('En az bir acente seçin veya "Tüm sözleşmeli acenteler" seçeneğini kullanın.');
    setSaving(true);
    try {
      await axios.put('/hotel-content/marketplace-distribution', { mode: state.mode, agency_ids: state.agency_ids });
      toast.success('Marketplace içerik dağıtımı kaydedildi.');
      await load();
    } catch (err) { toast.error(err.response?.data?.detail || 'Marketplace içerik dağıtımı kaydedilemedi.'); }
    finally { setSaving(false); }
  };
  return (
    <Card className="mt-4" data-testid="marketplace-content-targeting">
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2"><Send size={16} /> Marketplace acenteleri</CardTitle>
        <p className="text-xs text-slate-500">Fotoğraf, açıklama ve oda içerikleri kimlere gösterilsin? Satış yetkisi yine sözleşmeye bağlıdır.</p>
      </CardHeader>
      <CardContent className="space-y-2">
        {!state.is_listed && <p className="text-xs text-amber-700">Tesis marketplace'te yayında değil.</p>}
        <label className="flex items-center gap-2 text-sm"><input type="radio" checked={state.mode === 'all'} onChange={() => setState(c => ({ ...c, mode: 'all' }))} /> Tüm sözleşmeli acenteler</label>
        <label className="flex items-center gap-2 text-sm"><input type="radio" checked={state.mode === 'selected'} onChange={() => setState(c => ({ ...c, mode: 'selected' }))} /> Yalnız seçtiklerim</label>
        {state.mode === 'selected' && (
          (state.agencies || []).length === 0
            ? <p className="text-xs text-slate-400">Onaylı sözleşmesi olan marketplace acentesi yok.</p>
            : state.agencies.map(agency => (
              <label key={agency.id} className="flex items-center gap-2 rounded border p-2 text-sm">
                <input type="checkbox" checked={state.agency_ids.includes(agency.id)} onChange={() => toggle(agency.id)} />
                <span className="truncate">{agency.name}</span>
              </label>
            ))
        )}
        <Button size="sm" className="w-full" onClick={save} disabled={saving || !state.is_listed}>
          {saving && <Loader2 size={14} className="mr-2 animate-spin" />}Kaydet
        </Button>
      </CardContent>
    </Card>
  );
};

const ProtectedImage = ({ src, alt, className }) => {
  const [objectUrl, setObjectUrl] = useState('');
  useEffect(() => {
    if (!src) return undefined;
    if (!src.startsWith('/api/uploads/')) {
      setObjectUrl(src);
      return undefined;
    }
    let active = true;
    let createdUrl = '';
    axios.get(src.replace(/^\/api/, ''), { responseType: 'blob' }).then(({ data }) => {
      if (!active) return;
      createdUrl = URL.createObjectURL(data);
      setObjectUrl(createdUrl);
    }).catch(() => setObjectUrl(''));
    return () => {
      active = false;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [src]);
  return objectUrl ? <img src={objectUrl} alt={alt} className={className} /> : <div className={`${className} bg-slate-100`} aria-label={alt} />;
};

const AgencyContentDistribution = ({ user }) => {
  const { t, i18n } = useTranslation();
  const [content, setContent] = useState(null);
  const [savedContent, setSavedContent] = useState('');
  const [readiness, setReadiness] = useState(null);
  const refreshReadiness = useCallback(async () => {
    setReadiness(null);
    try { setReadiness((await axios.get('/hotel-content/readiness')).data); }
    catch { toast.error('Yayına hazırlık kontrolü alınamadı; yeniden kontrol edin.'); }
  }, []);
  const [agencies, setAgencies] = useState([]);
  const [selectedAgencies, setSelectedAgencies] = useState([]);
  const [pendingDeletes, setPendingDeletes] = useState({ rooms: new Set(), services: new Set() });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [distributing, setDistributing] = useState(false);
  const [distributeDialog, setDistributeDialog] = useState(null); // { preview, unpublishOmitted }
  const [previewLoading, setPreviewLoading] = useState(false);
  const [uploadingImages, setUploadingImages] = useState(false);

  const isSuperAdmin = user?.role === 'super_admin' || (Array.isArray(user?.roles) && user.roles.includes('super_admin'));
  const canDelete = isSuperAdmin || ['super_admin', 'admin'].includes(user?.role) || (Array.isArray(user?.roles) && user.roles.some((r) => ['super_admin', 'admin'].includes(r)));

  // FIX #10: Initial fetch — 5xx tek retry + AbortController
  const loadAll = useCallback(async ({ silent = false, signal } = {}) => {
    if (!silent) setLoading(true);
    const tryOnce = async () => {
      const [contentRes, agenciesRes] = await Promise.all([
        axios.get('/hotel-content', { signal }),
        axios.get('/agencies', { signal }),
      ]);
      return { content: contentRes.data, agencies: agenciesRes.data };
    };
    try {
      let res;
      try {
        res = await tryOnce();
      } catch (firstErr) {
        if (axios.isCancel?.(firstErr) || firstErr?.name === 'CanceledError') return;
        const st = firstErr?.response?.status;
        if (st && st >= 400 && st < 500) throw firstErr;
        await new Promise(r => setTimeout(r, 1500));
        res = await tryOnce();
      }
      setContent(res.content);
      setSavedContent(JSON.stringify(res.content));
      await refreshReadiness();
      const list = Array.isArray(res.agencies) ? res.agencies : (res.agencies?.items || []);
      setAgencies(list);
      const published = list.filter(a => a.published_content).map(a => a.id);
      setSelectedAgencies(published);
    } catch (e) {
      if (axios.isCancel?.(e) || e?.name === 'CanceledError') return;
      console.error('[AgencyContent] load failed:', e?.response?.status, e?.response?.data);
      if (!silent) {
        toast.error('Veriler yüklenemedi: ' + (e.response?.data?.detail || e.message));
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }, [refreshReadiness]);

  useEffect(() => {
    const ctrl = new AbortController();
    loadAll({ signal: ctrl.signal });
    return () => ctrl.abort();
  }, [loadAll]);

  const handleSaveContent = async () => {
    setSaving(true);
    try {
      // FIX #3: Local-state delete'leri kaydetme aninda kalicilastir.
      const cleaned = {
        ...content,
        room_types: (content?.room_types || []).filter((_, i) => !pendingDeletes.rooms.has(i)),
        services: (content?.services || []).filter((_, i) => !pendingDeletes.services.has(i)),
      };
      const res = await axios.put('/hotel-content', cleaned);
      setContent(res.data);
      setSavedContent(JSON.stringify(res.data));
      await refreshReadiness();
      setPendingDeletes({ rooms: new Set(), services: new Set() });
      toast.success('İçerik kaydedildi. Mevcut yayınlara güncel içerik yansır; kayıt işlemi marketplace satışını açmaz.');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Kaydetme hatası');
    } finally {
      setSaving(false);
    }
  };

  const uploadImages = async (files, roomIndex = null) => {
    if (!files?.length) return;
    setUploadingImages(true);
    try {
      const form = new FormData();
      [...files].forEach(file => form.append('files', file));
      const { data } = await axios.post(`/hotel-content/images?scope=${roomIndex === null ? 'hotel' : 'room'}`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      if (roomIndex === null) {
        setContent(prev => ({ ...prev, images: [...(prev.images || []), ...(data.urls || [])] }));
      } else {
        setContent(prev => {
          const roomTypes = [...(prev.room_types || [])];
          roomTypes[roomIndex] = { ...roomTypes[roomIndex], images: [...(roomTypes[roomIndex].images || []), ...(data.urls || [])] };
          return { ...prev, room_types: roomTypes };
        });
      }
      toast.success(`${data.uploaded || 0} görsel yüklendi. Yayınlamak için Kaydet'e basın.`);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Görsel yüklenemedi');
    } finally {
      setUploadingImages(false);
    }
  };

  const removeImage = (url, roomIndex = null) => {
    if (roomIndex === null) {
      setContent(prev => ({ ...prev, images: (prev.images || []).filter(image => image !== url) }));
      return;
    }
    setContent(prev => {
      const roomTypes = [...(prev.room_types || [])];
      roomTypes[roomIndex] = { ...roomTypes[roomIndex], images: (roomTypes[roomIndex].images || []).filter(image => image !== url) };
      return { ...prev, room_types: roomTypes };
    });
  };

  // FIX #1 (KRITIK): Dagitim artik 2 adim — once preview cek, kullaniciya
  // diff'i (X eklenecek, Y kaldirilacak) goster, sonra onayla.
  const openDistributeDialog = async () => {
    if (dirty) { toast.error('Önce içerik değişikliklerini kaydedin.'); return; }
    if (!readiness) { toast.error('Önce yayına hazırlık kontrolünü yenileyin.'); return; }
    if (selectedAgencies.length === 0 && !agencies.some(agency => agency.published_content)) {
      toast.error('En az bir acente seçin');
      return;
    }
    setPreviewLoading(true);
    try {
      const { data } = await axios.get('/hotel-content/distribute-preview', {
        params: { agency_ids: selectedAgencies.join(',') },
      });
      const fresh = (await axios.get('/hotel-content/readiness')).data;
      setReadiness(fresh);
      setDistributeDialog({ preview: data, readiness: fresh, acknowledged: false, unpublishOmitted: false });
    } catch (e) {
      toast.error('Önizleme alınamadı: ' + (e.response?.data?.detail || e.message));
    } finally {
      setPreviewLoading(false);
    }
  };

  const submitDistribute = async () => {
    if (!distributeDialog) return;
    setDistributing(true);
    try {
      const res = await axios.post('/hotel-content/distribute', {
        agency_ids: selectedAgencies,
        unpublish_omitted: distributeDialog.unpublishOmitted,
        expected_content_version: distributeDialog.readiness.content_version,
      });
      toast.success(res.data.message);
      setDistributeDialog(null);
      // Refresh agencies (silent)
      await loadAll({ silent: true });
    } catch (err) {
      const detail = err.response?.data?.detail;
      // Backend icerik validasyonu hatasi (#6): yapilandirilmis errors[]
      if (detail?.code === 'content_incomplete') {
        toast.error(detail.message || 'İçerik eksik', {
          description: (detail.errors || []).join('  •  '),
        });
      } else {
        toast.error(typeof detail === 'string' ? detail : (detail?.message || 'Dağıtım hatası'));
      }
    } finally {
      setDistributing(false);
    }
  };

  const toggleAgency = (agencyId) => {
    setSelectedAgencies(prev =>
      prev.includes(agencyId) ? prev.filter(id => id !== agencyId) : [...prev, agencyId]
    );
  };

  const selectAllAgencies = () => {
    const activeIds = agencies.filter(a => a.status === 'active').map(a => a.id);
    setSelectedAgencies(activeIds);
  };

  const deselectAllAgencies = () => setSelectedAgencies([]);

  // Room type helpers
  const addRoomType = () => {
    setContent(prev => ({
      ...prev,
      room_types: [...(prev.room_types || []), { room_type: '', name: '', description: '', capacity: 2, base_price: 0, images: [], amenities: [], bed_type: '' }]
    }));
  };

  const updateRoomType = (idx, field, value) => {
    setContent(prev => {
      const updated = [...(prev.room_types || [])];
      updated[idx] = { ...updated[idx], [field]: value };
      return { ...prev, room_types: updated };
    });
  };

  const markRoomDelete = (idx) => {
    setPendingDeletes(prev => {
      const next = new Set(prev.rooms);
      next.add(idx);
      return { ...prev, rooms: next };
    });
  };

  const undoRoomDelete = (idx) => {
    setPendingDeletes(prev => {
      const next = new Set(prev.rooms);
      next.delete(idx);
      return { ...prev, rooms: next };
    });
  };

  // Service helpers
  const addService = () => {
    setContent(prev => ({
      ...prev,
      services: [...(prev.services || []), { name: '', description: '', icon: '' }]
    }));
  };

  const updateService = (idx, field, value) => {
    setContent(prev => {
      const updated = [...(prev.services || [])];
      updated[idx] = { ...updated[idx], [field]: value };
      return { ...prev, services: updated };
    });
  };

  const markServiceDelete = (idx) => {
    setPendingDeletes(prev => {
      const next = new Set(prev.services);
      next.add(idx);
      return { ...prev, services: next };
    });
  };

  const undoServiceDelete = (idx) => {
    setPendingDeletes(prev => {
      const next = new Set(prev.services);
      next.delete(idx);
      return { ...prev, services: next };
    });
  };

  const hasPendingDeletes = pendingDeletes.rooms.size > 0 || pendingDeletes.services.size > 0;
  const dirty = JSON.stringify(content) !== savedContent || hasPendingDeletes;

  if (loading) {
    return (
      <div className="flex justify-center py-20"><Loader2 className="animate-spin text-slate-400" size={32} /></div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto" data-testid="agency-content-distribution">
      <div className="flex items-center justify-between">
        <div>
          {/* FIX #9: Türkçe karakter standartı */}
          <h1 className="text-2xl font-bold text-slate-900" data-testid="content-dist-title">{t('cm.pages_AgencyContentDistribution.icerik_dagitimi')}</h1>
          <p className="text-slate-500 text-sm mt-1">{t('cm.pages_AgencyContentDistribution.otel_bilgilerini_duzenleyin_ve_sectigini')}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => loadAll({ silent: true })}>
            <RefreshCw className="w-4 h-4 mr-1.5" /> {t('cm.pages_AgencyContentDistribution.yenile')}
          </Button>
          <Button variant="outline" onClick={handleSaveContent} disabled={saving} data-testid="save-content-btn">
            {saving ? <Loader2 className="animate-spin mr-1" size={14} /> : <Save size={14} className="mr-1" />}
            {t('cm.pages_AgencyContentDistribution.kaydet')}{hasPendingDeletes ? ` (${pendingDeletes.rooms.size + pendingDeletes.services.size} silme)` : ''}
          </Button>
          {/* FIX #1: Buton adi semantik — "Yayın Listesini Güncelle" */}
          <Button onClick={openDistributeDialog} disabled={distributing || previewLoading || saving || uploadingImages || dirty || !readiness} data-testid="distribute-btn" className="gap-2">
            {(distributing || previewLoading) ? <Loader2 className="animate-spin" size={14} /> : <Send size={14} />}
            {t('cm.pages_AgencyContentDistribution.yayin_listesini_guncelle')}
          </Button>
        </div>
      </div>

      <Card><CardHeader><CardTitle>Yayına hazırlık ve erişim kapsamı</CardTitle></CardHeader><CardContent className="space-y-3 text-sm">
        <p><strong>Otele bağlı portal:</strong> Sağdaki acente listesi yalnız bu portalın içerik erişimini yönetir. Seçimi kaldırmak tek başına erişimi kesmez; onay penceresinde yayından kaldırmayı ayrıca seçmelisiniz.</p>
        <p><strong>Marketplace:</strong> Erişim tesisin marketplace yayınına ve geçerli, onaylı sözleşmeye bağlıdır. Bu listeden acente kaldırmak marketplace erişimini veya sözleşmesini kapatmaz. Bunun için marketplace tesis yayını / sözleşme yönetimini kullanın.</p>
        <p>Kaydet, önceden yayınlanmış acentelere güncel içeriği yansıtır ve varsa marketplace içeriğini günceller; yeni satış yetkisi vermez.</p>
        {!readiness ? <p role="alert">Hazırlık durumu doğrulanamadı. <button type="button" onClick={refreshReadiness}>Tekrar kontrol et</button></p> : <>
          <p>PMS adı: {readiness.tenant_name || '—'} · Yayın adı: {readiness.content_name || '—'}</p>
          <p>Otele bağlı portal: {readiness.access.hotel_portal_published_count} aktif acenteye açık. Marketplace yayını: {readiness.access.marketplace_listed ? 'Açık' : 'Kapalı'} · Geçerli sözleşme: {readiness.access.marketplace_active_contract_count}</p>
          <p role="status">Kayıtlı sürüm {readiness.content_version}: {readiness.ready ? 'İçerik kontrolü tamam; satış uygunluğu ayrıca değerlendirilir.' : 'Yayın öncesi eksikler / uyarılar var.'}</p>
          <ul className="list-disc pl-5">{[...readiness.errors, ...readiness.warnings].map(item => <li key={item}>{item}</li>)}</ul>
          <p className="text-xs">Fotoğraf kontrolü kayıt varlığını denetler; görsellerin açıldığını ve kullanım haklarını ayrıca doğrulayın.</p>
        </>}
        {dirty && <p role="alert">Kaydedilmemiş değişiklikler var. Kontrol kayıtlı sürüme aittir; yayın listesi için önce Kaydet’e basın.</p>}
      </CardContent></Card>

      {hasPendingDeletes && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>
            {pendingDeletes.rooms.size + pendingDeletes.services.size} {t('cm.pages_AgencyContentDistribution.silme_islemi_bekliyor')}
            <strong className="mx-1">{t('cm.pages_AgencyContentDistribution.kaydet_a9270')}</strong>'e basana kadar uygulanmayacak.
          </span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Content Editor */}
        <div className="lg:col-span-2">
          <Tabs defaultValue="hotel" className="w-full">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="hotel" data-testid="tab-hotel">Otel Bilgileri</TabsTrigger>
              <TabsTrigger value="rooms" data-testid="tab-rooms">{t('cm.pages_AgencyContentDistribution.oda_tipleri')}</TabsTrigger>
              <TabsTrigger value="services" data-testid="tab-services">Hizmetler</TabsTrigger>
            </TabsList>

            {/* Hotel Info Tab */}
            <TabsContent value="hotel" className="space-y-4 mt-4">
              <Card>
                <CardContent className="pt-6 space-y-4">
                  <div>
                    <Label>{t('cm.pages_AgencyContentDistribution.otel_adi')}</Label>
                    <Input value={content?.hotel_name || ''} onChange={e => setContent(p => ({ ...p, hotel_name: e.target.value }))} data-testid="hotel-name-input" />
                  </div>
                  <div>
                    <Label>{t('cm.pages_AgencyContentDistribution.aciklama')}</Label>
                    <Textarea rows={3} value={content?.description || ''} onChange={e => setContent(p => ({ ...p, description: e.target.value }))} placeholder={t('cm.pages_AgencyContentDistribution.otel_hakkinda_kisa_tanitim')} />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label>Adres</Label>
                      <Input value={content?.address || ''} onChange={e => setContent(p => ({ ...p, address: e.target.value }))} />
                    </div>
                    <div>
                      <Label>Telefon</Label>
                      <Input value={content?.phone || ''} onChange={e => setContent(p => ({ ...p, phone: e.target.value }))} />
                    </div>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div>
                      <Label>Şehir / Bölge</Label>
                      <Input value={content?.city || ''} onChange={e => setContent(p => ({ ...p, city: e.target.value }))} placeholder="Kocaeli / Kartepe" />
                    </div>
                    <div>
                      <Label>Ülke kodu</Label>
                      <Input value={content?.country || 'TR'} maxLength={2} onChange={e => setContent(p => ({ ...p, country: e.target.value.toUpperCase() }))} />
                    </div>
                    <div>
                      <Label>Yıldız</Label>
                      <Input type="number" min="1" max="5" value={content?.star_rating || ''} onChange={e => setContent(p => ({ ...p, star_rating: e.target.value ? Number(e.target.value) : null }))} placeholder="5" />
                    </div>
                  </div>
                  <div>
                    <Label>E-posta</Label>
                    <Input value={content?.email || ''} onChange={e => setContent(p => ({ ...p, email: e.target.value }))} />
                  </div>
                  <div>
                    <Label>{t('cm.pages_AgencyContentDistribution.olanaklar_virgul_ile_ayirin')}</Label>
                    <Input
                      value={(content?.amenities || []).join(', ')}
                      onChange={e => setContent(p => ({ ...p, amenities: e.target.value.split(',').map(s => s.trim()).filter(Boolean) }))}
                      placeholder="Havuz, Spa, Restoran, WiFi..."
                    />
                  </div>
                  <div>
                    <Label>Pansiyon tipleri (virgülle ayırın)</Label>
                    <Input
                      value={(content?.meal_plans || []).join(', ')}
                      onChange={e => setContent(p => ({ ...p, meal_plans: e.target.value.split(',').map(s => s.trim()).filter(Boolean) }))}
                      placeholder="Oda kahvaltı, Yarım pansiyon, Her şey dahil"
                    />
                  </div>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between gap-3">
                      <div><Label>Tesis fotoğrafları</Label><p className="text-xs text-slate-500">JPG, PNG veya WebP yükleyin. İlk fotoğraf kapak görselidir.</p></div>
                      <label className="inline-flex h-9 cursor-pointer items-center rounded-md border border-slate-200 px-3 text-sm font-medium hover:bg-slate-50">
                        {uploadingImages ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ImagePlus className="mr-2 h-4 w-4" />} Fotoğraf ekle
                        <input type="file" accept="image/png,image/jpeg,image/webp" multiple className="hidden" disabled={uploadingImages} onChange={e => { uploadImages(e.target.files); e.target.value = ''; }} />
                      </label>
                    </div>
                    {(content?.images || []).length > 0 && <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">{content.images.map((url, index) => <div key={url} className="group relative aspect-[4/3] overflow-hidden rounded-lg border bg-slate-100"><ProtectedImage src={url} alt={`Tesis ${index + 1}`} className="h-full w-full object-cover" /><button type="button" onClick={() => removeImage(url)} className="absolute right-1 top-1 rounded-full bg-slate-950/75 p-1 text-white" aria-label="Fotoğrafı kaldır"><X size={14} /></button>{index === 0 && <Badge className="absolute bottom-1 left-1 bg-white/90 text-slate-800">Kapak</Badge>}</div>)}</div>}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Room Types Tab */}
            <TabsContent value="rooms" className="space-y-3 mt-4">
              {(content?.room_types || []).map((rt, idx) => {
                const marked = pendingDeletes.rooms.has(idx);
                return (
                  <Card key={idx} className={marked ? 'opacity-60 ring-1 ring-amber-300' : ''}>
                    <CardContent className="pt-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <h4 className="font-medium text-sm text-slate-700 flex items-center gap-2">
                          <Bed size={14} /> {t('cm.pages_AgencyContentDistribution.oda_tipi')} {idx + 1}
                          {marked && <Badge className="bg-amber-100 text-amber-800 border-amber-200 text-[10px]">{t('cm.pages_AgencyContentDistribution.silinmek_uzere')}</Badge>}
                        </h4>
                        {canDelete && (
                          marked ? (
                            <Button size="sm" variant="ghost" className="h-7 text-amber-700" onClick={() => undoRoomDelete(idx)} data-testid={`undo-delete-room-type-${idx}`}>
                              Geri Al
                            </Button>
                          ) : (
                            <Button size="sm" variant="ghost" className="text-rose-500 h-7" onClick={() => markRoomDelete(idx)} data-testid={`delete-room-type-${idx}`}>
                              <Trash2 size={13} />
                            </Button>
                          )
                        )}
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <Label className="text-xs">Tip Kodu</Label>
                          <Input value={rt.room_type} onChange={e => updateRoomType(idx, 'room_type', e.target.value)} placeholder="Standard" className="text-sm" />
                        </div>
                        <div>
                          <Label className="text-xs">{t('cm.pages_AgencyContentDistribution.gorunen_ad')}</Label>
                          <Input value={rt.name || rt.room_type} onChange={e => updateRoomType(idx, 'name', e.target.value)} className="text-sm" />
                        </div>
                      </div>
                      <div>
                        <Label className="text-xs">{t('cm.pages_AgencyContentDistribution.aciklama_1babd')}</Label>
                        <Textarea rows={2} value={rt.description} onChange={e => updateRoomType(idx, 'description', e.target.value)} className="text-sm" placeholder={t('cm.pages_AgencyContentDistribution.oda_aciklamasi')} />
                      </div>
                      <div className="grid grid-cols-3 gap-3">
                        <div>
                          <Label className="text-xs">Kapasite</Label>
                          <Input type="number" value={rt.capacity} onChange={e => updateRoomType(idx, 'capacity', parseInt(e.target.value) || 1)} className="text-sm" />
                        </div>
                        <div>
                          <Label className="text-xs">Fiyat</Label>
                          <Input type="number" value={rt.base_price} onChange={e => updateRoomType(idx, 'base_price', parseFloat(e.target.value) || 0)} className="text-sm" />
                        </div>
                        <div>
                          <Label className="text-xs">Yatak Tipi</Label>
                          <Input value={rt.bed_type} onChange={e => updateRoomType(idx, 'bed_type', e.target.value)} className="text-sm" placeholder="Double" />
                        </div>
                      </div>
                      <div>
                        <Label className="text-xs">{t('cm.pages_AgencyContentDistribution.oda_olanaklari_virgul_ile')}</Label>
                        <Input
                          value={(rt.amenities || []).join(', ')}
                          onChange={e => updateRoomType(idx, 'amenities', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                          className="text-sm" placeholder="WiFi, Minibar, Klima..."
                        />
                      </div>
                      <div className="space-y-2">
                        <div className="flex items-center justify-between"><Label className="text-xs">Oda fotoğrafları</Label><label className="cursor-pointer text-xs font-medium text-blue-600 hover:text-blue-700"><ImagePlus className="mr-1 inline h-3.5 w-3.5" />Fotoğraf ekle<input type="file" accept="image/png,image/jpeg,image/webp" multiple className="hidden" disabled={uploadingImages} onChange={e => { uploadImages(e.target.files, idx); e.target.value = ''; }} /></label></div>
                        {(rt.images || []).length > 0 && <div className="flex gap-2 overflow-x-auto pb-1">{rt.images.map(url => <div key={url} className="relative h-20 w-28 shrink-0 overflow-hidden rounded-md border bg-slate-100"><ProtectedImage src={url} alt={rt.name || rt.room_type} className="h-full w-full object-cover" /><button type="button" onClick={() => removeImage(url, idx)} className="absolute right-1 top-1 rounded-full bg-slate-950/75 p-0.5 text-white" aria-label="Oda fotoğrafını kaldır"><X size={12} /></button></div>)}</div>}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
              <Button variant="outline" onClick={addRoomType} className="w-full gap-2" data-testid="add-room-type-btn">
                <Plus size={14} /> {t('cm.pages_AgencyContentDistribution.oda_tipi_ekle')}
              </Button>
            </TabsContent>

            {/* Services Tab */}
            <TabsContent value="services" className="space-y-3 mt-4">
              {(content?.services || []).map((svc, idx) => {
                const marked = pendingDeletes.services.has(idx);
                return (
                  <Card key={idx} className={marked ? 'opacity-60 ring-1 ring-amber-300' : ''}>
                    <CardContent className="pt-4">
                      <div className="flex items-center justify-between mb-2">
                        <h4 className="font-medium text-sm text-slate-700 flex items-center gap-2">
                          Hizmet {idx + 1}
                          {marked && <Badge className="bg-amber-100 text-amber-800 border-amber-200 text-[10px]">{t('cm.pages_AgencyContentDistribution.silinmek_uzere_fd08f')}</Badge>}
                        </h4>
                        {canDelete && (
                          marked ? (
                            <Button size="sm" variant="ghost" className="h-7 text-amber-700" onClick={() => undoServiceDelete(idx)} data-testid={`undo-delete-service-${idx}`}>
                              Geri Al
                            </Button>
                          ) : (
                            <Button size="sm" variant="ghost" className="text-rose-500 h-7" onClick={() => markServiceDelete(idx)} data-testid={`delete-service-${idx}`}>
                              <Trash2 size={13} />
                            </Button>
                          )
                        )}
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <Label className="text-xs">{t('cm.pages_AgencyContentDistribution.hizmet_adi')}</Label>
                          <Input value={svc.name} onChange={e => updateService(idx, 'name', e.target.value)} className="text-sm" placeholder="Havuz" />
                        </div>
                        <div>
                          <Label className="text-xs">{t('cm.pages_AgencyContentDistribution.aciklama_1babd')}</Label>
                          <Input value={svc.description} onChange={e => updateService(idx, 'description', e.target.value)} className="text-sm" placeholder={t('cm.pages_AgencyContentDistribution.acik_havuz_08_00_20_00')} />
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
              <Button variant="outline" onClick={addService} className="w-full gap-2" data-testid="add-service-btn">
                <Plus size={14} /> {t('cm.pages_AgencyContentDistribution.hizmet_ekle')}
              </Button>
            </TabsContent>
          </Tabs>
        </div>

        {/* Right: Agency Selection */}
        <div>
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Building2 size={16} /> Otele bağlı portal acenteleri
              </CardTitle>
              <div className="flex gap-2 mt-2">
                <Button size="sm" variant="outline" className="text-xs h-7" onClick={selectAllAgencies}>{t('cm.pages_AgencyContentDistribution.tumunu_sec')}</Button>
                <Button size="sm" variant="outline" className="text-xs h-7" onClick={deselectAllAgencies}>Temizle</Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-2 max-h-[500px] overflow-y-auto">
              {agencies.filter(a => a.status === 'active').length === 0 ? (
                <p className="text-xs text-slate-400 text-center py-4">{t('cm.pages_AgencyContentDistribution.aktif_acente_yok')}</p>
              ) : (
                agencies.filter(a => a.status === 'active').map(agency => (
                  <div
                    key={agency.id}
                    className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition ${
                      selectedAgencies.includes(agency.id) ? 'bg-emerald-50 border-emerald-300' : 'bg-white hover:bg-slate-50'
                    }`}
                    onClick={() => toggleAgency(agency.id)}
                    data-testid={`agency-select-${agency.id}`}
                  >
                    {selectedAgencies.includes(agency.id) ? (
                      <CheckSquare size={18} className="text-emerald-600 flex-shrink-0" />
                    ) : (
                      <Square size={18} className="text-slate-300 flex-shrink-0" />
                    )}
                    <div className="min-w-0">
                      <div className="font-medium text-sm text-slate-800 truncate">{agency.name}</div>
                      <div className="text-xs text-slate-400">{agency.contact_name || 'Yetkili belirtilmemiş'}</div>
                    </div>
                    {agency.published_content && (
                      <Badge variant="outline" className="text-[10px] text-sky-600 border-sky-200 ml-auto flex-shrink-0">{t('cm.pages_AgencyContentDistribution.yayinda')}</Badge>
                    )}
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <MarketplaceContentTargeting />

          <div className="mt-4 p-4 bg-slate-50 rounded-lg text-sm text-slate-500">
            <p className="font-medium text-slate-700 mb-1">{t('cm.pages_AgencyContentDistribution.nasil_calisir')}</p>
            <ul className="space-y-1 text-xs">
              <li>{t('cm.pages_AgencyContentDistribution.1_otel_bilgilerini_oda_tiplerini_ve_hizm')}</li>
              <li>2. <strong>{t('cm.pages_AgencyContentDistribution.kaydet_a9270')}</strong> {t('cm.pages_AgencyContentDistribution.ile_icerigi_kaydedin_silme_islemleri_de_')}</li>
              <li>{t('cm.pages_AgencyContentDistribution.3_sagdaki_listeden_acenteleri_secin')}</li>
              <li>4. <strong>{t('cm.pages_AgencyContentDistribution.yayin_listesini_guncelle_c8c37')}</strong> {t('cm.pages_AgencyContentDistribution.ile_dagitimi_yapin_sistem_once_eklenecek')}</li>
              <li>{t('cm.pages_AgencyContentDistribution.5_secilen_acenteler_portallarinda_bu_ice')}</li>
            </ul>
          </div>
        </div>
      </div>

      {/* FIX #1: Distribute onay dialog'u — diff onizlemesi + destruktif unpublish acik onay */}
      <AlertDialog open={!!distributeDialog} onOpenChange={(o) => !o && setDistributeDialog(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('cm.pages_AgencyContentDistribution.yayin_listesini_guncelle_c8c37')}</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-3 text-sm">
                <p>Bu işlem yalnız otele bağlı portalı etkiler. Marketplace yayını ve sözleşme erişimi değişmez.</p>
                {(distributeDialog?.readiness?.errors || []).map(item => <p role="alert" key={item}>{item}</p>)}
                {(distributeDialog?.readiness?.warnings || []).length > 0 && <div>
                  <ul>{distributeDialog.readiness.warnings.map(item => <li key={item}>{item}</li>)}</ul>
                  <label><input type="checkbox" checked={!!distributeDialog.acknowledged} onChange={e => setDistributeDialog(prev => ({ ...prev, acknowledged: e.target.checked }))} /> İçerik uyarılarını inceledim; mevcut içerikle devam et</label>
                </div>}
                <div className="rounded-md border border-slate-200 bg-slate-50 p-3 space-y-1">
                  <div className="flex justify-between"><span>{t('cm.pages_AgencyContentDistribution.su_an_yayinda')}</span><strong>{distributeDialog?.preview?.currently_published ?? 0}</strong></div>
                  <div className="flex justify-between"><span>{t('cm.pages_AgencyContentDistribution.secili')}</span><strong>{distributeDialog?.preview?.selected ?? 0}</strong></div>
                  <div className="flex justify-between text-emerald-700"><span>{t('cm.pages_AgencyContentDistribution.yayina_eklenecek')}</span><strong>+{distributeDialog?.preview?.to_add ?? 0}</strong></div>
                  <div className={`flex justify-between ${distributeDialog?.unpublishOmitted ? 'text-rose-700' : 'text-slate-400'}`}>
                    <span>{t('cm.pages_AgencyContentDistribution.yayindan_kaldirilacak')}</span>
                    <strong>{distributeDialog?.unpublishOmitted ? `-${distributeDialog?.preview?.to_remove ?? 0}` : '0 (kapalı)'}</strong>
                  </div>
                </div>

                {(distributeDialog?.preview?.to_remove ?? 0) > 0 && (
                  <label className="flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 p-3 cursor-pointer">
                    <input
                      type="checkbox"
                      data-testid="unpublish-omitted-check"
                      checked={!!distributeDialog?.unpublishOmitted}
                      onChange={(e) => setDistributeDialog(d => ({ ...d, unpublishOmitted: e.target.checked }))}
                      className="mt-0.5"
                    />
                    <span className="text-rose-900">
                      <strong>Listede olmayan {distributeDialog?.preview?.to_remove} {t('cm.pages_AgencyContentDistribution.acentenin_yayinini_da_kaldir')}</strong>
                      <span className="block text-xs mt-1">{t('cm.pages_AgencyContentDistribution.bu_secenek')} <em>destruktif</em>{t('cm.pages_AgencyContentDistribution.isaretlemezseniz_mevcut_yayinlar_korunur')}</span>
                    </span>
                  </label>
                )}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cm.pages_AgencyContentDistribution.vazgec')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={submitDistribute}
              disabled={distributing || (selectedAgencies.length === 0 ? !distributeDialog?.unpublishOmitted : (!distributeDialog?.readiness?.can_publish || ((distributeDialog?.readiness?.warnings || []).length > 0 && !distributeDialog?.acknowledged)))}
              data-testid="confirm-distribute"
            >
              {distributing ? <Loader2 className="animate-spin mr-1" size={14} /> : <Send size={14} className="mr-1" />}
              {t('cm.pages_AgencyContentDistribution.onayla_ve_uygula')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Per-row delete confirms artik render edilmiyor — silmeler `markRoomDelete` ile pending listeye gidiyor */}
      {/* (Bilinçli: alert dialog kullanan eski deseni kaldirdik — Kaydet ile kalicilastirma daha guvenli) */}
    </div>
  );
};

export default AgencyContentDistribution;
