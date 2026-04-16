import { useState, useEffect } from 'react';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Building2, Plus, MapPin, Phone, Hash, Loader2, CheckCircle, XCircle, QrCode, Smartphone } from 'lucide-react';

export default function PropertiesPage() {
  const [tab, setTab] = useState('properties');
  const [properties, setProperties] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', address: '', phone: '', tax_no: '', city: '' });
  const [creating, setCreating] = useState(false);
  
  // Pre-checkin
  const [preCheckins, setPreCheckins] = useState([]);
  const [loadingPreCheckins, setLoadingPreCheckins] = useState(false);
  const [showCreatePreCheckin, setShowCreatePreCheckin] = useState(false);
  const [preCheckinForm, setPreCheckinForm] = useState({ property_id: '', reservation_ref: '', guest_name: '' });
  const [creatingPreCheckin, setCreatingPreCheckin] = useState(false);
  const [selectedQr, setSelectedQr] = useState(null);

  useEffect(() => { loadProperties(); }, []);
  useEffect(() => { if (tab === 'precheckin') loadPreCheckins(); }, [tab]);

  const loadProperties = async () => {
    try {
      const res = await api.getProperties();
      setProperties(res.properties || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const createPropertyHandler = async () => {
    if (!form.name.trim()) return;
    setCreating(true);
    try {
      await api.createProperty(form);
      setShowCreate(false);
      setForm({ name: '', address: '', phone: '', tax_no: '', city: '' });
      loadProperties();
    } catch (err) {
      alert(err.message);
    } finally {
      setCreating(false);
    }
  };

  const loadPreCheckins = async () => {
    setLoadingPreCheckins(true);
    try {
      const res = await api.listPreCheckins();
      setPreCheckins(res.tokens || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingPreCheckins(false);
    }
  };

  const createPreCheckinHandler = async () => {
    if (!preCheckinForm.property_id) {
      alert('Lütfen bir tesis seçin');
      return;
    }
    setCreatingPreCheckin(true);
    try {
      const res = await api.createPreCheckin(preCheckinForm);
      if (res.success) {
        setShowCreatePreCheckin(false);
        setPreCheckinForm({ property_id: '', reservation_ref: '', guest_name: '' });
        loadPreCheckins();
        // Show QR immediately
        setSelectedQr(res.token);
      }
    } catch (err) {
      alert(err.message);
    } finally {
      setCreatingPreCheckin(false);
    }
  };

  const PropertyCard = ({ prop }) => (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="pt-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-blue-50 flex items-center justify-center">
              <Building2 className="w-6 h-6 text-blue-500" />
            </div>
            <div>
              <h3 className="font-semibold">{prop.name}</h3>
              {prop.city && <p className="text-sm text-gray-500 flex items-center gap-1"><MapPin className="w-3 h-3" />{prop.city}</p>}
            </div>
          </div>
          <Badge variant={prop.is_active ? 'default' : 'secondary'}>
            {prop.is_active ? 'Aktif' : 'Pasif'}
          </Badge>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2 text-sm text-gray-600">
          {prop.address && <p className="flex items-center gap-1"><MapPin className="w-3 h-3" />{prop.address}</p>}
          {prop.phone && <p className="flex items-center gap-1"><Phone className="w-3 h-3" />{prop.phone}</p>}
          {prop.tax_no && <p className="flex items-center gap-1"><Hash className="w-3 h-3" />{prop.tax_no}</p>}
        </div>
        {prop.settings && (
          <div className="mt-3 flex flex-wrap gap-2">
            <Badge variant="outline" className={prop.settings.kiosk_enabled ? 'text-green-600' : 'text-gray-400'}>
              {prop.settings.kiosk_enabled ? <CheckCircle className="w-3 h-3 mr-1" /> : <XCircle className="w-3 h-3 mr-1" />}
              Kiosk
            </Badge>
            <Badge variant="outline" className={prop.settings.pre_checkin_enabled ? 'text-green-600' : 'text-gray-400'}>
              {prop.settings.pre_checkin_enabled ? <CheckCircle className="w-3 h-3 mr-1" /> : <XCircle className="w-3 h-3 mr-1" />}
              Ön Check-in
            </Badge>
            <Badge variant="outline" className={prop.settings.face_matching_enabled ? 'text-green-600' : 'text-gray-400'}>
              {prop.settings.face_matching_enabled ? <CheckCircle className="w-3 h-3 mr-1" /> : <XCircle className="w-3 h-3 mr-1" />}
              Yüz Eşleştirme
            </Badge>
          </div>
        )}
      </CardContent>
    </Card>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Tesis Yönetimi</h1>
          <p className="text-gray-500 mt-1">Çoklu tesis, ön check-in QR kodları</p>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="grid grid-cols-2 w-full max-w-md">
          <TabsTrigger value="properties"><Building2 className="w-4 h-4 mr-2" />Tesisler</TabsTrigger>
          <TabsTrigger value="precheckin"><QrCode className="w-4 h-4 mr-2" />Ön Check-in</TabsTrigger>
        </TabsList>

        {/* Properties Tab */}
        <TabsContent value="properties" className="space-y-4">
          <div className="flex justify-end">
            <Dialog open={showCreate} onOpenChange={setShowCreate}>
              <DialogTrigger asChild>
                <Button><Plus className="w-4 h-4 mr-2" />Yeni Tesis</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Yeni Tesis Ekle</DialogTitle>
                </DialogHeader>
                <div className="space-y-3">
                  <Input placeholder="Tesis Adı *" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                  <Input placeholder="Şehir" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} />
                  <Input placeholder="Adres" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
                  <Input placeholder="Telefon" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
                  <Input placeholder="Vergi No" value={form.tax_no} onChange={(e) => setForm({ ...form, tax_no: e.target.value })} />
                  <Button onClick={createPropertyHandler} disabled={creating || !form.name.trim()} className="w-full">
                    {creating ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
                    Oluştur
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>

          {loading ? (
            <div className="flex justify-center py-12"><Loader2 className="w-8 h-8 animate-spin text-gray-400" /></div>
          ) : properties.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center">
                <Building2 className="w-12 h-12 text-gray-300 mx-auto mb-4" />
                <h3 className="font-semibold text-gray-600 mb-2">Henüz tesis eklenmemiş</h3>
                <p className="text-sm text-gray-400 mb-4">İlk tesinizi ekleyerek çoklu tesis yönetimine başlayın</p>
                <Button onClick={() => setShowCreate(true)}><Plus className="w-4 h-4 mr-2" />Tesis Ekle</Button>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {properties.map((prop) => <PropertyCard key={prop.property_id || prop.id} prop={prop} />)}
            </div>
          )}
        </TabsContent>

        {/* Pre-Checkin Tab */}
        <TabsContent value="precheckin" className="space-y-4">
          <div className="flex justify-end">
            <Dialog open={showCreatePreCheckin} onOpenChange={setShowCreatePreCheckin}>
              <DialogTrigger asChild>
                <Button><QrCode className="w-4 h-4 mr-2" />Yeni QR Oluştur</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Ön Check-in QR Kodu</DialogTitle>
                </DialogHeader>
                <div className="space-y-3">
                  <div>
                    <label className="text-sm font-medium mb-1 block">Tesis *</label>
                    <select 
                      className="w-full border rounded-md p-2 text-sm"
                      value={preCheckinForm.property_id}
                      onChange={(e) => setPreCheckinForm({ ...preCheckinForm, property_id: e.target.value })}
                    >
                      <option value="">Tesis Seçin</option>
                      {properties.map(p => (
                        <option key={p.property_id || p.id} value={p.property_id}>{p.name}</option>
                      ))}
                    </select>
                  </div>
                  <Input placeholder="Misafir Adı" value={preCheckinForm.guest_name} onChange={(e) => setPreCheckinForm({ ...preCheckinForm, guest_name: e.target.value })} />
                  <Input placeholder="Rezervasyon Ref" value={preCheckinForm.reservation_ref} onChange={(e) => setPreCheckinForm({ ...preCheckinForm, reservation_ref: e.target.value })} />
                  <Button onClick={createPreCheckinHandler} disabled={creatingPreCheckin || !preCheckinForm.property_id} className="w-full">
                    {creatingPreCheckin ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <QrCode className="w-4 h-4 mr-2" />}
                    QR Kod Oluştur
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>

          {loadingPreCheckins ? (
            <div className="flex justify-center py-12"><Loader2 className="w-8 h-8 animate-spin text-gray-400" /></div>
          ) : preCheckins.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center">
                <Smartphone className="w-12 h-12 text-gray-300 mx-auto mb-4" />
                <h3 className="font-semibold text-gray-600 mb-2">Ön check-in QR kodu yok</h3>
                <p className="text-sm text-gray-400 mb-4">Misafirleriniz için QR kod oluşturarak telefondan kimlik taramasına başlayın</p>
                <Button onClick={() => setShowCreatePreCheckin(true)}><QrCode className="w-4 h-4 mr-2" />QR Oluştur</Button>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-2">
              {preCheckins.map((token) => (
                <Card key={token.token_id || token.id} className="hover:shadow-sm transition-shadow">
                  <CardContent className="pt-4 flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="font-medium">{token.guest_name || 'İsimsiz'}</p>
                        <Badge variant={token.status === 'active' ? 'default' : token.status === 'used' ? 'secondary' : 'outline'}>
                          {token.status === 'active' ? 'Aktif' : token.status === 'used' ? 'Kullanıldı' : token.status}
                        </Badge>
                      </div>
                      <div className="flex gap-2 text-xs text-gray-500 mt-1">
                        {token.reservation_ref && <span>Rez: {token.reservation_ref}</span>}
                        <span>{new Date(token.created_at).toLocaleDateString('tr-TR')}</span>
                      </div>
                    </div>
                    <Button size="sm" variant="outline" onClick={() => setSelectedQr(token)}>
                      <QrCode className="w-4 h-4 mr-1" />QR Göster
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* QR Code Dialog */}
      <Dialog open={!!selectedQr} onOpenChange={() => setSelectedQr(null)}>
        <DialogContent className="max-w-sm text-center">
          <DialogHeader>
            <DialogTitle>QR Kod</DialogTitle>
          </DialogHeader>
          {selectedQr && (
            <div className="space-y-4">
              <div className="bg-white p-4 rounded-lg inline-block mx-auto border">
                <img 
                  src={api.getPreCheckinQrUrl(selectedQr.token_id)} 
                  alt="QR Code" 
                  className="w-64 h-64 mx-auto"
                  onError={(e) => { e.target.style.display = 'none'; }}
                />
              </div>
              <div className="text-sm text-gray-600">
                {selectedQr.guest_name && <p>Misafir: <strong>{selectedQr.guest_name}</strong></p>}
                {selectedQr.reservation_ref && <p>Rezervasyon: <strong>{selectedQr.reservation_ref}</strong></p>}
              </div>
              <p className="text-xs text-gray-400">Bu QR kodu misafirin telefonuyla taratarak ön check-in yapabilir</p>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
