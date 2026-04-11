import React, { useEffect, useState } from "react";
import Layout from "@/components/Layout";
import axios from "axios";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Building2, TrendingUp, Percent, AlertTriangle, RefreshCw } from "lucide-react";
import { useTranslation } from 'react-i18next';

const CorporateContractsDashboard = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    try {
      setLoading(true);
      const res = await axios.get("/corporate/contracts/utilization");
      setData(res.data);
    } catch (err) {
      console.error("Failed to load corporate contracts utilization", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const summary = data?.summary || {};
  const contracts = data?.contracts || [];

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="reports">
      <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-4">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <h1 className="text-xl md:text-2xl font-bold flex items-center gap-2">
              <Building2 className="w-5 h-5 text-blue-600" />
              {t('nav.corporate')} Utilization
            </h1>
            <p className="text-xs md:text-sm text-gray-600">
              Kurumsal anlaşmalarınız için taahhüt edilen oda geceleri ve gerçekleşen performansın özeti.
            </p>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={loadData}
            disabled={loading}
          >
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} />
            Yenile
          </Button>
        </div>

        {/* Summary cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="text-xs text-gray-500 mb-1">Kontratlı Şirket Sayısı</div>
              <div className="text-2xl font-bold">{summary.total_companies ?? "-"}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-xs text-gray-500 mb-1">Taahhüt Edilen Oda Gecesi</div>
              <div className="text-2xl font-bold text-blue-700">{summary.total_committed_nights ?? 0}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-xs text-gray-500 mb-1">Gerçekleşen Oda Gecesi</div>
              <div className="text-2xl font-bold text-green-700">{summary.total_actual_nights ?? 0}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 flex items-center justify-between">
              <div>
                <div className="text-xs text-gray-500 mb-1">Ortalama Kullanım (%)</div>
                <div className="text-2xl font-bold text-purple-700">
                  {summary.avg_utilization_pct != null ? `${summary.avg_utilization_pct}%` : "-"}
                </div>
              </div>
              <Percent className="w-7 h-7 text-purple-500" />
            </CardContent>
          </Card>
        </div>

        {/* Contracts table */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <TrendingUp className="w-4 h-4" />
              Contract Bazlı Performans ({contracts.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="py-10 text-center text-gray-500 text-sm flex items-center justify-center gap-2">
                <RefreshCw className="w-5 h-5 animate-spin" />
                Yükleniyor...
              </div>
            ) : contracts.length === 0 ? (
              <div className="py-10 text-center text-gray-500 text-sm">
                Henüz room_nights_commitment alanı dolu aktif şirket bulunmuyor.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs md:text-sm">
                  <thead>
                    <tr className="border-b text-left text-gray-600">
                      <th className="py-2 pr-3">Şirket</th>
                      <th className="py-2 pr-3">Kod</th>
                      <th className="py-2 pr-3 text-right">Taahhüt Gece</th>
                      <th className="py-2 pr-3 text-right">Gerçek Gece</th>
                      <th className="py-2 pr-3 text-right">Kullanım %</th>
                      <th className="py-2 pr-3 text-right">{t("finance.revenue")}</th>
                      <th className="py-2 pr-3 text-right">Durum</th>
                    </tr>
                  </thead>
                  <tbody>
                    {contracts.map((c) => {
                      const utilization = c.utilization_pct ?? 0;
                      const isUnderUtil = c.status === "under_utilized";
                      return (
                        <tr key={c.company_id} className="border-b last:border-0 hover:bg-gray-50">
                          <td className="py-2 pr-3 whitespace-nowrap">
                            <div className="font-medium text-gray-900 flex items-center gap-1">
                              {c.company_name}
                            </div>
                            <div className="text-[11px] text-gray-500">{c.contact_person || c.contact_email}</div>
                          </td>
                          <td className="py-2 pr-3 text-[11px] text-gray-600">
                            {c.corporate_code || "-"}
                          </td>
                          <td className="py-2 pr-3 text-right">{c.room_nights_commitment}</td>
                          <td className="py-2 pr-3 text-right">{c.actual_room_nights}</td>
                          <td className="py-2 pr-3 text-right">
                            <div className="flex items-center gap-2 justify-end">
                              <span
                                className={`text-[11px] font-medium ${
                                  isUnderUtil ? 'text-amber-700' : 'text-green-700'
                                }`}
                              >
                                {utilization}%
                              </span>
                              <div className="w-24">
                                <Progress
                                  value={utilization}
                                  className={isUnderUtil ? 'h-1 bg-amber-100' : 'h-1 bg-emerald-100'}
                                />
                              </div>
                            </div>
                          </td>
                          <td className="py-2 pr-3 text-right">
                            ₺{c.revenue != null ? c.revenue.toFixed ? c.revenue.toFixed(0) : c.revenue : "-"}
                          </td>
                          <td className="py-2 pr-3 text-right">
                            <Badge className={isUnderUtil ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}>
                              {isUnderUtil ? "UNDER" : "HEALTHY"}
                            </Badge>
                          </td>
                        </tr>
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

export default CorporateContractsDashboard;
