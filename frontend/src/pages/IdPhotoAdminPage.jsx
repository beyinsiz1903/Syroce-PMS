/**
 * Task #86 — Misafir kimlik fotoğrafı ön görüntüleme & manuel silme paneli
 *
 * Otomatik temizlik (Task #72) 90 günde / yetimleri 24 saatte siliyor;
 * burada resepsiyon personeli **bekleyen kayıtları görür**, yanlış
 * yüklenen ya da KVKK silme talebi gelen bir fotoğrafı süresinden önce
 * **manuel silebilir**, KVKK kapsamında booking_id veya guest_id bazlı
 * **toplu silme** yapabilir. Fotoğraf bayt'ları sunucudan listede
 * dönmez; her satırda yalnızca metadata + sona erme tarihi gösterilir.
 *
 * Endpoint'ler (axios.defaults.baseURL `/api`):
 *   GET    /checkin/online/id-photos
 *   DELETE /checkin/online/id-photos/{photo_id}?reason=...
 *   POST   /checkin/online/id-photos/bulk-delete
 *   GET    /checkin/online/{checkin_id}/id-photo?reason=...   (önizleme)
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import Layout from "../components/Layout";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { promptDialog } from '@/lib/dialogs';
import {
  ArrowLeft, ShieldAlert, RefreshCw, Loader2, Trash2, Eye,
  CalendarClock, FileLock2, AlertTriangle, X, Pencil, Save, RotateCcw,
} from "lucide-react";

const PAGE_SIZE = 50;

const EMPTY_FILTERS = {
  booking_id: "",
  guest_id: "",
  claimed: "all", // "all" | "true" | "false"
  uploaded_after: "",
  uploaded_before: "",
};

function fmtTs(ts) {
  if (!ts) return "—";
  try { return new Date(ts).toLocaleString("tr-TR"); } catch { return ts; }
}

function fmtBytes(n) {
  if (typeof n !== "number" || !Number.isFinite(n)) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function ExpiryBadge({ expiresAt }) {
  if (!expiresAt) return <span className="text-gray-400">—</span>;
  let cls = "bg-emerald-50 text-emerald-700 border-emerald-200";
  let label = "süre içinde";
  try {
    const exp = new Date(expiresAt).getTime();
    const now = Date.now();
    const days = Math.floor((exp - now) / (1000 * 60 * 60 * 24));
    if (days < 0) {
      cls = "bg-rose-50 text-rose-700 border-rose-200";
      label = "süresi dolmuş";
    } else if (days < 7) {
      cls = "bg-amber-50 text-amber-700 border-amber-200";
      label = `${days} gün kaldı`;
    } else {
      label = `${days} gün`;
    }
  } catch {
    /* keep defaults */
  }
  return (
    <span
      className={`inline-block text-[10px] px-1.5 py-0.5 rounded border ${cls}`}
    >
      {label}
    </span>
  );
}

