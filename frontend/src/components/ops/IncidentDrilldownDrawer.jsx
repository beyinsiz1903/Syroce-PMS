import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { alertDialog } from '@/lib/dialogs';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  RefreshCw,
  XCircle,
  ArrowRight,
  ChevronRight,
  Activity,
  Send,
  RotateCcw,
  Bell,
  Inbox,
  Timer,
  User,
  Link2,
  Hash,
  Calendar,
  AlertCircle,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const API = "";

const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

// ── Helper Components ──────────────────────────────────────────────

const SeverityIcon = ({ severity, className = "w-4 h-4" }) => {
  const { t } = useTranslation();
  const map = {
    critical: <XCircle className={`${className} text-red-600`} />,
    warning: <AlertTriangle className={`${className} text-amber-600`} />,
    info: <Activity className={`${className} text-blue-600`} />,
    success: <CheckCircle2 className={`${className} text-green-600`} />,
  };
  return map[severity] || map.info;
};

const SeverityBadge = ({ severity }) => {
  const map = {
    critical: 'bg-red-100 text-red-800',
    warning: 'bg-amber-100 text-amber-800',
    info: 'bg-blue-100 text-blue-800',
    success: 'bg-green-100 text-green-800',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${map[severity] || map.info}`}>
      {severity}
    </span>
  );
};

const StatusBadge = ({ status }) => {
  const map = {
    succeeded: { color: 'bg-green-100 text-green-800', icon: CheckCircle2 },
    failed: { color: 'bg-red-100 text-red-800', icon: XCircle },
    dlq: { color: 'bg-red-100 text-red-800', icon: Inbox },
    retrying: { color: 'bg-amber-100 text-amber-800', icon: RotateCcw },
    pending: { color: 'bg-gray-100 text-gray-800', icon: Clock },
    delivering: { color: 'bg-blue-100 text-blue-800', icon: Send },
    resolved: { color: 'bg-green-100 text-green-800', icon: CheckCircle2 },
  };
  const s = map[status] || map.pending;
  const Icon = s.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${s.color}`}>
      <Icon className="w-3 h-3" />
      {status}
    </span>
  );
};

const TimeAgo = ({ timestamp }) => {
  if (!timestamp) return <span className="text-xs text-gray-400">—</span>;
  const now = new Date();
  const then = new Date(timestamp);
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);
  const diffHour = Math.floor(diffMs / 3600000);
  const diffDay = Math.floor(diffMs / 86400000);

  let text;
  if (diffMin < 1) text = 'az önce';
  else if (diffMin < 60) text = `${diffMin} dk önce`;
  else if (diffHour < 24) text = `${diffHour} sa önce`;
  else text = `${diffDay} gün önce`;

  return <span className="text-xs text-gray-500" title={then.toLocaleString('tr-TR')}>{text}</span>;
};

const InfoRow = ({ icon: Icon, label, value, mono = false }) => (
  <div className="flex items-center gap-2 text-xs">
    <Icon className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
    <span className="text-gray-500">{label}:</span>
    <span className={`text-gray-700 ${mono ? 'font-mono' : ''} truncate`}>{value || '—'}</span>
  </div>
);

// ── Timeline Node Component ────────────────────────────────────────

