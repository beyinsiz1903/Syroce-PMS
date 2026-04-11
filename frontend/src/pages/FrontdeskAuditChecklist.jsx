import React, { useState, useEffect } from "react";
import Layout from "@/components/Layout";
import axios from "axios";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Calendar, AlertTriangle, CheckCircle, RefreshCw, Users, FileText, LogOut, DoorOpen } from "lucide-react";
import { useTranslation } from 'react-i18next';

const FrontdeskAuditChecklist = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadChecklist = async () => {
    try {
      setLoading(true);
      const res = await axios.get("/frontdesk/audit-checklist");
      setData(res.data);
    } catch (err) {
      console.error("Failed to load frontdesk audit checklist", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadChecklist();
  }, []);

  const summary = data?.summary || {};

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="pms">
      <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-4">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <h1 className="text-xl md:text-2xl font-bold flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-600" />
              Audit Öncesi Checklist
            </h1>
            <p className="text-xs md:text-sm text-gray-600">
              Night audit öncesi front desk ve finance ekiplerinin hızlıca kontrol etmesi gereken kritik öğeler.
            </p>
          </div>
          <div className="flex items-center gap-3 text-xs md:text-sm text-gray-600">
            <div className="flex items-center gap-1">
              <Calendar className="w-4 h-4" />
              <span>{data?.date || ""}</span>
            </div>
            <Button size="sm" variant="outline" onClick={loadChecklist} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} />
              Yenile
            </Button>
          </div>
        </div>

        {/* Summary cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4 flex items-center justify-between">
              <div>
                <div className="text-xs text-gray-500 mb-1">Check-in Bekleyenler</div>
                <div className="text-xl font-semibold">{summary.unchecked_in_count ?? "-"}</div>
                <div className="text-[11px] text-gray-500 mt-1">
                  VIP: {summary.vip_unchecked_in ?? 0}
                </div>
              </div>
              <Users className="w-7 h-7 text-blue-600" />
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4 flex items-center justify-between">
              <div>
                <div className="text-xs text-gray-500 mb-1">Open Folios</div>
                <div className="text-xl font-semibold">{summary.open_folio_count ?? "-"}</div>
                <div className="text-[11px] text-gray-500 mt-1">
                  Toplam Bakiye: €
                  {summary.total_open_balance != null
                    ? summary.total_open_balance.toFixed
                      ? summary.total_open_balance.toFixed(2)
                      : summary.total_open_balance
                    : "-"}
                </div>
              </div>
              <FileText className="w-7 h-7 text-indigo-600" />
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4 flex items-center justify-between">
              <div>
                <div className="text-xs text-gray-500 mb-1">Unbalanced Folios</div>
                <div className="text-xl font-semibold">{summary.unbalanced_folio_count ?? "-"}</div>
              </div>
              <AlertTriangle className="w-7 h-7 text-red-500" />
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4 flex items-center justify-between">
              <div>
                <div className="text-xs text-gray-500 mb-1">Overdue Departures</div>
                <div className="text-xl font-semibold">{summary.overdue_departures_count ?? "-"}</div>
              </div>
              <DoorOpen className="w-7 h-7 text-amber-600" />
            </CardContent>
          </Card>
        </div>

        {/* Sections */}
        <div className="space-y-6">
          {/* Unchecked-in Arrivals */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Users className="w-4 h-4 text-blue-600" />
                Check-in Bekleyen Varışlar ({data?.unchecked_in_arrivals?.length || 0})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="py-8 text-center text-gray-500 text-sm">{t("common.loading")}</div>
              ) : !data?.unchecked_in_arrivals?.length ? (
                <div className="py-8 text-center text-green-600 text-sm flex items-center justify-center gap-2">
                  <CheckCircle className="w-4 h-4" />
                  Tüm bugünkü varışlar için check-in tamamlanmış görünüyor.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs md:text-sm">
                    <thead>
                      <tr className="border-b text-left text-gray-600">
                        <th className="py-2 pr-3">Rezervasyon</th>
                        <th className="py-2 pr-3">Misafir</th>
                        <th className="py-2 pr-3">Oda</th>
                        <th className="py-2 pr-3">VIP</th>
                        <th className="py-2 pr-3">Check-in</th>
                        <th className="py-2 pr-3">Check-out</th>
                        <th className="py-2 pr-3">Kanal</th>
                        <th className="py-2 pr-3">Notlar</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.unchecked_in_arrivals.map((a) => (
                        <tr key={a.booking_id} className="border-b last:border-0 hover:bg-gray-50">
                          <td className="py-2 pr-3 font-mono text-[11px]">{a.reservation_number || a.booking_id}</td>
                          <td className="py-2 pr-3">{a.guest_name}</td>
                          <td className="py-2 pr-3">{a.room_number || "-"}</td>
                          <td className="py-2 pr-3">
                            {a.vip_status ? (
                              <Badge className="bg-yellow-100 text-yellow-700 text-[10px]">VIP</Badge>
                            ) : (
                              <span className="text-[11px] text-gray-400">Normal</span>
                            )}
                          </td>
                          <td className="py-2 pr-3 text-[11px]">
                            {a.check_in ? new Date(a.check_in).toLocaleString("tr-TR") : "-"}
                          </td>
                          <td className="py-2 pr-3 text-[11px]">
                            {a.check_out ? new Date(a.check_out).toLocaleString("tr-TR") : "-"}
                          </td>
                          <td className="py-2 pr-3 text-[11px]">{a.ota_channel || "-"}</td>
                          <td className="py-2 pr-3 text-[11px] text-gray-600 max-w-xs truncate" title={a.special_requests || ""}>
                            {a.special_requests || "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Open Folios */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <FileText className="w-4 h-4 text-indigo-600" />
                Open Folios ({data?.open_folios?.length || 0})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="py-8 text-center text-gray-500 text-sm">{t("common.loading")}</div>
              ) : !data?.open_folios?.length ? (
                <div className="py-8 text-center text-green-600 text-sm flex items-center justify-center gap-2">
                  <CheckCircle className="w-4 h-4" />
                  Açık folio bulunmuyor.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs md:text-sm">
                    <thead>
                      <tr className="border-b text-left text-gray-600">
                        <th className="py-2 pr-3">Folio</th>
                        <th className="py-2 pr-3">Tip</th>
                        <th className="py-2 pr-3">Sahip</th>
                        <th className="py-2 pr-3 text-right">Bakiye</th>
                        <th className="py-2 pr-3">Oluşturma</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.open_folios.map((f) => (
                        <tr key={f.folio_id} className="border-b last:border-0 hover:bg-gray-50">
                          <td className="py-2 pr-3 font-mono text-[11px]">{f.folio_number || f.folio_id}</td>
                          <td className="py-2 pr-3 text-[11px] capitalize">{f.folio_type}</td>
                          <td className="py-2 pr-3">{f.owner_name || "-"}</td>
                          <td className="py-2 pr-3 text-right">
                            €{f.balance != null ? f.balance.toFixed ? f.balance.toFixed(2) : f.balance : "-"}
                          </td>
                          <td className="py-2 pr-3 text-[11px]">
                            {f.created_at ? new Date(f.created_at).toLocaleDateString("tr-TR") : "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Unbalanced Folios */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-red-500" />
                Unbalanced Folios ({data?.unbalanced_folios?.length || 0})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="py-8 text-center text-gray-500 text-sm">{t("common.loading")}</div>
              ) : !data?.unbalanced_folios?.length ? (
                <div className="py-8 text-center text-green-600 text-sm flex items-center justify-center gap-2">
                  <CheckCircle className="w-4 h-4" />
                  Şüpheli bakiye / dengesiz folio bulunmuyor.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs md:text-sm">
                    <thead>
                      <tr className="border-b text-left text-gray-600">
                        <th className="py-2 pr-3">Folio</th>
                        <th className="py-2 pr-3">Sahip</th>
                        <th className="py-2 pr-3 text-right">Bakiye</th>
                        <th className="py-2 pr-3 text-right">Gün</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.unbalanced_folios.map((f) => (
                        <tr key={f.folio_id} className="border-b last:border-0 hover:bg-gray-50">
                          <td className="py-2 pr-3 font-mono text-[11px]">{f.folio_number || f.folio_id}</td>
                          <td className="py-2 pr-3">{f.owner_name || "-"}</td>
                          <td className="py-2 pr-3 text-right">
                            €{f.balance != null ? f.balance.toFixed ? f.balance.toFixed(2) : f.balance : "-"}
                          </td>
                          <td className="py-2 pr-3 text-right">{f.days_open ?? "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Overdue Departures */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <DoorOpen className="w-4 h-4 text-amber-600" />
                Overdue Departures ({data?.overdue_departures?.length || 0})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="py-8 text-center text-gray-500 text-sm">{t("common.loading")}</div>
              ) : !data?.overdue_departures?.length ? (
                <div className="py-8 text-center text-green-600 text-sm flex items-center justify-center gap-2">
                  <CheckCircle className="w-4 h-4" />
                  Bugün için gecikmiş check-out bulunmuyor.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs md:text-sm">
                    <thead>
                      <tr className="border-b text-left text-gray-600">
                        <th className="py-2 pr-3">Rezervasyon</th>
                        <th className="py-2 pr-3">Misafir</th>
                        <th className="py-2 pr-3">Oda</th>
                        <th className="py-2 pr-3">Check-out</th>
                        <th className="py-2 pr-3 text-right">Bakiye</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.overdue_departures.map((o) => (
                        <tr key={o.booking_id} className="border-b last:border-0 hover:bg-gray-50">
                          <td className="py-2 pr-3 font-mono text-[11px]">{o.reservation_number || o.booking_id}</td>
                          <td className="py-2 pr-3">{o.guest_name || "-"}</td>
                          <td className="py-2 pr-3">{o.room_number || "-"}</td>
                          <td className="py-2 pr-3 text-[11px]">
                            {o.check_out ? new Date(o.check_out).toLocaleString("tr-TR") : "-"}
                          </td>
                          <td className="py-2 pr-3 text-right">
                            €{o.balance != null ? o.balance.toFixed ? o.balance.toFixed(2) : o.balance : "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </Layout>
  );
};

export default FrontdeskAuditChecklist;
