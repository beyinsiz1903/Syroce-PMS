import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { format } from 'date-fns';
import { 
  Activity, Database, RefreshCw, AlertTriangle, CheckCircle, XCircle, 
  ChevronLeft, ChevronRight, ArrowRightLeft 
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';

const StatusBadge = ({ status, code }) => {
  if (status === 'success') {
    return <Badge className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20"><CheckCircle className="w-3 h-3 mr-1" /> Success {code ? `(${code})` : ''}</Badge>;
  }
  if (status === 'noop') {
    return <Badge className="bg-zinc-500/10 text-zinc-400 border-zinc-500/20"><AlertTriangle className="w-3 h-3 mr-1" /> No Data</Badge>;
  }
  return <Badge className="bg-red-500/10 text-red-500 border-red-500/20"><XCircle className="w-3 h-3 mr-1" /> Failed {code ? `(${code})` : ''}</Badge>;
};

export default function IntegrationObservabilityDashboard() {
  const { t } = useTranslation();
  
  // Finance State
  const [financeLogs, setFinanceLogs] = useState([]);
  const [financeLoading, setFinanceLoading] = useState(true);
  const [financePage, setFinancePage] = useState(1);
  const [financeTotalPages, setFinanceTotalPages] = useState(1);
  const [financeProviderFilter, setFinanceProviderFilter] = useState('all');
  
  // ARI State
  const [driftStates, setDriftStates] = useState([]);
  const [driftLoading, setDriftLoading] = useState(true);
  const [outboundLogs, setOutboundLogs] = useState([]);
  const [outboundLoading, setOutboundLoading] = useState(true);

  const fetchFinanceLogs = useCallback(async (page = 1, provider = 'all') => {
    setFinanceLoading(true);
    try {
      let url = `/finance/integration/logs?page=${page}&limit=20`;
      if (provider !== 'all') url += `&provider=${provider}`;
      const res = await axios.get(url);
      setFinanceLogs(res.data.logs || []);
      setFinanceTotalPages(res.data.total_pages || 1);
      setFinancePage(page);
    } catch (err) {
      toast.error('Failed to load finance sync history');
      console.error(err);
    } finally {
      setFinanceLoading(false);
    }
  }, []);

  const fetchAriDrift = useCallback(async () => {
    setDriftLoading(true);
    try {
      const res = await axios.get('/channel-manager/ari/drift?limit=50&skip=0');
      setDriftStates(res.data.drift_states || []);
    } catch (err) {
      toast.error('Failed to load ARI drift states');
      console.error(err);
    } finally {
      setDriftLoading(false);
    }
  }, []);

  const fetchAriOutbound = useCallback(async () => {
    setOutboundLoading(true);
    try {
      const res = await axios.get('/channel-manager/ari/outbound-logs?limit=50&skip=0');
      setOutboundLogs(res.data.logs || []);
    } catch (err) {
      toast.error('Failed to load ARI outbound logs');
      console.error(err);
    } finally {
      setOutboundLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFinanceLogs();
    fetchAriDrift();
    fetchAriOutbound();
  }, [fetchFinanceLogs, fetchAriDrift, fetchAriOutbound]);

  const refreshAll = () => {
    fetchFinanceLogs(financePage, financeProviderFilter);
    fetchAriDrift();
    fetchAriOutbound();
    toast.success('Dashboard refreshed');
  };

  return (
    <div className="p-6 max-w-[1600px] mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Integration Observability</h1>
          <p className="text-zinc-400 mt-1">Monitor operational logs and drift states across Finance and Channel connectors.</p>
        </div>
        <Button onClick={refreshAll} variant="outline" className="gap-2">
          <RefreshCw className="w-4 h-4" />
          Refresh
        </Button>
      </div>

      <Tabs defaultValue="finance" className="w-full">
        <TabsList className="mb-4">
          <TabsTrigger value="finance" className="gap-2"><Database className="w-4 h-4" /> Finance ERP Sync</TabsTrigger>
          <TabsTrigger value="ari" className="gap-2"><Activity className="w-4 h-4" /> Channel ARI Monitor</TabsTrigger>
        </TabsList>

        <TabsContent value="finance" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Finance ERP Sync History</CardTitle>
                <CardDescription>Real-time audit log of invoice and payment synchronization to Logo and Netsis.</CardDescription>
              </div>
              <div className="flex gap-2">
                <Button 
                  variant={financeProviderFilter === 'all' ? 'default' : 'outline'} 
                  onClick={() => { setFinanceProviderFilter('all'); fetchFinanceLogs(1, 'all'); }}
                  size="sm"
                >All</Button>
                <Button 
                  variant={financeProviderFilter === 'logo' ? 'default' : 'outline'} 
                  onClick={() => { setFinanceProviderFilter('logo'); fetchFinanceLogs(1, 'logo'); }}
                  size="sm"
                >Logo</Button>
                <Button 
                  variant={financeProviderFilter === 'netsis' ? 'default' : 'outline'} 
                  onClick={() => { setFinanceProviderFilter('netsis'); fetchFinanceLogs(1, 'netsis'); }}
                  size="sm"
                >Netsis</Button>
              </div>
            </CardHeader>
            <CardContent>
              {financeLoading ? (
                <div className="flex justify-center p-8"><RefreshCw className="w-6 h-6 animate-spin text-zinc-500" /></div>
              ) : (
                <>
                  <div className="rounded-md border border-zinc-800 overflow-x-auto">
                    <table className="w-full text-sm text-left whitespace-nowrap">
                      <thead className="bg-zinc-900/50 text-zinc-400">
                        <tr>
                          <th className="px-4 py-3 font-medium">Timestamp</th>
                          <th className="px-4 py-3 font-medium">Provider</th>
                          <th className="px-4 py-3 font-medium">Status</th>
                          <th className="px-4 py-3 font-medium">Invoices</th>
                          <th className="px-4 py-3 font-medium">Payments</th>
                          <th className="px-4 py-3 font-medium">HTTP Codes</th>
                          <th className="px-4 py-3 font-medium">Error Details</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800">
                        {financeLogs.length === 0 ? (
                          <tr><td colSpan="7" className="px-4 py-8 text-center text-zinc-500">No sync logs found.</td></tr>
                        ) : financeLogs.map((log, i) => {
                          const statusDict = log.provider_response_status || {};
                          return (
                            <tr key={i} className="hover:bg-zinc-800/20 transition-colors">
                              <td className="px-4 py-3 text-zinc-300">
                                {format(new Date(log.synced_at || log.created_at), 'MMM dd, HH:mm:ss')}
                              </td>
                              <td className="px-4 py-3">
                                <Badge variant="outline" className="capitalize">{log.provider}</Badge>
                              </td>
                              <td className="px-4 py-3">
                                <StatusBadge status={log.status} />
                              </td>
                              <td className="px-4 py-3">
                                {log.synced_invoices > 0 ? <span className="text-emerald-400 font-medium">{log.synced_invoices}</span> : <span className="text-zinc-600">0</span>}
                              </td>
                              <td className="px-4 py-3">
                                {log.synced_payments > 0 ? <span className="text-emerald-400 font-medium">{log.synced_payments}</span> : <span className="text-zinc-600">0</span>}
                              </td>
                              <td className="px-4 py-3">
                                <div className="flex flex-col gap-1 text-xs">
                                  {typeof statusDict === 'object' ? (
                                    <>
                                      {statusDict.invoices && <span>INV: {statusDict.invoices}</span>}
                                      {statusDict.payments && <span>PAY: {statusDict.payments}</span>}
                                    </>
                                  ) : (
                                    <span>{statusDict}</span>
                                  )}
                                </div>
                              </td>
                              <td className="px-4 py-3 text-zinc-400 max-w-[200px] truncate" title={log.error_type || log.details}>
                                {log.error_type ? <span className="text-red-400">{log.error_type}</span> : log.details}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  
                  {/* Pagination */}
                  <div className="flex items-center justify-between mt-4">
                    <span className="text-sm text-zinc-500">Page {financePage} of {financeTotalPages}</span>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" onClick={() => fetchFinanceLogs(Math.max(1, financePage - 1), financeProviderFilter)} disabled={financePage <= 1}>
                        <ChevronLeft className="w-4 h-4" />
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => fetchFinanceLogs(Math.min(financeTotalPages, financePage + 1), financeProviderFilter)} disabled={financePage >= financeTotalPages}>
                        <ChevronRight className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="ari" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><AlertTriangle className="w-5 h-5 text-amber-500"/> ARI Drift States</CardTitle>
                <CardDescription>Discrepancies detected between PMS truth and Provider snapshot.</CardDescription>
              </CardHeader>
              <CardContent>
                {driftLoading ? (
                  <div className="flex justify-center p-8"><RefreshCw className="w-6 h-6 animate-spin text-zinc-500" /></div>
                ) : (
                  <div className="rounded-md border border-zinc-800 overflow-x-auto">
                    <table className="w-full text-sm text-left">
                      <thead className="bg-zinc-900/50 text-zinc-400">
                        <tr>
                          <th className="px-4 py-2">Provider</th>
                          <th className="px-4 py-2">Date</th>
                          <th className="px-4 py-2">Status</th>
                          <th className="px-4 py-2">Diff</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800">
                        {driftStates.length === 0 ? (
                          <tr><td colSpan="4" className="px-4 py-8 text-center text-zinc-500">No drift detected. System in sync.</td></tr>
                        ) : driftStates.map((drift, i) => (
                          <tr key={i}>
                            <td className="px-4 py-2 capitalize">{drift.provider}</td>
                            <td className="px-4 py-2 whitespace-nowrap">{drift.date || drift.date_from || '-'}</td>
                            <td className="px-4 py-2">
                              {drift.drift_type === "credentials_missing" ? (
                                <Badge className="bg-red-500/10 text-red-500">Credentials Missing</Badge>
                              ) : drift.drift_type === "provider_unavailable" ? (
                                <Badge className="bg-orange-500/10 text-orange-500">Provider Down</Badge>
                              ) : drift.drift_detected ? (
                                <Badge className="bg-amber-500/10 text-amber-500">Drifted</Badge>
                              ) : (
                                <Badge className="bg-emerald-500/10 text-emerald-500">Synced</Badge>
                              )}
                            </td>
                            <td className="px-4 py-2 text-xs font-mono text-zinc-400">
                              {drift.drift_type === "credentials_missing" ? (
                                "Check Credential Vault"
                              ) : drift.drift_type === "provider_unavailable" ? (
                                "API connection failed"
                              ) : drift.drift_detected && drift.drift_fields ? (
                                JSON.stringify(drift.drift_fields).substring(0, 50) + '...'
                              ) : '-'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><ArrowRightLeft className="w-5 h-5 text-blue-500"/> ARI Outbound Logs</CardTitle>
                <CardDescription>Recent push attempts from PMS to Channel Providers.</CardDescription>
              </CardHeader>
              <CardContent>
                {outboundLoading ? (
                  <div className="flex justify-center p-8"><RefreshCw className="w-6 h-6 animate-spin text-zinc-500" /></div>
                ) : (
                  <div className="rounded-md border border-zinc-800 overflow-x-auto">
                    <table className="w-full text-sm text-left">
                      <thead className="bg-zinc-900/50 text-zinc-400">
                        <tr>
                          <th className="px-4 py-2">Timestamp</th>
                          <th className="px-4 py-2">Provider</th>
                          <th className="px-4 py-2">Trigger</th>
                          <th className="px-4 py-2">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800">
                        {outboundLogs.length === 0 ? (
                          <tr><td colSpan="4" className="px-4 py-8 text-center text-zinc-500">No outbound logs.</td></tr>
                        ) : outboundLogs.map((log, i) => (
                          <tr key={i}>
                            <td className="px-4 py-2 whitespace-nowrap text-zinc-300">
                              {format(new Date(log.created_at), 'MM/dd HH:mm:ss')}
                            </td>
                            <td className="px-4 py-2 capitalize">{log.provider}</td>
                            <td className="px-4 py-2 truncate max-w-[120px]">{log.trigger_source || 'system'}</td>
                            <td className="px-4 py-2">
                              {log.status === 'success' ? <span className="text-emerald-500">OK</span> : <span className="text-red-500">Fail</span>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