const TimelineNode = ({ event, isFirst, isLast }) => {
  const [expanded, setExpanded] = useState(false);
  
  const getEventIcon = (eventType) => {
    if (eventType.includes('started')) return <Send className="w-3 h-3" />;
    if (eventType.includes('succeeded') || eventType.includes('completed')) return <CheckCircle2 className="w-3 h-3" />;
    if (eventType.includes('retry')) return <RotateCcw className="w-3 h-3" />;
    if (eventType.includes('failed') || eventType.includes('terminal') || eventType.includes('dlq')) return <XCircle className="w-3 h-3" />;
    if (eventType.includes('throttle') || eventType.includes('rate_limit')) return <Timer className="w-3 h-3" />;
    return <Activity className="w-3 h-3" />;
  };

  const getNodeColor = (severity) => {
    const map = {
      critical: 'bg-red-500',
      warning: 'bg-amber-500',
      success: 'bg-green-500',
      info: 'bg-blue-500',
    };
    return map[severity] || map.info;
  };

  return (
    <div className="relative flex gap-3">
      {/* Timeline line */}
      <div className="flex flex-col items-center">
        <div className={`w-6 h-6 rounded-full flex items-center justify-center text-white ${getNodeColor(event.severity)}`}>
          {getEventIcon(event.event_type)}
        </div>
        {!isLast && <div className="w-0.5 h-full bg-gray-200 my-1" />}
      </div>
      
      {/* Event content */}
      <div className="flex-1 pb-4">
        <div 
          className="border rounded-lg p-3 cursor-pointer hover:bg-gray-50 transition-colors"
          onClick={() => setExpanded(!expanded)}
          data-testid={`timeline-node-${event.event_id}`}
        >
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-2">
              <SeverityBadge severity={event.severity} />
              <span className="font-medium text-sm text-gray-900">{event.title}</span>
            </div>
            <div className="flex items-center gap-2">
              <TimeAgo timestamp={event.timestamp} />
              <ChevronRight className={`w-4 h-4 text-gray-400 transition-transform ${expanded ? 'rotate-90' : ''}`} />
            </div>
          </div>
          <p className="text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded inline-block">
            {event.event_type}
          </p>
          
          {expanded && event.details && Object.keys(event.details).length > 0 && (
            <div className="mt-3 pt-3 border-t">
              <p className="text-xs font-medium text-gray-600 mb-2">Detaylar:</p>
              <div className="space-y-1">
                {Object.entries(event.details).map(([key, value]) => (
                  <div key={key} className="flex text-xs">
                    <span className="text-gray-500 w-32 flex-shrink-0">{key}:</span>
                    <span className="text-gray-700 font-mono break-all">
                      {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// ── Main Drawer Component ──────────────────────────────────────────

const IncidentDrilldownDrawer = ({ open, onClose, correlationId, eventId, onRetryDlq }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [timelineData, setTimelineData] = useState(null);
  const [incidentData, setIncidentData] = useState(null);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    if (!open) return;
    
    if (correlationId) {
      fetchTimeline(correlationId);
    } else if (eventId) {
      fetchIncident(eventId);
    }
  }, [open, correlationId, eventId]);

  const fetchTimeline = async (corrId) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await axios.get(`/ops-events/timeline/${corrId}`, {
        headers: getAuthHeaders(),
      });
      setTimelineData(resp.data);
      setIncidentData(null);
    } catch (err) {
      setError(err.response?.data?.detail || 'Timeline verisi alınamadı');
    } finally {
      setLoading(false);
    }
  };

  const fetchIncident = async (evId) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await axios.get(`/ops-events/incident/${evId}/summary`, {
        headers: getAuthHeaders(),
      });
      setIncidentData(resp.data);
      
      // If incident has correlation_id, also fetch full timeline
      if (resp.data.correlation_id) {
        const timelineResp = await axios.get(`/ops-events/timeline/${resp.data.correlation_id}`, {
          headers: getAuthHeaders(),
        });
        setTimelineData(timelineResp.data);
      } else {
        setTimelineData(null);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Incident verisi alınamadı');
    } finally {
      setLoading(false);
    }
  };

  const handleDlqRetry = async () => {
    if (!timelineData?.dlq_item?.id) return;
    setRetrying(true);
    try {
      await axios.post(`/ops-events/webhook-dlq/${timelineData.dlq_item.id}/retry`, {}, {
        headers: getAuthHeaders(),
      });
      // Refresh data
      if (correlationId) fetchTimeline(correlationId);
      if (onRetryDlq) onRetryDlq();
    } catch (err) {
      alertDialog({ message: err.response?.data?.detail || 'Retry başarısız' });
    } finally {
      setRetrying(false);
    }
  };

  const summary = timelineData?.summary;
  const timeline = timelineData?.timeline || [];
  const delivery = timelineData?.delivery;
  const dlqItem = timelineData?.dlq_item;

  return (
    <Sheet open={open} onOpenChange={onClose}>
      <SheetContent className="w-[500px] sm:w-[600px] sm:max-w-full p-0" data-testid="incident-drilldown-drawer">
        <SheetHeader className="px-6 py-4 border-b bg-gray-50">
          <SheetTitle className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-blue-600" />
            Olay Timeline Drilldown
          </SheetTitle>
        </SheetHeader>

        <ScrollArea className="h-[calc(100vh-80px)]">
          <div className="p-6 space-y-6">
            {loading && (
              <div className="flex items-center justify-center py-12">
                <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
                <span className="ml-2 text-gray-600">{t('cm.components_ops_IncidentDrilldownDrawer.yukleniyor')}</span>
              </div>
            )}

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                {error}
              </div>
            )}

            {!loading && !error && summary && (
              <>
                {/* Summary Card */}
                <Card data-testid="timeline-summary-card">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base flex items-center justify-between">
                      <span>{t('cm.components_ops_IncidentDrilldownDrawer.ozet')}</span>
                      <div className="flex items-center gap-2">
                        {summary.is_recovered && (
                          <Badge className="bg-green-100 text-green-800">
                            <CheckCircle2 className="w-3 h-3 mr-1" /> {t('cm.components_ops_IncidentDrilldownDrawer.cozuldu')}
                          </Badge>
                        )}
                        {summary.is_terminal_failure && (
                          <Badge className="bg-red-100 text-red-800">
                            <XCircle className="w-3 h-3 mr-1" /> Terminal Failure
                          </Badge>
                        )}
                        {!summary.is_recovered && !summary.is_terminal_failure && (
                          <Badge className="bg-amber-100 text-amber-800">
                            <Clock className="w-3 h-3 mr-1" /> Devam Ediyor
                          </Badge>
                        )}
                      </div>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <InfoRow icon={Hash} label="Correlation ID" value={summary.correlation_id} mono />
                    <InfoRow icon={Calendar} label={t('cm.components_ops_IncidentDrilldownDrawer.baslangic')} value={new Date(summary.started_at).toLocaleString('tr-TR')} />
                    <InfoRow icon={Calendar} label={t('cm.components_ops_IncidentDrilldownDrawer.bitis')} value={new Date(summary.ended_at).toLocaleString('tr-TR')} />
                    <InfoRow icon={Timer} label={t('cm.components_ops_IncidentDrilldownDrawer.sure')} value={`${summary.duration_seconds} saniye`} />
                    <InfoRow icon={RotateCcw} label={t('cm.components_ops_IncidentDrilldownDrawer.retry_sayisi')} value={summary.retry_count} />
                    <InfoRow icon={Activity} label={t('cm.components_ops_IncidentDrilldownDrawer.event_sayisi')} value={summary.event_count} />
                    <InfoRow icon={Link2} label="Kanal" value={summary.affected_channel} />
                    <InfoRow icon={User} label="Tenant" value={summary.affected_tenant} />
                    
                    {summary.last_error && (
                      <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg">
                        <p className="text-xs font-medium text-red-700 mb-1">{t('cm.components_ops_IncidentDrilldownDrawer.son_hata')}</p>
                        <p className="text-xs text-red-600 font-mono break-all">{summary.last_error}</p>
                      </div>
                    )}

                    <div className="pt-3 flex items-center gap-2">
                      <SeverityBadge severity={summary.max_severity} />
                      <span className="text-xs text-gray-500">{t('cm.components_ops_IncidentDrilldownDrawer.en_yuksek_severity')}</span>
                    </div>
                  </CardContent>
                </Card>

                {/* DLQ Action Card */}
                {dlqItem && dlqItem.status === 'pending' && (
                  <Card className="border-red-200 bg-red-50/50" data-testid="dlq-action-card">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base flex items-center gap-2 text-red-800">
                        <Inbox className="w-4 h-4" />
                        DLQ - Manuel Aksiyon Gerekli
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2 text-xs mb-4">
                        <p><span className="text-gray-500">URL:</span> <span className="font-mono">{dlqItem.url}</span></p>
                        <p><span className="text-gray-500">Event:</span> <span className="font-medium">{dlqItem.event}</span></p>
                        <p><span className="text-gray-500">Deneme:</span> {dlqItem.attempt_count}/5</p>
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        className="w-full border-red-300 text-red-700 hover:bg-red-100"
                        onClick={handleDlqRetry}
                        disabled={retrying}
                        data-testid="dlq-retry-button"
                      >
                        {retrying ? (
                          <>
                            <RefreshCw className="w-3 h-3 mr-1 animate-spin" />
                            {t('cm.components_ops_IncidentDrilldownDrawer.retry_yapiliyor')}
                          </>
                        ) : (
                          <>
                            <RotateCcw className="w-3 h-3 mr-1" />
                            {t('cm.components_ops_IncidentDrilldownDrawer.simdi_retry_yap')}
                          </>
                        )}
                      </Button>
                    </CardContent>
                  </Card>
                )}

                {/* Delivery Details */}
                {delivery && (
                  <Card data-testid="delivery-details-card">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-base flex items-center gap-2">
                        <Send className="w-4 h-4" />
                        {t('cm.components_ops_IncidentDrilldownDrawer.webhook_teslimat_detayi')}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="text-gray-500">{t('cm.components_ops_IncidentDrilldownDrawer.durum')}</span>
                        <StatusBadge status={delivery.status} />
                      </div>
                      <InfoRow icon={Link2} label="URL" value={delivery.url} mono />
                      <InfoRow icon={Activity} label="Event" value={delivery.event} />
                      <InfoRow icon={RotateCcw} label="Deneme" value={`${delivery.attempt_count}/${delivery.max_attempts || 5}`} />
                      <InfoRow icon={Hash} label="Idempotency Key" value={delivery.idempotency_key} mono />
                      
                      {delivery.attempts && delivery.attempts.length > 0 && (
                        <div className="mt-3 pt-3 border-t">
                          <p className="text-xs font-medium text-gray-700 mb-2">{t('cm.components_ops_IncidentDrilldownDrawer.deneme_gecmisi')}</p>
                          <div className="space-y-1">
                            {delivery.attempts.map((att, i) => (
                              <div key={i} className="flex items-center justify-between text-[10px] p-1.5 bg-gray-50 rounded">
                                <span>#{att.attempt_number}</span>
                                <span className={att.error ? 'text-red-600' : 'text-green-600'}>
                                  {att.error || `HTTP ${att.status_code}`}
                                </span>
                                <span className="text-gray-400">
                                  {new Date(att.started_at).toLocaleTimeString('tr-TR')}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* Impact */}
                {incidentData?.impact && (
                  <Card data-testid="impact-card">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-base flex items-center gap-2">
                        <AlertCircle className="w-4 h-4" />
                        Etki Analizi
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2 text-xs">
                      <InfoRow icon={User} label="Etkilenen Tenant" value={incidentData.impact.affected_tenant} />
                      <InfoRow icon={Link2} label="Etkilenen Kanal" value={incidentData.impact.affected_channel} />
                      <div className="flex items-center gap-2">
                        <Bell className="w-3.5 h-3.5 text-gray-400" />
                        <span className="text-gray-500">{t('cm.components_ops_IncidentDrilldownDrawer.bildirim_gonderildi')}</span>
                        {incidentData.impact.notification_sent ? (
                          <CheckCircle2 className="w-4 h-4 text-green-600" />
                        ) : (
                          <XCircle className="w-4 h-4 text-gray-400" />
                        )}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Timeline */}
                {timeline.length > 0 && (
                  <Card data-testid="timeline-events-card">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-base flex items-center gap-2">
                        <ArrowRight className="w-4 h-4" />
                        Event Timeline ({timeline.length} {t('cm.components_ops_IncidentDrilldownDrawer.adim')}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-0">
                        {timeline.map((ev, i) => (
                          <TimelineNode
                            key={ev.event_id || i}
                            event={ev}
                            isFirst={i === 0}
                            isLast={i === timeline.length - 1}
                          />
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}
              </>
            )}

            {/* Single event view (no correlation_id) */}
            {!loading && !error && !summary && incidentData?.event && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">{t('cm.components_ops_IncidentDrilldownDrawer.tek_event_detayi')}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center gap-2">
                    <SeverityIcon severity={incidentData.event.severity} />
                    <span className="font-medium">{incidentData.event.title}</span>
                  </div>
                  <SeverityBadge severity={incidentData.event.severity} />
                  <p className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">
                    {incidentData.event.event_type}
                  </p>
                  <InfoRow icon={Calendar} label="Zaman" value={new Date(incidentData.event.created_at).toLocaleString('tr-TR')} />
                  <InfoRow icon={Link2} label="Kanal" value={incidentData.event.channel} />
                  
                  {incidentData.event.details && Object.keys(incidentData.event.details).length > 0 && (
                    <div className="mt-3 pt-3 border-t">
                      <p className="text-xs font-medium text-gray-700 mb-2">Detaylar:</p>
                      <pre className="text-[10px] bg-gray-50 p-2 rounded overflow-x-auto">
                        {JSON.stringify(incidentData.event.details, null, 2)}
                      </pre>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
};

export default IncidentDrilldownDrawer;
