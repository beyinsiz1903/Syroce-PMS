import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Phone, PhoneIncoming, PhoneOutgoing, PhoneMissed, Clock, RefreshCw, AlertCircle, PhoneCall, Headset, Play } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { BarChart, Bar, XAxis, YAxis, Tooltip as RechartsTooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

// Stat Card Component
const StatCard = ({ title, value, icon: Icon, colorClass, subtitle }) => (
  <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 flex items-center gap-4 hover:shadow-md transition-shadow">
    <div className={`p-3 rounded-xl ${colorClass}`}>
      <Icon className="w-6 h-6" />
    </div>
    <div>
      <p className="text-sm font-medium text-gray-500 mb-1">{title}</p>
      <h3 className="text-2xl font-bold text-gray-900">{value}</h3>
      {subtitle && <p className="text-xs text-gray-400 mt-1">{subtitle}</p>}
    </div>
  </div>
);

// Helpers
function formatDuration(seconds) {
  const total = Number(seconds) || 0;
  if (total <= 0) return "0 dk 0 sn";
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m} dk ${String(s).padStart(2, "0")} sn`;
}

function formatDateTime(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function isToday(dateString) {
  if (!dateString) return false;
  const date = new Date(dateString);
  const today = new Date();
  return date.getDate() === today.getDate() &&
    date.getMonth() === today.getMonth() &&
    date.getFullYear() === today.getFullYear();
}

const STATUS_LABEL = {
  ringing: "Çalıyor",
  answered: "Yanıtlandı",
  completed: "Tamamlandı",
  missed: "Cevapsız",
  failed: "Başarısız",
};

export default function ContactCenterDashboard() {
  const { t } = useTranslation();
  const [calls, setCalls] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [playingId, setPlayingId] = useState(null);

  const fetchCalls = async () => {
    setLoading(true);
    setError(null);
    try {
      // Get up to 200 calls to calculate accurate daily stats locally
      const res = await axios.get("/contact-center/calls", { params: { limit: 200 } });
      setCalls(Array.isArray(res.data?.items) ? res.data.items : []);
    } catch (err) {
      if (err?.response?.status === 503) {
        setError("Sesli arama altyapısı henüz yapılandırılmadı.");
      } else if (err?.response?.status === 403) {
        setError("Çağrı geçmişini görüntüleme yetkiniz yok.");
      } else {
        setError("Çağrı verileri yüklenirken bir hata oluştu.");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCalls();
  }, []);

  // Compute Daily Stats
  const todayCalls = calls.filter(c => isToday(c.started_at));
  const totalToday = todayCalls.length;
  const inboundToday = todayCalls.filter(c => c.direction === 'inbound').length;
  const outboundToday = todayCalls.filter(c => c.direction === 'outbound').length;
  const missedToday = todayCalls.filter(c => c.direction === 'inbound' && c.status === 'missed').length;
  
  const totalDurationSeconds = todayCalls.reduce((acc, c) => acc + (Number(c.duration_seconds) || 0), 0);
  const totalDuration = formatDuration(totalDurationSeconds);

  // Hourly Data
  const hourlyCounts = Array(24).fill(0);
  todayCalls.forEach(c => {
    if (c.started_at) {
      const h = new Date(c.started_at).getHours();
      hourlyCounts[h]++;
    }
  });
  const hourlyData = hourlyCounts.map((count, i) => ({
    hour: `${String(i).padStart(2, '0')}:00`,
    Çağrı: count,
  })).filter(d => d.Çağrı > 0 || (parseInt(d.hour) >= 8 && parseInt(d.hour) <= 20)); // Show active hours or hours with calls

  // Pie Data
  const pieData = [
    { name: t('contactCenter.inbound', 'Gelen'), value: inboundToday },
    { name: t('contactCenter.outbound', 'Giden'), value: outboundToday },
  ].filter(d => d.value > 0);
  const PIE_COLORS = ['#10b981', '#6366f1']; // Emerald for Inbound, Indigo for Outbound

  // Recent 10 calls for the table
  const recentCalls = calls.slice(0, 10);

  return (
    <div className="max-w-7xl mx-auto p-4 sm:p-6 lg:p-8 space-y-8 bg-gray-50/30 min-h-screen">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Headset className="w-7 h-7 text-indigo-600" />
            {t('contactCenter.dashboard', 'Çağrı Merkezi Paneli')}
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            {t('contactCenter.dashboardSubtitle', 'Günlük çağrı istatistikleri ve anlık görüşme geçmişi.')}
          </p>
        </div>
        <button
          onClick={fetchCalls}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          {loading ? t('common.refreshing', 'Yenileniyor...') : t('common.refresh', 'Yenile')}
        </button>
      </div>

      {error && (
        <div className="p-4 bg-red-50 text-red-700 rounded-xl border border-red-100 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title={t('contactCenter.totalToday', 'Bugün Toplam Çağrı')}
          value={totalToday}
          icon={PhoneCall}
          colorClass="bg-blue-100 text-blue-600"
        />
        <StatCard
          title={t('contactCenter.inboundToday', 'Gelen Çağrılar')}
          value={inboundToday}
          icon={PhoneIncoming}
          colorClass="bg-emerald-100 text-emerald-600"
        />
        <StatCard
          title={t('contactCenter.missedToday', 'Cevapsız Çağrılar')}
          value={missedToday}
          icon={PhoneMissed}
          colorClass="bg-rose-100 text-rose-600"
          subtitle={t('contactCenter.missedSubtitle', 'Gelen çağrılar baz alınmıştır')}
        />
        <StatCard
          title={t('contactCenter.totalDuration', 'Toplam Görüşme (Bugün)')}
          value={totalDuration}
          icon={Clock}
          colorClass="bg-purple-100 text-purple-600"
        />
      </div>

      {/* Charts */}
      {calls.length > 0 && !loading && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 lg:col-span-2">
            <h3 className="text-sm font-semibold text-gray-800 mb-4">{t('contactCenter.hourlyChart', 'Saatlik Çağrı Yoğunluğu (Bugün)')}</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={hourlyData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                  <XAxis dataKey="hour" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#6b7280' }} dy={10} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#6b7280' }} />
                  <RechartsTooltip 
                    cursor={{ fill: '#f3f4f6' }}
                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                  />
                  <Bar dataKey="Çağrı" fill="#6366f1" radius={[4, 4, 0, 0]} barSize={32} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            <h3 className="text-sm font-semibold text-gray-800 mb-4">{t('contactCenter.directionChart', 'Çağrı Yönü Dağılımı (Bugün)')}</h3>
            <div className="h-64 flex items-center justify-center">
              {pieData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={80}
                      paddingAngle={5}
                      dataKey="value"
                    >
                      {pieData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <RechartsTooltip 
                      contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="text-sm text-gray-400">Veri yok</div>
              )}
            </div>
            {pieData.length > 0 && (
              <div className="flex justify-center gap-4 mt-2">
                {pieData.map((entry, index) => (
                  <div key={entry.name} className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: PIE_COLORS[index % PIE_COLORS.length] }}></div>
                    <span className="text-xs text-gray-600 font-medium">{entry.name} ({entry.value})</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Recent Calls Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-gray-50/50">
          <h2 className="text-lg font-semibold text-gray-900">{t('contactCenter.recentCalls', 'Son Çağrılar')}</h2>
        </div>
        
        {loading && calls.length === 0 ? (
          <div className="p-12 flex justify-center">
            <RefreshCw className="w-8 h-8 text-gray-300 animate-spin" />
          </div>
        ) : calls.length === 0 ? (
          <div className="p-12 text-center text-gray-500">
            <Phone className="w-12 h-12 mx-auto mb-3 text-gray-200" />
            <p>{t('contactCenter.noCalls', 'Henüz çağrı kaydı bulunmamaktadır.')}</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-gray-50/50 border-b border-gray-100">
                  <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">{t('contactCenter.direction', 'Yön')}</th>
                  <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">{t('contactCenter.phone', 'Telefon')}</th>
                  <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">{t('contactCenter.status', 'Durum')}</th>
                  <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">{t('contactCenter.date', 'Tarih')}</th>
                  <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">{t('contactCenter.duration', 'Süre')}</th>
                  <th className="px-6 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Detay / Kayıt</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {recentCalls.map(call => {
                  const isInbound = call.direction === 'inbound';
                  return (
                    <tr key={call.id} className="hover:bg-gray-50/50 transition-colors">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium ${
                          isInbound ? 'bg-emerald-50 text-emerald-700 border border-emerald-100' : 'bg-indigo-50 text-indigo-700 border border-indigo-100'
                        }`}>
                          {isInbound ? <PhoneIncoming className="w-3 h-3" /> : <PhoneOutgoing className="w-3 h-3" />}
                          {isInbound ? t('contactCenter.inbound', 'Gelen') : t('contactCenter.outbound', 'Giden')}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap font-medium text-gray-900">
                        {call.caller_phone_masked || t('contactCenter.unknownNumber', "Bilinmeyen Numara")}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                          call.status === 'completed' || call.status === 'answered' ? 'text-emerald-700 bg-emerald-50' :
                          call.status === 'missed' ? 'text-rose-700 bg-rose-50' :
                          call.status === 'ringing' ? 'text-amber-700 bg-amber-50' : 'text-gray-700 bg-gray-50'
                        }`}>
                          {STATUS_LABEL[call.status] || call.status || "—"}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {formatDateTime(call.started_at)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {formatDuration(call.duration_seconds)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <div className="flex flex-col items-end gap-2">
                          <div className="flex gap-2 items-center">
                            {call.notes && (
                              <span className="text-[11px] text-gray-500 italic max-w-[150px] truncate" title={call.notes}>
                                Not: {call.notes}
                              </span>
                            )}
                            {call.has_recording && (
                              <button
                                onClick={() => setPlayingId(playingId === call.id ? null : call.id)}
                                className={`p-1.5 rounded-full hover:bg-gray-100 ${playingId === call.id ? 'text-indigo-600 bg-indigo-50' : 'text-gray-400'}`}
                                title="Kaydı Dinle"
                              >
                                <Play className="w-4 h-4" />
                              </button>
                            )}
                          </div>
                          {playingId === call.id && (
                            <audio 
                              controls 
                              autoPlay 
                              className="h-8 w-48"
                              src={`/api/contact-center/calls/${call.id}/recording`}
                            />
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
