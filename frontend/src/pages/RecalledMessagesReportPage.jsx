/**
 * Task #35 — Geri Alınan Mesajlar Raporu
 *
 * Yöneticiler için tarih aralığı + gönderen + öncelik filtreleriyle
 * geri alınan iç mesajları listeler. Audit kaydı action="recall_internal_message"
 * olan kayıtları döker.
 *
 * Endpoint: GET /audit/recalled-messages  (axios.defaults.baseURL
 * zaten `/api` ile bittiği için yol göreli yazılır.)
 */
import { useState, useEffect, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import Layout from "../components/Layout";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  ArrowLeft, Undo2, RefreshCw, Loader2, ChevronDown,
  ChevronRight, Clock, User as UserIcon, Building2, AlertTriangle,
} from "lucide-react";

const HOURS_24 = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, "0"));

function emptySummary() {
  return { by_sender: [], by_priority: [], by_hour_of_day: [] };
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
          className="bg-rose-500 h-full"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 text-right text-gray-700 font-semibold">{count}</span>
    </div>
  );
}

export default function RecalledMessagesReportPage({ user, tenant, onLogout }) {
  const navigate = useNavigate();
  const [filters, setFilters] = useState({
    start_date: "",
    end_date: "",
    sender_id: "",
    priority: "",
  });
  const PAGE_SIZE = 50;
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState(emptySummary);
  const [expandedIds, setExpandedIds] = useState(new Set());

  const loadReport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (filters.start_date) params.start_date = `${filters.start_date}T00:00:00`;
      if (filters.end_date) params.end_date = `${filters.end_date}T23:59:59`;
      if (filters.sender_id) params.sender_id = filters.sender_id;
      if (filters.priority) params.priority = filters.priority;
      params.limit = PAGE_SIZE;
      params.offset = offset;
      const res = await axios.get("/audit/recalled-messages", { params });
      const data = res.data || {};
      setEvents(Array.isArray(data.events) ? data.events : []);
      setTotal(typeof data.total === "number" ? data.total : 0);
      setSummary({
        by_sender: data.summary?.by_sender || [],
        by_priority: data.summary?.by_priority || [],
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
  }, [filters, offset]);

  useEffect(() => { loadReport(); }, [loadReport]);

  // Filtre değişince ilk sayfaya dön — kullanıcı 3. sayfadayken filtreyi
  // sıkıştırırsa eski offset boş sayfa gösterirdi.
  useEffect(() => {
    setOffset(0);
  }, [filters.start_date, filters.end_date, filters.sender_id, filters.priority]);

  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + events.length, total);
  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;

  const topSender = summary.by_sender[0];
  const urgentCount = useMemo(() => {
    const u = summary.by_priority.find((p) => p.priority === "urgent");
    return u ? u.count : 0;
  }, [summary.by_priority]);

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
      currentModule="recalled-messages-report"
      title="Geri Alınan Mesajlar Raporu"
      subtitle="Hangi kullanıcı hangi mesajını ne zaman geri aldı"
    >
      <div
        data-testid="recalled-messages-report-page"
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

          {/* Filtreler */}
          <Card data-testid="report-filters" className="mb-4">
            <CardContent className="p-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2 items-end">
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
                    Geri alan kullanıcı kimliği
                  </label>
                  <Input
                    data-testid="filter-sender-id"
                    placeholder="user-..."
                    value={filters.sender_id}
                    onChange={(e) =>
                      setFilters((p) => ({ ...p, sender_id: e.target.value }))
                    }
                    className="h-8 text-xs"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-gray-500 block mb-1">
                    Orijinal öncelik
                  </label>
                  <select
                    data-testid="filter-priority"
                    value={filters.priority}
                    onChange={(e) =>
                      setFilters((p) => ({ ...p, priority: e.target.value }))
                    }
                    className="bg-white border border-gray-300 rounded text-xs px-2 h-8 text-gray-700 w-full"
                  >
                    <option value="">Tümü</option>
                    <option value="urgent">Acil</option>
                    <option value="normal">Normal</option>
                  </select>
                </div>
                <div>
                  <Button
                    data-testid="apply-filters-btn"
                    size="sm"
                    onClick={loadReport}
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

          {/* Özet kartlar */}
          <div
            data-testid="summary-cards"
            className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6"
          >
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500">Toplam geri alma</p>
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
                  <AlertTriangle className="w-3 h-3 text-amber-600" />
                  Acilden geri alınan
                </p>
                <p
                  data-testid="card-urgent-recalls"
                  className="text-2xl font-bold text-amber-600"
                >
                  {urgentCount}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500">En yoğun saat</p>
                <p
                  data-testid="card-peak-hour"
                  className="text-2xl font-bold text-rose-600"
                >
                  {peakHour ? `${peakHour.hour}:00` : "—"}
                </p>
                {peakHour && (
                  <p className="text-[11px] text-gray-500">
                    {peakHour.count} kayıt
                  </p>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500">En çok geri alan</p>
                <p
                  data-testid="card-top-sender"
                  className="text-sm font-bold text-gray-900 truncate"
                >
                  {topSender ? topSender.sender_name || topSender.sender_id : "—"}
                </p>
                {topSender && (
                  <p className="text-[11px] text-gray-500">
                    {topSender.sender_department || "—"} · {topSender.count}{" "}
                    geri alma
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
                    <Undo2 className="w-4 h-4 text-rose-600" />
                    Geri Alma Kayıtları
                    <span
                      data-testid="page-range-label"
                      className="text-[10px] bg-rose-50 text-rose-700 border border-rose-200 rounded px-1.5 py-0.5"
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
                      Seçili filtrelerle eşleşen geri alma kaydı yok.
                    </div>
                  ) : (
                    <ul data-testid="event-list" className="divide-y divide-gray-100">
                      {events.map((ev, idx) => {
                        const id = ev.id || `${ev.timestamp}-${idx}`;
                        const before = ev.before_snapshot || {};
                        const after = ev.after_snapshot || {};
                        const expanded = expandedIds.has(id);
                        const recipient =
                          before.to_user_name ||
                          before.to_department ||
                          "—";
                        const isUrgent = before.priority === "urgent";
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
                                    {before.from_user_name || ev.actor_id}
                                  </span>
                                  {before.from_department && (
                                    <span className="text-[10px] bg-gray-100 text-gray-700 border border-gray-200 rounded px-1.5">
                                      {before.from_department}
                                    </span>
                                  )}
                                  <span className="text-gray-400">→</span>
                                  <span className="text-gray-700 flex items-center gap-1">
                                    <Building2 className="w-3 h-3" />
                                    {recipient}
                                  </span>
                                  {isUrgent && (
                                    <span
                                      data-testid={`badge-urgent-${id}`}
                                      className="text-[10px] bg-amber-50 text-amber-700 border border-amber-200 rounded px-1.5"
                                    >
                                      Acil
                                    </span>
                                  )}
                                  {after.alarm_cleared && (
                                    <span className="text-[10px] bg-emerald-50 text-emerald-700 border border-emerald-200 rounded px-1.5">
                                      Alarm temizlendi
                                    </span>
                                  )}
                                </div>
                                {before.message_preview && (
                                  <p className="text-xs text-gray-600 mt-1 truncate">
                                    {before.message_preview}
                                  </p>
                                )}
                              </div>
                            </button>
                            {expanded && (
                              <div
                                data-testid={`event-detail-${id}`}
                                className="mt-2 ml-5 bg-gray-50 border border-gray-200 rounded p-2 text-[11px]"
                              >
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                  <div>
                                    <p className="text-gray-500 mb-1 font-semibold">
                                      Orijinal mesaj
                                    </p>
                                    <pre className="text-gray-700 overflow-auto max-h-48">
                                      {JSON.stringify(before, null, 2)}
                                    </pre>
                                  </div>
                                  <div>
                                    <p className="text-gray-500 mb-1 font-semibold">
                                      Geri alma eylemi
                                    </p>
                                    <pre className="text-gray-700 overflow-auto max-h-48">
                                      {JSON.stringify(after, null, 2)}
                                    </pre>
                                  </div>
                                </div>
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
              <Card data-testid="card-by-sender">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-700 flex items-center gap-2">
                    <UserIcon className="w-4 h-4" /> Geri alan sıralaması
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {summary.by_sender.length === 0 ? (
                    <p className="text-xs text-gray-500">Veri yok</p>
                  ) : (
                    summary.by_sender.map((s) => (
                      <div
                        key={s.sender_id}
                        data-testid={`sender-${s.sender_id}`}
                        className="flex justify-between items-center py-1 text-xs"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="text-gray-800 truncate">
                            {s.sender_name || s.sender_id}
                          </p>
                          {s.sender_department && (
                            <p className="text-[10px] text-gray-500">
                              {s.sender_department}
                            </p>
                          )}
                        </div>
                        <span className="text-gray-900 font-semibold ml-2">
                          {s.count}
                        </span>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>

              <Card data-testid="card-by-priority">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-700 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4" /> Önceliğe göre
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {summary.by_priority.length === 0 ? (
                    <p className="text-xs text-gray-500">Veri yok</p>
                  ) : (
                    summary.by_priority.map((p) => (
                      <div
                        key={p.priority}
                        data-testid={`priority-${p.priority}`}
                        className="flex justify-between items-center py-1 text-xs"
                      >
                        <span className="text-gray-700 capitalize">
                          {p.priority === "urgent"
                            ? "Acil"
                            : p.priority === "normal"
                            ? "Normal"
                            : p.priority}
                        </span>
                        <span className="text-gray-900 font-semibold">
                          {p.count}
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
