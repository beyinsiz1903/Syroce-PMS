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

export default function SettingsHotelTab({ editMode, setEditMode, setHotelForm, tenant, handleSaveHotelInfo, hotelSaving, overRoomLimit, hotelForm, parseInt, currentPlan, subscription }) {
    const { t } = useTranslation();
    return (
        <TabsContent value="hotel" className="space-y-4">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>{t('settings.hotelInfo')}</CardTitle>
                    <CardDescription>İsim, adres ve iletişim bilgileri</CardDescription>
                  </div>
                  {!editMode ? <Button variant="outline" size="sm" onClick={() => setEditMode(true)}>
                      <Pencil className="w-4 h-4 mr-1" /> Düzenle
                    </Button> : <div className="flex gap-2">
                      <Button variant="outline" size="sm" onClick={() => {
            setEditMode(false);
            setHotelForm({
              property_name: tenant?.property_name || '',
              phone: tenant?.phone || tenant?.contact_phone || '',
              email: tenant?.email || tenant?.contact_email || '',
              address: tenant?.address || '',
              location: tenant?.location || '',
              description: tenant?.description || '',
              total_rooms: tenant?.total_rooms || 0
            });
          }}>
                        <X className="w-4 h-4 mr-1" /> İptal
                      </Button>
                      <Button size="sm" onClick={handleSaveHotelInfo} disabled={hotelSaving || overRoomLimit}>
                        <Save className="w-4 h-4 mr-1" /> {hotelSaving ? 'Kaydediyor...' : 'Kaydet'}
                      </Button>
                    </div>}
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label>Otel Adı</Label>
                  <Input value={hotelForm.property_name || ''} readOnly={!editMode} className={!editMode ? 'bg-slate-50' : ''} onChange={e => setHotelForm({
          ...hotelForm,
          property_name: e.target.value
        })} />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label>Telefon</Label>
                    <Input value={hotelForm.phone || ''} readOnly={!editMode} className={!editMode ? 'bg-slate-50' : ''} onChange={e => setHotelForm({
            ...hotelForm,
            phone: e.target.value
          })} placeholder="+905551234567" />
                  </div>
                  <div>
                    <Label>E-posta</Label>
                    <Input type="email" value={hotelForm.email || ''} readOnly={!editMode} className={!editMode ? 'bg-slate-50' : ''} onChange={e => setHotelForm({
            ...hotelForm,
            email: e.target.value
          })} />
                  </div>
                </div>
                <div>
                  <Label>Adres</Label>
                  <Input value={hotelForm.address || ''} readOnly={!editMode} className={!editMode ? 'bg-slate-50' : ''} onChange={e => setHotelForm({
          ...hotelForm,
          address: e.target.value
        })} />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label>Lokasyon / Şehir</Label>
                    <Input value={hotelForm.location || ''} readOnly={!editMode} className={!editMode ? 'bg-slate-50' : ''} onChange={e => setHotelForm({
            ...hotelForm,
            location: e.target.value
          })} />
                  </div>
                  <div>
                    <Label>Toplam Oda Sayısı</Label>
                    <Input type="number" min={0} value={hotelForm.total_rooms ?? ''} readOnly={!editMode} className={`${!editMode ? 'bg-slate-50' : ''} ${overRoomLimit ? 'border-rose-400 focus-visible:ring-rose-400' : ''}`} onChange={e => setHotelForm({
            ...hotelForm,
            total_rooms: parseInt(e.target.value) || 0
          })} />
                    {editMode && currentPlan.maxRooms && <p className={`text-[11px] mt-1 ${overRoomLimit ? 'text-rose-600 font-medium' : 'text-slate-500'}`}>
                        Plan limiti: max {currentPlan.maxRooms} oda
                        {overRoomLimit && ' — Kaydetmek için planı yükseltin.'}
                      </p>}
                  </div>
                </div>
                <div>
                  <Label>Açıklama</Label>
                  <textarea value={hotelForm.description || ''} readOnly={!editMode} className={`w-full border rounded-md px-3 py-2 text-sm min-h-[80px] ${!editMode ? 'bg-slate-50' : ''} focus:outline-none focus:ring-2 focus:ring-indigo-500`} onChange={e => setHotelForm({
          ...hotelForm,
          description: e.target.value
        })} placeholder="Otel hakkında kısa açıklama..." />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-sm">{t('settings.subscription')}</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-slate-500">Plan</span><span className="font-semibold">{currentPlan.label}</span></div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Durum</span>
                  <StatusBadge intent={subscription?.status === 'active' ? 'success' : 'neutral'}>
                    {subscription?.status === 'active' ? 'Aktif' : subscription?.status || '—'}
                  </StatusBadge>
                </div>
                <div className="flex justify-between"><span className="text-slate-500">Oda</span><span className="font-semibold">{subscription?.rooms_count || 0} / {currentPlan.maxRooms || '∞'}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Kullanıcı</span><span className="font-semibold">{subscription?.users_count || 0} / {currentPlan.maxUsers || '∞'}</span></div>
              </CardContent>
            </Card>
          </TabsContent>
    );
}
