/**
 * Task #83 — KVKK Kimlik Fotoğrafı Görüntüleme Raporu
 *
 * Yöneticiler için tarih aralığı + personel + booking + check-in
 * filtreleriyle resepsiyonun açtığı kimlik fotoğrafı görüntüleme
 * audit kayıtlarını listeler. Audit kaydı action="view_online_checkin_id_photo"
 * olan olayları döker. KVKK denetimleri sırasında kanıt olarak
 * CSV dışa aktarımı destekler.
 *
 * Endpoints:
 *   - GET /audit/id-photo-views      (JSON listeleme + özet)
 *   - GET /audit/id-photo-views.csv  (filtreli CSV indirme)
 *
 * axios.defaults.baseURL zaten `/api` ile bittiği için yollar
 * göreli yazılır.
 */
import { useState, useEffect, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import Layout from "../components/Layout";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  ArrowLeft, ShieldCheck, RefreshCw, Loader2, ChevronDown,
  ChevronRight, Clock, User as UserIcon, FileText, Download,
  CalendarDays,
} from "lucide-react";

const HOURS_24 = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, "0"));

function emptySummary() {
  return { by_actor: [], by_booking: [], by_hour_of_day: [] };
}

function formatTs(ts) {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString("tr-TR");
  } catch {
    return ts;
  }
}

function HourBar({ hour, count, max }) {
  const pct = max > 0 ? Math.round((count / max) * 100) : 0;
  return (
    <div
      data-testid={`hour-bar-${hour}`}
      className="flex items-center gap-2 text-[11px]"
    >
      <span className="w-6 font-mono text-gray-500">{hour}</span>
      <div className="flex-1 bg-gray-100 rounded h-3 overflow-hidden">
        <div
          className="bg-indigo-500 h-full"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 text-right text-gray-700 font-semibold">{count}</span>
    </div>
  );
}

