import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';

import { Skeleton } from '../components/ui/skeleton';
import { StatusBadge, DocTypeBadge } from '../components/StatusBadges';
import { api } from '../lib/api';
import {
  LogIn,
  LogOut,
  Users,
  ShieldCheck,
  ScanLine,
  ArrowRight,
  Camera,
  Layers,
  TrendingUp,
} from 'lucide-react';
import { XAxis, YAxis, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    try {
      const data = await api.getDashboardStats();
      setStats(data);
    } catch (err) {
      console.error('Failed to load stats:', err);
    } finally {
      setLoading(false);
    }
  };

  const kpis = stats ? [
    { title: 'Bugün Check-in', value: stats.today_checkins, icon: LogIn, color: 'var(--brand-success)', bg: 'var(--brand-success-soft)' },
    { title: 'Bugün Check-out', value: stats.today_checkouts, icon: LogOut, color: 'var(--brand-info)', bg: 'var(--brand-info-soft)' },
    { title: 'Toplam Misafir', value: stats.total_guests, icon: Users, color: 'var(--brand-sky)', bg: 'var(--brand-sky-soft)' },
    { title: 'İnceleme Bekleyen', value: stats.pending_reviews, icon: ShieldCheck, color: 'var(--brand-warning)', bg: 'var(--brand-warning-soft)' },
  ] : [];

  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    try {
      return new Date(dateStr).toLocaleString('tr-TR', { 
        day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' 
      });
    } catch { return dateStr; }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-[var(--brand-ink)]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            Genel Bakış
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Misafir giriş/çıkış özeti ve son taramalar
          </p>
        </div>
        <div className="flex gap-2">
          <Link to="/scan">
            <Button className="bg-[var(--brand-sky)] hover:bg-[#094C6E] text-white" data-testid="topbar-new-scan-button">
              <Camera className="w-4 h-4 mr-2" />
              Yeni Tarama
            </Button>
          </Link>
          <Link to="/bulk-scan">
            <Button variant="outline">
              <Layers className="w-4 h-4 mr-2" />
              Toplu Tarama
            </Button>
          </Link>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="bg-white">
              <CardContent className="p-4">
                <Skeleton className="h-4 w-24 mb-3" />
                <Skeleton className="h-8 w-16" />
              </CardContent>
            </Card>
          ))
        ) : (
          kpis.map((kpi, i) => (
            <Card key={i} className="bg-white kpi-card cursor-default">
              <CardContent className="p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-muted-foreground">{kpi.title}</span>
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: kpi.bg }}>
                    <kpi.icon className="w-4 h-4" style={{ color: kpi.color }} />
                  </div>
                </div>
                <p className="text-2xl sm:text-3xl font-semibold tabular-nums" style={{ fontFamily: "'Space Grotesk', sans-serif", color: kpi.color }}>
                  {kpi.value}
                </p>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_420px] gap-4">
        {/* Left: Chart + Recent Guests */}
        <div className="space-y-4">
          {/* Weekly Chart */}
          <Card className="bg-white">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-[var(--brand-sky)]" />
                Haftalık Misafir Girişi
              </CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <Skeleton className="h-40 w-full" />
              ) : (
                <ResponsiveContainer width="100%" height={160}>
                  <AreaChart data={stats?.weekly_stats || []}>
                    <defs>
                      <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#0B5E8A" stopOpacity={0.15} />
                        <stop offset="95%" stopColor="#0B5E8A" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis 
                      dataKey="day" 
                      axisLine={false} 
                      tickLine={false} 
                      tick={{ fontSize: 11, fill: '#64748b' }}
                    />
                    <YAxis 
                      axisLine={false} 
                      tickLine={false} 
                      tick={{ fontSize: 11, fill: '#64748b' }}
                      allowDecimals={false}
                    />
                    <Tooltip 
                      contentStyle={{ 
                        backgroundColor: 'white', 
                        border: '1px solid #e2e8f0', 
                        borderRadius: '8px',
                        fontSize: '12px'
                      }}
                    />
                    <Area 
                      type="monotone" 
                      dataKey="count" 
                      stroke="#0B5E8A" 
                      strokeWidth={2}
                      fill="url(#colorCount)" 
                      name="Misafir"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Recent Guests */}
          <Card className="bg-white">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium">Son Misafirler</CardTitle>
                <Link to="/guests">
                  <Button variant="ghost" size="sm" className="text-xs">
                    Tümünü Gör <ArrowRight className="w-3 h-3 ml-1" />
                  </Button>
                </Link>
              </div>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="space-y-3">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="flex items-center gap-3">
                      <Skeleton className="h-10 w-10 rounded-full" />
                      <div className="flex-1">
                        <Skeleton className="h-4 w-32 mb-1" />
                        <Skeleton className="h-3 w-20" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : stats?.recent_guests?.length > 0 ? (
                <div className="space-y-2">
                  {stats.recent_guests.map((guest) => (
                    <Link
                      key={guest.id}
                      to={`/guests/${guest.id}`}
                      className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-[hsl(var(--secondary))] transition-colors duration-150"
                    >
                      <div className="w-10 h-10 rounded-full bg-[var(--brand-sky-soft)] flex items-center justify-center">
                        <span className="text-sm font-medium text-[var(--brand-sky)]">
                          {(guest.first_name?.[0] || '') + (guest.last_name?.[0] || '')}
                        </span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-[var(--brand-ink)] truncate">
                          {guest.first_name} {guest.last_name}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {guest.id_number || guest.document_number || '—'}
                        </p>
                      </div>
                      <StatusBadge status={guest.status} />
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-8">
                  Henüz misafir kaydı yok
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right: Quick Actions + Recent Scans */}
        <div className="space-y-4">
          {/* Quick Scan CTA */}
          <Card className="bg-white border-[var(--brand-sky)] border-2 border-dashed">
            <CardContent className="p-5 text-center">
              <div className="w-14 h-14 rounded-2xl bg-[var(--brand-sky-soft)] flex items-center justify-center mx-auto mb-3">
                <ScanLine className="w-7 h-7 text-[var(--brand-sky)]" />
              </div>
              <h3 className="text-base font-semibold mb-1" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                Hızlı Kimlik Tarama
              </h3>
              <p className="text-xs text-muted-foreground mb-4">
                Kamerayı açın, kimliği gösterin, bilgiler anında çıkarılsın.
              </p>
              <Link to="/scan">
                <Button className="bg-[var(--brand-sky)] hover:bg-[#094C6E] text-white w-full">
                  <Camera className="w-4 h-4 mr-2" />
                  Taramayı Başlat
                </Button>
              </Link>
            </CardContent>
          </Card>

          {/* Stats Summary */}
          <Card className="bg-white">
            <CardContent className="p-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-lg bg-[var(--brand-sky-soft)]">
                  <p className="text-xs text-muted-foreground">Toplam Tarama</p>
                  <p className="text-xl font-semibold text-[var(--brand-sky)]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                    {loading ? '—' : stats?.total_scans || 0}
                  </p>
                </div>
                <div className="p-3 rounded-lg bg-[var(--brand-success-soft)]">
                  <p className="text-xs text-muted-foreground">Aktif Misafir</p>
                  <p className="text-xl font-semibold text-[var(--brand-success)]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                    {loading ? '—' : stats?.currently_checked_in || 0}
                  </p>
                </div>
                <div className="p-3 rounded-lg bg-[var(--brand-info-soft)]">
                  <p className="text-xs text-muted-foreground">Bugün Tarama</p>
                  <p className="text-xl font-semibold text-[var(--brand-info)]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                    {loading ? '—' : stats?.today_scans || 0}
                  </p>
                </div>
                <div className="p-3 rounded-lg bg-[var(--brand-amber-soft)]">
                  <p className="text-xs text-muted-foreground">Bekleyen</p>
                  <p className="text-xl font-semibold text-[var(--brand-amber)]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                    {loading ? '—' : stats?.pending_reviews || 0}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Recent Scans */}
          <Card className="bg-white">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Son Taramalar</CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="space-y-2">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </div>
              ) : stats?.recent_scans?.length > 0 ? (
                <div className="space-y-2">
                  {stats.recent_scans.map((scan) => (
                    <div key={scan.id} className="flex items-center gap-3 p-2 rounded-lg bg-[hsl(var(--secondary))]">
                      <div className={`w-2 h-2 rounded-full ${
                        scan.status === 'completed' ? 'bg-[var(--brand-success)]' : 'bg-[var(--brand-danger)]'
                      }`} />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium truncate">
                          {scan.extracted_data?.first_name} {scan.extracted_data?.last_name || 'Bilinmiyor'}
                        </p>
                        <p className="text-[10px] text-muted-foreground">
                          {formatDate(scan.created_at)}
                        </p>
                      </div>
                      <DocTypeBadge type={scan.document_type} />
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-6">
                  Henüz tarama yapılmadı
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
