import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { api } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Switch } from '../components/ui/switch';

import { Skeleton } from '../components/ui/skeleton';
import { Settings, Shield, Clock, Loader2, RefreshCcw, AlertTriangle } from 'lucide-react';

export default function SettingsPage() {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [cleanupResult, setCleanupResult] = useState(null);

  useEffect(() => { loadSettings(); }, []);

  const loadSettings = async () => {
    try {
      const data = await api.getKvkkSettings();
      setSettings(data.settings);
    } catch (err) { toast.error('Ayarlar yüklenemedi'); }
    finally { setLoading(false); }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const result = await api.updateKvkkSettings(settings);
      setSettings(result.settings);
      toast.success('Ayarlar kaydedildi');
    } catch (err) { toast.error('Kaydetme hatası'); }
    finally { setSaving(false); }
  };

  const handleCleanup = async () => {
    if (!window.confirm('Eski verileri temizlemek istediğinize emin misiniz?')) return;
    setCleaning(true);
    try {
      const result = await api.triggerCleanup();
      setCleanupResult(result.results);
      toast.success('Temizlik tamamlandı');
    } catch (err) { toast.error('Temizlik hatası'); }
    finally { setCleaning(false); }
  };

  const updateField = (key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-[var(--brand-ink)]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>Ayarlar & KVKK</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Veri saklama politikaları ve KVKK uyumu</p>
        </div>
        <Button onClick={handleSave} disabled={saving} className="bg-[var(--brand-sky)] hover:bg-[#094C6E] text-white" data-testid="save-settings-button">
          {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Settings className="w-4 h-4 mr-2" />}
          Ayarları Kaydet
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* KVKK Settings */}
        <Card className="bg-white">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Shield className="w-4 h-4 text-[var(--brand-sky)]" />
              KVKK Ayarları
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <Label className="text-sm font-medium">KVKK Onayı Zorunlu</Label>
                <p className="text-xs text-muted-foreground">Tarama öncesi misafirden onay alınsın mı?</p>
              </div>
              <Switch
                checked={settings?.kvkk_consent_required || false}
                onCheckedChange={v => updateField('kvkk_consent_required', v)}
                data-testid="kvkk-consent-toggle"
              />
            </div>

            <div className="space-y-1.5">
              <Label className="text-sm">KVKK Bilgilendirme Metni</Label>
              <Textarea
                value={settings?.kvkk_consent_text || ''}
                onChange={e => updateField('kvkk_consent_text', e.target.value)}
                rows={4}
                className="text-xs"
              />
            </div>

            <div className="space-y-1.5">
              <Label className="text-sm">Veri İşleme Amacı</Label>
              <Textarea
                value={settings?.data_processing_purpose || ''}
                onChange={e => updateField('data_processing_purpose', e.target.value)}
                rows={2}
                className="text-xs"
              />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <Label className="text-sm font-medium">Görüntü Saklama</Label>
                <p className="text-xs text-muted-foreground">Tarama görüntülerini sunucuda sakla</p>
              </div>
              <Switch
                checked={settings?.store_scan_images || false}
                onCheckedChange={v => updateField('store_scan_images', v)}
              />
            </div>
          </CardContent>
        </Card>

        {/* Retention Settings */}
        <Card className="bg-white">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Clock className="w-4 h-4 text-[var(--brand-warning)]" />
              Veri Saklama Süreleri
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <Label className="text-sm font-medium">Otomatik Temizlik</Label>
                <p className="text-xs text-muted-foreground">Süresi dolan verileri otomatik sil</p>
              </div>
              <Switch
                checked={settings?.auto_cleanup_enabled || false}
                onCheckedChange={v => updateField('auto_cleanup_enabled', v)}
              />
            </div>

            <div className="space-y-1.5">
              <Label className="text-sm">Tarama Verisi Saklama Süresi (gün)</Label>
              <Input
                type="number"
                min="1"
                value={settings?.retention_days_scans || 90}
                onChange={e => updateField('retention_days_scans', parseInt(e.target.value) || 90)}
              />
              <p className="text-[10px] text-muted-foreground">{settings?.retention_days_scans || 90} gün sonra tarama verileri silinir</p>
            </div>

            <div className="space-y-1.5">
              <Label className="text-sm">Denetim Kaydı Saklama Süresi (gün)</Label>
              <Input
                type="number"
                min="1"
                value={settings?.retention_days_audit || 365}
                onChange={e => updateField('retention_days_audit', parseInt(e.target.value) || 365)}
              />
              <p className="text-[10px] text-muted-foreground">{settings?.retention_days_audit || 365} gün sonra denetim kayıtları silinir</p>
            </div>

            {/* Manual Cleanup */}
            <div className="pt-3 border-t border-[hsl(var(--border))]">
              <Button variant="outline" onClick={handleCleanup} disabled={cleaning} className="w-full" data-testid="run-cleanup-button">
                {cleaning ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCcw className="w-4 h-4 mr-2" />}
                Manuel Temizlik Çalıştır
              </Button>
              {cleanupResult && (
                <div className="mt-2 p-2 rounded bg-[hsl(var(--secondary))] text-xs">
                  <p>Silinen tarama: {cleanupResult.scans_deleted}</p>
                  <p>Silinen denetim kaydı: {cleanupResult.audit_deleted}</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* KVKK Info */}
      <Card className="bg-white border-[var(--brand-warning)] border">
        <CardContent className="p-4">
          <div className="flex gap-3">
            <AlertTriangle className="w-5 h-5 text-[var(--brand-warning)] shrink-0 mt-0.5" />
            <div>
              <h3 className="text-sm font-semibold text-[var(--brand-ink)] mb-1">KVKK Uyum Bilgisi</h3>
              <ul className="text-xs text-muted-foreground space-y-1">
                <li>Misafir verileri yalnızca konaklama işlemleri için işlenir (6698 sayılı KVKK).</li>
                <li>Veriler belirlenen saklama süresi sonunda otomatik silinir.</li>
                <li>Misafir "Unutulma Hakkı" kapsamında verilerinin anonimleştirilmesini talep edebilir.</li>
                <li>Tüm veri işleme aktiviteleri denetim izinde kayıt altına alınır.</li>
                <li>Görüntü saklama kapatılarak yalnızca metin verisi işlenebilir.</li>
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