export default function IdPhotoAdminPage({ user, tenant, onLogout }) {
  const navigate = useNavigate();
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState(EMPTY_FILTERS);
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [retentionDays, setRetentionDays] = useState(90);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Per-row delete dialog state
  const [confirmTarget, setConfirmTarget] = useState(null); // row obj
  const [confirmReason, setConfirmReason] = useState("");
  const [deletingId, setDeletingId] = useState(null);
  const [rowError, setRowError] = useState(null);

  // Bulk delete state
  const [bulkBookingId, setBulkBookingId] = useState("");
  const [bulkGuestId, setBulkGuestId] = useState("");
  const [bulkReason, setBulkReason] = useState("");
  const [bulkSubmitting, setBulkSubmitting] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const [bulkError, setBulkError] = useState(null);

  // Preview (download decrypted bytes through the existing staff endpoint)
  const [previewing, setPreviewing] = useState(null); // photo_id while loading
  const [previewError, setPreviewError] = useState(null);

  // Task #124 — Per-tenant saklama süresi düzenleyicisi
  const [retentionMeta, setRetentionMeta] = useState({
    source: "env_default",   // "tenant" | "env_default"
    env_default: 90,
    tenant_override: null,
    min_days: 1,
    max_days: 365,
  });
  const [retentionEditing, setRetentionEditing] = useState(false);
  const [retentionDraft, setRetentionDraft] = useState("");
  const [retentionSaving, setRetentionSaving] = useState(false);
  const [retentionError, setRetentionError] = useState(null);

  const buildParams = useCallback(() => {
    const p = {};
    if (appliedFilters.booking_id.trim()) p.booking_id = appliedFilters.booking_id.trim();
    if (appliedFilters.guest_id.trim()) p.guest_id = appliedFilters.guest_id.trim();
    if (appliedFilters.claimed === "true") p.claimed = true;
    if (appliedFilters.claimed === "false") p.claimed = false;
    if (appliedFilters.uploaded_after) p.uploaded_after = `${appliedFilters.uploaded_after}T00:00:00`;
    if (appliedFilters.uploaded_before) p.uploaded_before = `${appliedFilters.uploaded_before}T23:59:59`;
    return p;
  }, [appliedFilters]);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get("/checkin/online/id-photos", {
        params: { ...buildParams(), limit: PAGE_SIZE, offset },
      });
      const data = res.data || {};
      setItems(Array.isArray(data.items) ? data.items : []);
      setTotal(typeof data.total === "number" ? data.total : 0);
      if (typeof data.retention_days === "number") {
        setRetentionDays(data.retention_days);
      }
    } catch (err) {
      setError(err?.response?.data?.detail || "Liste yüklenemedi.");
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [buildParams, offset]);

  useEffect(() => { loadList(); }, [loadList]);

  // Task #124 — Saklama süresi meta'sını ayrıca yükle. Liste cevabı zaten
  // efektif gün sayısını döner (banner için), ancak "tenant özelleşmiş mi?"
  // bilgisi sadece settings GET'inde var; rozet/edit formu bunu ister.
  const loadRetentionMeta = useCallback(async () => {
    try {
      const res = await axios.get(
        "/checkin/online/settings/id-photo-retention",
      );
      const data = res.data || {};
      if (typeof data.retention_days === "number") {
        setRetentionDays(data.retention_days);
      }
      setRetentionMeta({
        source: data.source === "tenant" ? "tenant" : "env_default",
        env_default: typeof data.env_default === "number" ? data.env_default : 90,
        tenant_override:
          typeof data.tenant_override === "number" ? data.tenant_override : null,
        min_days: typeof data.min_days === "number" ? data.min_days : 1,
        max_days: typeof data.max_days === "number" ? data.max_days : 365,
      });
    } catch {
      // Settings endpoint sessizce başarısız olursa kart yine de görünsün —
      // liste cevabındaki retention_days banner için yeterli.
    }
  }, []);

  useEffect(() => { loadRetentionMeta(); }, [loadRetentionMeta]);

  const beginEditRetention = useCallback(() => {
    setRetentionDraft(String(retentionDays));
    setRetentionError(null);
    setRetentionEditing(true);
  }, [retentionDays]);

  const cancelEditRetention = useCallback(() => {
    setRetentionEditing(false);
    setRetentionError(null);
    setRetentionDraft("");
  }, []);

  const saveRetention = useCallback(async (payload) => {
    setRetentionSaving(true);
    setRetentionError(null);
    try {
      const res = await axios.put(
        "/checkin/online/settings/id-photo-retention",
        payload,
      );
      const data = res.data || {};
      if (typeof data.retention_days === "number") {
        setRetentionDays(data.retention_days);
      }
      setRetentionMeta((prev) => ({
        ...prev,
        source: data.source === "tenant" ? "tenant" : "env_default",
        env_default:
          typeof data.env_default === "number" ? data.env_default : prev.env_default,
        tenant_override:
          typeof data.tenant_override === "number"
            ? data.tenant_override
            : null,
      }));
      setRetentionEditing(false);
      setRetentionDraft("");
      // Liste içindeki "kalan gün" rozetlerinin yeni saklama süresine göre
      // yeniden hesaplanması için listeyi tazele.
      await loadList();
    } catch (err) {
      setRetentionError(
        err?.response?.data?.detail || "Saklama süresi güncellenemedi.",
      );
    } finally {
      setRetentionSaving(false);
    }
  }, [loadList]);

  const submitRetention = useCallback(() => {
    const trimmed = retentionDraft.trim();
    if (!trimmed) {
      setRetentionError("Bir gün değeri girin (boş bırakmak için 'Varsayılana dön').");
      return;
    }
    const n = Number.parseInt(trimmed, 10);
    if (!Number.isFinite(n) || String(n) !== trimmed) {
      setRetentionError("Sadece pozitif tam sayı (gün) girilebilir.");
      return;
    }
    if (n < retentionMeta.min_days || n > retentionMeta.max_days) {
      setRetentionError(
        `Değer ${retentionMeta.min_days} – ${retentionMeta.max_days} gün aralığında olmalı.`,
      );
      return;
    }
    saveRetention({ retention_days: n });
  }, [retentionDraft, retentionMeta.min_days, retentionMeta.max_days, saveRetention]);

  const resetRetention = useCallback(() => {
    saveRetention({ retention_days: null });
  }, [saveRetention]);

  const handleApply = useCallback(() => {
    setAppliedFilters(filters);
    setOffset(0);
  }, [filters]);

  const handleReset = useCallback(() => {
    setFilters(EMPTY_FILTERS);
    setAppliedFilters(EMPTY_FILTERS);
    setOffset(0);
  }, []);

  const counters = useMemo(() => {
    const orphans = items.filter((it) => !it.claimed).length;
    const claimed = items.filter((it) => it.claimed).length;
    return { orphans, claimed };
  }, [items]);

  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + items.length, total);
  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;

  const submitDelete = useCallback(async () => {
    if (!confirmTarget) return;
    const reasonClean = confirmReason.trim();
    if (!reasonClean) {
      setRowError("Silme gerekçesi zorunludur (KVKK).");
      return;
    }
    setDeletingId(confirmTarget.photo_id);
    setRowError(null);
    try {
      await axios.delete(
        `/checkin/online/id-photos/${encodeURIComponent(confirmTarget.photo_id)}`,
        { params: { reason: reasonClean } },
      );
      setConfirmTarget(null);
      setConfirmReason("");
      await loadList();
    } catch (err) {
      setRowError(err?.response?.data?.detail || "Silme başarısız oldu.");
    } finally {
      setDeletingId(null);
    }
  }, [confirmTarget, confirmReason, loadList]);

  const submitBulkDelete = useCallback(async () => {
    setBulkError(null);
    setBulkResult(null);
    const bk = bulkBookingId.trim();
    const gid = bulkGuestId.trim();
    const reasonClean = bulkReason.trim();
    if (!bk && !gid) {
      setBulkError("booking_id veya guest_id alanlarından en az biri zorunlu.");
      return;
    }
    if (!reasonClean) {
      setBulkError("Toplu silme için gerekçe zorunlu (KVKK).");
      return;
    }
    setBulkSubmitting(true);
    try {
      const res = await axios.post("/checkin/online/id-photos/bulk-delete", {
        booking_id: bk || undefined,
        guest_id: gid || undefined,
        reason: reasonClean,
      });
      setBulkResult(res.data || null);
      setBulkBookingId("");
      setBulkGuestId("");
      setBulkReason("");
      await loadList();
    } catch (err) {
      setBulkError(err?.response?.data?.detail || "Toplu silme başarısız.");
    } finally {
      setBulkSubmitting(false);
    }
  }, [bulkBookingId, bulkGuestId, bulkReason, loadList]);

  const handlePreview = useCallback(async (row) => {
    if (!row?.checkin_id) {
      setPreviewError("Bu kayıt henüz bir check-in formuna bağlanmamış (yetim).");
      return;
    }
    const reason = await promptDialog({ message: "Önizleme için KVKK gerekçesi girin (örn. polis denetimi, check-in doğrulaması):", defaultValue: "" });
    const reasonClean = (reason || "").trim();
    if (!reasonClean) return;
    setPreviewing(row.photo_id);
    setPreviewError(null);
    try {
      const res = await axios.get(
        `/checkin/online/${encodeURIComponent(row.checkin_id)}/id-photo`,
        { params: { reason: reasonClean }, responseType: "blob" },
      );
      const url = URL.createObjectURL(res.data);
      const w = window.open(url, "_blank", "noopener,noreferrer");
      if (!w) {
        setPreviewError("Tarayıcı önizleme penceresini engelledi (popup).");
      }
      // Browser keeps the blob alive while the new tab uses it; revoke after a delay.
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      setPreviewError(
        err?.response?.data?.detail || "Önizleme yüklenemedi.",
      );
    } finally {
      setPreviewing(null);
    }
  }, []);

  return (
    <Layout
      user={user}
      tenant={tenant}
      onLogout={onLogout}
      currentModule="id-photo-admin"
      title="Bekleyen Kimlik Fotoğrafları"
      subtitle="Ön görüntüleme & manuel/KVKK silme — saklama süresi içindeki tüm kayıtlar"
    >
      <div data-testid="id-photo-admin-page" className="min-h-screen bg-gray-50">
        <div className="max-w-7xl mx-auto px-4 py-6">
          <div className="flex items-center justify-between mb-6">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate(-1)}
              className="text-gray-600"
            >
              <ArrowLeft className="w-4 h-4 mr-1" /> Geri
            </Button>
            <Button
              data-testid="refresh-btn"
              size="sm"
              variant="outline"
              onClick={loadList}
              disabled={loading}
            >
              {loading ? (
                <Loader2 className="w-3 h-3 animate-spin mr-1" />
              ) : (
                <RefreshCw className="w-3 h-3 mr-1" />
              )}
              Yenile
            </Button>
          </div>

          {/* KVKK uyarısı */}
          <div
            data-testid="kvkk-banner"
            className="mb-4 text-xs bg-rose-50 border border-rose-200 text-rose-800 rounded p-2 flex items-start gap-2"
          >
            <ShieldAlert className="w-4 h-4 mt-0.5 shrink-0" />
            <p>
              Burada listelenen kayıtlar misafirlerin kimlik fotoğraflarına ait
              meta bilgileridir. KVKK kapsamında <strong>her görüntüleme</strong>{" "}
              ve <strong>her silme işlemi</strong> denetim kaydına yazılır;
              gereksiz açma / silme yapmayın. Otomatik temizlik kayıtları{" "}
              <strong>{retentionDays} gün</strong> sonra siler — manuel silmeyi
              yalnızca yanlış yükleme veya KVKK silme talebi gibi gerekçelerle
              kullanın.
            </p>
          </div>

          {/* Üst sayaç şeridi */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500">Toplam (filtreli)</p>
                <p data-testid="card-total" className="text-2xl font-bold text-gray-900">
                  {total}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500">Bu sayfada – bağlı</p>
                <p data-testid="card-claimed" className="text-2xl font-bold text-emerald-700">
                  {counters.claimed}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500">Bu sayfada – yetim</p>
                <p data-testid="card-orphans" className="text-2xl font-bold text-amber-700">
                  {counters.orphans}
                </p>
              </CardContent>
            </Card>
            <Card data-testid="card-retention-wrapper">
              <CardContent className="p-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-xs text-gray-500 flex items-center gap-1">
                    <CalendarClock className="w-3 h-3" /> Saklama süresi
                  </p>
                  {!retentionEditing && (
                    <button
                      type="button"
                      data-testid="retention-edit-btn"
                      onClick={beginEditRetention}
                      className="text-gray-400 hover:text-indigo-600 transition"
                      title="Saklama süresini düzenle"
                      aria-label="Saklama süresini düzenle"
                    >
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>

                {!retentionEditing ? (
                  <>
                    <p
                      data-testid="card-retention"
                      className="text-2xl font-bold text-indigo-700"
                    >
                      {retentionDays} gün
                    </p>
                    <p
                      data-testid="retention-source"
                      className="text-[10px] text-gray-500 mt-0.5"
                    >
                      {retentionMeta.source === "tenant"
                        ? "Otele özel ayar"
                        : `Sistem varsayılanı (${retentionMeta.env_default} gün)`}
                    </p>
                  </>
                ) : (
                  <div className="mt-1 space-y-1.5" data-testid="retention-editor">
                    <div className="flex items-center gap-1">
                      <Input
                        data-testid="retention-input"
                        type="number"
                        min={retentionMeta.min_days}
                        max={retentionMeta.max_days}
                        value={retentionDraft}
                        onChange={(e) => setRetentionDraft(e.target.value)}
                        disabled={retentionSaving}
                        className="h-7 text-sm w-20 px-1.5"
                      />
                      <span className="text-xs text-gray-500">gün</span>
                      <Button
                        data-testid="retention-save-btn"
                        size="sm"
                        variant="default"
                        onClick={submitRetention}
                        disabled={retentionSaving}
                        className="h-7 px-2 ml-auto"
                      >
                        {retentionSaving ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <Save className="w-3 h-3" />
                        )}
                      </Button>
                      <Button
                        data-testid="retention-cancel-btn"
                        size="sm"
                        variant="ghost"
                        onClick={cancelEditRetention}
                        disabled={retentionSaving}
                        className="h-7 px-1.5"
                      >
                        <X className="w-3 h-3" />
                      </Button>
                    </div>
                    {retentionMeta.source === "tenant" && (
                      <button
                        type="button"
                        data-testid="retention-reset-btn"
                        onClick={resetRetention}
                        disabled={retentionSaving}
                        className="text-[10px] text-indigo-600 hover:underline flex items-center gap-1 disabled:opacity-50"
                      >
                        <RotateCcw className="w-3 h-3" />
                        Sistem varsayılanına dön ({retentionMeta.env_default} gün)
                      </button>
                    )}
                    <p className="text-[10px] text-gray-500">
                      İzin verilen: {retentionMeta.min_days}–{retentionMeta.max_days} gün
                    </p>
                    {retentionError && (
                      <p
                        data-testid="retention-error"
                        className="text-[11px] text-rose-600"
                      >
                        {retentionError}
                      </p>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Filtreler */}
          <Card data-testid="list-filters" className="mb-4">
            <CardContent className="p-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-2 items-end">
                <div>
                  <label className="text-[11px] text-gray-500 block mb-1">
                    Booking kimliği
                  </label>
                  <Input
                    data-testid="filter-booking-id"
                    placeholder="bk-..."
                    value={filters.booking_id}
                    onChange={(e) =>
                      setFilters((p) => ({ ...p, booking_id: e.target.value }))
                    }
                    className="h-8 text-xs"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-gray-500 block mb-1">
                    Misafir kimliği
                  </label>
                  <Input
                    data-testid="filter-guest-id"
                    placeholder="g-..."
                    value={filters.guest_id}
                    onChange={(e) =>
                      setFilters((p) => ({ ...p, guest_id: e.target.value }))
                    }
                    className="h-8 text-xs"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-gray-500 block mb-1">Durum</label>
                  <select
                    data-testid="filter-claimed"
                    value={filters.claimed}
                    onChange={(e) =>
                      setFilters((p) => ({ ...p, claimed: e.target.value }))
                    }
                    className="h-8 text-xs rounded border border-input bg-background px-2 w-full"
                  >
                    <option value="all">Hepsi</option>
                    <option value="true">Bağlı (claim'li)</option>
                    <option value="false">Yetim (claim'siz)</option>
                  </select>
                </div>
                <div>
                  <label className="text-[11px] text-gray-500 block mb-1">
                    Yüklendi (sonra)
                  </label>
                  <Input
                    data-testid="filter-uploaded-after"
                    type="date"
                    value={filters.uploaded_after}
                    onChange={(e) =>
                      setFilters((p) => ({ ...p, uploaded_after: e.target.value }))
                    }
                    className="h-8 text-xs"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-gray-500 block mb-1">
                    Yüklendi (önce)
                  </label>
                  <Input
                    data-testid="filter-uploaded-before"
                    type="date"
                    value={filters.uploaded_before}
                    onChange={(e) =>
                      setFilters((p) => ({ ...p, uploaded_before: e.target.value }))
                    }
                    className="h-8 text-xs"
                  />
                </div>
                <div className="flex gap-2">
                  <Button
                    data-testid="apply-filters-btn"
                    size="sm"
                    onClick={handleApply}
                    className="flex-1 h-8 text-xs"
                  >
                    Uygula
                  </Button>
                  <Button
                    data-testid="reset-filters-btn"
                    size="sm"
                    variant="outline"
                    onClick={handleReset}
                    className="h-8 text-xs"
                  >
                    Sıfırla
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Hata banner'ları */}
          {error && (
            <div
              data-testid="list-error"
              className="bg-red-50 border border-red-200 text-red-800 text-xs rounded p-2 mb-3"
            >
              {error}
            </div>
          )}
          {previewError && (
            <div
              data-testid="preview-error"
              className="bg-red-50 border border-red-200 text-red-800 text-xs rounded p-2 mb-3 flex items-start gap-2"
            >
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{previewError}</span>
            </div>
          )}

          {/* Liste */}
          <Card className="mb-6">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-gray-700 flex items-center gap-2">
                <FileLock2 className="w-4 h-4 text-indigo-600" />
                Bekleyen Kayıtlar
                <span
                  data-testid="page-range-label"
                  className="text-[10px] bg-indigo-50 text-indigo-700 border border-indigo-200 rounded px-1.5 py-0.5"
                >
                  {pageStart}–{pageEnd} / {total}
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
                </div>
              ) : items.length === 0 ? (
                <div
                  data-testid="empty-state"
                  className="text-center py-8 text-gray-500 text-sm"
                >
                  Filtrelerle eşleşen bekleyen kimlik fotoğrafı yok.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table
                    data-testid="id-photo-table"
                    className="w-full text-xs"
                  >
                    <thead>
                      <tr className="text-left text-gray-500 border-b">
                        <th className="py-2 pr-2">Yüklendi</th>
                        <th className="py-2 pr-2">Booking</th>
                        <th className="py-2 pr-2">Misafir</th>
                        <th className="py-2 pr-2">Check-in</th>
                        <th className="py-2 pr-2">Durum</th>
                        <th className="py-2 pr-2">Boyut</th>
                        <th className="py-2 pr-2">Sona erme</th>
                        <th className="py-2 pr-2 text-right">İşlemler</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((it) => (
                        <tr
                          key={it.photo_id}
                          data-testid={`id-photo-row-${it.photo_id}`}
                          className="border-b last:border-0 hover:bg-gray-50"
                        >
                          <td className="py-2 pr-2 text-gray-700 whitespace-nowrap">
                            {fmtTs(it.uploaded_at)}
                          </td>
                          <td className="py-2 pr-2 text-gray-700 truncate max-w-[160px]">
                            {it.booking_id || "—"}
                          </td>
                          <td className="py-2 pr-2 text-gray-700 truncate max-w-[160px]">
                            {it.guest_id || "—"}
                          </td>
                          <td className="py-2 pr-2 text-gray-700 truncate max-w-[160px]">
                            {it.checkin_id || (
                              <span className="text-amber-600">— (yetim)</span>
                            )}
                          </td>
                          <td className="py-2 pr-2">
                            {it.claimed ? (
                              <span className="text-[10px] bg-emerald-50 text-emerald-700 border border-emerald-200 rounded px-1.5 py-0.5">
                                bağlı
                              </span>
                            ) : (
                              <span className="text-[10px] bg-amber-50 text-amber-700 border border-amber-200 rounded px-1.5 py-0.5">
                                yetim
                              </span>
                            )}
                          </td>
                          <td className="py-2 pr-2 text-gray-700 whitespace-nowrap">
                            {fmtBytes(it.size_bytes)}
                          </td>
                          <td className="py-2 pr-2 whitespace-nowrap">
                            <ExpiryBadge expiresAt={it.expires_at} />
                          </td>
                          <td className="py-2 pr-2 text-right whitespace-nowrap">
                            <Button
                              data-testid={`preview-btn-${it.photo_id}`}
                              size="sm"
                              variant="outline"
                              onClick={() => handlePreview(it)}
                              disabled={previewing === it.photo_id || !it.checkin_id}
                              className="h-7 text-[11px] mr-1"
                              title={
                                it.checkin_id
                                  ? "KVKK gerekçesi ile önizleme"
                                  : "Yetim kayıt önizlenemez"
                              }
                            >
                              {previewing === it.photo_id ? (
                                <Loader2 className="w-3 h-3 animate-spin" />
                              ) : (
                                <Eye className="w-3 h-3" />
                              )}
                            </Button>
                            <Button
                              data-testid={`delete-btn-${it.photo_id}`}
                              size="sm"
                              variant="outline"
                              onClick={() => {
                                setConfirmTarget(it);
                                setConfirmReason("");
                                setRowError(null);
                              }}
                              disabled={deletingId === it.photo_id}
                              className="h-7 text-[11px] text-rose-700 border-rose-200 hover:bg-rose-50"
                            >
                              {deletingId === it.photo_id ? (
                                <Loader2 className="w-3 h-3 animate-spin" />
                              ) : (
                                <Trash2 className="w-3 h-3" />
                              )}
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {total > PAGE_SIZE && (
                <div
                  data-testid="pagination-bar"
                  className="flex items-center justify-between mt-3 pt-2 border-t border-gray-100 text-xs text-gray-600"
                >
                  <span>
                    {pageStart}–{pageEnd} arası, toplam {total} kayıt
                  </span>
                  <div className="flex gap-2">
                    <Button
                      data-testid="pagination-prev"
                      size="sm"
                      variant="outline"
                      onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
                      disabled={!hasPrev || loading}
                      className="h-7 text-xs"
                    >
                      Önceki
                    </Button>
                    <Button
                      data-testid="pagination-next"
                      size="sm"
                      variant="outline"
                      onClick={() => setOffset((o) => o + PAGE_SIZE)}
                      disabled={!hasNext || loading}
                      className="h-7 text-xs"
                    >
                      Sonraki
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* KVKK toplu silme */}
          <Card data-testid="bulk-delete-card" className="mb-6 border-rose-200">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-rose-800 flex items-center gap-2">
                <ShieldAlert className="w-4 h-4" />
                KVKK Toplu Silme
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-[11px] text-gray-600 mb-2">
                Bir misafir KVKK kapsamında verilerinin silinmesini talep
                ettiğinde, ilgili booking_id <em>ya da</em> guest_id altındaki
                tüm kimlik fotoğrafları tek seferde silinir. Her silme ayrı bir
                audit kaydı bırakır.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <Input
                  data-testid="bulk-booking-id"
                  placeholder="booking_id"
                  value={bulkBookingId}
                  onChange={(e) => setBulkBookingId(e.target.value)}
                  className="h-8 text-xs"
                />
                <Input
                  data-testid="bulk-guest-id"
                  placeholder="guest_id"
                  value={bulkGuestId}
                  onChange={(e) => setBulkGuestId(e.target.value)}
                  className="h-8 text-xs"
                />
                <Input
                  data-testid="bulk-reason"
                  placeholder="Gerekçe (KVKK silme talebi #...)"
                  value={bulkReason}
                  onChange={(e) => setBulkReason(e.target.value)}
                  className="h-8 text-xs"
                />
              </div>
              <div className="mt-2 flex items-center gap-2">
                <Button
                  data-testid="bulk-submit-btn"
                  size="sm"
                  variant="outline"
                  onClick={submitBulkDelete}
                  disabled={bulkSubmitting}
                  className="h-8 text-xs text-rose-700 border-rose-300 hover:bg-rose-50"
                >
                  {bulkSubmitting ? (
                    <Loader2 className="w-3 h-3 animate-spin mr-1" />
                  ) : (
                    <Trash2 className="w-3 h-3 mr-1" />
                  )}
                  Toplu sil
                </Button>
                {bulkResult && (
                  <span
                    data-testid="bulk-result"
                    className="text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-2 py-0.5"
                  >
                    {bulkResult.deleted}/{bulkResult.matched} kayıt silindi
                    {Array.isArray(bulkResult.failed_photo_ids) &&
                    bulkResult.failed_photo_ids.length > 0
                      ? ` · ${bulkResult.failed_photo_ids.length} başarısız`
                      : ""}
                  </span>
                )}
                {bulkError && (
                  <span
                    data-testid="bulk-error"
                    className="text-[11px] text-rose-700 bg-rose-50 border border-rose-200 rounded px-2 py-0.5"
                  >
                    {bulkError}
                  </span>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Tek kayıt silme modalı */}
      {confirmTarget && (
        <div
          data-testid="delete-modal"
          className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget && !deletingId) {
              setConfirmTarget(null);
              setRowError(null);
            }
          }}
        >
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-4">
            <div className="flex items-start justify-between mb-2">
              <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                <Trash2 className="w-4 h-4 text-rose-600" />
                Kimlik fotoğrafını sil
              </h3>
              <button
                type="button"
                onClick={() => {
                  if (deletingId) return;
                  setConfirmTarget(null);
                  setRowError(null);
                }}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <p className="text-xs text-gray-600 mb-2">
              <strong>photo_id:</strong>{" "}
              <span className="font-mono">{confirmTarget.photo_id}</span>
              <br />
              <strong>booking:</strong> {confirmTarget.booking_id || "—"}
              {confirmTarget.checkin_id ? (
                <> · <strong>check-in:</strong> {confirmTarget.checkin_id}</>
              ) : null}
            </p>
            <p className="text-[11px] text-rose-700 bg-rose-50 border border-rose-200 rounded p-2 mb-2">
              Bu işlem geri alınamaz. Şifrelenmiş dosya ve metadata kaydı
              silinir; KVKK denetimi için audit kaydı bırakılır
              (<code>action=manual_delete</code>).
            </p>
            <label className="text-[11px] text-gray-600 block mb-1">
              Silme gerekçesi (zorunlu)
            </label>
            <Input
              data-testid="delete-reason-input"
              autoFocus
              value={confirmReason}
              onChange={(e) => setConfirmReason(e.target.value)}
              placeholder="örn. yanlış yükleme, KVKK silme talebi #2026-..."
              className="h-8 text-xs mb-2"
              maxLength={500}
            />
            {rowError && (
              <div
                data-testid="delete-modal-error"
                className="text-[11px] text-rose-700 bg-rose-50 border border-rose-200 rounded p-1.5 mb-2"
              >
                {rowError}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setConfirmTarget(null);
                  setRowError(null);
                }}
                disabled={!!deletingId}
                className="h-8 text-xs"
              >
                Vazgeç
              </Button>
              <Button
                data-testid="confirm-delete-btn"
                size="sm"
                onClick={submitDelete}
                disabled={!!deletingId}
                className="h-8 text-xs bg-rose-600 hover:bg-rose-700"
              >
                {deletingId ? (
                  <Loader2 className="w-3 h-3 animate-spin mr-1" />
                ) : (
                  <Trash2 className="w-3 h-3 mr-1" />
                )}
                Sil
              </Button>
            </div>
          </div>
        </div>
      )}
    </Layout>
  );
}
