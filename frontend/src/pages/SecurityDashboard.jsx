import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import Layout from '@/components/MaybeLayout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { Shield, ShieldCheck, ShieldAlert, Lock, Unlock, Activity, AlertTriangle, Users, Clock, RefreshCw, Loader2, Eye, TrendingUp, Zap, Server, Globe, Key, UserCheck, Ban } from 'lucide-react';
const API = "";
const SecurityDashboard = ({
  user,
  tenant,
  onLogout,
  embedded = false
}) => {
  const {
    t
  } = useTranslation();
  const token = localStorage.getItem('token');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const fetchData = useCallback(async () => {
    try {
      const res = await fetch(`/api/security/summary`, {
        credentials: "include",
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (!res.ok) throw new Error();
      setData(await res.json());
    } catch {
      toast.error(t('securityDashboard.loadFailed'));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [token]);
  useEffect(() => {
    fetchData();
  }, [fetchData]);
  const refreshToken = async () => {
    try {
      const res = await fetch(`/api/auth/refresh-token`, {
        credentials: "include",
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (!res.ok) throw new Error();
      const result = await res.json();
      localStorage.setItem('token', result.access_token);
      toast.success(t('securityDashboard.tokenRefreshed'));
    } catch {
      toast.error(t('securityDashboard.tokenRefreshFailed'));
    }
  };
  if (loading) {
    return <Layout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout} currentModule="security">
        <div className="flex items-center justify-center min-h-[60vh]">
          <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
        </div>
      </Layout>;
  }
  const o = data?.overview || {};
  const apm = data?.apm || {};
  const events = data?.recent_events || [];
  return <Layout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout} currentModule="security">
      <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-6" data-testid="security-dashboard">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Shield className="w-7 h-7 text-emerald-600" />
              {t('securityDashboard.title')}
            </h1>
            <p className="text-sm text-gray-500 mt-1">{t('securityDashboard.subtitle')}</p>
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={refreshToken} data-testid="refresh-token-btn">
              <Key className="w-4 h-4 mr-1" />{t('securityDashboard.refreshToken')}
            </Button>
            <Button size="sm" variant="outline" onClick={fetchData} data-testid="refresh-data-btn">
              <RefreshCw className="w-4 h-4 mr-1" />{t('common.refresh')}
            </Button>
          </div>
        </div>

        {/* Status Banner */}
        <Card className={`border-l-4 ${o.failed_logins_24h > 10 ? 'border-l-red-500 bg-red-50/30' : 'border-l-emerald-500 bg-emerald-50/30'}`}>
          <CardContent className="p-4 flex items-center gap-3">
            {o.failed_logins_24h > 10 ? <ShieldAlert className="w-6 h-6 text-red-600" /> : <ShieldCheck className="w-6 h-6 text-emerald-600" />}
            <div>
              <p className="font-semibold text-gray-900">
                {o.failed_logins_24h > 10 ? t('securityDashboard.securityWarning') : t('securityDashboard.systemSecure')}
              </p>
              <p className="text-xs text-gray-500">
                Son güncelleme: {new Date(data?.timestamp).toLocaleString('tr-TR')}
              </p>
            </div>
          </CardContent>
        </Card>

        {/* KPI Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <Card data-testid="kpi-failed-logins">
            <CardContent className="p-4 text-center">
              <Ban className="w-5 h-5 text-red-500 mx-auto mb-1" />
              <p className="text-2xl font-bold text-red-600">{o.failed_logins_24h || 0}</p>
              <p className="text-[10px] text-gray-500">{t('securityDashboard.failedLogins24h')}</p>
            </CardContent>
          </Card>
          <Card data-testid="kpi-successful-logins">
            <CardContent className="p-4 text-center">
              <UserCheck className="w-5 h-5 text-emerald-500 mx-auto mb-1" />
              <p className="text-2xl font-bold text-emerald-600">{o.successful_logins_24h || 0}</p>
              <p className="text-[10px] text-gray-500">{t('securityDashboard.successfulLogins24h')}</p>
            </CardContent>
          </Card>
          <Card data-testid="kpi-active-sessions">
            <CardContent className="p-4 text-center">
              <Users className="w-5 h-5 text-blue-500 mx-auto mb-1" />
              <p className="text-2xl font-bold text-blue-600">{o.active_sessions || 0}</p>
              <p className="text-[10px] text-gray-500">{t('securityDashboard.activeSessions')}</p>
            </CardContent>
          </Card>
          <Card data-testid="kpi-total-users">
            <CardContent className="p-4 text-center">
              <Lock className="w-5 h-5 text-indigo-500 mx-auto mb-1" />
              <p className="text-2xl font-bold text-indigo-600">{o.total_users || 0}</p>
              <p className="text-[10px] text-gray-500">{t('securityDashboard.totalUsers')}</p>
            </CardContent>
          </Card>
          <Card data-testid="kpi-rate-limits">
            <CardContent className="p-4 text-center">
              <Zap className="w-5 h-5 text-amber-500 mx-auto mb-1" />
              <p className="text-2xl font-bold text-amber-600">{o.rate_limit_hits || 0}</p>
              <p className="text-[10px] text-gray-500">{t('securityDashboard.rateLimitHit')}</p>
            </CardContent>
          </Card>
          <Card data-testid="kpi-error-rate">
            <CardContent className="p-4 text-center">
              <AlertTriangle className="w-5 h-5 text-amber-500 mx-auto mb-1" />
              <p className="text-2xl font-bold text-amber-600">{apm.error_rate?.toFixed(1) || 0}%</p>
              <p className="text-[10px] text-gray-500">{t('securityDashboard.errorRate')}</p>
            </CardContent>
          </Card>
        </div>

        {/* Performance & Security Details */}
        <div className="grid md:grid-cols-2 gap-4">
          {/* API Performans */}
          <Card data-testid="api-performance">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2">
                <Activity className="w-4 h-4 text-blue-600" />
                {t('securityDashboard.apiPerformance')}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 bg-blue-50 rounded-lg">
                  <p className="text-xs text-blue-600 font-medium">{t('securityDashboard.requestsPerMin')}</p>
                  <p className="text-xl font-bold text-blue-800">{apm.requests_per_minute?.toFixed(1) || 0}</p>
                </div>
                <div className="p-3 bg-green-50 rounded-lg">
                  <p className="text-xs text-green-600 font-medium">{t('securityDashboard.avgResponse')}</p>
                  <p className="text-xl font-bold text-green-800">{apm.avg_response_ms?.toFixed(0) || 0}ms</p>
                </div>
                <div className="p-3 bg-amber-50 rounded-lg">
                  <p className="text-xs text-amber-600 font-medium">{t('securityDashboard.slowRequests')}</p>
                  <p className="text-xl font-bold text-amber-800">{apm.slow_requests || 0}</p>
                </div>
                <div className="p-3 bg-red-50 rounded-lg">
                  <p className="text-xs text-red-600 font-medium">{t('securityDashboard.errorRate')}</p>
                  <p className="text-xl font-bold text-red-800">{apm.error_rate?.toFixed(1) || 0}%</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* {t('securityDashboard.securityControls')} */}
          <Card data-testid="security-controls">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-600" />
                {t('securityDashboard.securityControls')}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {[{
              name: 'HTTPS / HSTS',
              status: true,
              icon: Lock
            }, {
              name: 'CSP (Content Security Policy)',
              status: true,
              icon: Shield
            }, {
              name: 'X-Frame-Options',
              status: true,
              icon: Globe
            }, {
              name: 'Rate Limiting',
              status: true,
              icon: Zap
            }, {
              name: 'GZip Compression',
              status: true,
              icon: Server
            }, {
              name: 'JWT Validation',
              status: true,
              icon: Key
            }, {
              name: 'Input Sanitization',
              status: true,
              icon: ShieldCheck
            }, {
              name: 'Audit Logging',
              status: true,
              icon: Eye
            }].map((item, i) => <div key={item.id || i} className="flex items-center justify-between p-2 rounded-lg hover:bg-gray-50">
                  <div className="flex items-center gap-2">
                    <item.icon className="w-3.5 h-3.5 text-gray-500" />
                    <span className="text-sm text-gray-700">{item.name}</span>
                  </div>
                  <Badge className={item.status ? 'bg-emerald-100 text-emerald-700 border-emerald-200' : 'bg-red-100 text-red-700'}>
                    {item.status ? t('common.active') : t('common.inactive')}
                  </Badge>
                </div>)}
            </CardContent>
          </Card>
        </div>

        {/* Recent Security Events */}
        <Card data-testid="security-events">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm flex items-center gap-2">
              <Clock className="w-4 h-4 text-gray-600" />
              {t('securityDashboard.recentEvents')}
              <Badge variant="secondary" className="text-xs">{events.length}</Badge>
            </CardTitle>
            <CardDescription>{t('securityDashboard.last7Days')}</CardDescription>
          </CardHeader>
          <CardContent>
            {events.length > 0 ? <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="events-table">
                  <thead>
                    <tr className="border-b bg-gray-50">
                      <th className="py-2 px-3 text-left text-xs font-semibold text-gray-500">{t('securityDashboard.time')}</th>
                      <th className="py-2 px-3 text-left text-xs font-semibold text-gray-500">{t('securityDashboard.event')}</th>
                      <th className="py-2 px-3 text-left text-xs font-semibold text-gray-500">{t('securityDashboard.userCol')}</th>
                      <th className="py-2 px-3 text-left text-xs font-semibold text-gray-500">{t('securityDashboard.detail')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map((evt, i) => {
                  const isAlert = evt.action === 'login_failed';
                  return <tr key={evt.id || i} className={`border-b hover:bg-gray-50 ${isAlert ? 'bg-red-50/30' : ''}`}>
                          <td className="py-2 px-3 text-xs text-gray-500 whitespace-nowrap">
                            {new Date(evt.timestamp).toLocaleString('tr-TR', {
                        day: '2-digit',
                        month: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                          </td>
                          <td className="py-2 px-3">
                            <Badge className={evt.action === 'login_failed' ? 'bg-red-100 text-red-700' : evt.action === 'login_success' ? 'bg-green-100 text-green-700' : evt.action === 'token_refresh' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-700'} variant="outline">
                              {evt.action === 'login_failed' ? t('securityDashboard.loginFailed') : evt.action === 'login_success' ? t('securityDashboard.loginSuccess') : evt.action === 'token_refresh' ? t('securityDashboard.tokenRefresh') : evt.action === 'password_change' ? t('securityDashboard.passwordChange') : evt.action}
                            </Badge>
                          </td>
                          <td className="py-2 px-3 text-xs text-gray-700">{evt.user_email || '-'}</td>
                          <td className="py-2 px-3 text-xs text-gray-500 max-w-[200px] truncate">{evt.details || '-'}</td>
                        </tr>;
                })}
                  </tbody>
                </table>
              </div> : <div className="text-center py-8 text-gray-400">
                <Shield className="w-10 h-10 mx-auto mb-2 opacity-30" />
                <p className="text-sm">{t('securityDashboard.noEvents')}</p>
              </div>}
          </CardContent>
        </Card>
      </div>
    </Layout>;
};
export default SecurityDashboard;