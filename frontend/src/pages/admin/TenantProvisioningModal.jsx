import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Building2, CheckCircle2, KeyRound, Loader2, Network, ReceiptText, ShieldCheck } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';

const emptyNilveraSeller = {
  vkn: '', name: '', tax_office: '', address: '', city: '', country: 'Türkiye',
};

const TenantProvisioningModal = ({ open, onOpenChange, tenant, onSuccess }) => {
  const tenantId = tenant?.id || tenant?._id;
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState('');
  const [data, setData] = useState(null);
  const [chains, setChains] = useState([]);
  const [provider, setProvider] = useState('');
  const [chainId, setChainId] = useState('none');
  const [isHeadquarters, setIsHeadquarters] = useState(false);
  const [newChainName, setNewChainName] = useState('');
  const [credentials, setCredentials] = useState({});
  const [nilveraEnabled, setNilveraEnabled] = useState(false);
  const [nilveraApiKey, setNilveraApiKey] = useState('');
  const [nilveraSeller, setNilveraSeller] = useState(emptyNilveraSeller);

  const selectedProvider = useMemo(
    () => data?.providers?.find((item) => item.provider === provider),
    [data, provider],
  );

  const load = async () => {
    if (!tenantId) return;
    setLoading(true);
    try {
      const [provisioningRes, chainsRes] = await Promise.all([
        axios.get(`/admin/tenants/${tenantId}/provisioning`),
        axios.get('/admin/chains'),
      ]);
      const next = provisioningRes.data;
      setData(next);
      setChains(chainsRes.data?.chains || []);
      setProvider(next.tenant?.channel_manager_provider || '');
      setChainId(next.tenant?.chain_id || 'none');
      setIsHeadquarters(!!next.tenant?.is_chain_headquarters);
      setNilveraEnabled(!!next.nilvera?.enabled);
      setNilveraSeller({ ...emptyNilveraSeller, ...(next.nilvera?.seller || {}) });
      setCredentials({});
      setNilveraApiKey('');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Kurulum bilgileri yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, tenantId]);

  const saveScope = async () => {
    setSaving('scope');
    try {
      await axios.patch(`/admin/tenants/${tenantId}/provisioning`, {
        channel_manager_provider: provider || null,
        chain_id: chainId === 'none' ? null : chainId,
        is_chain_headquarters: chainId === 'none' ? false : isHeadquarters,
      });
      toast.success('Otel kurulum kapsamı kaydedildi');
      await load();
      onSuccess?.();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Kurulum kapsamı kaydedilemedi');
    } finally {
      setSaving('');
    }
  };

  const createChain = async () => {
    if (newChainName.trim().length < 2) {
      toast.error('Zincir adı en az 2 karakter olmalıdır');
      return;
    }
    setSaving('chain');
    try {
      const response = await axios.post('/admin/chains', {
        name: newChainName.trim(),
        headquarters_tenant_id: tenantId,
      });
      const chain = response.data.chain;
      setChains((current) => [...current, { ...chain, property_count: 1 }]);
      setChainId(chain.id);
      setIsHeadquarters(true);
      setNewChainName('');
      toast.success('Zincir oluşturuldu ve bu otel merkez olarak bağlandı');
      await load();
      onSuccess?.();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Zincir oluşturulamadı');
    } finally {
      setSaving('');
    }
  };

  const saveProviderCredentials = async () => {
    if (!provider) {
      toast.error('Önce Exely veya HotelRunner seçin');
      return;
    }
    setSaving('provider');
    try {
      await axios.post(`/admin/tenants/${tenantId}/integrations/${provider}/credentials`, { credentials });
      toast.success('Kimlik bilgileri şifreli kaydedildi; bağlantı testi çalıştırılmadı');
      setCredentials({});
      await load();
      onSuccess?.();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Kimlik bilgileri kaydedilemedi');
    } finally {
      setSaving('');
    }
  };

  const saveNilvera = async () => {
    setSaving('nilvera');
    try {
      const payload = { enabled: nilveraEnabled };
      if (nilveraApiKey.trim()) payload.api_key = nilveraApiKey.trim();
      const sellerRequiredKeys = ['vkn', 'name', 'tax_office', 'address', 'city'];
      const sellerStarted = sellerRequiredKeys.some((key) => String(nilveraSeller[key] || '').trim());
      if (sellerStarted) {
        payload.seller = nilveraSeller;
      }
      await axios.put(`/admin/tenants/${tenantId}/integrations/nilvera`, payload);
      toast.success('Nilvera ayarları şifreli kaydedildi; dış servis çağrısı yapılmadı');
      setNilveraApiKey('');
      await load();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Nilvera ayarları kaydedilemedi');
    } finally {
      setSaving('');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[92vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-indigo-600" />
            Otel Kurulumu · {tenant?.property_name || 'Otel'}
          </DialogTitle>
        </DialogHeader>

        {loading && !data ? (
          <div className="py-16 flex items-center justify-center text-slate-500">
            <Loader2 className="w-5 h-5 mr-2 animate-spin" /> Kurulum bilgileri yükleniyor
          </div>
        ) : (
          <div className="space-y-5">
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs text-blue-800">
              Bu panel yalnızca ayarları ve şifreli sırları kaydeder. Provider bağlantı testi, veri çekme veya production senkronizasyonu başlatmaz.
            </div>

            <section className="rounded-xl border p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Network className="w-4 h-4 text-indigo-600" />
                <h3 className="font-semibold text-slate-900">Zincir otel yapısı</h3>
              </div>
              <div className="grid md:grid-cols-2 gap-3">
                <div>
                  <Label>Bağlı zincir</Label>
                  <select
                    className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
                    value={chainId}
                    onChange={(event) => {
                      setChainId(event.target.value);
                      if (event.target.value === 'none') setIsHeadquarters(false);
                    }}
                  >
                    <option value="none">Bağımsız otel</option>
                    {chains.map((chain) => (
                      <option key={chain.id} value={chain.id}>{chain.name} ({chain.property_count || 0} otel)</option>
                    ))}
                  </select>
                </div>
                <div className="flex items-end gap-2">
                  <Input value={newChainName} onChange={(event) => setNewChainName(event.target.value)} placeholder="Yeni zincir adı" />
                  <Button variant="outline" onClick={createChain} disabled={saving === 'chain'}>
                    {saving === 'chain' ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Zincir oluştur'}
                  </Button>
                </div>
              </div>
              <div className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
                <div>
                  <p className="text-sm font-medium">Zincir merkezi</p>
                  <p className="text-xs text-slate-500">Bu tesis zincirin ana yönetim oteli olarak işaretlenir.</p>
                </div>
                <Switch checked={isHeadquarters} disabled={chainId === 'none'} onCheckedChange={setIsHeadquarters} />
              </div>
            </section>

            <section className="rounded-xl border p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Building2 className="w-4 h-4 text-cyan-600" />
                <h3 className="font-semibold text-slate-900">Kanal yöneticisi</h3>
              </div>
              <div className="grid md:grid-cols-2 gap-3">
                <div>
                  <Label>Altyapı</Label>
                  <select
                    data-testid="provisioning-provider"
                    className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
                    value={provider}
                    onChange={(event) => { setProvider(event.target.value); setCredentials({}); }}
                  >
                    <option value="">Otomatik / henüz seçilmedi</option>
                    <option value="exely">Exely</option>
                    <option value="hotelrunner">HotelRunner</option>
                  </select>
                </div>
                <div className="flex items-end">
                  {selectedProvider?.has_credentials ? (
                    <span className="inline-flex items-center gap-1 text-sm text-emerald-700"><CheckCircle2 className="w-4 h-4" /> Şifreli bilgiler kayıtlı</span>
                  ) : <span className="text-sm text-amber-700">Kimlik bilgileri bekleniyor</span>}
                </div>
              </div>
              {selectedProvider && (
                <div className="grid md:grid-cols-2 gap-3 rounded-lg bg-slate-50 p-3">
                  {selectedProvider.fields.map((field) => (
                    <div key={field.key}>
                      <Label>{field.label}{field.required ? ' *' : ''}</Label>
                      <Input
                        className="mt-1"
                        type={field.type === 'password' ? 'password' : 'text'}
                        autoComplete="new-password"
                        value={credentials[field.key] || ''}
                        placeholder={selectedProvider.credentials?.fields?.[field.key] || ''}
                        onChange={(event) => setCredentials((current) => ({ ...current, [field.key]: event.target.value }))}
                      />
                    </div>
                  ))}
                  <div className="md:col-span-2 flex justify-end">
                    <Button onClick={saveProviderCredentials} disabled={saving === 'provider'}>
                      <KeyRound className="w-4 h-4 mr-1.5" />
                      {saving === 'provider' ? 'Şifreleniyor...' : 'Kimlik bilgilerini kaydet'}
                    </Button>
                  </div>
                </div>
              )}
            </section>

            <section className="rounded-xl border p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ReceiptText className="w-4 h-4 text-emerald-600" />
                  <div><h3 className="font-semibold text-slate-900">Nilvera e-Belge</h3><p className="text-xs text-slate-500">API anahtarı ekranda hiçbir zaman geri gösterilmez.</p></div>
                </div>
                <Switch checked={nilveraEnabled} onCheckedChange={setNilveraEnabled} />
              </div>
              <div className="grid md:grid-cols-3 gap-3">
                <div className="md:col-span-3">
                  <Label>API Anahtarı {data?.nilvera?.api_key_set && '(kayıtlı — değiştirmek için yenisini girin)'}</Label>
                  <Input className="mt-1" type="password" autoComplete="new-password" value={nilveraApiKey} onChange={(event) => setNilveraApiKey(event.target.value)} />
                </div>
                {[
                  ['vkn', 'VKN/TCKN'], ['name', 'Firma unvanı'], ['tax_office', 'Vergi dairesi'],
                  ['address', 'Adres'], ['city', 'Şehir'], ['country', 'Ülke'],
                ].map(([key, label]) => (
                  <div key={key}>
                    <Label>{label}</Label>
                    <Input className="mt-1" value={nilveraSeller[key]} onChange={(event) => setNilveraSeller((current) => ({ ...current, [key]: event.target.value }))} />
                  </div>
                ))}
              </div>
              <div className="flex justify-end">
                <Button variant="outline" onClick={saveNilvera} disabled={saving === 'nilvera'}>
                  {saving === 'nilvera' ? 'Kaydediliyor...' : 'Nilvera ayarlarını kaydet'}
                </Button>
              </div>
            </section>

            <div className="flex justify-end gap-2 border-t pt-4">
              <Button variant="outline" onClick={() => onOpenChange(false)}>Kapat</Button>
              <Button onClick={saveScope} disabled={saving === 'scope'} data-testid="save-provisioning-scope">
                {saving === 'scope' ? 'Kaydediliyor...' : 'Zincir ve sağlayıcı seçimini kaydet'}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default TenantProvisioningModal;
