import { useEffect, useState, useCallback } from 'react';
import api from '@/api/axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { PageHeader } from '@/components/ui/page-header';
import { Loader2, Plus, Trash2, Save, Clock, RefreshCw, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { confirmDialog } from '@/lib/dialogs';
import { formatCurrency } from '@/lib/currency';
import { useTranslation } from 'react-i18next';
const CHARGE_TYPES = [{
  v: 'flat',
  l: 'Sabit Tutar'
}, {
  v: 'percent_of_nightly',
  l: 'Gecelik %'
}, {
  v: 'percent_of_total',
  l: 'Toplam %'
}, {
  v: 'free',
  l: 'Ücretsiz'
}];
const TENANT_CURRENCY = 'TRY';
const blank = (label = '') => ({
  id: '',
  label,
  from_hour: 8,
  to_hour: 12,
  charge_type: 'percent_of_nightly',
  charge_value: 50
});
const clampHour = (n, fallback) => {
  const v = parseInt(n);
  if (isNaN(v)) return fallback;
  return Math.max(0, Math.min(23, v));
};
const fmtRange = r => `${String(r.from_hour).padStart(2, '0')}:00–${String(r.to_hour).padStart(2, '0')}:00`;
const valueLabel = r => {
  if (r.charge_type === 'free') return 'Ücretsiz';
  if (r.charge_type === 'flat') return formatCurrency(r.charge_value, TENANT_CURRENCY);
  return `%${r.charge_value}`;
};
function detectIssues(rules, sectionName) {
  const issues = [];
  if (!rules || rules.length === 0) return issues;
  const sorted = [...rules].sort((a, b) => a.from_hour - b.from_hour || a.to_hour - b.to_hour);
  for (const r of sorted) {
    if (r.from_hour >= r.to_hour) issues.push(`${sectionName}: '${r.label || '?'}' başlangıç < bitiş olmalı`);
  }
  for (let i = 0; i < sorted.length - 1; i++) {
    if (sorted[i].to_hour > sorted[i + 1].from_hour) {
      issues.push(`${sectionName}: '${sorted[i].label}' ile '${sorted[i + 1].label}' çakışıyor`);
    } else if (sorted[i].to_hour < sorted[i + 1].from_hour) {
      issues.push(`${sectionName}: '${sorted[i].label}' ile '${sorted[i + 1].label}' arasında ${sorted[i].to_hour}–${sorted[i + 1].from_hour} boşluk var`);
    }
  }
  return issues;
}
function RuleEditor({
  title,
  rules,
  setRules,
  onDelete
}) {
  const { t, i18n } = useTranslation();
  return <Card className="p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold flex items-center gap-2 text-slate-900">
          <Clock className="w-4 h-4 text-slate-500" /> {title}
        </h2>
        <Button size="sm" variant="outline" onClick={() => setRules([...rules, blank()])}>
          <Plus className="w-3.5 h-3.5 mr-1" /> {t('cm.pages_EarlyLatePricingSettings.kural_ekle')}
        </Button>
      </div>
      {rules.length === 0 && <div className="text-sm text-slate-400 py-6 text-center border border-dashed rounded">
          {t('cm.pages_EarlyLatePricingSettings.henuz_kural_yok_kural_ekle_ile_baslayin')}
        </div>}
      <div className="space-y-2">
        {rules.map((r, i) => <div key={r.id || i} className="grid grid-cols-12 gap-2 items-end border rounded p-2 bg-white">
            <div className="col-span-3">
              <Label className="text-[10px] text-slate-500">Etiket</Label>
              <Input value={r.label} placeholder={fmtRange(r)} onChange={e => {
            const c = [...rules];
            c[i] = {
              ...r,
              label: e.target.value
            };
            setRules(c);
          }} className="h-8" />
            </div>
            <div className="col-span-2">
              <Label className="text-[10px] text-slate-500">{t('cm.pages_EarlyLatePricingSettings.baslangic_saat')}</Label>
              <Input type="number" min={0} max={23} value={r.from_hour} onChange={e => {
            const c = [...rules];
            c[i] = {
              ...r,
              from_hour: clampHour(e.target.value, 0)
            };
            setRules(c);
          }} className="h-8" />
            </div>
            <div className="col-span-2">
              <Label className="text-[10px] text-slate-500">{t('cm.pages_EarlyLatePricingSettings.bitis_saat')}</Label>
              <Input type="number" min={0} max={23} value={r.to_hour} onChange={e => {
            const c = [...rules];
            c[i] = {
              ...r,
              to_hour: clampHour(e.target.value, 0)
            };
            setRules(c);
          }} className="h-8" />
            </div>
            <div className="col-span-2">
              <Label className="text-[10px] text-slate-500">{t('cm.pages_EarlyLatePricingSettings.ucret_tipi')}</Label>
              <Select value={r.charge_type} onValueChange={v => {
            const c = [...rules];
            c[i] = {
              ...r,
              charge_type: v
            };
            setRules(c);
          }}>
                <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
                <SelectContent>{CHARGE_TYPES.map(t => <SelectItem key={t.v} value={t.v}>{t.l}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="col-span-2">
              <Label className="text-[10px] text-slate-500">
                {t('cm.pages_EarlyLatePricingSettings.deger')} {r.charge_type === 'flat' ? `(${TENANT_CURRENCY})` : r.charge_type.startsWith('percent') ? '(%)' : ''}
              </Label>
              <Input type="number" min={0} value={r.charge_value} onChange={e => {
            const c = [...rules];
            c[i] = {
              ...r,
              charge_value: parseFloat(e.target.value) || 0
            };
            setRules(c);
          }} className="h-8" disabled={r.charge_type === 'free'} />
            </div>
            <div className="col-span-1 flex justify-end">
              <Button size="icon" variant="ghost" className="h-8 w-8 text-rose-600 hover:text-rose-700 hover:bg-rose-50" onClick={async () => {
            const ok = await confirmDialog({
              message: `'${r.label || fmtRange(r)}' kuralını silmek istiyor musunuz?`,
              confirmText: 'Sil',
              cancelText: 'Vazgeç'
            });
            if (ok) onDelete(i);
          }} title={t('cm.pages_EarlyLatePricingSettings.sil')}>
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            </div>
          </div>)}
      </div>
    </Card>;
}
export default function EarlyLatePricingSettings() {
  const { t, i18n } = useTranslation();
  const [cfg, setCfg] = useState(null);
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const {
        data
      } = await api.get('/pms/settings/early-late-pricing');
      const {
        _meta,
        ...rest
      } = data || {};
      setCfg(rest);
      setMeta(_meta || null);
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || 'Bilinmeyen hata';
      setError(msg);
      toast.error('Yükleme hatası: ' + msg);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  const issues = cfg ? [...detectIssues(cfg.early_checkin, 'Erken Giriş'), ...detectIssues(cfg.late_checkout, 'Geç Çıkış')] : [];
  const save = async () => {
    if (issues.length > 0) {
      const ok = await confirmDialog({
        message: `${issues.length} doğrulama uyarısı var. Yine de kaydetmek istiyor musunuz? Backend reddedebilir.`,
        confirmText: 'Yine de Kaydet',
        cancelText: 'Vazgeç'
      });
      if (!ok) return;
    }
    setSaving(true);
    try {
      const {
        data
      } = await api.put('/pms/settings/early-late-pricing', cfg);
      const {
        _meta,
        ...rest
      } = data || {};
      setCfg(rest);
      setMeta(_meta || null);
      toast.success('Kurallar kaydedildi');
    } catch (e) {
      toast.error('Hata: ' + (e.response?.data?.detail || e.message));
    } finally {
      setSaving(false);
    }
  };
  if (loading) {
    return <div className="p-12 text-center">
        <Loader2 className="inline w-6 h-6 animate-spin text-slate-400" />
      </div>;
  }
  if (error || !cfg) {
    return <div className="p-6 max-w-3xl mx-auto">
        <Card className="p-6 text-center">
          <AlertCircle className="w-10 h-10 text-rose-500 mx-auto mb-3" />
          <div className="font-semibold text-slate-900 mb-1">{t('cm.pages_EarlyLatePricingSettings.kurallar_yuklenemedi')}</div>
          <div className="text-sm text-slate-500 mb-4">{error || 'Bilinmeyen hata'}</div>
          <Button onClick={load} variant="outline">
            <RefreshCw className="w-4 h-4 mr-1.5" /> Tekrar Dene
          </Button>
        </Card>
      </div>;
  }
  return <div className="p-6 max-w-6xl mx-auto space-y-4" data-testid="early-late-pricing-settings">
      <PageHeader icon={Clock} title={t('cm.pages_EarlyLatePricingSettings.erken_giris_gec_cikis_ucretleri')} subtitle={`Saat-bazlı otomatik ek ücret kuralları. Para birimi: ${TENANT_CURRENCY}.`} actions={<div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={load} disabled={loading || saving}>
              <RefreshCw className="w-4 h-4 mr-1.5" /> {t('cm.pages_EarlyLatePricingSettings.yenile')}
            </Button>
            <Button onClick={save} disabled={saving} size="sm">
              {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
              {t('cm.pages_EarlyLatePricingSettings.kaydet')}
            </Button>
          </div>} />

      {meta && <div className="text-xs text-slate-500">
          {meta.is_default ? 'Varsayılan kurallar gösteriliyor (henüz kaydedilmemiş).' : <>{t('cm.pages_EarlyLatePricingSettings.son_guncelleme')} {meta.updated_at ? new Date(meta.updated_at).toLocaleString(i18n.language) : '—'} {meta.updated_by_name ? `· ${meta.updated_by_name}` : ''}</>}
        </div>}

      {issues.length > 0 && <Card className="p-3 border-amber-200 bg-amber-50">
          <div className="flex items-start gap-2 text-sm text-amber-900">
            <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <div>
              <div className="font-semibold mb-1">{issues.length} {t('cm.pages_EarlyLatePricingSettings.uyari')}</div>
              <ul className="list-disc ml-5 space-y-0.5">
                {issues.map((m, i) => <li key={m.id || i}>{m}</li>)}
              </ul>
            </div>
          </div>
        </Card>}

      <Card className="p-4 grid grid-cols-2 gap-4">
        <div>
          <Label className="text-xs text-slate-500">{t('cm.pages_EarlyLatePricingSettings.standart_giris_saati_0_23')}</Label>
          <Input type="number" min={0} max={23} value={cfg.standard_checkin_hour} onChange={e => setCfg({
          ...cfg,
          standard_checkin_hour: clampHour(e.target.value, 14)
        })} className="h-9" />
        </div>
        <div>
          <Label className="text-xs text-slate-500">{t('cm.pages_EarlyLatePricingSettings.standart_cikis_saati_0_23')}</Label>
          <Input type="number" min={0} max={23} value={cfg.standard_checkout_hour} onChange={e => setCfg({
          ...cfg,
          standard_checkout_hour: clampHour(e.target.value, 12)
        })} className="h-9" />
        </div>
      </Card>

      <RuleEditor title={t('cm.pages_EarlyLatePricingSettings.erken_giris_kurallari')} rules={cfg.early_checkin} setRules={r => setCfg({
      ...cfg,
      early_checkin: r
    })} onDelete={i => setCfg({
      ...cfg,
      early_checkin: cfg.early_checkin.filter((_, j) => j !== i)
    })} />
      <RuleEditor title={t('cm.pages_EarlyLatePricingSettings.gec_cikis_kurallari')} rules={cfg.late_checkout} setRules={r => setCfg({
      ...cfg,
      late_checkout: r
    })} onDelete={i => setCfg({
      ...cfg,
      late_checkout: cfg.late_checkout.filter((_, j) => j !== i)
    })} />

      {/* Kural önizleme rozetleri */}
      <Card className="p-4">
        <div className="text-xs font-semibold text-slate-500 mb-2">{t('cm.pages_EarlyLatePricingSettings.ozet')}</div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-xs text-slate-500 mb-1">{t('cm.pages_EarlyLatePricingSettings.erken_giris')}</div>
            <div className="flex flex-wrap gap-1.5">
              {cfg.early_checkin.map(r => <span key={r.id || r.label} className="text-xs px-2 py-0.5 rounded bg-sky-50 border border-sky-200 text-sky-800">
                  {fmtRange(r)} → {valueLabel(r)}
                </span>)}
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-500 mb-1">{t('cm.pages_EarlyLatePricingSettings.gec_cikis')}</div>
            <div className="flex flex-wrap gap-1.5">
              {cfg.late_checkout.map(r => <span key={r.id || r.label} className="text-xs px-2 py-0.5 rounded bg-amber-50 border border-amber-200 text-amber-800">
                  {fmtRange(r)} → {valueLabel(r)}
                </span>)}
            </div>
          </div>
        </div>
      </Card>
    </div>;
}