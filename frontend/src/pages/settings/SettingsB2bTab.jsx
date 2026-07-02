import { useTranslation } from 'react-i18next';
import React, { useState, useEffect, useMemo, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Settings as SettingsIcon, Users, CreditCard, Shield, Plus, Trash2, Building2, Zap, Crown, ArrowRight, CheckCircle2, Lock, AlertTriangle, ArrowDown, Sparkles, Clock, Receipt, Save, Pencil, X, FileText, Upload, Image, DoorOpen, RefreshCw, Infinity as InfinityIcon, UserCheck, MessageSquare, KeyRound, Copy, Plug } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import BulkRoomsDialog from '@/components/pms/BulkRoomsDialog';
import { useCurrency } from '@/context/CurrencyContext';
import { formatCurrency } from '@/lib/currency';
import { confirmDialog } from '@/lib/dialogs';

export default function SettingsB2bTab({ b2bInfo, copyToClipboard, b2bCodeOnce, setB2bCodeOnce, handleRegenerateCode, b2bBusy, loadB2B, b2bLoading, b2bRequests, handleApproveRequest, handleRejectRequest }) {
    const { t } = useTranslation();
    return (
        <TabsContent value="b2b" className="space-y-4" data-testid="b2b-settings-content">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <KeyRound className="w-5 h-5" /> Bağlantı Bilgileri
                  </CardTitle>
                  <CardDescription>
                    Acente otomasyonunuzu otele bağlamak için Otel ID ve Bağlantı Kodu'nu acente uygulamasına girin.
                    Bağlantı Kodu yalnızca bağlantı isteği oluşturabilir; API key yalnızca sizin onayınızla üretilir.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label>Otel ID</Label>
                      <div className="flex items-center gap-2">
                        <Input value={b2bInfo?.hotel_id ?? ''} readOnly className="bg-slate-50 font-mono" />
                        <Button variant="outline" size="sm" onClick={() => copyToClipboard(String(b2bInfo?.hotel_id ?? ''), 'Otel ID')} disabled={!b2bInfo?.hotel_id}>
                          <Copy className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>
                    <div>
                      <Label>Tenant ID</Label>
                      <div className="flex items-center gap-2">
                        <Input value={b2bInfo?.tenant_id ?? ''} readOnly className="bg-slate-50 font-mono text-xs" />
                        <Button variant="outline" size="sm" onClick={() => copyToClipboard(String(b2bInfo?.tenant_id ?? ''), 'Tenant ID')} disabled={!b2bInfo?.tenant_id}>
                          <Copy className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>
                  </div>

                  <div className="border-t pt-4">
                    <Label>Bağlantı Kodu</Label>
                    {b2bCodeOnce ? <div className="mt-1 rounded-md border border-amber-300 bg-amber-50 p-3 space-y-2">
                        <div className="flex items-center gap-2 text-sm font-medium text-amber-800">
                          <AlertTriangle className="w-4 h-4" /> Bu kod yalnızca bir kez gösterilir. Güvenli saklayın.
                        </div>
                        <div className="flex items-center gap-2">
                          <Input value={b2bCodeOnce} readOnly className="bg-white font-mono text-xs" data-testid="b2b-connect-code-once" />
                          <Button variant="outline" size="sm" onClick={() => copyToClipboard(b2bCodeOnce, 'Bağlantı Kodu')}>
                            <Copy className="w-4 h-4" />
                          </Button>
                        </div>
                        <button onClick={() => setB2bCodeOnce('')} className="text-xs text-slate-500 hover:underline">Gizle</button>
                      </div> : <div className="mt-1 flex items-center gap-2 text-sm text-slate-600">
                        {b2bInfo?.has_active_code ? <span className="font-mono">{b2bInfo.code_prefix}</span> : <span>Henüz bağlantı kodu üretilmedi.</span>}
                      </div>}
                    <div className="mt-3">
                      <Button onClick={handleRegenerateCode} disabled={b2bBusy} data-testid="b2b-regenerate-code" className="bg-black text-white hover:bg-black/90">
                        <RefreshCw className="w-4 h-4 mr-1" />
                        {b2bInfo?.has_active_code ? 'Yeni Kod Üret' : 'Bağlantı Kodu Üret'}
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle>Bağlantı İstekleri</CardTitle>
                      <CardDescription>Acentelerden gelen bağlantı isteklerini onaylayın veya reddedin.</CardDescription>
                    </div>
                    <Button variant="outline" size="sm" onClick={loadB2B} disabled={b2bLoading}>
                      <RefreshCw className="w-4 h-4 mr-1" /> Yenile
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {b2bLoading ? <div className="py-8 text-center text-sm text-slate-500">Yükleniyor...</div> : b2bRequests.length === 0 ? <div className="py-8 text-center text-sm text-slate-500">Henüz bağlantı isteği yok.</div> : <div className="space-y-2" data-testid="b2b-requests-list">
                      {b2bRequests.map(req => <div key={req.id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-md border p-3">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-medium truncate">{req.agency_name}</span>
                              <span className={`text-xs px-2 py-0.5 rounded-full ${req.status === 'pending' ? 'bg-amber-100 text-amber-800' : req.status === 'approved' ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800'}`}>
                                {req.status === 'pending' ? 'Bekliyor' : req.status === 'approved' ? 'Onaylandı' : 'Reddedildi'}
                              </span>
                            </div>
                            <div className="text-xs text-slate-500 mt-0.5 space-x-2">
                              {req.contact_email ? <span>{req.contact_email}</span> : null}
                              {req.created_at ? <span>{new Date(req.created_at).toLocaleString('tr-TR')}</span> : null}
                              {req.key_prefix ? <span className="font-mono">{req.key_prefix}</span> : null}
                            </div>
                          </div>
                          {req.status === 'pending' ? <div className="flex items-center gap-2 shrink-0">
                              <Button size="sm" onClick={() => handleApproveRequest(req)} disabled={b2bBusy} className="bg-black text-white hover:bg-black/90" data-testid="b2b-approve">
                                <CheckCircle2 className="w-4 h-4 mr-1" /> Onayla
                              </Button>
                              <Button size="sm" variant="outline" onClick={() => handleRejectRequest(req)} disabled={b2bBusy} data-testid="b2b-reject">
                                <X className="w-4 h-4 mr-1" /> Reddet
                              </Button>
                            </div> : null}
                        </div>)}
                    </div>}
                </CardContent>
              </Card>
            </TabsContent>
    );
}
