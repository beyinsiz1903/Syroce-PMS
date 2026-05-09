import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Send, Save, Plus, Trash2, Loader2, Bed,
  Building2, CheckSquare, Square, RefreshCw, AlertTriangle
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

const AgencyContentDistribution = ({ user }) => {
  const { t } = useTranslation();
  const [content, setContent] = useState(null);
  const [agencies, setAgencies] = useState([]);
  const [selectedAgencies, setSelectedAgencies] = useState([]);
  const [pendingDeletes, setPendingDeletes] = useState({ rooms: new Set(), services: new Set() });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [distributing, setDistributing] = useState(false);
  const [distributeDialog, setDistributeDialog] = useState(null); // { preview, unpublishOmitted }
  const [previewLoading, setPreviewLoading] = useState(false);

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
  }, []);

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
      setPendingDeletes({ rooms: new Set(), services: new Set() });
      toast.success('İçerik kaydedildi');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Kaydetme hatası');
    } finally {
      setSaving(false);
    }
  };

  // FIX #1 (KRITIK): Dagitim artik 2 adim — once preview cek, kullaniciya
  // diff'i (X eklenecek, Y kaldirilacak) goster, sonra onayla.
  const openDistributeDialog = async () => {
    if (selectedAgencies.length === 0) {
      toast.error('En az bir acente seçin');
      return;
    }
    setPreviewLoading(true);
    try {
      const { data } = await axios.get('/hotel-content/distribute-preview', {
        params: { agency_ids: selectedAgencies.join(',') },
      });
      setDistributeDialog({ preview: data, unpublishOmitted: false });
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
          <Button onClick={openDistributeDialog} disabled={distributing || previewLoading} data-testid="distribute-btn" className="gap-2">
            {(distributing || previewLoading) ? <Loader2 className="animate-spin" size={14} /> : <Send size={14} />}
            {t('cm.pages_AgencyContentDistribution.yayin_listesini_guncelle')}
          </Button>
        </div>
      </div>

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
                <Building2 size={16} /> Acenteler
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
              disabled={distributing}
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
