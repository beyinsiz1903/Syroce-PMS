import React, { useState, useEffect } from 'react';
import axios from 'axios';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Ban, TrendingDown, Building2, Radio, AlertTriangle } from 'lucide-react';

const REASON_COLORS = {
  misafir_gelmedi: { bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-700', bar: 'bg-amber-500' },
  iptal_gec_islendi: { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-700', bar: 'bg-blue-500' },
  overbooking: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700', bar: 'bg-red-500' },
  belirtilmemis: { bg: 'bg-gray-50', border: 'border-gray-200', text: 'text-gray-500', bar: 'bg-gray-400' },
};

const CHANNEL_COLORS = {
  direct: 'bg-emerald-500',
  booking: 'bg-blue-500',
  expedia: 'bg-yellow-500',
  airbnb: 'bg-rose-500',
  agency: 'bg-purple-500',
};

const NoShowAnalytics = ({ user, tenant, onLogout }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState('30');

  useEffect(() => {
    loadAnalytics();
  }, [period]);

  const loadAnalytics = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`/pms/no-show-analytics?days=${period}`);
      setData(res.data);
    } catch (err) {
      console.error('No-show analytics error:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading || !data) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="no-show-analytics">
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-amber-600" />
        </div>
      </Layout>
    );
  }

  const maxDaily = Math.max(...(data.daily?.map(d => d.count) || [1]), 1);
  const maxRoomType = Math.max(...(data.by_room_type?.map(r => r.count) || [1]), 1);
  const maxChannel = Math.max(...(data.by_channel?.map(c => c.count) || [1]), 1);

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="no-show-analytics">
      <div className="p-6 space-y-6 max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between" data-testid="noshow-analytics-header">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-100 flex items-center justify-center">
              <Ban className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">No-Show Analitik</h1>
              <p className="text-sm text-gray-500">Gelmeyen rezervasyon verileri ve gelir etkisi</p>
            </div>
          </div>
          <Select value={period} onValueChange={setPeriod}>
            <SelectTrigger className="w-36" data-testid="period-select">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">Son 7 gun</SelectItem>
              <SelectItem value="30">Son 30 gun</SelectItem>
              <SelectItem value="90">Son 90 gun</SelectItem>
              <SelectItem value="365">Son 1 yil</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card className="border-l-4 border-l-amber-500" data-testid="total-noshow-card">
            <CardContent className="pt-5 pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Toplam No-Show</p>
                  <p className="text-3xl font-bold text-gray-900 mt-1">{data.total_no_shows}</p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center">
                  <Ban className="w-5 h-5 text-amber-500" />
                </div>
              </div>
              <p className="text-xs text-gray-400 mt-2">Son {data.period_days} gun</p>
            </CardContent>
          </Card>

          <Card className="border-l-4 border-l-red-500" data-testid="revenue-loss-card">
            <CardContent className="pt-5 pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Gelir Kaybi</p>
                  <p className="text-3xl font-bold text-red-600 mt-1">{data.total_revenue_loss.toLocaleString('tr-TR')} TL</p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-red-50 flex items-center justify-center">
                  <TrendingDown className="w-5 h-5 text-red-500" />
                </div>
              </div>
              <p className="text-xs text-gray-400 mt-2">Kaybedilen potansiyel gelir</p>
            </CardContent>
          </Card>

          <Card className="border-l-4 border-l-blue-500" data-testid="avg-daily-card">
            <CardContent className="pt-5 pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Gunluk Ortalama</p>
                  <p className="text-3xl font-bold text-gray-900 mt-1">
                    {data.total_no_shows > 0 ? (data.total_no_shows / Math.max(data.daily?.length || 1, 1)).toFixed(1) : '0'}
                  </p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5 text-blue-500" />
                </div>
              </div>
              <p className="text-xs text-gray-400 mt-2">No-show / gun</p>
            </CardContent>
          </Card>

          <Card className="border-l-4 border-l-purple-500" data-testid="avg-loss-card">
            <CardContent className="pt-5 pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Ort. Kayip / No-Show</p>
                  <p className="text-3xl font-bold text-gray-900 mt-1">
                    {data.total_no_shows > 0 ? Math.round(data.total_revenue_loss / data.total_no_shows).toLocaleString('tr-TR') : '0'} TL
                  </p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-purple-50 flex items-center justify-center">
                  <TrendingDown className="w-5 h-5 text-purple-500" />
                </div>
              </div>
              <p className="text-xs text-gray-400 mt-2">Rezervasyon basina kayip</p>
            </CardContent>
          </Card>
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* By Reason */}
          <Card data-testid="by-reason-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold text-gray-700">Sebep Bazli Dagilim</CardTitle>
            </CardHeader>
            <CardContent>
              {data.by_reason?.length > 0 ? (
                <div className="space-y-3">
                  {data.by_reason.map((r, i) => {
                    const colors = REASON_COLORS[r.reason] || REASON_COLORS.belirtilmemis;
                    const pct = data.total_no_shows > 0 ? Math.round((r.count / data.total_no_shows) * 100) : 0;
                    return (
                      <div key={r.reason} className={`rounded-lg p-3 ${colors.bg} ${colors.border} border`} data-testid={`reason-row-${i}`}>
                        <div className="flex items-center justify-between mb-1.5">
                          <span className={`text-sm font-medium ${colors.text}`}>{r.label}</span>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-gray-500">{pct}%</span>
                            <Badge variant="secondary" className="text-xs">{r.count}</Badge>
                          </div>
                        </div>
                        <div className="w-full h-2 bg-white/60 rounded-full overflow-hidden">
                          <div className={`h-full rounded-full ${colors.bar} transition-all`} style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-sm text-gray-400 py-6 text-center">Veri yok</p>
              )}
            </CardContent>
          </Card>

          {/* By Room Type */}
          <Card data-testid="by-room-type-card">
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <Building2 className="w-4 h-4 text-gray-500" />
                <CardTitle className="text-sm font-semibold text-gray-700">Oda Tipi Bazli</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              {data.by_room_type?.length > 0 ? (
                <div className="space-y-3">
                  {data.by_room_type.map((rt, i) => (
                    <div key={rt.room_type} className="flex items-center gap-3" data-testid={`room-type-row-${i}`}>
                      <div className="w-24 text-sm font-medium text-gray-700 truncate">{rt.room_type}</div>
                      <div className="flex-1 h-7 bg-gray-100 rounded-md overflow-hidden relative">
                        <div
                          className="h-full bg-gradient-to-r from-amber-400 to-amber-500 rounded-md transition-all"
                          style={{ width: `${(rt.count / maxRoomType) * 100}%` }}
                        />
                        <div className="absolute inset-0 flex items-center px-2">
                          <span className="text-xs font-semibold text-gray-800">{rt.count} no-show</span>
                        </div>
                      </div>
                      <div className="w-24 text-right text-xs text-red-600 font-medium">
                        -{rt.revenue_loss.toLocaleString('tr-TR')} TL
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-400 py-6 text-center">Veri yok</p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Second Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* By Channel */}
          <Card data-testid="by-channel-card">
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <Radio className="w-4 h-4 text-gray-500" />
                <CardTitle className="text-sm font-semibold text-gray-700">Kanal Bazli</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              {data.by_channel?.length > 0 ? (
                <div className="space-y-3">
                  {data.by_channel.map((ch, i) => {
                    const barColor = CHANNEL_COLORS[ch.channel] || 'bg-gray-500';
                    return (
                      <div key={ch.channel} className="flex items-center gap-3" data-testid={`channel-row-${i}`}>
                        <div className="w-20 text-sm font-medium text-gray-700 capitalize truncate">{ch.channel}</div>
                        <div className="flex-1 h-7 bg-gray-100 rounded-md overflow-hidden relative">
                          <div
                            className={`h-full ${barColor} rounded-md transition-all`}
                            style={{ width: `${(ch.count / maxChannel) * 100}%` }}
                          />
                          <div className="absolute inset-0 flex items-center px-2">
                            <span className="text-xs font-semibold text-white drop-shadow">{ch.count}</span>
                          </div>
                        </div>
                        <div className="w-24 text-right text-xs text-red-600 font-medium">
                          -{ch.revenue_loss.toLocaleString('tr-TR')} TL
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-sm text-gray-400 py-6 text-center">Veri yok</p>
              )}
            </CardContent>
          </Card>

          {/* Daily Trend */}
          <Card data-testid="daily-trend-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold text-gray-700">Gunluk Trend</CardTitle>
            </CardHeader>
            <CardContent>
              {data.daily?.length > 0 ? (
                <div className="flex items-end gap-[2px] h-40">
                  {data.daily.slice(-30).map((d, i) => (
                    <div key={d.date} className="flex-1 flex flex-col items-center justify-end group relative" data-testid={`daily-bar-${i}`}>
                      <div className="absolute -top-6 hidden group-hover:block bg-gray-800 text-white text-[10px] px-1.5 py-0.5 rounded whitespace-nowrap z-10">
                        {d.date}: {d.count}
                      </div>
                      <div
                        className="w-full bg-amber-400 hover:bg-amber-500 rounded-t transition-all cursor-pointer min-h-[2px]"
                        style={{ height: `${(d.count / maxDaily) * 100}%` }}
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-400 py-6 text-center">Veri yok</p>
              )}
              {data.daily?.length > 0 && (
                <div className="flex justify-between mt-2 text-[10px] text-gray-400">
                  <span>{data.daily[Math.max(data.daily.length - 30, 0)]?.date}</span>
                  <span>{data.daily[data.daily.length - 1]?.date}</span>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Recent No-Shows Table */}
        <Card data-testid="recent-noshow-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold text-gray-700">Son No-Show Kayitlari</CardTitle>
          </CardHeader>
          <CardContent>
            {data.recent?.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs text-gray-500 uppercase tracking-wide">
                      <th className="pb-2 pr-4">Tarih</th>
                      <th className="pb-2 pr-4">Misafir</th>
                      <th className="pb-2 pr-4">Oda Tipi</th>
                      <th className="pb-2 pr-4">Kanal</th>
                      <th className="pb-2 pr-4">Sebep</th>
                      <th className="pb-2 text-right">Tutar</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent.map((r, i) => {
                      const colors = REASON_COLORS[r.reason] || REASON_COLORS.belirtilmemis;
                      return (
                        <tr key={r.id || i} className="border-b last:border-0 hover:bg-gray-50" data-testid={`recent-row-${i}`}>
                          <td className="py-2.5 pr-4 text-gray-600">{r.date}</td>
                          <td className="py-2.5 pr-4 font-medium text-gray-800">{r.guest_name}</td>
                          <td className="py-2.5 pr-4 text-gray-600">{r.room_type}</td>
                          <td className="py-2.5 pr-4">
                            <Badge variant="outline" className="text-xs capitalize">{r.channel}</Badge>
                          </td>
                          <td className="py-2.5 pr-4">
                            <span className={`text-xs px-2 py-0.5 rounded-full ${colors.bg} ${colors.text} font-medium`}>
                              {r.reason_label}
                            </span>
                          </td>
                          <td className="py-2.5 text-right text-red-600 font-medium">{r.amount.toLocaleString('tr-TR')} TL</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-gray-400 py-6 text-center">Henuz no-show kaydi yok</p>
            )}
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
};

export default NoShowAnalytics;
