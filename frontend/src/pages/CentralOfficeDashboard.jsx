import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import axios from 'axios';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { useTranslation } from 'react-i18next';
const BACKEND = "";
const COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899'];
export default function CentralOfficeDashboard({
  user,
  tenant,
  onLogout
}) {
  const {
    t
  } = useTranslation();
  const [dashboard, setDashboard] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [revenue, setRevenue] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const headers = {};
  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [dashRes, compRes, revRes, alertRes] = await Promise.all([axios.get(`/central-office/dashboard`, {
        headers
      }), axios.get(`/central-office/occupancy-comparison`, {
        headers
      }), axios.get(`/central-office/revenue-report`, {
        headers
      }), axios.get(`/central-office/alerts`, {
        headers
      })]);
      setDashboard(dashRes.data);
      setComparison(compRes.data);
      setRevenue(revRes.data);
      setAlerts(alertRes.data.alerts || []);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  useEffect(() => {
    fetchAll();
  }, []);
  const kpi = dashboard?.chain_kpi;
  return <>
      <div className="p-6 space-y-6">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold">Merkez Ofis Dashboard</h1>
            <p className="text-gray-500">Zincir genelinde konsolide raporlama ve KPI</p>
          </div>
          <Button variant="outline" onClick={fetchAll} disabled={loading}>
            {loading ? 'Yükleniyor...' : 'Yenile'}
          </Button>
        </div>

        {kpi && <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <Card>
              <CardContent className="pt-6 text-center">
                <div className="text-3xl font-bold text-blue-600">{kpi.total_properties}</div>
                <p className="text-sm text-gray-500">Toplam Otel</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6 text-center">
                <div className="text-3xl font-bold">{kpi.total_rooms}</div>
                <p className="text-sm text-gray-500">Toplam Oda</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6 text-center">
                <div className="text-3xl font-bold text-green-600">%{kpi.chain_occupancy_rate}</div>
                <p className="text-sm text-gray-500">Doluluk Orani</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6 text-center">
                <div className="text-3xl font-bold text-amber-600">{kpi.today_checkins}</div>
                <p className="text-sm text-gray-500">Bugunki Check-in</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6 text-center">
                <div className="text-3xl font-bold text-indigo-600">{kpi.total_guests}</div>
                <p className="text-sm text-gray-500">Toplam Misafir</p>
              </CardContent>
            </Card>
          </div>}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {comparison && <Card>
              <CardHeader><CardTitle>Doluluk Karsilastirmasi</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={comparison.comparison || []}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="property_name" tick={{
                  fontSize: 11
                }} />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="occupancy_rate" fill="#3B82F6" name="Doluluk %" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>}

          {revenue && <Card>
              <CardHeader><CardTitle>Gelir Dagilimi</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie data={revenue.properties || []} dataKey="total_revenue" nameKey="property_name" cx="50%" cy="50%" outerRadius={100} label>
                      {(revenue.properties || []).map((entry, i) => <Cell key={entry.id || i} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <p className="text-center text-lg font-bold mt-2">
                  Toplam: {revenue.total_chain_revenue?.toLocaleString('tr-TR')} TRY
                </p>
              </CardContent>
            </Card>}
        </div>

        {/* Property Breakdown */}
        {dashboard?.property_breakdown && <Card>
            <CardHeader><CardTitle>Otel Bazli Detay</CardTitle></CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="text-left p-3 text-sm">Otel</th>
                      <th className="text-right p-3 text-sm">Toplam Oda</th>
                      <th className="text-right p-3 text-sm">{t("housekeeping.occupied")}</th>
                      <th className="text-right p-3 text-sm">Bos</th>
                      <th className="text-right p-3 text-sm">Doluluk</th>
                      <th className="text-right p-3 text-sm">Check-in</th>
                      <th className="text-right p-3 text-sm">{t("finance.revenue")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dashboard.property_breakdown.map((p, i) => <tr key={p.id || i} className="border-t">
                        <td className="p-3 font-medium">{p.property_name}</td>
                        <td className="p-3 text-right">{p.total_rooms}</td>
                        <td className="p-3 text-right">{p.occupied_rooms}</td>
                        <td className="p-3 text-right">{p.available_rooms}</td>
                        <td className="p-3 text-right">
                          <Badge className={p.occupancy_rate > 70 ? 'bg-green-100 text-green-700' : p.occupancy_rate > 40 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'}>
                            %{p.occupancy_rate}
                          </Badge>
                        </td>
                        <td className="p-3 text-right">{p.today_checkins}</td>
                        <td className="p-3 text-right">{p.total_revenue?.toLocaleString('tr-TR')} TRY</td>
                      </tr>)}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>}

        {/* Alerts */}
        {alerts.length > 0 && <Card>
            <CardHeader><CardTitle>Uyarilar</CardTitle></CardHeader>
            <CardContent>
              <div className="space-y-2">
                {alerts.map((a, i) => <div key={a.id || i} className={`p-3 rounded-lg border ${a.severity === 'warning' ? 'bg-yellow-50 border-yellow-200' : 'bg-blue-50 border-blue-200'}`}>
                    <div className="flex justify-between">
                      <span className="font-medium">{a.property}</span>
                      <Badge variant="outline">{a.type}</Badge>
                    </div>
                    <p className="text-sm mt-1">{a.message}</p>
                  </div>)}
              </div>
            </CardContent>
          </Card>}
      </div>
    </>;
}