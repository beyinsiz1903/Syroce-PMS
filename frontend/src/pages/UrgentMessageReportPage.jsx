/**
 * Task #26 — Acil Mesaj Raporu
 *
 * Yöneticiler için tarih aralığı + gönderen + alıcı departman
 * filtreleriyle acil mesaj kullanımını özetler. Her satırdan
 * audit_logs'tan dönen ham `after_snapshot` detayına genişletilebilir.
 *
 * Endpoint: GET /audit/urgent-message-report  (axios.defaults.baseURL
 * zaten `/api` ile bittiği için yol göreli yazılır.)
 */
import { useState, useEffect, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";

import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  ArrowLeft, AlertTriangle, RefreshCw, Loader2, ChevronDown,
  ChevronRight, Clock, User as UserIcon, Building2,
} from "lucide-react";
import { useTranslation } from 'react-i18next';

const HOURS_24 = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, "0"));

function emptySummary() {
  return { by_sender: [], by_recipient_department: [], by_hour_of_day: [] };
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
  const { t } = useTranslation();
  const pct = max > 0 ? Math.round((count / max) * 100) : 0;
  return (
    <div
      data-testid={`hour-bar-${hour}`}
      className="flex items-center gap-2 text-[11px]"
    >
      <span className="w-6 font-mono text-gray-500">{hour}</span>
      <div className="flex-1 bg-gray-100 rounded h-3 overflow-hidden">
        <div
          className="bg-amber-500 h-full"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 text-right text-gray-700 font-semibold">{count}</span>
    </div>
  );
}

