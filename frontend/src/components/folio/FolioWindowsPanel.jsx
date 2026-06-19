import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Card, CardContent } from "../ui/card";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Layers, Plus, RefreshCw, User, Building2, Crown, Briefcase } from "lucide-react";
import { useTranslation } from 'react-i18next';

const PAYOR_OPTIONS = [
  { value: "guest", label: "Misafir", Icon: User },
  { value: "company", label: "Şirket", Icon: Building2 },
  { value: "agency", label: "Acente", Icon: Briefcase },
  { value: "master", label: "Master", Icon: Crown },
];

function payorMeta(type) {
  return PAYOR_OPTIONS.find((o) => o.value === type) || { label: type || "—", Icon: User };
}

export default function FolioWindowsPanel({ bookingId, currentFolioId }) {
  const { t } = useTranslation();
  const [windows, setWindows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [newPayor, setNewPayor] = useState("guest");
  const [adding, setAdding] = useState(false);
  const token = localStorage.getItem("token");
  const headers = { Authorization: `Bearer ${token}` };

  const fetchWindows = useCallback(async () => {
    if (!bookingId) return;
    setLoading(true);
    try {
      const { data } = await axios.get(`/folio-windows/booking/${bookingId}`, { headers });
      setWindows(Array.isArray(data) ? data : []);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Window listesi alınamadı");
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [bookingId, token]);

  useEffect(() => { fetchWindows(); }, [fetchWindows]);

  const openWindow = async () => {
    setAdding(true);
    try {
      await axios.post(`/folio-windows`, { booking_id: bookingId, payor_type: newPayor }, { headers });
      toast.success("Yeni window açıldı");
      setShowAdd(false);
      fetchWindows();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Window açılamadı");
    } finally {
      setAdding(false);
    }
  };

  const changePayor = async (folioId, payorType) => {
    try {
      await axios.patch(`/folio-windows/${folioId}/payor`, { payor_type: payorType }, { headers });
      toast.success("Payor güncellendi");
      fetchWindows();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Güncellenemedi");
    }
  };

  const usedSet = new Set(windows.map((w) => w.window_number).filter((n) => n > 0));
  const canAdd = usedSet.size < 8;

  return (
    <Card className="bg-white border-gray-200 shadow-sm">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-blue-600" />
            <h3 className="text-sm font-semibold text-gray-800">
              Folio Windows ({windows.length})
            </h3>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={fetchWindows} disabled={loading}>
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            </Button>
            <Button
              size="sm"
              onClick={() => setShowAdd((v) => !v)}
              disabled={!canAdd}
              className="bg-blue-600 hover:bg-blue-700 text-white"
              data-testid="window-add-btn"
            >
              <Plus className="w-3.5 h-3.5 mr-1" /> {t('cm.components_folio_FolioWindowsPanel.window_ekle')}
            </Button>
          </div>
        </div>

        {showAdd && canAdd && (
          <div className="border border-blue-200 bg-blue-50 rounded-md p-3 mb-4 flex items-center gap-2">
            <span className="text-xs text-gray-700">Payor:</span>
            <select
              className="border rounded-md px-2 py-1 text-sm"
              value={newPayor}
              onChange={(e) => setNewPayor(e.target.value)}
              data-testid="window-payor-select"
            >
              {PAYOR_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <Button size="sm" onClick={openWindow} disabled={adding} className="bg-emerald-600 hover:bg-emerald-700 text-white">
              {adding ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : "Aç"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowAdd(false)}>{t('cm.components_folio_FolioWindowsPanel.iptal')}</Button>
          </div>
        )}

        {!canAdd && (
          <p className="text-xs text-amber-600 mb-3">Window limiti doldu (8/8).</p>
        )}

        {windows.length === 0 && !loading && (
          <p className="text-sm text-gray-500 py-6 text-center">{t('cm.components_folio_FolioWindowsPanel.henuz_window_yok')}</p>
        )}

        <div className="grid gap-2">
          {windows.map((w) => {
            const meta = payorMeta(w.payor_type);
            const isCurrent = w.folio_id === currentFolioId;
            return (
              <div
                key={w.folio_id}
                className={`border rounded-md p-3 flex items-center justify-between ${
                  isCurrent ? "border-blue-400 bg-blue-50" : "border-gray-200 bg-white"
                }`}
                data-testid={`window-row-${w.window_number || 0}`}
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center text-sm font-semibold text-gray-700">
                    {w.window_number || "—"}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <meta.Icon className="w-3.5 h-3.5 text-gray-500" />
                      <span className="text-sm font-medium text-gray-800">{meta.label}</span>
                      <Badge variant="outline" className="text-xs">{w.folio_number}</Badge>
                      <Badge className={w.status === "open" ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-600"}>
                        {w.status}
                      </Badge>
                      {isCurrent && <Badge className="bg-blue-100 text-blue-700 text-xs">aktif</Badge>}
                    </div>
                    <div className="text-xs text-gray-500 mt-0.5">
                      {w.charges_count} masraf · {w.payments_count} {t('cm.components_folio_FolioWindowsPanel.odeme')}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <p className="text-xs text-gray-500">{t('cm.components_folio_FolioWindowsPanel.bakiye')}</p>
                    <p className={`text-sm font-bold ${w.balance > 0 ? "text-red-600" : "text-emerald-600"}`}>
                      {(w.balance || 0).toFixed(2)}
                    </p>
                  </div>
                  {w.status === "open" && (
                    <select
                      className="border rounded-md px-2 py-1 text-xs"
                      value={w.payor_type || ""}
                      onChange={(e) => changePayor(w.folio_id, e.target.value)}
                      title={t('cm.components_folio_FolioWindowsPanel.payor_degistir')}
                      data-testid={`window-payor-${w.window_number || 0}`}
                    >
                      <option value="" disabled>Payor</option>
                      {PAYOR_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
