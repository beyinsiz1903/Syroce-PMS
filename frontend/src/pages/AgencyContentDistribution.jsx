import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Send, Save, Plus, Trash2, Loader2, Image, Bed, Wifi, Coffee,
  Building2, CheckSquare, Square, MapPin, Phone, Mail, FileText
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import Layout from '@/components/Layout';

const AgencyContentDistribution = ({ user, tenant, onLogout }) => {
  const [content, setContent] = useState(null);
  const [agencies, setAgencies] = useState([]);
  const [selectedAgencies, setSelectedAgencies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [distributing, setDistributing] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const [contentRes, agenciesRes] = await Promise.all([
          axios.get('/hotel-content'),
          axios.get('/agencies'),
        ]);
        setContent(contentRes.data);
        setAgencies(agenciesRes.data);
        // Pre-select agencies that already have published content
        const published = agenciesRes.data.filter(a => a.published_content).map(a => a.id);
        setSelectedAgencies(published);
      } catch {
        toast.error('Veriler yuklenemedi');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const handleSaveContent = async () => {
    setSaving(true);
    try {
      const res = await axios.put('/hotel-content', content);
      setContent(res.data);
      toast.success('Icerik kaydedildi');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Kaydetme hatasi');
    } finally {
      setSaving(false);
    }
  };

  const handleDistribute = async () => {
    if (selectedAgencies.length === 0) return toast.error('En az bir acente secin');
    setDistributing(true);
    try {
      const res = await axios.post('/hotel-content/distribute', { agency_ids: selectedAgencies });
      toast.success(res.data.message);
      // Refresh agencies
      const { data } = await axios.get('/agencies');
      setAgencies(data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Dagitim hatasi');
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

  const removeRoomType = (idx) => {
    setContent(prev => ({
      ...prev,
      room_types: (prev.room_types || []).filter((_, i) => i !== idx)
    }));
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

  const removeService = (idx) => {
    setContent(prev => ({
      ...prev,
      services: (prev.services || []).filter((_, i) => i !== idx)
    }));
  };

  if (loading) {
    return <Layout user={user} tenant={tenant} onLogout={onLogout}>
      <div className="flex justify-center py-20"><Loader2 className="animate-spin text-slate-400" size={32} /></div>
    </Layout>;
  }

  const pageContent = (
    <div className="p-6 space-y-6 max-w-6xl mx-auto" data-testid="agency-content-distribution">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900" data-testid="content-dist-title">Icerik Dagitimi</h1>
          <p className="text-slate-500 text-sm mt-1">Otel bilgilerini duzenleyin ve sectiginiz acentelere gonderin</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleSaveContent} disabled={saving} data-testid="save-content-btn">
            {saving ? <Loader2 className="animate-spin mr-1" size={14} /> : <Save size={14} className="mr-1" />}
            Kaydet
          </Button>
          <Button onClick={handleDistribute} disabled={distributing} data-testid="distribute-btn" className="gap-2">
            {distributing ? <Loader2 className="animate-spin" size={14} /> : <Send size={14} />}
            Secili Acentelere Gonder
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Content Editor */}
        <div className="lg:col-span-2">
          <Tabs defaultValue="hotel" className="w-full">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="hotel" data-testid="tab-hotel">Otel Bilgileri</TabsTrigger>
              <TabsTrigger value="rooms" data-testid="tab-rooms">Oda Tipleri</TabsTrigger>
              <TabsTrigger value="services" data-testid="tab-services">Hizmetler</TabsTrigger>
            </TabsList>

            {/* Hotel Info Tab */}
            <TabsContent value="hotel" className="space-y-4 mt-4">
              <Card>
                <CardContent className="pt-6 space-y-4">
                  <div>
                    <Label>Otel Adi</Label>
                    <Input value={content?.hotel_name || ''} onChange={e => setContent(p => ({ ...p, hotel_name: e.target.value }))} data-testid="hotel-name-input" />
                  </div>
                  <div>
                    <Label>Aciklama</Label>
                    <Textarea rows={3} value={content?.description || ''} onChange={e => setContent(p => ({ ...p, description: e.target.value }))} placeholder="Otel hakkinda kisa tanitim..." />
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
                    <Label>Olanaklar (virgul ile ayirin)</Label>
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
              {(content?.room_types || []).map((rt, idx) => (
                <Card key={idx}>
                  <CardContent className="pt-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="font-medium text-sm text-slate-700 flex items-center gap-2"><Bed size={14} /> Oda Tipi {idx + 1}</h4>
                      <Button size="sm" variant="ghost" className="text-red-500 h-7" onClick={() => removeRoomType(idx)}>
                        <Trash2 size={13} />
                      </Button>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label className="text-xs">Tip Kodu</Label>
                        <Input value={rt.room_type} onChange={e => updateRoomType(idx, 'room_type', e.target.value)} placeholder="Standard" className="text-sm" />
                      </div>
                      <div>
                        <Label className="text-xs">Gorunen Ad</Label>
                        <Input value={rt.name || rt.room_type} onChange={e => updateRoomType(idx, 'name', e.target.value)} className="text-sm" />
                      </div>
                    </div>
                    <div>
                      <Label className="text-xs">Aciklama</Label>
                      <Textarea rows={2} value={rt.description} onChange={e => updateRoomType(idx, 'description', e.target.value)} className="text-sm" placeholder="Oda aciklamasi..." />
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
                      <Label className="text-xs">Oda Olanaklari (virgul ile)</Label>
                      <Input
                        value={(rt.amenities || []).join(', ')}
                        onChange={e => updateRoomType(idx, 'amenities', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                        className="text-sm" placeholder="WiFi, Minibar, Klima..."
                      />
                    </div>
                  </CardContent>
                </Card>
              ))}
              <Button variant="outline" onClick={addRoomType} className="w-full gap-2" data-testid="add-room-type-btn">
                <Plus size={14} /> Oda Tipi Ekle
              </Button>
            </TabsContent>

            {/* Services Tab */}
            <TabsContent value="services" className="space-y-3 mt-4">
              {(content?.services || []).map((svc, idx) => (
                <Card key={idx}>
                  <CardContent className="pt-4">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-medium text-sm text-slate-700">Hizmet {idx + 1}</h4>
                      <Button size="sm" variant="ghost" className="text-red-500 h-7" onClick={() => removeService(idx)}>
                        <Trash2 size={13} />
                      </Button>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label className="text-xs">Hizmet Adi</Label>
                        <Input value={svc.name} onChange={e => updateService(idx, 'name', e.target.value)} className="text-sm" placeholder="Havuz" />
                      </div>
                      <div>
                        <Label className="text-xs">Aciklama</Label>
                        <Input value={svc.description} onChange={e => updateService(idx, 'description', e.target.value)} className="text-sm" placeholder="Acik havuz, 08:00-20:00" />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
              <Button variant="outline" onClick={addService} className="w-full gap-2" data-testid="add-service-btn">
                <Plus size={14} /> Hizmet Ekle
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
                <Button size="sm" variant="outline" className="text-xs h-7" onClick={selectAllAgencies}>Tumunu Sec</Button>
                <Button size="sm" variant="outline" className="text-xs h-7" onClick={deselectAllAgencies}>Temizle</Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-2 max-h-[500px] overflow-y-auto">
              {agencies.filter(a => a.status === 'active').length === 0 ? (
                <p className="text-xs text-slate-400 text-center py-4">Aktif acente yok</p>
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
                      <div className="text-xs text-slate-400">{agency.contact_name || 'Yetkili belirtilmemis'}</div>
                    </div>
                    {agency.published_content && (
                      <Badge variant="outline" className="text-[10px] text-blue-500 border-blue-200 ml-auto flex-shrink-0">Yayinda</Badge>
                    )}
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <div className="mt-4 p-4 bg-slate-50 rounded-lg text-sm text-slate-500">
            <p className="font-medium text-slate-700 mb-1">Nasil calisir?</p>
            <ul className="space-y-1 text-xs">
              <li>1. Otel bilgilerini, oda tiplerini ve hizmetleri duzenleyin</li>
              <li>2. "Kaydet" ile icerigi kaydedin</li>
              <li>3. Sagdaki listeden acenteleri secin</li>
              <li>4. "Secili Acentelere Gonder" ile dagitimi yapin</li>
              <li>5. Secilen acenteler portallarinda bu icerigi gorur</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );

  return <Layout user={user} tenant={tenant} onLogout={onLogout}>{pageContent}</Layout>;
};

export default AgencyContentDistribution;
