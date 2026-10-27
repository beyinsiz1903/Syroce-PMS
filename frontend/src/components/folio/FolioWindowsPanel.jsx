import { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Card, CardContent } from "../ui/card";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Layers, Plus, RefreshCw, User, Building2, Crown, Briefcase } from "lucide-react";
import { useTranslation } from 'react-i18next';
import { formatCurrency, cachedTenantCurrency } from '@/lib/currency';
const PAYOR_OPTIONS = [{
  value: "guest",
  label: "Misafir",
  Icon: User
}, {
  value: "company",
  label: "Şirket",
  Icon: Building2
}, {
  value: "agency",
  label: "Acente",
  Icon: Briefcase
}, {
  value: "master",
  label: "Ana hesap",
  Icon: Crown
}];
function payorMeta(type) {
  return PAYOR_OPTIONS.find(o => o.value === type) || {
    label: type || "—",
    Icon: User
  };
}
export default function FolioWindowsPanel({
  bookingId,
  currentFolioId,
  onSelect,
  onChanged,
  readOnly = false,
  revision,
}) {
  const {
    t
  } = useTranslation();
  const [windows, setWindows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [newPayor, setNewPayor] = useState("guest");
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState('');
  const [accounts, setAccounts] = useState([]);
  const [accountId, setAccountId] = useState('');
  const [accountError, setAccountError] = useState('');
  const [windowError, setWindowError] = useState('');
  const requestVersion = useRef(0);
  const headers = {};
  const fetchWindows = useCallback(async () => {
    if (!bookingId) return;
    const version = ++requestVersion.current;
    setLoading(true); setWindowError(''); setWindows([]);
    try {
      const {
        data
      } = await axios.get(`/folio-windows/booking/${bookingId}`, {
        headers
      });
      if (version === requestVersion.current) setWindows(Array.isArray(data) ? data : []);
    } catch (e) {
      if (version === requestVersion.current) {
        const message = e.response?.data?.detail || "Folyo hesapları alınamadı. Yenileyin.";
        setWindowError(message); toast.error(message);
      }
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [bookingId]);
  useEffect(() => {
    fetchWindows();
    return () => { requestVersion.current += 1; };
  }, [fetchWindows, revision]);
  useEffect(() => {
    let active = true;
    if (!showAdd || !['company', 'agency'].includes(newPayor)) return () => { active = false; };
    setAccounts([]); setAccountError('');
    axios.get('/pms/cari-accounts').then(({ data }) => { if (active) setAccounts(data.accounts || []); })
      .catch(() => { if (active) setAccountError('Cari hesaplar alınamadı. Yeniden açıp deneyin.'); });
    return () => { active = false; };
  }, [showAdd, newPayor]);
  const openWindow = async () => {
    if (readOnly || (['company', 'agency'].includes(newPayor) && !accountId)) return;
    setAdding(true);
    try {
      const payload = { payor_type: newPayor, ...(['company', 'agency'].includes(newPayor) ? { cari_account_id: accountId } : {}) };
      if (editingId) await axios.patch(`/folio-windows/${editingId}/payor`, payload);
      else await axios.post('/folio-windows', { booking_id: bookingId, ...payload });
      toast.success(editingId ? 'Ödeyen güncellendi' : 'Yeni folyo açıldı');
      setShowAdd(false);
      setEditingId(''); setAccountId('');
      await fetchWindows();
      onChanged?.();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Folyo hesabı açılamadı");
    } finally {
      setAdding(false);
    }
  };
  const usedSet = new Set(windows.map(w => w.window_number).filter(n => n > 0));
  const canAdd = usedSet.size < 8;
  return <Card className="bg-white border-gray-200 shadow-sm">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-blue-600" />
            <h3 className="text-sm font-semibold text-gray-800">
              Folyo Hesapları ({windows.length})
            </h3>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={fetchWindows} disabled={loading} aria-label="Folyo hesaplarını yenile">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            </Button>
            {!readOnly && <Button size="sm" onClick={() => { setEditingId(''); setAccountId(''); setNewPayor('guest'); setShowAdd(v => !v); }} disabled={!canAdd} className="bg-blue-600 hover:bg-blue-700 text-white" data-testid="window-add-btn">
              <Plus className="w-3.5 h-3.5 mr-1" /> Yeni hesap
            </Button>}
          </div>
        </div>

        {!readOnly && showAdd && (canAdd || editingId) && <div className="border border-blue-200 bg-blue-50 rounded-md p-3 mb-4 flex flex-wrap items-center gap-2">
            <span className="text-xs text-gray-700">Ödeyen:</span>
            <select aria-label="Folyo ödeyen türü" className="border rounded-md px-2 py-1 text-sm" value={newPayor} onChange={e => { setNewPayor(e.target.value); setAccountId(''); }} data-testid="window-payor-select">
              {PAYOR_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            {['company', 'agency'].includes(newPayor) && <select aria-label="Folyo cari hesabı" value={accountId} onChange={e => setAccountId(e.target.value)} className="rounded border p-2"><option value="">Cari hesap seçin</option>{accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select>}
            {accountError && <p role="alert">{accountError}</p>}
            <Button size="sm" onClick={openWindow} disabled={adding || (!!accountError && ['company', 'agency'].includes(newPayor)) || (['company', 'agency'].includes(newPayor) && !accountId)} className="bg-emerald-600 hover:bg-emerald-700 text-white">
              {adding ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : editingId ? 'Kaydet' : 'Aç'}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowAdd(false)}>{t('cm.components_folio_FolioWindowsPanel.iptal')}</Button>
          </div>}

        {!canAdd && <p className="text-xs text-amber-600 mb-3">En fazla 8 ayrı hesap açılabilir.</p>}

        {windowError && <p role="alert" className="text-sm text-destructive">{windowError}</p>}
        {windows.length === 0 && !loading && !windowError && <p className="text-sm text-gray-500 py-6 text-center">Henüz folyo hesabı açılmamış.</p>}

        <div className="grid gap-3">
          {windows.map(w => {
          const meta = payorMeta(w.payor_type || w.folio_type);
          const isCurrent = w.folio_id === currentFolioId;
          return <div key={w.folio_id} className={`rounded-xl border p-4 ${isCurrent ? "border-blue-400 bg-blue-50" : "border-gray-200 bg-white"}`} data-testid={`window-row-${w.window_number || 0}`}>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="flex min-w-0 items-start gap-3">
                  <div className="h-8 w-8 shrink-0 rounded-lg bg-slate-100 flex items-center justify-center text-sm font-semibold text-slate-600">
                    {w.window_number || "—"}
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <meta.Icon className="w-3.5 h-3.5 text-gray-500" />
                      <span className="text-sm font-medium text-gray-800">{meta.label}</span>
                      <span className="whitespace-nowrap text-xs text-slate-500">{w.folio_number}</span>
                      <Badge className={w.status === "open" ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-600"}>
                        {w.status === 'open' ? 'Açık' : w.status === 'closed' ? 'Kapalı' : 'Arşiv'}
                      </Badge>
                      {isCurrent && <Badge className="bg-blue-100 text-blue-700 text-xs">Seçili hesap</Badge>}
                    </div>
                    {w.cari_account_name && <p className="text-xs font-medium">{w.cari_account_name}</p>}
                    <div className="text-xs text-gray-500 mt-0.5">
                      {w.charges_count || 0} hizmet kaydı · {w.payments_count || 0} ödeme hareketi
                    </div>
                  </div>
                </div>
                  <div className="ml-auto shrink-0 text-right">
                    <p className="text-xs text-gray-500">{t('cm.components_folio_FolioWindowsPanel.bakiye')}</p>
                    <p className={`mt-1 whitespace-nowrap text-lg font-semibold tabular-nums ${w.balance > 0 ? "text-slate-900" : "text-emerald-700"}`}>
                      {formatCurrency(w.balance || 0, w.currency || cachedTenantCurrency(), { locale: 'tr-TR', decimals: 2, compactDecimals: false })}
                    </p>
                  </div>
              </div>
                  {(onSelect || (!readOnly && w.status === 'open')) && <div className="mt-3 flex flex-wrap gap-2 border-t pt-3">
                    {onSelect && (readOnly || w.status === 'open') && <Button size="sm" variant="outline" aria-pressed={isCurrent} className={isCurrent ? 'border-blue-300 bg-white text-blue-700' : ''} onClick={() => onSelect(w.folio_id)}>{isCurrent ? 'Seçili hesap' : 'Bu folyoyu seç'}</Button>}
                    {!readOnly && w.status === 'open' && <Button size="sm" variant="outline" onClick={() => { setEditingId(w.folio_id); setNewPayor(w.payor_type || w.folio_type || 'guest'); setAccountId(w.cari_account_id || ''); setShowAdd(true); }}>Ödeyeni düzenle</Button>}
                  </div>}
              </div>;
        })}
        </div>
      </CardContent>
    </Card>;
}
