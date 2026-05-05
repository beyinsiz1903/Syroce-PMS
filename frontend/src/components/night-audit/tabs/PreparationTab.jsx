import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Calendar, AlertOctagon, AlertTriangle, CheckCircle2,
  ArrowRight, RefreshCw, Building2, Users, Bed, Brush,
  ShieldAlert, Clock, Info, Play,
} from 'lucide-react';

const ACTION_LABELS = {
  edit_booking: 'Rezervasyona git',
  checkout_or_extend: 'Çıkış / uzat',
  checkin_or_no_show: 'Check-in / no-show',
  open_run: 'Açık denetimi aç',
};

function bookingHref(item) {
  if (item.run_id) return null;
  if (item.id) return `/pms?edit=${item.id}#bookings`;
  return null;
}

function StatTile({ icon: Icon, label, value, hint, tone = 'gray' }) {
  const toneMap = {
    gray: 'bg-gray-50 text-gray-700',
    indigo: 'bg-indigo-50 text-indigo-700',
    emerald: 'bg-emerald-50 text-emerald-700',
    amber: 'bg-amber-50 text-amber-700',
    blue: 'bg-blue-50 text-blue-700',
    rose: 'bg-rose-50 text-rose-700',
  };
  return (
    <div className={`flex items-center gap-3 p-3 rounded-lg border ${toneMap[tone]}`}>
      <div className="rounded-md p-2 bg-white/70">
        <Icon className="w-4 h-4" />
      </div>
      <div className="min-w-0">
        <p className="text-[11px] uppercase tracking-wide opacity-70">{label}</p>
        <p className="text-sm font-semibold leading-tight">{value}</p>
        {hint && <p className="text-[11px] opacity-70">{hint}</p>}
      </div>
    </div>
  );
}

