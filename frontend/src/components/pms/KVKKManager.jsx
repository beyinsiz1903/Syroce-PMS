import { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Shield, CheckCircle, Database, UserX
} from 'lucide-react';

const REQUEST_TYPE_KEYS = ['access', 'erasure', 'rectification', 'portability', 'objection'];
const POLICY_LABELS = {
  guest_pii: 'Misafir kişisel verileri',
  booking_history: 'Rezervasyon geçmişi',
  audit_logs: 'Denetim kayıtları',
  marketing_consents: 'Pazarlama izinleri',
};

// No endpoint's first page is a complete count. Stop visibly on an incomplete
// or non-advancing source instead of silently labelling a partial list "all".
async function loadAllPages(path, key, limit) {
  const rows = [];
  const seen = new Set();
  for (let page = 0; page < 100; page += 1) {
    const { data } = await axios.get(path, { params: { skip: page * limit, limit } });
    const chunk = data?.[key];
    if (!Array.isArray(chunk)) throw new Error('KVKK source contract is incomplete');
    for (const row of chunk) {
      if (!row?.id || seen.has(row.id)) throw new Error('KVKK source pagination did not advance');
      seen.add(row.id);
      rows.push(row);
    }
    const total = Number.isInteger(data.total) && data.total >= 0 ? data.total : null;
    if (total !== null && rows.length >= total) return rows;
    if (chunk.length < limit) {
      if (total !== null && rows.length < total) throw new Error('KVKK source ended before its total');
      return rows;
    }
  }
  throw new Error('KVKK source exceeded the safe pagination window');
}

