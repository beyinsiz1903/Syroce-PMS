import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import Layout from "@/components/Layout";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Calendar, RefreshCw, Filter, ArrowLeft, List } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from 'react-i18next';

const getDateOffset = (offsetDays) => {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().split("T")[0];
};

const NightAuditLogs = ({ user, tenant, onLogout }) => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [startDate, setStartDate] = useState(getDateOffset(-7));
  const [endDate, setEndDate] = useState(getDateOffset(0));
  const [status, setStatus] = useState("all");
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);

  const loadLogs = async () => {
    try {
      setLoading(true);
      const params = {
        limit: 100,
        skip: 0,
      };
      if (startDate) params.start_date = startDate;
      if (endDate) params.end_date = endDate;
      if (status && status !== "all") params.status = status;

      const res = await axios.get("/night-audit/history", { params });
      setLogs(res.data.logs || []);
      setStats(res.data.stats || null);
    } catch (err) {
      console.error("Failed to load night audit logs", err);
      toast.error("Night audit logları yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, []);

  const handleFilter = () => {
    loadLogs();
  };

  const renderStatusBadge = (value) => {
    const v = value || "unknown";
    let color = "bg-gray-100 text-gray-700";
    if (v === "completed") color = "bg-green-100 text-green-700";
    else if (v === "failed") color = "bg-red-100 text-red-700";
    else if (v === "in_progress") color = "bg-yellow-100 text-yellow-700";
    return <Badge className={color}>{v}</Badge>;
  };

  const renderActionLabel = (log) => {
    const action = log?.metadata?.action;
    if (!action) return "general";
    if (action === "no_show_handling") return "No-Show Handling";
    if (action === "post_room_charges") return "Room Charges Posting";
    return action;
  };

  const renderNoShowDetails = (log) => {
    const details = log?.metadata?.no_show_details;
    if (!details || !Array.isArray(details) || details.length === 0) return null;

    return (
      <div className="mt-3 border-t pt-3">
        <div className="text-xs font-semibold text-gray-700 mb-2">No-Show Detayları</div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b text-left text-gray-600">
                <th className="py-1 pr-2">Booking ID</th>
                <th className="py-1 pr-2">Room</th>
                <th className="py-1 pr-2">Folio</th>
                <th className="py-1 pr-2 text-right">Fee Posted</th>
                <th className="py-1 pr-2 text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {details.map((d) => (
                <tr key={d.booking_id} className="border-b last:border-0">
                  <td className="py-1 pr-2 font-mono text-[11px]">{d.booking_id}</td>
                  <td className="py-1 pr-2">{d.room_number || d.room_id || "-"}</td>
                  <td className="py-1 pr-2 font-mono text-[11px]">{d.folio_id || "-"}</td>
                  <td className="py-1 pr-2 text-right">{d.fee_posted ? t("common.yes") : t("common.no")}</td>
                  <td className="py-1 pr-2 text-right">
                    {d.fee_amount ? `€${d.fee_amount.toFixed(2)}` : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="reports">
      <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate("/reports")}
              className="hidden md:inline-flex"
            >
              <ArrowLeft className="w-4 h-4 mr-1" />
              Reports
            </Button>
            <div>
              <h1 className="text-xl md:text-2xl font-bold flex items-center gap-2">
                <List className="w-5 h-5 text-blue-600" />
                Night Audit Logları
              </h1>
              <p className="text-xs md:text-sm text-gray-600">
                Her night audit adımı için ayrıntılı kayıt: kim, ne zaman, hangi odada, hangi işlem.
              </p>
            </div>
          </div>
        </div>

        {/* Filters + Stats */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Card className="lg:col-span-2">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Filter className="w-4 h-4" />
                Filtreler
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
                <div>
                  <div className="flex items-center gap-1 text-xs text-gray-600 mb-1">
                    <Calendar className="w-3 h-3" />
                    Başlangıç Tarihi
                  </div>
                  <Input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="h-9"
                  />
                </div>
                <div>
                  <div className="flex items-center gap-1 text-xs text-gray-600 mb-1">
                    <Calendar className="w-3 h-3" />
                    Bitiş Tarihi
                  </div>
                  <Input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="h-9"
                  />
                </div>
                <div>
                  <div className="text-xs text-gray-600 mb-1">Durum</div>
                  <select
                    className="h-9 w-full border rounded-md text-sm px-2"
                    value={status}
                    onChange={(e) => setStatus(e.target.value)}
                  >
                    <option value="all">{t("common.all")}</option>
                    <option value="completed">Completed</option>
                    <option value="failed">Failed</option>
                    <option value="in_progress">In Progress</option>
                  </select>
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={loadLogs}
                  disabled={loading}
                >
                  <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} />
                  Yenile
                </Button>
                <Button size="sm" onClick={handleFilter} disabled={loading}>
                  <Filter className="w-4 h-4 mr-1" />
                  Uygula
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Özet İstatistikler</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs text-gray-700">
              {stats ? (
                <>
                  <div className="flex justify-between">
                    <span>Toplam Audit</span>
                    <span className="font-semibold">{stats.total_audits}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Başarılı</span>
                    <span className="font-semibold text-green-700">{stats.successful}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Başarısız</span>
                    <span className="font-semibold text-red-700">{stats.failed}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Success Rate</span>
                    <span className="font-semibold">{stats.success_rate}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Toplam Charges</span>
                    <span className="font-semibold">
                      €{stats.total_charges.toFixed ? stats.total_charges.toFixed(2) : stats.total_charges}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>İşlenen Oda Sayısı</span>
                    <span className="font-semibold">{stats.total_rooms}</span>
                  </div>
                </>
              ) : (
                <div className="text-gray-500 text-xs">Henüz istatistik bulunmuyor.</div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Logs table */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <List className="w-4 h-4" />
              Audit Log Kayıtları ({logs.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex items-center justify-center py-16 text-gray-500 text-sm">
                <RefreshCw className="w-5 h-5 mr-2 animate-spin" />
                Yükleniyor...
              </div>
            ) : logs.length === 0 ? (
              <div className="py-10 text-center text-gray-500 text-sm">
                Kayıt bulunamadı. Filtreleri değiştirip tekrar deneyin.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs md:text-sm">
                  <thead>
                    <tr className="border-b text-left text-gray-600">
                      <th className="py-2 pr-3">Tarih</th>
                      <th className="py-2 pr-3">Saat</th>
                      <th className="py-2 pr-3">Kullanıcı</th>
                      <th className="py-2 pr-3">Durum</th>
                      <th className="py-2 pr-3">Aksiyon</th>
                      <th className="py-2 pr-3 text-right">Oda</th>
                      <th className="py-2 pr-3 text-right">Charges</th>
                      <th className="py-2 pr-3 text-right">Tutar</th>
                      <th className="py-2 pr-3 text-right">Detay</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map((log) => {
                      const ts = log.timestamp ? new Date(log.timestamp) : null;
                      const dateStr = ts ? ts.toLocaleDateString("tr-TR") : "-";
                      const timeStr = ts ? ts.toLocaleTimeString("tr-TR") : "-";
                      const isExpanded = expandedId === log.id;

                      return (
                        <React.Fragment key={log.id}>
                          <tr className="border-b last:border-0 hover:bg-gray-50">
                            <td className="py-2 pr-3 whitespace-nowrap">{log.audit_date || dateStr}</td>
                            <td className="py-2 pr-3 whitespace-nowrap">{timeStr}</td>
                            <td className="py-2 pr-3 whitespace-nowrap">{log.user_name || log.user_id || "-"}</td>
                            <td className="py-2 pr-3">{renderStatusBadge(log.status)}</td>
                            <td className="py-2 pr-3 whitespace-nowrap">{renderActionLabel(log)}</td>
                            <td className="py-2 pr-3 text-right">{log.rooms_processed ?? "-"}</td>
                            <td className="py-2 pr-3 text-right">{log.charges_posted ?? "-"}</td>
                            <td className="py-2 pr-3 text-right">
                              {log.total_amount != null ? `€${log.total_amount.toFixed ? log.total_amount.toFixed(2) : log.total_amount}` : "-"}
                            </td>
                            <td className="py-2 pr-3 text-right">
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-xs"
                                onClick={() => setExpandedId(isExpanded ? null : log.id)}
                              >
                                {isExpanded ? t("common.close") : "Detay"}
                              </Button>
                            </td>
                          </tr>
                          {isExpanded && (
                            <tr className="bg-gray-50 border-b last:border-0">
                              <td colSpan={9} className="py-2 px-3">
                                <div className="text-xs text-gray-700">
                                  {/* No-show detayları var ise tablo olarak göster */}
                                  {renderNoShowDetails(log)}

                                  {/* Genel metadata JSON görünümü */}
                                  <div className="mt-3">
                                    <div className="text-[11px] font-semibold text-gray-600 mb-1">
                                      Ham Metadata
                                    </div>
                                    <pre className="bg-white border rounded p-2 text-[11px] overflow-x-auto max-h-48">
                                      {JSON.stringify(log.metadata || {}, null, 2)}
                                    </pre>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
};

export default NightAuditLogs;
