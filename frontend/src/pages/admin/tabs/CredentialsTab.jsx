import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, RefreshCw, Key, Zap, RotateCcw, XCircle } from 'lucide-react';
import { API } from '../shared';

const CredentialsTab = () => {
  const [creds, setCreds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);

  const fetchCreds = useCallback(async () => {
    setLoading(true);
    try { const { data } = await axios.get(`${API}/admin/credentials`); setCreds(data.credentials || []); } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchCreds(); }, [fetchCreds]);

  const handleTest = async (cid) => {
    setActionLoading(`test-${cid}`);
    try { const { data } = await axios.post(`${API}/admin/credentials/${cid}/test`); toast.success(`Baglanti testi: ${data.success ? 'Basarili' : 'Basarisiz'}`); } catch (e) { toast.error(e.response?.data?.detail || 'Test hatasi'); }
    setActionLoading(null);
  };

  const handleDisable = async (cid) => {
    setActionLoading(`disable-${cid}`);
    try { await axios.post(`${API}/admin/credentials/${cid}/disable`); toast.success('Connector devre disi birakildi'); fetchCreds(); } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
    setActionLoading(null);
  };

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">Credential Yonetimi (RBAC Korumali)</h3>
        <Button size="sm" variant="outline" className="border-slate-700 text-slate-300" onClick={fetchCreds}><RefreshCw className="w-3.5 h-3.5 mr-1" /> Yenile</Button>
      </div>
      {creds.map(c => (
        <Card key={c.connector_id} data-testid={`cred-${c.connector_id}`} className="bg-slate-800/50 border-slate-700">
          <CardContent className="p-4">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <Key className="w-4 h-4 text-amber-400" />
                  <span className="text-sm font-medium text-white">{c.display_name}</span>
                  <Badge className={`border text-xs ${c.encrypted ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' : 'bg-red-500/15 text-red-400 border-red-500/30'}`}>{c.encrypted ? c.encryption_algorithm || 'Encrypted' : 'Not Encrypted'}</Badge>
                  <Badge className={`border text-xs ${c.status === 'active' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' : 'bg-slate-500/15 text-slate-400 border-slate-500/30'}`}>{c.status}</Badge>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                  <div><span className="text-slate-500">Provider:</span> <span className="text-white">{c.provider}</span></div>
                  <div><span className="text-slate-500">Environment:</span> <span className="text-white">{c.environment}</span></div>
                  <div><span className="text-slate-500">Last Tested:</span> <span className="text-white">{c.last_tested ? new Date(c.last_tested).toLocaleDateString('tr-TR') : '-'}</span></div>
                  <div><span className="text-slate-500">Last Rotated:</span> <span className="text-white">{c.last_rotated ? new Date(c.last_rotated).toLocaleDateString('tr-TR') : '-'}</span></div>
                </div>
                {c.masked_credentials && Object.keys(c.masked_credentials).length > 0 && (
                  <div className="mt-2 flex gap-2 flex-wrap">
                    {Object.entries(c.masked_credentials).map(([k, v]) => (
                      <span key={k} className="text-[10px] bg-slate-900 text-slate-400 px-2 py-0.5 rounded font-mono">{k}: {v}</span>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex gap-1 flex-shrink-0">
                <Button data-testid={`test-cred-${c.connector_id}`} size="sm" variant="ghost" className="text-emerald-400 h-7 px-2" disabled={actionLoading === `test-${c.connector_id}`} onClick={() => handleTest(c.connector_id)}>
                  {actionLoading === `test-${c.connector_id}` ? <Loader2 className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
                </Button>
                <Button size="sm" variant="ghost" className="text-blue-400 h-7 px-2" onClick={() => toast.info('Credential rotation icin yeni degerler gerekli')}><RotateCcw className="w-3 h-3" /></Button>
                <Button data-testid={`disable-${c.connector_id}`} size="sm" variant="ghost" className="text-red-400 h-7 px-2" disabled={actionLoading === `disable-${c.connector_id}`} onClick={() => handleDisable(c.connector_id)}>
                  {actionLoading === `disable-${c.connector_id}` ? <Loader2 className="w-3 h-3 animate-spin" /> : <XCircle className="w-3 h-3" />}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
      {creds.length === 0 && <Card className="bg-slate-800/50 border-slate-700"><CardContent className="py-12 text-center text-slate-400">Credential bulunamadi</CardContent></Card>}
    </div>
  );
};

export default CredentialsTab;