const KVKKManager = () => {
  const { t } = useTranslation();
  const tv = useCallback((k) => t(`pmsComponents.kvkk.${k}`), [t]);

  const [activeTab, setActiveTab] = useState('policies');
  const [requests, setRequests] = useState([]);
  const [showNewRequest, setShowNewRequest] = useState(false);
  const [newRequest, setNewRequest] = useState({ guest_name: '', type: '', details: '' });
  const [consents, setConsents] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [retentionPolicy, setRetentionPolicy] = useState(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [loadWarning, setLoadWarning] = useState('');
  const [failedSources, setFailedSources] = useState({});
  const loadVersionRef = useRef(0);
  const mutationRef = useRef(false);

  const loadData = useCallback(async () => {
    const version = ++loadVersionRef.current;
    setLoading(true);
    setLoadWarning('');
    try {
      const [reqRes, consentRes, auditRes, policyRes] = await Promise.allSettled([
        loadAllPages('/kvkk/requests', 'requests', 100),
        loadAllPages('/kvkk/consents', 'consents', 100),
        loadAllPages('/kvkk/audit-log', 'logs', 200),
        axios.get('/gdpr/retention-policy'),
      ]);
      if (version !== loadVersionRef.current) return;
      if (reqRes.status === 'fulfilled') setRequests(reqRes.value); else setRequests([]);
      if (consentRes.status === 'fulfilled') setConsents(consentRes.value); else setConsents([]);
      if (auditRes.status === 'fulfilled') setAuditLogs(auditRes.value); else setAuditLogs([]);
      if (policyRes.status === 'fulfilled') setRetentionPolicy(policyRes.value.data || null); else setRetentionPolicy(null);
      setFailedSources({ requests: reqRes.status === 'rejected', consents: consentRes.status === 'rejected', audit: auditRes.status === 'rejected' });
      const failed = [reqRes, consentRes, auditRes, policyRes].filter(result => result.status === 'rejected').length;
      if (failed) {
        const message = `${failed} KVKK veri kaynağı yüklenemedi. Eksik bilgiler gösterilmiyor.`;
        setLoadWarning(message);
        toast.warning(message);
      }
    } catch {
      toast.error(tv('loadError'));
    } finally {
      if (version === loadVersionRef.current) setLoading(false);
    }
  }, [tv]);

  useEffect(() => { loadData(); return () => { loadVersionRef.current += 1; }; }, [loadData]);

  const createRequest = async () => {
    if (mutationRef.current || !newRequest.guest_name.trim() || !newRequest.type) return;
    mutationRef.current = true;
    setSubmitting(true);
    try {
      const res = await axios.post('/kvkk/requests', newRequest);
      setRequests(prev => [res.data, ...prev]);
      setNewRequest({ guest_name: '', type: '', details: '' });
      setShowNewRequest(false);
      toast.success(tv('requestCreated'));
      await loadData();
    } catch {
      toast.error(tv('createError'));
    } finally {
      mutationRef.current = false;
      setSubmitting(false);
    }
  };

  const completeRequest = async (id) => {
    if (mutationRef.current) return;
    mutationRef.current = true;
    setSubmitting(true);
    try {
      await axios.patch(`/kvkk/requests/${id}`, { status: 'completed' });
      await loadData();
      toast.success(tv('requestCompleted'));
    } catch {
      toast.error(tv('completeError'));
    } finally {
      mutationRef.current = false;
      setSubmitting(false);
    }
  };

  const count = (source, value) => loading ? '…' : failedSources[source] ? '—' : value;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <Shield className="h-5 w-5" /> {tv('title')}
        </h2>
        <div className="flex gap-2"><Button variant="outline" onClick={loadData} disabled={loading || submitting}>Yenile</Button><Button onClick={() => setShowNewRequest(true)} disabled={submitting}>{tv('newRequest')}</Button></div>
      </div>

      {loadWarning && <div role="alert" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">{loadWarning}</div>}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card><CardContent className="p-3 text-center"><div className="text-2xl font-bold">{count('requests', requests.length)}</div><div className="text-xs text-muted-foreground">{tv('totalRequests')}</div></CardContent></Card>
        <Card className="border-yellow-200"><CardContent className="p-3 text-center"><div className="text-2xl font-bold text-yellow-600">{count('requests', requests.filter(r => r.status === 'pending').length)}</div><div className="text-xs text-muted-foreground">{tv('pending')}</div></CardContent></Card>
        <Card className="border-green-200"><CardContent className="p-3 text-center"><div className="text-2xl font-bold text-green-600">{count('requests', requests.filter(r => r.status === 'completed').length)}</div><div className="text-xs text-muted-foreground">{tv('completed')}</div></CardContent></Card>
        <Card><CardContent className="p-3 text-center"><div className="text-2xl font-bold">{retentionPolicy?.policies?.length ?? '—'}</div><div className="text-xs text-muted-foreground">{tv('retentionPolicyCount')}</div></CardContent></Card>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="flex w-full justify-start overflow-x-auto">
          <TabsTrigger className="shrink-0" value="policies">{tv('policiesTab')}</TabsTrigger>
          <TabsTrigger className="shrink-0" value="requests">{tv('requestsTab')} ({count('requests', requests.length)})</TabsTrigger>
          <TabsTrigger className="shrink-0" value="consents">{tv('consentsTab')} ({count('consents', consents.length)})</TabsTrigger>
          <TabsTrigger className="shrink-0" value="audit">{tv('auditTab')} ({count('audit', auditLogs.length)})</TabsTrigger>
        </TabsList>

        <TabsContent value="policies">
          <Card>
            <CardContent className="p-0">
              {retentionPolicy && <div className="flex flex-wrap gap-2 border-b p-3 text-xs"><Badge variant={retentionPolicy.configured ? 'default' : 'secondary'}>{retentionPolicy.configured ? 'Tesise özel politika' : 'Varsayılan politika'}</Badge><Badge variant="outline">Otomatik anonimleştirme: {retentionPolicy.auto_anonymize ? 'Açık' : 'Kapalı'}</Badge></div>}
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted"><tr><th className="p-3 text-left">{tv('dataCategory')}</th><th className="p-3 text-left">{tv('retentionPeriod')}</th><th className="p-3 text-left">Anonimleştirme</th><th className="p-3 text-left">{tv('statusLabel')}</th></tr></thead>
                  <tbody>
                    {!retentionPolicy && !loading && <tr><td colSpan="4" className="p-4 text-center text-muted-foreground">Saklama politikası yüklenemedi.</td></tr>}
                    {(retentionPolicy?.policies || []).map((policy) => (
                      <tr key={policy.data_type} className="border-t">
                        <td className="p-3 font-medium">{POLICY_LABELS[policy.data_type] || policy.data_type}</td>
                        <td className="p-3"><Badge variant="outline">{policy.retention_days} gün</Badge></td>
                        <td className="p-3 text-muted-foreground">{policy.auto_anonymize ? 'Süre sonunda otomatik' : 'Manuel/yasal süreç'}</td>
                        <td className="p-3"><Badge className={retentionPolicy.configured ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'}>{retentionPolicy.configured ? 'Yapılandırıldı' : 'Varsayılan'}</Badge></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="requests" className="space-y-2">
          {loading && <p className="text-center text-muted-foreground py-4">{tv('loading')}</p>}
          {!loading && !failedSources.requests && requests.length === 0 && <p className="text-center text-muted-foreground py-8">{tv('noRequests')}</p>}
          {requests.map(req => (
            <Card key={req.id}>
              <CardContent className="flex flex-col gap-3 p-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{req.guest_name}</span>
                    <Badge variant="outline">{tv(`requestTypes.${req.type}`)}</Badge>
                    <Badge variant={req.status === 'completed' ? 'default' : req.status === 'pending' ? 'secondary' : 'outline'}>
                      {req.status === 'completed' ? tv('completed') : req.status === 'pending' ? tv('pending') : tv('processing')}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">{req.details}</p>
                  <div className="text-xs text-muted-foreground">
                    {tv('requestDate')} {req.date} {req.response_date ? `| ${tv('responseDate')} ${req.response_date}` : `| ${tv('mustRespond')}`}
                  </div>
                </div>
                {req.status !== 'completed' && (
                  <Button className="w-full sm:w-auto" size="sm" disabled={submitting || loading} onClick={() => completeRequest(req.id)}><CheckCircle className="h-3 w-3 mr-1" />{tv('completeRequest')}</Button>
                )}
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="consents">
          <Card className="overflow-hidden">
            <CardContent className="p-0">
              <div className="overflow-x-auto"><table className="w-full min-w-[640px] text-sm">
                <thead className="bg-muted"><tr><th className="p-3 text-left">{tv('guestLabel')}</th><th className="p-3 text-center">{tv('emailMarketing')}</th><th className="p-3 text-center">{tv('smsMarketing')}</th><th className="p-3 text-center">{tv('dataSharing')}</th><th className="p-3 text-left">{tv('date')}</th></tr></thead>
                <tbody>
                  {!loading && !failedSources.consents && consents.length === 0 && <tr><td colSpan="5" className="p-4 text-center text-muted-foreground">{tv('noConsents')}</td></tr>}
                  {consents.map(c => (
                    <tr key={c.id} className="border-t">
                      <td className="p-3 font-medium">{c.guest_name}</td>
                      <td className="p-3 text-center">{c.email_marketing ? <CheckCircle className="h-4 w-4 text-green-500 mx-auto" /> : <UserX className="h-4 w-4 text-red-400 mx-auto" />}</td>
                      <td className="p-3 text-center">{c.sms_marketing ? <CheckCircle className="h-4 w-4 text-green-500 mx-auto" /> : <UserX className="h-4 w-4 text-red-400 mx-auto" />}</td>
                      <td className="p-3 text-center">{c.data_sharing ? <CheckCircle className="h-4 w-4 text-green-500 mx-auto" /> : <UserX className="h-4 w-4 text-red-400 mx-auto" />}</td>
                      <td className="p-3 text-muted-foreground">{c.date}</td>
                    </tr>
                  ))}
                </tbody>
              </table></div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="audit">
          <Card>
            <CardContent className="p-4">
              <div className="space-y-3">
                {!loading && !failedSources.audit && auditLogs.length === 0 && <p className="text-center text-muted-foreground py-4">{tv('noAuditLogs')}</p>}
                {auditLogs.map((log) => (
                  <div key={log.id} className="flex flex-col gap-1 border-b pb-2 last:border-0 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <Database className="h-3 w-3 text-muted-foreground" />
                        <span className="text-sm font-medium">{log.action}</span>
                      </div>
                      <div className="text-xs text-muted-foreground">{tv('user')} {log.user} | {tv('target')} {log.target}</div>
                    </div>
                    <div className="text-xs text-muted-foreground">{log.timestamp ? new Date(log.timestamp).toLocaleString('tr-TR') : ''}</div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={showNewRequest} onOpenChange={open => { if (!mutationRef.current) setShowNewRequest(open); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>{tv('newRequestTitle')}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label htmlFor="kvkk-request-guest">{tv('guestName')}</Label><Input id="kvkk-request-guest" disabled={submitting} value={newRequest.guest_name} onChange={e => setNewRequest(p => ({ ...p, guest_name: e.target.value }))} /></div>
            <div><Label>{tv('requestType')}</Label>
              <Select disabled={submitting} value={newRequest.type} onValueChange={v => setNewRequest(p => ({ ...p, type: v }))}>
                <SelectTrigger><SelectValue placeholder={tv('requestTypePlaceholder')} /></SelectTrigger>
                <SelectContent>
                  {REQUEST_TYPE_KEYS.map(k => (
                    <SelectItem key={k} value={k}>{tv(`requestTypes.${k}`)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div><Label htmlFor="kvkk-request-details">{tv('details')}</Label><Textarea id="kvkk-request-details" disabled={submitting} value={newRequest.details} onChange={e => setNewRequest(p => ({ ...p, details: e.target.value }))} placeholder={tv('detailsPlaceholder')} /></div>
            <Button className="w-full" onClick={createRequest} disabled={submitting || !newRequest.guest_name.trim() || !newRequest.type}>{tv('createRequest')}</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default KVKKManager;
