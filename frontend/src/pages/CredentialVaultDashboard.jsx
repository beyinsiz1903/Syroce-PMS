import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { 
  ShieldCheck, Key, RefreshCw, AlertTriangle, CheckCircle, Database, Link as LinkIcon
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Switch } from '@/components/ui/switch';

export default function CredentialVaultDashboard() {
  const { t } = useTranslation();
  
  // States for providers
  const [cmProviders, setCmProviders] = useState([]);
  const [financeProviders, setFinanceProviders] = useState({ logo: null, netsis: null });
  const [readiness, setReadiness] = useState(null);
  const [loading, setLoading] = useState(true);

  // Modal states
  const [showModal, setShowModal] = useState(false);
  const [activeProvider, setActiveProvider] = useState(null);
  const [activeType, setActiveType] = useState('channel'); // 'channel' | 'finance'
  
  // Channel Manager form
  const [cmForm, setCmForm] = useState({});
  // Finance form
  const [financeForm, setFinanceForm] = useState({ api_url: '', api_key: '', username: '', password: '' });
  
  const [saving, setSaving] = useState(false);

  const fetchProviders = useCallback(async () => {
    setLoading(true);
    try {
      const [cmRes, finRes, readRes] = await Promise.all([
        axios.get('/channel-manager/config/providers'),
        axios.get('/finance/integration/credentials'),
        axios.get('/integration-rollout/readiness')
      ]);
      
      setCmProviders(cmRes.data.providers || []);
      setFinanceProviders(finRes.data.providers || { logo: null, netsis: null });
      setReadiness(readRes.data);
    } catch (err) {
      toast.error('Failed to load credential vault status');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProviders();
  }, [fetchProviders]);

  const handleOpenCmModal = (provider) => {
    setActiveType('channel');
    setActiveProvider(provider);
    const initialForm = {};
    if (provider.fields) {
      provider.fields.forEach(f => { initialForm[f.key] = ''; });
    }
    setCmForm(initialForm);
    setShowModal(true);
  };

  const handleOpenFinanceModal = (providerKey) => {
    setActiveType('finance');
    setActiveProvider({ provider: providerKey, display_name: providerKey === 'logo' ? 'Logo ERP' : 'Netsis ERP' });
    setFinanceForm({ api_url: '', api_key: '', username: '', password: '' });
    setShowModal(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (activeType === 'channel') {
        await axios.post(`/channel-manager/config/providers/${activeProvider.provider}/credentials`, {
          credentials: cmForm,
          property_id: 'default'
        });
      } else {
        // Prepare relevant finance credentials depending on what user filled
        // Filter out empty fields just in case, or submit all
        const creds = {};
        for (const [k, v] of Object.entries(financeForm)) {
          if (v) creds[k] = v;
        }
        await axios.post(`/finance/integration/credentials/${activeProvider.provider}`, {
          credentials: creds
        });
      }
      
      toast.success(`${activeProvider.display_name} credentials securely stored`);
      setShowModal(false);
      fetchProviders();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save credentials');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleRollout = async (key, val) => {
    try {
      const newConfig = { ...readiness.config, [key]: val };
      await axios.post('/integration-rollout/config', newConfig);
      setReadiness(prev => ({ ...prev, config: newConfig }));
      toast.success('Rollout config updated');
    } catch (err) {
      toast.error('Failed to update rollout config');
    }
  };

  return (
    <div className="p-6 max-w-[1200px] mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <ShieldCheck className="w-8 h-8 text-emerald-500" />
            Credential Vault
          </h1>
          <p className="text-zinc-400 mt-1">Securely manage API keys and secrets for external integrations.</p>
        </div>
        <Button onClick={fetchProviders} variant="outline" className="gap-2">
          <RefreshCw className="w-4 h-4" />
          Refresh
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center p-12"><RefreshCw className="w-6 h-6 animate-spin text-zinc-500" /></div>
      ) : (
        <Tabs defaultValue="credentials" className="space-y-6">
          <TabsList className="bg-zinc-900 border border-zinc-800">
            <TabsTrigger value="credentials">Credentials</TabsTrigger>
            <TabsTrigger value="rollout">Rollout & Readiness</TabsTrigger>
          </TabsList>
          
          <TabsContent value="credentials" className="space-y-8">
          {/* Finance ERP Integrations */}
          <section>
            <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
              <Database className="w-5 h-5 text-blue-500" /> Finance ERP Providers
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {['logo', 'netsis'].map(key => {
                const info = financeProviders[key];
                const hasCreds = info?.has_credentials;
                const displayName = key === 'logo' ? 'Logo ERP' : 'Netsis ERP';
                
                return (
                  <Card key={key} className="bg-zinc-900/40 border-zinc-800">
                    <CardHeader className="pb-3">
                      <div className="flex justify-between items-start">
                        <CardTitle className="text-lg capitalize">{displayName}</CardTitle>
                        {hasCreds ? (
                          <Badge className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20">
                            <CheckCircle className="w-3 h-3 mr-1" /> Configured
                          </Badge>
                        ) : (
                          <Badge className="bg-amber-500/10 text-amber-500 border-amber-500/20">
                            <AlertTriangle className="w-3 h-3 mr-1" /> Missing
                          </Badge>
                        )}
                      </div>
                      <CardDescription>Accounting Sync Integration</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="flex justify-between items-center mt-2">
                        <div className="text-sm text-zinc-400">
                          {hasCreds ? 'Encrypted keys stored securely in vault.' : 'Requires API configuration to enable sync.'}
                        </div>
                        <Button 
                          variant={hasCreds ? "secondary" : "default"}
                          size="sm"
                          className="gap-2"
                          onClick={() => handleOpenFinanceModal(key)}
                        >
                          <Key className="w-4 h-4" />
                          {hasCreds ? 'Update Keys' : 'Configure'}
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </section>

          {/* Channel Manager Integrations */}
          <section>
            <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
              <LinkIcon className="w-5 h-5 text-indigo-500" /> Channel Manager Providers
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {cmProviders.map(provider => (
                <Card key={provider.provider} className="bg-zinc-900/40 border-zinc-800">
                  <CardHeader className="pb-3">
                    <div className="flex justify-between items-start">
                      <CardTitle className="text-lg">{provider.display_name}</CardTitle>
                      {provider.has_credentials ? (
                        <Badge className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20">
                          <CheckCircle className="w-3 h-3 mr-1" /> Configured
                        </Badge>
                      ) : (
                        <Badge className="bg-amber-500/10 text-amber-500 border-amber-500/20">
                          <AlertTriangle className="w-3 h-3 mr-1" /> Missing
                        </Badge>
                      )}
                    </div>
                    <CardDescription>ARI & Reservations Sync</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex justify-between items-center mt-2">
                      <div className="text-sm text-zinc-400">
                        {provider.has_credentials ? 'Encrypted credentials stored.' : 'Requires API configuration.'}
                      </div>
                      <Button 
                        variant={provider.has_credentials ? "secondary" : "default"}
                        size="sm"
                        className="gap-2"
                        onClick={() => handleOpenCmModal(provider)}
                      >
                        <Key className="w-4 h-4" />
                        {provider.has_credentials ? 'Update Keys' : 'Configure'}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </section>
          </TabsContent>

          <TabsContent value="rollout" className="space-y-6">
            <Card className="bg-zinc-900/40 border-zinc-800">
              <CardHeader>
                <CardTitle>Tenant Integration Rollout</CardTitle>
                <CardDescription>Safely enable or disable integrations for this property. Integrations will fail-closed if disabled.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {readiness && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Finance Readiness */}
                    <div className="space-y-4 p-4 border border-zinc-800 rounded-lg">
                      <div className="flex justify-between items-center">
                        <h3 className="font-semibold text-lg flex items-center gap-2">
                          <Database className="w-4 h-4 text-blue-500" />
                          Finance ERP Sync
                        </h3>
                        {readiness.finance.status === 'Ready' ? (
                          <Badge className="bg-emerald-500/10 text-emerald-500">Ready</Badge>
                        ) : (
                          <Badge className="bg-red-500/10 text-red-500">Blocked</Badge>
                        )}
                      </div>
                      <div className="text-sm text-zinc-400 space-y-2">
                        <p>Credentials configured: {readiness.finance.configured ? 'Yes' : 'No'}</p>
                      </div>
                      <div className="flex items-center justify-between pt-4 border-t border-zinc-800">
                        <Label htmlFor="finance-toggle" className="font-medium">Enable ERP Sync</Label>
                        <Switch 
                          id="finance-toggle" 
                          checked={readiness.config.finance_erp_enabled}
                          onCheckedChange={(val) => handleToggleRollout('finance_erp_enabled', val)}
                          disabled={readiness.finance.status === 'Blocked'}
                        />
                      </div>
                    </div>

                    {/* Channel Manager Readiness */}
                    <div className="space-y-4 p-4 border border-zinc-800 rounded-lg">
                      <div className="flex justify-between items-center">
                        <h3 className="font-semibold text-lg flex items-center gap-2">
                          <LinkIcon className="w-4 h-4 text-purple-500" />
                          Channel Manager ARI
                        </h3>
                        {readiness.channel.status === 'Ready' ? (
                          <Badge className="bg-emerald-500/10 text-emerald-500">Ready</Badge>
                        ) : readiness.channel.status === 'Warning' ? (
                          <Badge className="bg-amber-500/10 text-amber-500">Warning</Badge>
                        ) : (
                          <Badge className="bg-red-500/10 text-red-500">Blocked</Badge>
                        )}
                      </div>
                      <div className="text-sm text-zinc-400 space-y-2">
                        <p>Credentials configured: {readiness.channel.configured ? 'Yes' : 'No'}</p>
                        {readiness.channel.system_errors?.length > 0 && (
                          <div className="text-amber-500">
                            Recent SYSTEM errors detected: {readiness.channel.system_errors.map(e => e.drift_type).join(', ')}
                          </div>
                        )}
                      </div>
                      <div className="flex flex-col gap-4 pt-4 border-t border-zinc-800">
                        <div className="flex items-center justify-between">
                          <Label htmlFor="channel-toggle" className="font-medium">Enable ARI Sync / Push</Label>
                          <Switch 
                            id="channel-toggle" 
                            checked={readiness.config.channel_ari_enabled}
                            onCheckedChange={(val) => handleToggleRollout('channel_ari_enabled', val)}
                            disabled={readiness.channel.status === 'Blocked'}
                          />
                        </div>
                        <div className="flex items-center justify-between">
                          <Label htmlFor="drift-toggle" className="font-medium">Enable Background Drift Monitoring</Label>
                          <Switch 
                            id="drift-toggle" 
                            checked={readiness.config.drift_monitoring_enabled}
                            onCheckedChange={(val) => handleToggleRollout('drift_monitoring_enabled', val)}
                            disabled={readiness.channel.status === 'Blocked'}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      )}

      {/* Credential Input Modal */}
      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="sm:max-w-[425px] bg-zinc-950 border-zinc-800">
          <DialogHeader>
            <DialogTitle>Configure {activeProvider?.display_name}</DialogTitle>
          </DialogHeader>
          <div className="py-4 space-y-4">
            <div className="bg-amber-500/10 text-amber-500 p-3 rounded-md text-sm flex gap-2">
              <ShieldCheck className="w-5 h-5 shrink-0" />
              <span>Credentials will be securely encrypted via AAD before being stored. Previous keys will be overwritten.</span>
            </div>

            {activeType === 'channel' && activeProvider?.fields?.map(field => (
              <div key={field.key} className="space-y-2">
                <Label htmlFor={field.key}>{field.label} {field.required && <span className="text-red-500">*</span>}</Label>
                <Input
                  id={field.key}
                  type={field.type === 'password' ? 'password' : 'text'}
                  value={cmForm[field.key] || ''}
                  onChange={(e) => setCmForm({ ...cmForm, [field.key]: e.target.value })}
                  className="bg-zinc-900 border-zinc-800"
                  autoComplete="off"
                />
              </div>
            ))}

            {activeType === 'finance' && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="api_url">API Endpoint URL</Label>
                  <Input
                    id="api_url"
                    value={financeForm.api_url}
                    onChange={(e) => setFinanceForm({ ...financeForm, api_url: e.target.value })}
                    className="bg-zinc-900 border-zinc-800"
                    placeholder="https://..."
                    autoComplete="off"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="api_key">API Key / Token</Label>
                  <Input
                    id="api_key"
                    type="password"
                    value={financeForm.api_key}
                    onChange={(e) => setFinanceForm({ ...financeForm, api_key: e.target.value })}
                    className="bg-zinc-900 border-zinc-800"
                    autoComplete="off"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="username">Username (Optional)</Label>
                    <Input
                      id="username"
                      value={financeForm.username}
                      onChange={(e) => setFinanceForm({ ...financeForm, username: e.target.value })}
                      className="bg-zinc-900 border-zinc-800"
                      autoComplete="off"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password">Password (Optional)</Label>
                    <Input
                      id="password"
                      type="password"
                      value={financeForm.password}
                      onChange={(e) => setFinanceForm({ ...financeForm, password: e.target.value })}
                      className="bg-zinc-900 border-zinc-800"
                      autoComplete="off"
                    />
                  </div>
                </div>
              </>
            )}
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowModal(false)} disabled={saving}>Cancel</Button>
            <Button onClick={handleSave} disabled={saving} className="gap-2">
              {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Key className="w-4 h-4" />}
              Save Credentials
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
