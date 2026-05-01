import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Switch } from '@/components/ui/switch';
import Layout from '@/components/Layout';
import axios from 'axios';
import { useTranslation } from 'react-i18next';

const BACKEND = "";

export default function SecurityCenter({ user, tenant, onLogout }) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('2fa');
  const [twoFAStatus, setTwoFAStatus] = useState(null);
  const [setupData, setSetupData] = useState(null);
  const [verifyCode, setVerifyCode] = useState('');
  const [backupCodes, setBackupCodes] = useState(null);
  const [ipRules, setIpRules] = useState([]);
  const [newIP, setNewIP] = useState('');
  const [newIPType, setNewIPType] = useState('whitelist');
  const [newIPDesc, setNewIPDesc] = useState('');
  const [ipCheck, setIpCheck] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const fetch2FAStatus = useCallback(async () => {
    try {
      const res = await axios.get(`/security/2fa/status`, { headers });
      setTwoFAStatus(res.data);
    } catch (e) { console.error(e); }
  }, []);

  const fetchIPRules = useCallback(async () => {
    try {
      const res = await axios.get(`/security/ip/rules`, { headers });
      setIpRules(res.data.rules || []);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => { fetch2FAStatus(); fetchIPRules(); }, []);

  const setup2FA = async () => {
    setLoading(true);
    try {
      const res = await axios.post(`/security/2fa/setup`, {}, { headers });
      setSetupData(res.data);
      setMessage('');
    } catch (e) { setMessage(e.response?.data?.detail || 'Hata'); }
    setLoading(false);
  };

  const verify2FA = async () => {
    setLoading(true);
    try {
      const res = await axios.post(`/security/2fa/verify`, { code: verifyCode }, { headers });
      setBackupCodes(res.data.backup_codes);
      setMessage(res.data.message);
      setSetupData(null);
      fetch2FAStatus();
    } catch (e) { setMessage(e.response?.data?.detail || 'Geçersiz kod'); }
    setLoading(false);
  };

  const disable2FA = async () => {
    const code = prompt('2FA kodunuzu girin:');
    if (!code) return;
    try {
      await axios.post(`/security/2fa/disable`, { code }, { headers });
      setMessage('2FA devre dışı bırakıldı');
      fetch2FAStatus();
    } catch (e) { setMessage(e.response?.data?.detail || 'Hata'); }
  };

  const addIPRule = async () => {
    if (!newIP) return;
    try {
      await axios.post(`/security/ip/rules`, {
        ip_address: newIP, rule_type: newIPType, description: newIPDesc
      }, { headers });
      setNewIP(''); setNewIPDesc('');
      fetchIPRules();
    } catch (e) { setMessage(e.response?.data?.detail || 'Hata'); }
  };

  const deleteIPRule = async (ruleId) => {
    try {
      await axios.delete(`/security/ip/rules/${ruleId}`, { headers });
      fetchIPRules();
    } catch (e) { setMessage(e.response?.data?.detail || 'Hata'); }
  };

  const checkIP = async () => {
    try {
      const res = await axios.post(`/security/ip/check`, {}, { headers });
      setIpCheck(res.data);
    } catch (e) { console.error(e); }
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout}>
      <div className="p-6 space-y-6">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold">Güvenlik Merkezi</h1>
            <p className="text-gray-500">2FA, IP erişim kontrolu ve güvenlik ayarları</p>
          </div>
        </div>

        {message && (
          <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-blue-700">
            {message}
          </div>
        )}

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="2fa">2FA Dogrulama</TabsTrigger>
            <TabsTrigger value="ip">IP Erisim Kontrolu</TabsTrigger>
          </TabsList>

          <TabsContent value="2fa" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  Iki Faktorlu Dogrulama (2FA)
                  {twoFAStatus?.enabled ? (
                    <Badge className="bg-green-100 text-green-700">Aktif</Badge>
                  ) : (
                    <Badge variant="outline">Devre Disi</Badge>
                  )}
                </CardTitle>
                <CardDescription>
                  TOTP tabanli ek güvenlik katmani. Google Authenticator veya benzer uygulamalarla kullanin.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {!twoFAStatus?.enabled && !setupData && (
                  <Button onClick={setup2FA} disabled={loading}>
                    {loading ? 'Hazirlaniyor...' : '2FA Etkinlestir'}
                  </Button>
                )}

                {setupData && (
                  <div className="space-y-4">
                    <div className="p-4 bg-gray-50 rounded-lg text-center">
                      <p className="mb-2 font-medium">QR Kodu Tarayin</p>
                      <img src={setupData.qr_code} alt="QR Code" className="mx-auto w-48 h-48" />
                      <p className="mt-2 text-sm text-gray-500">Manuel giriş: <code className="bg-gray-200 px-2 py-1 rounded">{setupData.manual_entry_key}</code></p>
                    </div>
                    <div className="flex gap-2">
                      <Input
                        value={verifyCode}
                        onChange={(e) => setVerifyCode(e.target.value)}
                        placeholder="6 haneli kod"
                        maxLength={6}
                      />
                      <Button onClick={verify2FA} disabled={loading || verifyCode.length !== 6}>
                        Dogrula
                      </Button>
                    </div>
                  </div>
                )}

                {backupCodes && (
                  <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                    <p className="font-medium text-yellow-800 mb-2">Yedek Kodlariniz (guvenli yere kaydedin!)</p>
                    <div className="grid grid-cols-2 gap-1">
                      {backupCodes.map((code, i) => (
                        <code key={i} className="bg-white px-2 py-1 rounded text-sm">{code}</code>
                      ))}
                    </div>
                  </div>
                )}

                {twoFAStatus?.enabled && (
                  <div className="space-y-2">
                    <p className="text-sm text-gray-600">Yedek kod sayısı: {twoFAStatus.backup_codes_remaining}</p>
                    <p className="text-sm text-gray-600">Son doğrulama: {twoFAStatus.last_verified || 'Bilinmiyor'}</p>
                    <Button variant="destructive" onClick={disable2FA}>2FA Devre Disi Birak</Button>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="ip" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>IP Erisim Kurallari</CardTitle>
                <CardDescription>Whitelist ve blacklist ile IP bazli erişim kontrolu</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex gap-2 items-end">
                  <div className="flex-1">
                    <label className="text-sm font-medium">IP Adresi</label>
                    <Input value={newIP} onChange={(e) => setNewIP(e.target.value)} placeholder="192.168.1.1 veya 10.0.0.0/24" />
                  </div>
                  <div>
                    <label className="text-sm font-medium">Tip</label>
                    <select className="w-full border rounded px-3 py-2" value={newIPType} onChange={(e) => setNewIPType(e.target.value)}>
                      <option value="whitelist">Beyaz Liste</option>
                      <option value="blacklist">Kara Liste</option>
                    </select>
                  </div>
                  <div className="flex-1">
                    <label className="text-sm font-medium">Açıklama</label>
                    <Input value={newIPDesc} onChange={(e) => setNewIPDesc(e.target.value)} placeholder="Ofis IP" />
                  </div>
                  <Button onClick={addIPRule}>{t("common.add")}</Button>
                </div>

                <div className="flex gap-2">
                  <Button variant="outline" onClick={checkIP}>IP Kontrol Et</Button>
                  {ipCheck && (
                    <Badge className={ipCheck.allowed ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}>
                      {ipCheck.client_ip}: {ipCheck.allowed ? 'Izin Verildi' : 'Engellendi'}
                    </Badge>
                  )}
                </div>

                <div className="border rounded-lg">
                  <table className="w-full">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="text-left p-3 text-sm">IP Adresi</th>
                        <th className="text-left p-3 text-sm">Tip</th>
                        <th className="text-left p-3 text-sm">Açıklama</th>
                        <th className="text-left p-3 text-sm">Durum</th>
                        <th className="text-left p-3 text-sm">İşlem</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ipRules.map(rule => (
                        <tr key={rule.id} className="border-t">
                          <td className="p-3 font-mono text-sm">{rule.ip_address}</td>
                          <td className="p-3">
                            <Badge className={rule.rule_type === 'whitelist' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}>
                              {rule.rule_type === 'whitelist' ? 'Beyaz Liste' : 'Kara Liste'}
                            </Badge>
                          </td>
                          <td className="p-3 text-sm">{rule.description || '-'}</td>
                          <td className="p-3">
                            <Badge variant={rule.is_active ? 'default' : 'outline'}>
                              {rule.is_active ? 'Aktif' : 'Pasif'}
                            </Badge>
                          </td>
                          <td className="p-3">
                            <Button variant="ghost" size="sm" className="text-red-500" onClick={() => deleteIPRule(rule.id)}>{t("common.delete")}</Button>
                          </td>
                        </tr>
                      ))}
                      {ipRules.length === 0 && (
                        <tr><td colSpan="5" className="p-8 text-center text-gray-400">Henüz kural eklenmemis</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
}