export default function UrgentMessageReportPage({ user, tenant, onLogout }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [filters, setFilters] = useState({
    start_date: "",
    end_date: "",
    sender_id: "",
    recipient_department: "",
  });
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
      // ISO datetime'a normalize et — input type=date "YYYY-MM-DD" döner.
      if (filters.start_date) params.start_date = `${filters.start_date}T00:00:00`;
      if (filters.end_date) params.end_date = `${filters.end_date}T23:59:59`;
      if (filters.sender_id) params.sender_id = filters.sender_id;
      if (filters.recipient_department) {
        params.recipient_department = filters.recipient_department;
      }
      const res = await axios.get("/audit/urgent-message-report", { params });
      const data = res.data || {};
      setEvents(Array.isArray(data.events) ? data.events : []);
      setTotal(typeof data.total === "number" ? data.total : 0);
      setSummary({
        by_sender: data.summary?.by_sender || [],
        by_recipient_department: data.summary?.by_recipient_department || [],
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
  }, [filters]);

  useEffect(() => { loadReport(); }, [loadReport]);

  const topSender = summary.by_sender[0];
  const topDept = summary.by_recipient_department[0];

  // by_hour_of_day yalnızca dolu saat kovalarını döner. UI'da 0-23
  // saatlerin tamamını gösterip yokları 0 ile doldurmak okumayı
  // kolaylaştırır.
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
    <>
      <div
        data-testid="urgent-message-report-page"
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
              {t('cm.pages_UrgentMessageReportPage.yenile')}
            </Button>
          </div>

          {/* Filtreler */}
          <Card data-testid="report-filters" className="mb-4">
            <CardContent className="p-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2 items-end">
                <div>
                  <label className="text-[11px] text-gray-500 block mb-1">
                    {t('cm.pages_UrgentMessageReportPage.baslangic')}
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
                    {t('cm.pages_UrgentMessageReportPage.bitis')}
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
                    {t('cm.pages_UrgentMessageReportPage.gonderen_kullanici_kimligi')}
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
                    {t('cm.pages_UrgentMessageReportPage.alici_departman')}
                  </label>
                  <select
                    data-testid="filter-recipient-department"
                    value={filters.recipient_department}
                    onChange={(e) =>
                      setFilters((p) => ({
                        ...p,
                        recipient_department: e.target.value,
                      }))
                    }
                    className="bg-white border border-gray-300 rounded text-xs px-2 h-8 text-gray-700 w-full"
                  >
                    <option value="">{t('cm.pages_UrgentMessageReportPage.tumu')}</option>
                    <option value="Reception">Reception</option>
                    <option value="Housekeeping">Housekeeping</option>
                    <option value="Maintenance">Maintenance</option>
                    <option value="Finance">Finance</option>
                    <option value="Management">Management</option>
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
                <p className="text-xs text-gray-500">{t('cm.pages_UrgentMessageReportPage.toplam_acil_mesaj')}</p>
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
                <p className="text-xs text-gray-500">{t('cm.pages_UrgentMessageReportPage.en_yogun_saat')}</p>
                <p
                  data-testid="card-peak-hour"
                  className="text-2xl font-bold text-amber-600"
                >
                  {peakHour ? `${peakHour.hour}:00` : "—"}
                </p>
                {peakHour && (
                  <p className="text-[11px] text-gray-500">
                    {peakHour.count} mesaj
                  </p>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500">{t('cm.pages_UrgentMessageReportPage.en_cok_gonderen')}</p>
                <p
                  data-testid="card-top-sender"
                  className="text-sm font-bold text-gray-900 truncate"
                >
                  {topSender ? topSender.sender_name || topSender.sender_id : "—"}
                </p>
                {topSender && (
                  <p className="text-[11px] text-gray-500">
                    {topSender.sender_department || "—"} · {topSender.count}{" "}
                    mesaj
                  </p>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500">{t('cm.pages_UrgentMessageReportPage.en_cok_alan_departman')}</p>
                <p
                  data-testid="card-top-dept"
                  className="text-sm font-bold text-gray-900 truncate"
                >
                  {topDept ? topDept.department : "—"}
                </p>
                {topDept && (
                  <p className="text-[11px] text-gray-500">
                    {topDept.count} mesaj
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
                    <AlertTriangle className="w-4 h-4 text-amber-600" />
                    Acil Mesajlar
                    <span className="text-[10px] bg-amber-50 text-amber-700 border border-amber-200 rounded px-1.5 py-0.5">
                      {events.length} {t('cm.pages_UrgentMessageReportPage.kayit')}
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
                      {t('cm.pages_UrgentMessageReportPage.secili_filtrelerle_eslesen_acil_mesaj_ka')}
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
                                    {snap.from_user_name || ev.actor_id}
                                  </span>
                                  {snap.from_department && (
                                    <span className="text-[10px] bg-gray-100 text-gray-700 border border-gray-200 rounded px-1.5">
                                      {snap.from_department}
                                    </span>
                                  )}
                                  <span className="text-gray-400">→</span>
                                  <span className="text-gray-700 flex items-center gap-1">
                                    <Building2 className="w-3 h-3" />
                                    {snap.to_department ||
                                      snap.to_user_name ||
                                      "—"}
                                  </span>
                                </div>
                                {snap.message_preview && (
                                  <p className="text-xs text-gray-600 mt-1 truncate">
                                    {snap.message_preview}
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
                                  {JSON.stringify(snap, null, 2)}
                                </pre>
                              </div>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Yan panel: özetler */}
            <div className="space-y-4">
              <Card data-testid="card-by-sender">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-700 flex items-center gap-2">
                    <UserIcon className="w-4 h-4" /> {t('cm.pages_UrgentMessageReportPage.gonderen_siralamasi')}
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

              <Card data-testid="card-by-department">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-700 flex items-center gap-2">
                    <Building2 className="w-4 h-4" /> {t('cm.pages_UrgentMessageReportPage.alici_departmanlar')}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {summary.by_recipient_department.length === 0 ? (
                    <p className="text-xs text-gray-500">Veri yok</p>
                  ) : (
                    summary.by_recipient_department.map((d) => (
                      <div
                        key={d.department}
                        data-testid={`dept-${d.department}`}
                        className="flex justify-between items-center py-1 text-xs"
                      >
                        <span className="text-gray-700">{d.department}</span>
                        <span className="text-gray-900 font-semibold">
                          {d.count}
                        </span>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>

              <Card data-testid="card-by-hour">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-700 flex items-center gap-2">
                    <Clock className="w-4 h-4" /> {t('cm.pages_UrgentMessageReportPage.saat_dagilimi_utc')}
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
    </>
  );
}
