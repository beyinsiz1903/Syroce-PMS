import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Skeleton } from './ui/skeleton';
import { api } from '../lib/api';
import { History, Edit3, LogIn, LogOut, Trash2, Plus, ArrowRight } from 'lucide-react';

const ACTION_MAP = {
  created: { label: 'Oluşturuldu', icon: Plus, color: 'var(--brand-sky)', bg: 'var(--brand-sky-soft)' },
  updated: { label: 'Güncellendi', icon: Edit3, color: 'var(--brand-warning)', bg: 'var(--brand-warning-soft)' },
  checked_in: { label: 'Check-in', icon: LogIn, color: 'var(--brand-success)', bg: 'var(--brand-success-soft)' },
  checked_out: { label: 'Check-out', icon: LogOut, color: 'var(--brand-info)', bg: 'var(--brand-info-soft)' },
  deleted: { label: 'Silindi', icon: Trash2, color: 'var(--brand-danger)', bg: 'var(--brand-danger-soft)' },
};

const FIELD_LABELS = {
  first_name: 'Ad',
  last_name: 'Soyad',
  id_number: 'Kimlik No',
  birth_date: 'Doğum Tarihi',
  gender: 'Cinsiyet',
  nationality: 'Uyruk',
  document_type: 'Belge Türü',
  document_number: 'Belge No',
  birth_place: 'Doğum Yeri',
  expiry_date: 'Geçerlilik Tarihi',
  issue_date: 'Veriliş Tarihi',
  notes: 'Not',
  status: 'Durum',
  mother_name: 'Anne Adı',
  father_name: 'Baba Adı',
  address: 'Adres',
};

export default function AuditTrail({ guestId }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (guestId) loadAudit();
  }, [guestId]);

  const loadAudit = async () => {
    try {
      const data = await api.getGuestAudit(guestId);
      setLogs(data.audit_logs || []);
    } catch (err) {
      console.error('Failed to load audit:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    try {
      return new Date(dateStr).toLocaleString('tr-TR', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit'
      });
    } catch { return dateStr; }
  };

  if (loading) {
    return (
      <Card className="bg-white">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Denetim İzi</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="bg-white">
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <History className="w-4 h-4 text-[var(--brand-sky)]" />
          Denetim İzi
          <Badge variant="outline" className="text-[10px] ml-1">{logs.length} kayıt</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent data-testid="audit-trail-section">
        {logs.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-6">Denetim kaydı yok</p>
        ) : (
          <div className="space-y-3">
            {logs.map((log) => {
              const actionConfig = ACTION_MAP[log.action] || ACTION_MAP.updated;
              const ActionIcon = actionConfig.icon;
              const changes = log.changes || {};
              const hasManualEdits = log.metadata?.had_manual_edits;
              
              return (
                <div key={log.id} className="relative pl-8 pb-3 border-b border-[hsl(var(--border))] last:border-0 last:pb-0">
                  {/* Timeline dot */}
                  <div 
                    className="absolute left-0 top-0.5 w-6 h-6 rounded-full flex items-center justify-center"
                    style={{ backgroundColor: actionConfig.bg }}
                  >
                    <ActionIcon className="w-3 h-3" style={{ color: actionConfig.color }} />
                  </div>
                  
                  {/* Header */}
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium" style={{ color: actionConfig.color }}>
                      {actionConfig.label}
                    </span>
                    {hasManualEdits && log.action === 'created' && (
                      <Badge variant="outline" className="text-[10px] bg-[var(--brand-amber-soft)] text-[var(--brand-amber)] border-[#FED7AA]">
                        Manuel Düzenleme
                      </Badge>
                    )}
                    <span className="text-[10px] text-muted-foreground ml-auto">
                      {formatDate(log.created_at)}
                    </span>
                  </div>
                  
                  {/* Field changes */}
                  {Object.keys(changes).length > 0 && (
                    <div className="space-y-1">
                      {Object.entries(changes).map(([field, diff]) => (
                        <div key={field} className="flex items-center gap-1.5 text-xs">
                          <span className="text-muted-foreground font-medium min-w-[80px]">
                            {FIELD_LABELS[field] || field}:
                          </span>
                          {diff.old && (
                            <span className="text-[var(--brand-danger)] line-through bg-[var(--brand-danger-soft)] px-1 rounded">
                              {diff.old}
                            </span>
                          )}
                          {diff.old && diff.new && (
                            <ArrowRight className="w-3 h-3 text-muted-foreground shrink-0" />
                          )}
                          {diff.new && (
                            <span className="text-[var(--brand-success)] bg-[var(--brand-success-soft)] px-1 rounded">
                              {diff.new}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Creation with original data comparison */}
                  {log.action === 'created' && hasManualEdits && (
                    <div className="mt-1.5 p-2 rounded bg-[var(--brand-amber-soft)] border border-[#FED7AA]">
                      <p className="text-[10px] font-medium text-[var(--brand-amber)] mb-1">AI Çıkarımı vs Manuel Düzeltme</p>
                      {Object.entries(changes).map(([field, diff]) => (
                        <div key={field} className="flex items-center gap-1.5 text-[11px]">
                          <span className="text-muted-foreground min-w-[80px]">{FIELD_LABELS[field] || field}:</span>
                          <span className="text-[var(--brand-slate)]">{diff.old || '—'}</span>
                          <ArrowRight className="w-2.5 h-2.5 text-muted-foreground" />
                          <span className="font-medium text-[var(--brand-ink)]">{diff.new || '—'}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