export default function PreparationTab({ onStartRun, onPreviewLoaded, refreshKey = 0 }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/night-audit/preview');
      setData(res.data);
      if (typeof onPreviewLoaded === 'function') {
        onPreviewLoaded(res.data);
      }
    } catch (e) {
      console.error('preview failed', e);
    } finally {
      setLoading(false);
    }
  }, [onPreviewLoaded]);

  useEffect(() => { load(); }, [load, refreshKey]);

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center py-12 text-gray-500 text-sm">
        <RefreshCw className="w-5 h-5 mr-2 animate-spin" />
        Hazırlık özeti yükleniyor...
      </div>
    );
  }
  if (!data) return null;

  const drift = data.date_drift_days || 0;
  const blockers = data.blockers || [];
  const warnings = data.warnings || [];
  const rooms = data.rooms || {};
  const guests = data.guests || {};

  return (
    <div className="space-y-4">
      {/* Sistem tarihi rozeti — HotelRunner muadili */}
      {drift !== 0 && (
        <Card className="border-amber-300 bg-amber-50/60" data-testid="date-drift-banner">
          <CardContent className="py-3 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-600 mt-0.5" />
            <div className="text-sm">
              <p className="font-semibold text-amber-900">
                Sistem tarihi PMS iş gününden farklı
              </p>
              <p className="text-amber-800">
                Takvim: <span className="font-medium">{data.calendar_date}</span> · PMS iş günü:{' '}
                <span className="font-medium">{data.business_date}</span>{' '}
                <span className="opacity-80">({drift > 0 ? `${drift} gün geride` : `${-drift} gün ileride`})</span>
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Durum + tek dokunuş Başlat */}
      <Card>
        <CardContent className="py-4 flex flex-col md:flex-row md:items-center gap-3 justify-between">
          <div className="flex items-center gap-3">
            {data.ready ? (
              <CheckCircle2 className="w-6 h-6 text-emerald-600" />
            ) : (
              <ShieldAlert className="w-6 h-6 text-rose-600" />
            )}
            <div>
              <p className="text-sm font-semibold text-gray-900">
                {data.ready
                  ? 'Gece denetimi için hazır görünüyorsunuz'
                  : `Başlatılamıyor — ${blockers.length} engelleyici sorun var`}
              </p>
              <p className="text-xs text-gray-500">
                İş günü: {data.business_date} · {warnings.length} uyarı
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={load} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
              Yenile
            </Button>
            <Button
              size="sm"
              onClick={onStartRun}
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
              data-testid="prep-start-btn"
            >
              <Play className="w-4 h-4 mr-1" />
              Denetim Başlat
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Genel durum kartları */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile icon={Bed} tone="indigo" label="Oda Toplam" value={rooms.total ?? '-'}
          hint={`Dolu ${rooms.occupied ?? 0} · Müsait ${rooms.available ?? 0}`} />
        <StatTile icon={Brush} tone="amber" label="Kirli Oda" value={rooms.dirty ?? 0}
          hint={`Arıza ${rooms.out_of_order ?? 0} · Blok ${rooms.blocked ?? 0}`} />
        <StatTile icon={Users} tone="emerald" label="İçerideki Misafir" value={guests.in_house ?? 0}
          hint={`Bugün giriş ${guests.arriving_today ?? 0} · Çıkış ${guests.departing_today ?? 0}`} />
        <StatTile icon={Calendar} tone="blue" label="İş Günü" value={data.business_date}
          hint={drift !== 0 ? `Takvim ${data.calendar_date}` : 'Takvimle aynı'} />
      </div>

      {/* Engelleyiciler */}
      {blockers.length > 0 && (
        <Card data-testid="blockers-card" className="border-rose-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2 text-rose-700">
              <AlertOctagon className="w-4 h-4" />
              Engelleyiciler ({blockers.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {blockers.map((b) => {
              const isOpen = expanded === b.category;
              return (
                <div key={b.category} className="border rounded-lg">
                  <button
                    type="button"
                    onClick={() => setExpanded(isOpen ? null : b.category)}
                    className="w-full flex items-start justify-between gap-3 px-3 py-2 text-left hover:bg-rose-50/50"
                    data-testid={`blocker-${b.category}`}
                  >
                    <div className="flex items-start gap-2 min-w-0">
                      <Badge className="bg-rose-100 text-rose-700 border border-rose-200 text-[11px] shrink-0">
                        {b.count}
                      </Badge>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-900">{b.label}</p>
                        <p className="text-xs text-gray-600">{b.message}</p>
                      </div>
                    </div>
                    <ArrowRight
                      className={`w-4 h-4 text-gray-400 shrink-0 transition-transform ${isOpen ? 'rotate-90' : ''}`}
                    />
                  </button>
                  {isOpen && (
                    <div className="border-t px-3 py-2 bg-gray-50/60 space-y-1">
                      {(b.items || []).length === 0 ? (
                        <p className="text-xs text-gray-500">Detay yok.</p>
                      ) : (
                        (b.items || []).map((it, idx) => {
                          const href = bookingHref(it);
                          return (
                            <div key={it.id || it.run_id || idx}
                              className="flex items-center justify-between text-xs px-2 py-1 rounded bg-white border">
                              <div className="min-w-0 flex items-center gap-2">
                                <span className="font-medium text-gray-800 truncate">
                                  {it.guest_name || it.confirmation_code || it.run_id || it.id || '-'}
                                </span>
                                {it.room_no && (
                                  <span className="text-gray-500">Oda {it.room_no}</span>
                                )}
                                {(it.check_in || it.check_out) && (
                                  <span className="text-gray-400">
                                    {it.check_in || '-'} → {it.check_out || '-'}
                                  </span>
                                )}
                                {it.status && (
                                  <Badge className="bg-gray-100 text-gray-600 border border-gray-200 text-[10px]">
                                    {it.status}
                                  </Badge>
                                )}
                              </div>
                              {href && (
                                <Button
                                  size="sm" variant="ghost"
                                  className="h-7 px-2 text-indigo-700 hover:text-indigo-900"
                                  onClick={() => navigate(href)}
                                >
                                  {ACTION_LABELS[b.action] || 'Aç'}
                                  <ArrowRight className="w-3.5 h-3.5 ml-1" />
                                </Button>
                              )}
                            </div>
                          );
                        })
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {/* Uyarılar */}
      {warnings.length > 0 && (
        <Card data-testid="warnings-card" className="border-amber-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2 text-amber-800">
              <AlertTriangle className="w-4 h-4" />
              Uyarılar ({warnings.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1.5">
              {warnings.map((w) => (
                <div key={w.category} className="flex items-start gap-2 text-xs px-3 py-2 bg-amber-50/60 rounded border border-amber-100">
                  <Info className="w-3.5 h-3.5 text-amber-600 mt-0.5" />
                  <div className="min-w-0">
                    <p className="font-medium text-gray-800">{w.label} <span className="text-amber-700">({w.count})</span></p>
                    <p className="text-gray-600">{w.message}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Hazır rozeti — engelleyici yoksa: yalnızca öneri notu, durum kartı yukarıda zaten gösteriyor */}
      {blockers.length === 0 && warnings.length === 0 && (
        <p className="text-xs text-gray-500 px-1" data-testid="ready-hint">
          İpucu: ilk kez çalıştırıyorsanız önce Simülasyon (kuru çalıştırma) yapıp ne yazılacağını kontrol etmenizi öneririz.
        </p>
      )}
    </div>
  );
}