export default function IdPhotoViewReportPage({ user, tenant, onLogout }) {
  const navigate = useNavigate();
  // `filters` kullanıcının yazmakta olduğu draft, `appliedFilters`
  // ise sunucuya gönderilen son haldir. Her tuş basımında sorgu
  // atmamak için ayrı tutulur (bkz. code review): yalnızca "Uygula"
  // ve sayfalama backend isteğini tetikler. Böylece input'a yazarken
  // istek selliyle hem ağ trafiği hem de okuma yükü oluşmaz.
  const EMPTY_FILTERS = {
    start_date: "",
    end_date: "",
    actor_id: "",
    booking_id: "",
    checkin_id: "",
  };
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState(EMPTY_FILTERS);
  const PAGE_SIZE = 50;
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState(null);
  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState(emptySummary);
  const [expandedIds, setExpandedIds] = useState(new Set());

  // Filtreyi axios params'a çevirir. CSV indirme butonu da aynı
  // appliedFilters'tan beslenir — ekran ile dosya birbirini tutsun.
  const buildParams = useCallback(() => {
    const params = {};
    if (appliedFilters.start_date)
      params.start_date = `${appliedFilters.start_date}T00:00:00`;
    if (appliedFilters.end_date)
      params.end_date = `${appliedFilters.end_date}T23:59:59`;
    if (appliedFilters.actor_id) params.actor_id = appliedFilters.actor_id;
    if (appliedFilters.booking_id) params.booking_id = appliedFilters.booking_id;
    if (appliedFilters.checkin_id) params.checkin_id = appliedFilters.checkin_id;
    return params;
  }, [appliedFilters]);

  const loadReport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = { ...buildParams(), limit: PAGE_SIZE, offset };
      const res = await axios.get("/audit/id-photo-views", { params });
      const data = res.data || {};
      setEvents(Array.isArray(data.events) ? data.events : []);
      setTotal(typeof data.total === "number" ? data.total : 0);
      setSummary({
        by_actor: data.summary?.by_actor || [],
        by_booking: data.summary?.by_booking || [],
        by_hour_of_day: data.summary?.by_hour_of_day || [],
      });
    } catch (err) {
      setError(err?.response?.data?.detail || "Rapor yüklenemedi.");
      setEvents([]);
      setTotal(0);
      setSummary(emptySummary());
    } finally {
      setLoading(false);
    }
  }, [buildParams, offset]);

  // Yalnızca appliedFilters veya offset değişince fetch — draft (filters)
  // değişiklikleri network gürültüsü yaratmaz.
  useEffect(() => { loadReport(); }, [loadReport]);

  // Apply butonuna basıldığında: draft'ı uygula + ilk sayfaya dön.
  const handleApply = useCallback(() => {
    setAppliedFilters(filters);
    setOffset(0);
  }, [filters]);

  const handleExportCsv = useCallback(async () => {
    setExporting(true);
    setExportError(null);
    try {
      const params = buildParams();
      const res = await axios.get("/audit/id-photo-views.csv", {
        params,
        responseType: "blob",
      });
      const blob = new Blob([res.data], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
      a.download = `kvkk-id-photo-views-${ts}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(
        err?.response?.data?.detail || "CSV dışa aktarımı başarısız oldu."
      );
    } finally {
      setExporting(false);
    }
  }, [buildParams]);

  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + events.length, total);
  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;

  const topActor = summary.by_actor[0];
  const topBooking = summary.by_booking[0];

  const fullHours = useMemo(() => {
    const map = new Map();
    summary.by_hour_of_day.forEach((b) => map.set(b.hour, b.count));
    const filled = HOURS_24.map((h) => ({ hour: h, count: map.get(h) || 0 }));
    const max = Math.max(0, ...filled.map((b) => b.count));
    return { filled, max };
  }, [summary.by_hour_of_day]);

  const peakHour = useMemo(() => {
    if (!summary.by_hour_of_day.length) return null;
    return summary.by_hour_of_day.reduce(
      (best, b) => (b.count > best.count ? b : best),
      summary.by_hour_of_day[0]
    );
  }, [summary.by_hour_of_day]);

  const toggleExpand = (id) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <Layout
      user={user}
      tenant={tenant}
      onLogout={onLogout}
      currentModule="id-photo-view-report"
      title="Kimlik Fotoğrafı Görüntüleme Raporu"
      subtitle="KVKK denetimi — kim, ne zaman, hangi misafirin kimliğini açtı"
    >
      <div
        data-testid="id-photo-view-report-page"
        className="min-h-screen bg-gray-50"
      >
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
            <div className="flex items-center gap-2">
              <Button
                data-testid="export-csv-btn"
                size="sm"
                variant="outline"
                onClick={handleExportCsv}
                disabled={exporting || loading}
              >
                {exporting ? (
                  <Loader2 className="w-3 h-3 animate-spin mr-1" />
                ) : (
                  <Download className="w-3 h-3 mr-1" />
                )}
                CSV indir
              </Button>
              <Button
                data-testid="refresh-btn"
                size="sm"
                variant="outline"
                onClick={loadReport}
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
          </div>

          {/* KVKK uyarısı */}
          <div
            data-testid="kvkk-banner"
            className="mb-4 text-xs bg-indigo-50 border border-indigo-200 text-indigo-800 rounded p-2 flex items-start gap-2"
          >
            <ShieldCheck className="w-4 h-4 mt-0.5 shrink-0" />
            <p>
              Bu rapor 6698 sayılı Kişisel Verilerin Korunması Kanunu kapsamında
              tutulan kimlik fotoğrafı görüntüleme erişim kayıtlarını içerir.
              Kayıtlar yalnızca yöneticiler tarafından denetim amacıyla
              kullanılabilir; üçüncü şahıslarla paylaşılması KVKK ihlali
              oluşturur.
            </p>
          </div>

          {/* Filtreler */}
          <Card data-testid="report-filters" className="mb-4">
            <CardContent className="p-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-2 items-end">
                <div>
                  <label className="text-[11px] text-gray-500 block mb-1">
                    Başlangıç
                  </label>
                  <Input
                    data-testid="filter-start-date"
                    type="date"
                    value={filters.start_date}
                    onChange={(e) =>
                      setFilters((p) => ({ ...p, start_date: e.target.value }))
                    }
                    className="h-8 text-xs"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-gray-500 block mb-1">
                    Bitiş
                  </label>
                  <Input
                    data-testid="filter-end-date"
                    type="date"
                    value={filters.end_date}
                    onChange={(e) =>
                      setFilters((p) => ({ ...p, end_date: e.target.value }))
                    }
                    className="h-8 text-xs"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-gray-500 block mb-1">
                    Personel kimliği
                  </label>
                  <Input
                    data-testid="filter-actor-id"
                    placeholder="user-..."
                    value={filters.actor_id}
                    onChange={(e) =>
                      setFilters((p) => ({ ...p, actor_id: e.target.value }))
                    }
                    className="h-8 text-xs"
                  />
                </div>
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
                    Check-in kimliği
                  </label>
                  <Input
                    data-testid="filter-checkin-id"
                    placeholder="ck-..."
                    value={filters.checkin_id}
                    onChange={(e) =>
                      setFilters((p) => ({ ...p, checkin_id: e.target.value }))
                    }
                    className="h-8 text-xs"
                  />
                </div>
                <div>
                  <Button
                    data-testid="apply-filters-btn"
                    size="sm"
                    onClick={handleApply}
                    className="w-full h-8 text-xs"
                  >
                    Uygula
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {error && (
            <div
              data-testid="report-error"
              className="bg-red-50 border border-red-200 text-red-800 text-xs rounded p-2 mb-4"
            >
              {error}
            </div>
          )}
          {exportError && (
            <div
              data-testid="export-error"
              className="bg-red-50 border border-red-200 text-red-800 text-xs rounded p-2 mb-4"
            >
              {exportError}
            </div>
          )}

          {/* Özet kartlar */}
          <div
            data-testid="summary-cards"
            className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6"
          >
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500">Toplam görüntüleme</p>
                <p
                  data-testid="card-total"
                  className="text-2xl font-bold text-gray-900"
                >
                  {total}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500 flex items-center gap-1">
                  <CalendarDays className="w-3 h-3" />
                  En yoğun saat (UTC)
                </p>
                <p
                  data-testid="card-peak-hour"
                  className="text-2xl font-bold text-indigo-600"
                >
                  {peakHour ? `${peakHour.hour}:00` : "—"}
                </p>
                {peakHour && (
                  <p className="text-[11px] text-gray-500">
                    {peakHour.count} görüntüleme
                  </p>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500">En çok açan personel</p>
                <p
                  data-testid="card-top-actor"
                  className="text-sm font-bold text-gray-900 truncate"
                >
                  {topActor ? topActor.actor_id : "—"}
                </p>
                {topActor && (
                  <p className="text-[11px] text-gray-500">
                    {topActor.count} görüntüleme
                  </p>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500">En çok açılan booking</p>
                <p
                  data-testid="card-top-booking"
                  className="text-sm font-bold text-gray-900 truncate"
                >
                  {topBooking ? topBooking.booking_id : "—"}
                </p>
                {topBooking && (
                  <p className="text-[11px] text-gray-500">
                    {topBooking.count} görüntüleme
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Olay tablosu */}
            <div className="lg:col-span-2 space-y-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-700 flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-indigo-600" />
                    Görüntüleme Kayıtları
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
                  ) : events.length === 0 ? (
                    <div
                      data-testid="empty-state"
                      className="text-center py-8 text-gray-500 text-sm"
                    >
                      Seçili filtrelerle eşleşen kimlik fotoğrafı görüntüleme
                      kaydı yok.
                    </div>
                  ) : (
                    <ul data-testid="event-list" className="divide-y divide-gray-100">
                      {events.map((ev, idx) => {
                        const id = ev.id || `${ev.timestamp}-${idx}`;
                        const snap = ev.after_snapshot || {};
                        const expanded = expandedIds.has(id);
                        return (
                          <li
                            key={id}
                            data-testid={`event-row-${id}`}
                            className="py-2"
                          >
                            <button
                              type="button"
                              onClick={() => toggleExpand(id)}
                              className="w-full flex items-start gap-2 text-left hover:bg-gray-50 rounded px-1 py-1"
                            >
                              {expanded ? (
                                <ChevronDown className="w-3 h-3 mt-1 text-gray-400" />
                              ) : (
                                <ChevronRight className="w-3 h-3 mt-1 text-gray-400" />
                              )}
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 flex-wrap text-xs">
                                  <span className="text-gray-500 flex items-center gap-1">
                                    <Clock className="w-3 h-3" />
                                    {formatTs(ev.timestamp)}
                                  </span>
                                  <span className="font-semibold text-gray-900 flex items-center gap-1">
                                    <UserIcon className="w-3 h-3" />
                                    {ev.actor_id || "—"}
                                  </span>
                                  {ev.actor_role && (
                                    <span className="text-[10px] bg-gray-100 text-gray-700 border border-gray-200 rounded px-1.5">
                                      {ev.actor_role}
                                    </span>
                                  )}
                                  <span className="text-gray-400">·</span>
                                  <span className="text-gray-700 flex items-center gap-1">
                                    <FileText className="w-3 h-3" />
                                    booking {snap.booking_id || "—"}
                                  </span>
                                  <span className="text-gray-400">·</span>
                                  <span className="text-gray-700">
                                    check-in {ev.target_id || "—"}
                                  </span>
                                </div>
                                {snap.photo_id && (
                                  <p className="text-[11px] text-gray-500 mt-1 truncate">
                                    photo_id: {snap.photo_id}
                                    {snap.content_type
                                      ? ` · ${snap.content_type}`
                                      : ""}
                                  </p>
                                )}
                              </div>
                            </button>
                            {expanded && (
                              <div
                                data-testid={`event-detail-${id}`}
                                className="mt-2 ml-5 bg-gray-50 border border-gray-200 rounded p-2 text-[11px]"
                              >
                                <pre className="text-gray-700 overflow-auto max-h-48">
                                  {JSON.stringify(
                                    {
                                      timestamp: ev.timestamp,
                                      actor_id: ev.actor_id,
                                      actor_role: ev.actor_role,
                                      checkin_id: ev.target_id,
                                      ...snap,
                                    },
                                    null,
                                    2
                                  )}
                                </pre>
                              </div>
                            )}
                          </li>
                        );
                      })}
                    </ul>
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
                          onClick={() =>
                            setOffset((o) => Math.max(0, o - PAGE_SIZE))
                          }
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
            </div>

            {/* Yan panel: özetler */}
            <div className="space-y-4">
              <Card data-testid="card-by-actor">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-700 flex items-center gap-2">
                    <UserIcon className="w-4 h-4" /> Personel sıralaması
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {summary.by_actor.length === 0 ? (
                    <p className="text-xs text-gray-500">Veri yok</p>
                  ) : (
                    summary.by_actor.map((a) => (
                      <div
                        key={a.actor_id}
                        data-testid={`actor-${a.actor_id}`}
                        className="flex justify-between items-center py-1 text-xs"
                      >
                        <span className="text-gray-800 truncate">
                          {a.actor_id}
                        </span>
                        <span className="text-gray-900 font-semibold ml-2">
                          {a.count}
                        </span>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>

              <Card data-testid="card-by-booking">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-700 flex items-center gap-2">
                    <FileText className="w-4 h-4" /> Booking sıralaması
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {summary.by_booking.length === 0 ? (
                    <p className="text-xs text-gray-500">Veri yok</p>
                  ) : (
                    summary.by_booking.map((b) => (
                      <div
                        key={b.booking_id}
                        data-testid={`booking-${b.booking_id}`}
                        className="flex justify-between items-center py-1 text-xs"
                      >
                        <span className="text-gray-700">{b.booking_id}</span>
                        <span className="text-gray-900 font-semibold">
                          {b.count}
                        </span>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>

              <Card data-testid="card-by-hour">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-700 flex items-center gap-2">
                    <Clock className="w-4 h-4" /> Saat dağılımı (UTC)
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-1">
                  {fullHours.filled.map((b) => (
                    <HourBar
                      key={b.hour}
                      hour={b.hour}
                      count={b.count}
                      max={fullHours.max}
                    />
                  ))}
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
}
