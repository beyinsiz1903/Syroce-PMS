import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  AlertTriangle, CreditCard, Star, LogOut, ArrowRight,
  BedDouble, Users, Calendar, Loader2, SprayCan, RefreshCw
} from 'lucide-react';

const SEVERITY_STYLES = {
  high: { bg: 'bg-red-50', border: 'border-red-200', icon: 'text-red-600', badge: 'bg-red-100 text-red-700' },
  medium: { bg: 'bg-amber-50', border: 'border-amber-200', icon: 'text-amber-600', badge: 'bg-amber-100 text-amber-700' },
  info: { bg: 'bg-blue-50', border: 'border-blue-200', icon: 'text-blue-600', badge: 'bg-blue-100 text-blue-700' },
};

const ALERT_ICONS = {
  dirty_rooms_blocking: SprayCan,
  pending_payments: CreditCard,
  vip_arrivals: Star,
  departures_with_balance: LogOut,
};

export const CommandCenter = ({ className = '' }) => {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await axios.get('/pms/operational-alerts');
      setData(res.data);
    } catch (e) {
      console.error('operational-alerts fail:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <Card className={`${className}`}>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 animate-spin text-slate-400 mr-2" />
          <span className="text-sm text-slate-500">Operasyonel durum yukleniyor...</span>
        </CardContent>
      </Card>
    );
  }

  if (!data) return null;

  const { alerts, summary } = data;
  const hasAlerts = alerts && alerts.length > 0;

  const handleAction = (alert) => {
    if (alert.action === 'housekeeping') navigate('/housekeeping');
    else if (alert.action === 'payments') navigate('/pms');
    else if (alert.action === 'frontdesk') navigate('/pms');
  };

  return (
    <div className={`space-y-4 ${className}`} data-testid="command-center">
      {/* Summary Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card className="bg-white border border-slate-100 shadow-sm hover:shadow-md transition-all" data-testid="cc-arrivals">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-emerald-50 flex items-center justify-center flex-shrink-0">
                <Calendar className="w-5 h-5 text-emerald-600" />
              </div>
              <div>
                <div className="text-2xl font-bold text-slate-900" style={{ fontFamily: 'Manrope' }}>{summary?.arrivals_today || 0}</div>
                <div className="text-xs text-slate-500">Bugun Gelis</div>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-white border border-slate-100 shadow-sm hover:shadow-md transition-all" data-testid="cc-departures">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center flex-shrink-0">
                <LogOut className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <div className="text-2xl font-bold text-slate-900" style={{ fontFamily: 'Manrope' }}>{summary?.departures_today || 0}</div>
                <div className="text-xs text-slate-500">Bugun Cikis</div>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-white border border-slate-100 shadow-sm hover:shadow-md transition-all" data-testid="cc-inhouse">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-purple-50 flex items-center justify-center flex-shrink-0">
                <Users className="w-5 h-5 text-purple-600" />
              </div>
              <div>
                <div className="text-2xl font-bold text-slate-900" style={{ fontFamily: 'Manrope' }}>{summary?.inhouse || 0}</div>
                <div className="text-xs text-slate-500">Iceride</div>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-white border border-slate-100 shadow-sm hover:shadow-md transition-all" data-testid="cc-dirty">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center flex-shrink-0">
                <BedDouble className="w-5 h-5 text-amber-600" />
              </div>
              <div>
                <div className="text-2xl font-bold text-slate-900" style={{ fontFamily: 'Manrope' }}>{summary?.dirty_rooms || 0}</div>
                <div className="text-xs text-slate-500">Kirli Oda</div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Alerts Section */}
      {hasAlerts ? (
        <Card className="border border-slate-200 shadow-sm overflow-hidden" data-testid="cc-alerts">
          <div className="px-5 py-3 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-800" style={{ fontFamily: 'Manrope' }}>
              <AlertTriangle className="w-4 h-4 inline mr-1.5 text-amber-500" />
              Dikkat Gerektiren ({alerts.length})
            </h3>
            <Button variant="ghost" size="sm" onClick={load} className="h-7 text-xs text-slate-500" data-testid="cc-refresh">
              <RefreshCw className="w-3.5 h-3.5 mr-1" /> Yenile
            </Button>
          </div>
          <CardContent className="p-0">
            <div className="divide-y divide-slate-100">
              {alerts.map((alert, i) => {
                const style = SEVERITY_STYLES[alert.severity] || SEVERITY_STYLES.info;
                const Icon = ALERT_ICONS[alert.type] || AlertTriangle;
                return (
                  <div key={i} className={`px-5 py-3.5 ${style.bg} hover:brightness-95 transition-all`} data-testid={`cc-alert-${alert.type}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-3 flex-1 min-w-0">
                        <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${style.bg} border ${style.border}`}>
                          <Icon className={`w-4.5 h-4.5 ${style.icon}`} />
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-slate-800">{alert.title}</span>
                            <Badge className={`text-[10px] px-1.5 py-0 ${style.badge}`}>{alert.severity === 'high' ? 'Acil' : alert.severity === 'medium' ? 'Orta' : 'Bilgi'}</Badge>
                          </div>
                          <p className="text-xs text-slate-500 mt-0.5">{alert.description}</p>
                          {alert.items && alert.items.length > 0 && (
                            <div className="flex flex-wrap gap-1.5 mt-2">
                              {alert.items.slice(0, 3).map((item, j) => (
                                <span key={j} className="inline-flex items-center text-[11px] bg-white/70 border border-slate-200 rounded-md px-2 py-0.5 text-slate-600">
                                  {item.room_number && <span className="font-semibold mr-1">Oda {item.room_number}</span>}
                                  {item.guest_name}
                                  {item.balance > 0 && <span className="ml-1 font-semibold text-red-600">{item.balance.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} TL</span>}
                                </span>
                              ))}
                              {alert.items.length > 3 && <span className="text-[11px] text-slate-400">+{alert.items.length - 3} daha</span>}
                            </div>
                          )}
                        </div>
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 text-xs flex-shrink-0 border-slate-300 hover:bg-white"
                        onClick={() => handleAction(alert)}
                        data-testid={`cc-action-${alert.type}`}
                      >
                        {alert.action_label} <ArrowRight className="w-3.5 h-3.5 ml-1" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card className="border border-emerald-100 bg-emerald-50/50" data-testid="cc-no-alerts">
          <CardContent className="py-6 text-center">
            <div className="w-10 h-10 rounded-full bg-emerald-100 flex items-center justify-center mx-auto mb-2">
              <span className="text-emerald-600 text-lg font-bold">&#10003;</span>
            </div>
            <p className="text-sm font-medium text-emerald-700">Tum operasyonlar yolunda</p>
            <p className="text-xs text-emerald-500 mt-0.5">Acil dikkat gerektiren durum yok</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default CommandCenter;
