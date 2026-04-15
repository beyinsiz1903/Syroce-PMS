import { useState, useEffect } from 'react';
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

const CATEGORY_KEYS = ['guestId', 'folioInvoice', 'contactInfo', 'preferencesNotes', 'cameraRecords', 'marketingConsents', 'complaintRecords', 'employeeRecords'];
const RETENTION_KEYS = ['tenYears', 'tenYears', 'threeYears', 'fiveYears', 'thirtyDays', 'untilRevoked', 'fiveYears', 'fifteenYears'];
const LEGAL_KEYS = ['kbs', 'tax', 'consent', 'legitimate', 'security', 'explicitConsent', 'legal', 'labor'];
const REQUEST_TYPE_KEYS = ['access', 'erasure', 'rectification', 'portability', 'objection'];

const KVKKManager = () => {
  const { t } = useTranslation();
  const tv = (k) => t(`pmsComponents.kvkk.${k}`);

  const [activeTab, setActiveTab] = useState('policies');
  const [requests, setRequests] = useState([]);
  const [showNewRequest, setShowNewRequest] = useState(false);
  const [newRequest, setNewRequest] = useState({ guest_name: '', type: '', details: '' });
  const [consents, setConsents] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [reqRes, consentRes, auditRes] = await Promise.allSettled([
        axios.get('/kvkk/requests'),
        axios.get('/kvkk/consents'),
        axios.get('/kvkk/audit-log'),
      ]);
      if (reqRes.status === 'fulfilled') setRequests(reqRes.value.data.requests || []);
      if (consentRes.status === 'fulfilled') setConsents(consentRes.value.data.consents || []);
      if (auditRes.status === 'fulfilled') setAuditLogs(auditRes.value.data.logs || []);
    } catch {
      toast.error(tv('loadError'));
    } finally {
      setLoading(false);
    }
  };

  const createRequest = async () => {
    if (!newRequest.guest_name || !newRequest.type) return;
    try {
      const res = await axios.post('/kvkk/requests', newRequest);
      setRequests(prev => [res.data, ...prev]);
      setNewRequest({ guest_name: '', type: '', details: '' });
      setShowNewRequest(false);
      toast.success(tv('requestCreated'));
    } catch {
      toast.error(tv('createError'));
    }
  };

  const completeRequest = async (id) => {
    try {
      await axios.patch(`/kvkk/requests/${id}`, { status: 'completed' });
      setRequests(prev => prev.map(r => r.id === id ? { ...r, status: 'completed', response_date: new Date().toISOString().split('T')[0] } : r));
      toast.success(tv('requestCompleted'));
    } catch {
      toast.error(tv('completeError'));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <Shield className="h-5 w-5" /> {tv('title')}
        </h2>
        <Button onClick={() => setShowNewRequest(true)}>{tv('newRequest')}</Button>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <Card><CardContent className="p-3 text-center"><div className="text-2xl font-bold">{requests.length}</div><div className="text-xs text-muted-foreground">{tv('totalRequests')}</div></CardContent></Card>
        <Card className="border-yellow-200"><CardContent className="p-3 text-center"><div className="text-2xl font-bold text-yellow-600">{requests.filter(r => r.status === 'pending').length}</div><div className="text-xs text-muted-foreground">{tv('pending')}</div></CardContent></Card>
        <Card className="border-green-200"><CardContent className="p-3 text-center"><div className="text-2xl font-bold text-green-600">{requests.filter(r => r.status === 'completed').length}</div><div className="text-xs text-muted-foreground">{tv('completed')}</div></CardContent></Card>
        <Card><CardContent className="p-3 text-center"><div className="text-2xl font-bold">{CATEGORY_KEYS.length}</div><div className="text-xs text-muted-foreground">{tv('retentionPolicyCount')}</div></CardContent></Card>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="policies">{tv('policiesTab')}</TabsTrigger>
          <TabsTrigger value="requests">{tv('requestsTab')} ({requests.length})</TabsTrigger>
          <TabsTrigger value="consents">{tv('consentsTab')} ({consents.length})</TabsTrigger>
          <TabsTrigger value="audit">{tv('auditTab')} ({auditLogs.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="policies">
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted"><tr><th className="p-3 text-left">{tv('dataCategory')}</th><th className="p-3 text-left">{tv('retentionPeriod')}</th><th className="p-3 text-left">{tv('legalBasis')}</th><th className="p-3 text-left">{tv('statusLabel')}</th></tr></thead>
                  <tbody>
                    {CATEGORY_KEYS.map((catKey, i) => (
                      <tr key={catKey} className="border-t">
                        <td className="p-3 font-medium">{tv(`categories.${catKey}`)}</td>
                        <td className="p-3"><Badge variant="outline">{tv(`retentions.${RETENTION_KEYS[i]}`)}</Badge></td>
                        <td className="p-3 text-muted-foreground">{tv(`legalBases.${LEGAL_KEYS[i]}`)}</td>
                        <td className="p-3"><Badge className="bg-green-100 text-green-800">{tv('active')}</Badge></td>
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
          {!loading && requests.length === 0 && <p className="text-center text-muted-foreground py-8">{tv('noRequests')}</p>}
          {requests.map(req => (
            <Card key={req.id}>
              <CardContent className="p-3 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
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
                  <Button size="sm" onClick={() => completeRequest(req.id)}><CheckCircle className="h-3 w-3 mr-1" />{tv('completeRequest')}</Button>
                )}
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="consents">
          <Card>
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead className="bg-muted"><tr><th className="p-3 text-left">{tv('guestLabel')}</th><th className="p-3 text-center">{tv('emailMarketing')}</th><th className="p-3 text-center">{tv('smsMarketing')}</th><th className="p-3 text-center">{tv('dataSharing')}</th><th className="p-3 text-left">{tv('date')}</th></tr></thead>
                <tbody>
                  {consents.length === 0 && <tr><td colSpan="5" className="p-4 text-center text-muted-foreground">{tv('noConsents')}</td></tr>}
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
              </table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="audit">
          <Card>
            <CardContent className="p-4">
              <div className="space-y-3">
                {auditLogs.length === 0 && <p className="text-center text-muted-foreground py-4">{tv('noAuditLogs')}</p>}
                {auditLogs.map((log) => (
                  <div key={log.id} className="flex items-center justify-between border-b pb-2 last:border-0">
                    <div>
                      <div className="flex items-center gap-2">
                        <Database className="h-3 w-3 text-muted-foreground" />
                        <span className="text-sm font-medium">{log.action}</span>
                      </div>
                      <div className="text-xs text-muted-foreground">{tv('user')} {log.user} | {tv('target')} {log.target}</div>
                    </div>
                    <div className="text-xs text-muted-foreground">{log.timestamp ? new Date(log.timestamp).toLocaleString() : ''}</div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={showNewRequest} onOpenChange={setShowNewRequest}>
        <DialogContent>
          <DialogHeader><DialogTitle>{tv('newRequestTitle')}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>{tv('guestName')}</Label><Input value={newRequest.guest_name} onChange={e => setNewRequest(p => ({ ...p, guest_name: e.target.value }))} /></div>
            <div><Label>{tv('requestType')}</Label>
              <Select value={newRequest.type} onValueChange={v => setNewRequest(p => ({ ...p, type: v }))}>
                <SelectTrigger><SelectValue placeholder={tv('requestTypePlaceholder')} /></SelectTrigger>
                <SelectContent>
                  {REQUEST_TYPE_KEYS.map(k => (
                    <SelectItem key={k} value={k}>{tv(`requestTypes.${k}`)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div><Label>{tv('details')}</Label><Textarea value={newRequest.details} onChange={e => setNewRequest(p => ({ ...p, details: e.target.value }))} placeholder={tv('detailsPlaceholder')} /></div>
            <Button className="w-full" onClick={createRequest}>{tv('createRequest')}</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default KVKKManager;
