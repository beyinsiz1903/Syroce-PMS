/**
 * Task #35 — Geri Alınan Mesajlar Raporu
 *
 * Yöneticiler için tarih aralığı + gönderen + öncelik filtreleriyle
 * geri alınan iç mesajları listeler. Audit kaydı action="recall_internal_message"
 * (ve include_denied=true ise "recall_internal_message_denied") olan kayıtları
 * döker.
 *
 * Endpoint: GET /audit/recalled-messages
 */
import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";

import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { PageHeader } from "../components/ui/page-header";
import { KpiCard } from "../components/ui/kpi-card";
import { StatusBadge } from "../components/ui/status-badge";
import {
  ArrowLeft,
  Undo2,
  RefreshCw,
  Loader2,
  ChevronDown,
  ChevronRight,
  Clock,
  User as UserIcon,
  Building2,
  AlertTriangle,
  Download,
  Inbox,
  History,
  TrendingUp,
} from "lucide-react";

const HOURS_24 = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, "0"));
const PAGE_SIZE = 50;
const SENDER_DEBOUNCE_MS = 350;

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

function csvEscape(value) {
  if (value === null || value === undefined) return "";
  const s = String(value).replace(/\r?\n/g, " ");
  if (/[",;]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function downloadCsv(filename, rows) {
  const blob = new Blob([rows.map((r) => r.join(",")).join("\n")], {
    type: "text/csv;charset=utf-8;",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function HourBar({ hour, count, max }) {
  const pct = max > 0 ? Math.round((count / max) * 100) : 0;
  return (
    <div
      data-testid={`hour-bar-${hour}`}
      className="flex items-center gap-2 text-[11px]"
    >
      <span className="w-6 font-mono text-slate-500">{hour}</span>
      <div className="flex-1 bg-slate-100 rounded h-3 overflow-hidden">
        <div className="bg-rose-500 h-full" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-8 text-right text-slate-700 font-semibold">{count}</span>
    </div>
  );
}

function DetailGrid({ data }) {
  const entries = Object.entries(data || {}).filter(
    ([, v]) => v !== null && v !== undefined && v !== "",
  );
  if (entries.length === 0) {
    return <p className="text-[11px] text-slate-500 italic">Veri yok</p>;
  }
  return (
    <dl className="grid grid-cols-1 gap-y-1 text-[11px]">
      {entries.map(([k, v]) => (
        <div key={k} className="grid grid-cols-3 gap-2">
          <dt className="text-slate-500 truncate">{k}</dt>
          <dd className="col-span-2 text-slate-800 break-words">
            {typeof v === "object" ? JSON.stringify(v) : String(v)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export default function RecalledMessagesReportPage() {
  const navigate = useNavigate();

  // Draft (UI) vs applied (effective) filters: prevents per-keystroke fetches.
  const [draft, setDraft] = useState({
    start_date: "",
    end_date: "",
    sender_id: "",
    priority: "",
    include_denied: false,
  });
  const [applied, setApplied] = useState(draft);
  const [offset, setOffset] = useState(0);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState(emptySummary);
  const [expandedIds, setExpandedIds] = useState(new Set());

  // Debounce only the free-text sender_id field; date/priority/checkbox commit
  // immediately so filtering still feels instant.
  const debounceRef = useRef(null);
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setApplied((prev) =>
        prev.sender_id === draft.sender_id ? prev : { ...prev, sender_id: draft.sender_id },
      );
    }, SENDER_DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [draft.sender_id]);

  // Non-debounced fields commit instantly into `applied`.
  useEffect(() => {
    setApplied((prev) => ({
      ...prev,
      start_date: draft.start_date,
      end_date: draft.end_date,
      priority: draft.priority,
      include_denied: draft.include_denied,
    }));
  }, [draft.start_date, draft.end_date, draft.priority, draft.include_denied]);

  // Reset to first page when applied filters change.
  useEffect(() => {
    setOffset(0);
  }, [
    applied.start_date,
    applied.end_date,
    applied.sender_id,
    applied.priority,
    applied.include_denied,
  ]);

  const loadReport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (applied.start_date) params.start_date = `${applied.start_date}T00:00:00`;
      if (applied.end_date) params.end_date = `${applied.end_date}T23:59:59`;
      if (applied.sender_id) params.sender_id = applied.sender_id;
      if (applied.priority) params.priority = applied.priority;
      if (applied.include_denied) params.include_denied = true;
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
      const detail = err?.response?.data?.detail || "Rapor yüklenemedi.";
      setError(detail);
      setEvents([]);
      setTotal(0);
      setSummary(emptySummary());
      toast.error(detail);
    } finally {
      setLoading(false);
    }
  }, [applied, offset]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  // Prune stale expandedIds after events change so refresh does not retain
  // ids that no longer exist in the visible list.
  useEffect(() => {
    setExpandedIds((prev) => {
      if (prev.size === 0) return prev;
      const visible = new Set(
        events.map((ev, idx) => ev.id || `${ev.timestamp}-${idx}`),
      );
      let changed = false;
      const next = new Set();
      prev.forEach((id) => {
        if (visible.has(id)) next.add(id);
        else changed = true;
      });
      return changed ? next : prev;
    });
  }, [events]);

  const deniedCount = useMemo(
    () =>
      events.filter(
        (e) => e.operation_name === "recall_internal_message_denied",
      ).length,
    [events],
  );

  const successCount = events.length - deniedCount;

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
      summary.by_hour_of_day[0],
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

  const handleExportCsv = () => {
    if (events.length === 0) {
      toast.error("Dışa aktarılacak kayıt yok.");
      return;
    }
    const header = [
      "timestamp",
      "operation",
      "actor_id",
      "from_user",
      "from_department",
      "to_user",
      "to_department",
      "priority",
      "message_preview",
      "status",
      "elapsed_seconds",
    ];
    const rows = [header.map(csvEscape)];
    events.forEach((ev) => {
      const before = ev.before_snapshot || {};
      const after = ev.after_snapshot || {};
      rows.push(
        [
          ev.timestamp,
          ev.operation_name,
          ev.actor_id,
          before.from_user_name,
          before.from_department,
          before.to_user_name,
          before.to_department,
          before.priority,
          before.message_preview,
          ev.operation_name === "recall_internal_message_denied"
            ? "denied"
            : "recalled",
          after.elapsed_seconds,
        ].map(csvEscape),
      );
    });
    const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    downloadCsv(`recalled-messages-${ts}.csv`, rows);
  };

  const handleApply = () => {
    // Force-commit any pending sender_id debounce.
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setApplied({ ...draft });
  };

  const refreshButton = (
    <Button
      data-testid="refresh-btn"
      variant="outline"
      size="sm"
      onClick={loadReport}
      disabled={loading}
    >
      <RefreshCw
        className={`w-4 h-4 mr-1.5 ${loading ? "animate-spin" : ""}`}
      />
      Yenile
    </Button>
  );

  const exportButton = (
    <Button
      data-testid="export-csv-btn"
      variant="outline"
      size="sm"
      onClick={handleExportCsv}
      disabled={loading || events.length === 0}
    >
      <Download className="w-4 h-4 mr-1.5" />
      CSV indir
    </Button>
  );

  const backButton = (
    <Button
      variant="outline"
      size="sm"
      onClick={() => navigate(-1)}
    >
      <ArrowLeft className="w-4 h-4 mr-1.5" />
      Geri
    </Button>
  );

  return (
    <div
      data-testid="recalled-messages-report-page"
      className="max-w-7xl mx-auto px-4 py-4 space-y-4"
    >
      <PageHeader
        icon={Undo2}
        title="Geri Alınan Mesajlar"
        subtitle="5 dakikalık pencere içinde geri çekilen iç mesajların denetim raporu"
        actions={
          <>
            {backButton}
            {exportButton}
            {refreshButton}
          </>
        }
      />

      {/* Filtreler */}
      <Card data-testid="report-filters">
        <CardContent className="p-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2 items-end">
            <div>
              <label className="text-[11px] text-slate-500 block mb-1">
                Başlangıç
              </label>
              <Input
                data-testid="filter-start-date"
                type="date"
                value={draft.start_date}
                onChange={(e) =>
                  setDraft((p) => ({ ...p, start_date: e.target.value }))
                }
                className="h-8 text-xs"
              />
            </div>
            <div>
              <label className="text-[11px] text-slate-500 block mb-1">
                Bitiş
              </label>
              <Input
                data-testid="filter-end-date"
                type="date"
                value={draft.end_date}
                onChange={(e) =>
                  setDraft((p) => ({ ...p, end_date: e.target.value }))
                }
                className="h-8 text-xs"
              />
            </div>
            <div>
              <label className="text-[11px] text-slate-500 block mb-1">
                Geri alan kullanıcı kimliği
              </label>
              <Input
                data-testid="filter-sender-id"
                placeholder="user-..."
                value={draft.sender_id}
                onChange={(e) =>
                  setDraft((p) => ({ ...p, sender_id: e.target.value }))
                }
                className="h-8 text-xs"
              />
            </div>
            <div>
              <label className="text-[11px] text-slate-500 block mb-1">
                Orijinal öncelik
              </label>
              <select
                data-testid="filter-priority"
                value={draft.priority}
                onChange={(e) =>
                  setDraft((p) => ({ ...p, priority: e.target.value }))
                }
                className="bg-white border border-slate-300 rounded text-xs px-2 h-8 text-slate-700 w-full"
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
                onClick={handleApply}
                className="w-full h-8 text-xs"
              >
                Uygula
              </Button>
            </div>
          </div>
          <div className="mt-2 flex items-center gap-2">
            <input
              data-testid="filter-include-denied"
              id="filter-include-denied"
              type="checkbox"
              checked={draft.include_denied}
              onChange={(e) =>
                setDraft((p) => ({ ...p, include_denied: e.target.checked }))
              }
              className="h-3 w-3"
            />
            <label
              htmlFor="filter-include-denied"
              className="text-[11px] text-slate-700 cursor-pointer"
            >
              Süre dolduğu için reddedilen geri alma denemelerini de göster
            </label>
          </div>
        </CardContent>
      </Card>

      {error && (
        <div
          data-testid="report-error"
          className="bg-rose-50 border border-rose-200 text-rose-800 text-xs rounded p-2"
        >
          {error}
        </div>
      )}

      {/* Özet kartlar — Sprint A KpiCard intent palette */}
      <div
        data-testid="summary-cards"
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3"
      >
        <KpiCard
          data-testid="card-total"
          icon={Inbox}
          intent="info"
          label="Toplam geri alma"
          value={total}
          sub={
            applied.include_denied
              ? `${successCount} başarılı · ${deniedCount} reddedilen (bu sayfa)`
              : "Başarılı geri çekme kayıtları"
          }
        />
        <KpiCard
          data-testid="card-urgent-recalls"
          icon={AlertTriangle}
          intent={urgentCount > 0 ? "warning" : "neutral"}
          label="Acilden geri alınan"
          value={urgentCount}
          sub="Öncelik = Acil olan kayıtlar"
        />
        <KpiCard
          data-testid="card-peak-hour"
          icon={History}
          intent="danger"
          label="En yoğun saat (UTC)"
          value={peakHour ? `${peakHour.hour}:00` : "—"}
          sub={peakHour ? `${peakHour.count} kayıt` : "Veri yok"}
        />
        <KpiCard
          data-testid="card-top-sender"
          icon={TrendingUp}
          intent="neutral"
          label="En çok geri alan"
          value={topSender ? topSender.sender_name || topSender.sender_id : "—"}
          sub={
            topSender
              ? `${topSender.sender_department || "—"} · ${topSender.count} geri alma`
              : "Veri yok"
          }
        />
      </div>

      {applied.include_denied && (
        <div
          data-testid="denied-summary-banner"
          className="text-xs bg-rose-50 border border-rose-200 text-rose-800 rounded p-2"
        >
          Bu sayfadaki kayıtların{" "}
          <strong data-testid="denied-count-inline">{deniedCount}</strong>{" "}
          tanesi süre dolduğu için reddedilen geri alma denemesidir
          (5 dakikalık pencere aşıldı).
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Olay tablosu */}
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-slate-700 flex items-center gap-2">
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
                  <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
                </div>
              ) : events.length === 0 ? (
                <div
                  data-testid="empty-state"
                  className="text-center py-8 text-slate-500 text-sm"
                >
                  Seçili filtrelerle eşleşen geri alma kaydı yok.
                </div>
              ) : (
                <ul data-testid="event-list" className="divide-y divide-slate-100">
                  {events.map((ev, idx) => {
                    const id = ev.id || `${ev.timestamp}-${idx}`;
                    const before = ev.before_snapshot || {};
                    const after = ev.after_snapshot || {};
                    const expanded = expandedIds.has(id);
                    const recipient =
                      before.to_user_name || before.to_department || "—";
                    const isUrgent = before.priority === "urgent";
                    const isDenied =
                      ev.operation_name === "recall_internal_message_denied";
                    return (
                      <li
                        key={id}
                        data-testid={`event-row-${id}`}
                        className="py-2"
                      >
                        <button
                          type="button"
                          onClick={() => toggleExpand(id)}
                          className="w-full flex items-start gap-2 text-left hover:bg-slate-50 rounded px-1 py-1"
                        >
                          {expanded ? (
                            <ChevronDown className="w-3 h-3 mt-1 text-slate-400" />
                          ) : (
                            <ChevronRight className="w-3 h-3 mt-1 text-slate-400" />
                          )}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap text-xs">
                              <span className="text-slate-500 flex items-center gap-1">
                                <Clock className="w-3 h-3" />
                                {formatTs(ev.timestamp)}
                              </span>
                              <span className="font-semibold text-slate-900 flex items-center gap-1">
                                <UserIcon className="w-3 h-3" />
                                {before.from_user_name || ev.actor_id}
                              </span>
                              {before.from_department && (
                                <StatusBadge intent="neutral">
                                  {before.from_department}
                                </StatusBadge>
                              )}
                              <span className="text-slate-400">→</span>
                              <span className="text-slate-700 flex items-center gap-1">
                                <Building2 className="w-3 h-3" />
                                {recipient}
                              </span>
                              {isUrgent && (
                                <StatusBadge
                                  intent="warning"
                                  data-testid={`badge-urgent-${id}`}
                                >
                                  Acil
                                </StatusBadge>
                              )}
                              {isDenied ? (
                                <StatusBadge
                                  intent="danger"
                                  data-testid={`badge-denied-${id}`}
                                >
                                  Reddedildi (süre doldu
                                  {typeof after.elapsed_seconds === "number"
                                    ? ` · ${Math.round(
                                        after.elapsed_seconds / 60,
                                      )} dk`
                                    : ""}
                                  )
                                </StatusBadge>
                              ) : (
                                <StatusBadge
                                  intent="success"
                                  data-testid={`badge-recalled-${id}`}
                                >
                                  Geri alındı
                                </StatusBadge>
                              )}
                            </div>
                            {before.message_preview && (
                              <p className="text-xs text-slate-600 mt-1 truncate">
                                {before.message_preview}
                              </p>
                            )}
                          </div>
                        </button>
                        {expanded && (
                          <div
                            data-testid={`event-detail-${id}`}
                            className="mt-2 ml-5 bg-slate-50 border border-slate-200 rounded p-3"
                          >
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                              <div>
                                <p className="text-[11px] text-slate-500 mb-1 font-semibold uppercase tracking-wide">
                                  Orijinal mesaj
                                </p>
                                <DetailGrid data={before} />
                              </div>
                              <div>
                                <p className="text-[11px] text-slate-500 mb-1 font-semibold uppercase tracking-wide">
                                  Geri alma eylemi
                                </p>
                                <DetailGrid data={after} />
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
                  className="flex items-center justify-between mt-3 pt-2 border-t border-slate-100 text-xs text-slate-600"
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
              <CardTitle className="text-sm text-slate-700 flex items-center gap-2">
                <UserIcon className="w-4 h-4" /> Geri alan sıralaması
              </CardTitle>
            </CardHeader>
            <CardContent>
              {summary.by_sender.length === 0 ? (
                <p className="text-xs text-slate-500">Veri yok</p>
              ) : (
                summary.by_sender.map((s) => (
                  <div
                    key={s.sender_id}
                    data-testid={`sender-${s.sender_id}`}
                    className="flex justify-between items-center py-1 text-xs"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-slate-800 truncate">
                        {s.sender_name || s.sender_id}
                      </p>
                      {s.sender_department && (
                        <p className="text-[10px] text-slate-500">
                          {s.sender_department}
                        </p>
                      )}
                    </div>
                    <span className="text-slate-900 font-semibold ml-2">
                      {s.count}
                    </span>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card data-testid="card-by-priority">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-slate-700 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" /> Önceliğe göre
              </CardTitle>
            </CardHeader>
            <CardContent>
              {summary.by_priority.length === 0 ? (
                <p className="text-xs text-slate-500">Veri yok</p>
              ) : (
                summary.by_priority.map((p) => (
                  <div
                    key={p.priority}
                    data-testid={`priority-${p.priority}`}
                    className="flex justify-between items-center py-1 text-xs"
                  >
                    <span className="text-slate-700 capitalize">
                      {p.priority === "urgent"
                        ? "Acil"
                        : p.priority === "normal"
                        ? "Normal"
                        : p.priority}
                    </span>
                    <span className="text-slate-900 font-semibold">
                      {p.count}
                    </span>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card data-testid="card-by-hour">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-slate-700 flex items-center gap-2">
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
  );
}
