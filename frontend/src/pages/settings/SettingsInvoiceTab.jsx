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

export default function SettingsInvoiceTab({ loadInvoiceSettings, invoiceLoading, handleSaveInvoiceSettings, invoiceSaving, invoiceSettings, setInvoiceSettings, handleLogoUpload, CURRENCY_OPTIONS }) {
    const { t } = useTranslation();
    return (
        <TabsContent value="invoice" className="space-y-4" data-testid="invoice-settings-content">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm flex items-center justify-between">
                  <span className="flex items-center gap-2"><FileText className="w-4 h-4" /> Fatura & Logo Ayarları</span>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={loadInvoiceSettings} disabled={invoiceLoading}>
                      <RefreshCw className={`w-4 h-4 mr-1.5 ${invoiceLoading ? 'animate-spin' : ''}`} /> Yenile
                    </Button>
                    <Button size="sm" onClick={handleSaveInvoiceSettings} disabled={invoiceSaving} data-testid="save-invoice-settings-btn">
                      <Save className="w-4 h-4 mr-1" /> {invoiceSaving ? 'Kaydediliyor...' : 'Kaydet'}
                    </Button>
                  </div>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {invoiceLoading ? <div className="text-center py-8 text-slate-400">Yükleniyor...</div> : <>
                    {/* Logo Upload */}
                    <div>
                      <Label>Otel Logosu</Label>
                      <div className="flex items-center gap-4 mt-2">
                        {invoiceSettings.logo_data ? <div className="relative">
                            <img src={invoiceSettings.logo_data} alt="Logo" className="h-16 max-w-[200px] object-contain border rounded-lg p-2" />
                            <button type="button" onClick={() => setInvoiceSettings(prev => ({
                ...prev,
                logo_data: null
              }))} className="absolute -top-2 -right-2 w-5 h-5 bg-rose-500 text-white rounded-full flex items-center justify-center text-xs hover:bg-rose-600" aria-label="Logoyu kaldır">
                              <X className="w-3 h-3" />
                            </button>
                          </div> : <div className="h-16 w-32 border-2 border-dashed rounded-lg flex items-center justify-center text-slate-400">
                            <Image className="w-6 h-6" />
                          </div>}
                        <div className="flex flex-col gap-1">
                          <Button asChild variant="outline" size="sm" className="w-fit">
                            <label className="cursor-pointer">
                              <Upload className="w-4 h-4 mr-1.5" /> Logo Yükle
                              <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={handleLogoUpload} data-testid="logo-upload-input" />
                            </label>
                          </Button>
                          <p className="text-[10px] text-slate-500">PNG, JPG, WebP — max 2MB / 2000×2000 px</p>
                        </div>
                      </div>
                    </div>

                    {/* Hotel Info for Invoice */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <Label>Otel Adı (Fatura)</Label>
                        <Input value={invoiceSettings.hotel_name || ''} onChange={e => setInvoiceSettings(prev => ({
              ...prev,
              hotel_name: e.target.value
            }))} placeholder="Otel adı" />
                      </div>
                      <div>
                        <Label>E-posta</Label>
                        <Input value={invoiceSettings.hotel_email || ''} onChange={e => setInvoiceSettings(prev => ({
              ...prev,
              hotel_email: e.target.value
            }))} placeholder="info@otel.com" />
                      </div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <Label>Telefon</Label>
                        <Input value={invoiceSettings.hotel_phone || ''} onChange={e => setInvoiceSettings(prev => ({
              ...prev,
              hotel_phone: e.target.value
            }))} />
                      </div>
                      <div>
                        <Label>Adres</Label>
                        <Input value={invoiceSettings.hotel_address || ''} onChange={e => setInvoiceSettings(prev => ({
              ...prev,
              hotel_address: e.target.value
            }))} />
                      </div>
                    </div>

                    {/* Tax Info */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <Label>Vergi Numarası</Label>
                        <Input value={invoiceSettings.tax_id || ''} onChange={e => setInvoiceSettings(prev => ({
              ...prev,
              tax_id: e.target.value
            }))} placeholder="1234567890" data-testid="tax-id-input" />
                      </div>
                      <div>
                        <Label>Vergi Dairesi</Label>
                        <Input value={invoiceSettings.tax_office || ''} onChange={e => setInvoiceSettings(prev => ({
              ...prev,
              tax_office: e.target.value
            }))} placeholder="Beyoğlu" data-testid="tax-office-input" />
                      </div>
                    </div>

                    {/* Currency — sistem geneli etki taşıdığı için warning kasıtlı amber */}
                    <div className="rounded-md border border-amber-200 bg-amber-50 p-4">
                      <Label className="text-amber-900 font-semibold">Para Birimi (Tüm Sistem)</Label>
                      <p className="text-xs text-amber-800 mt-1 mb-3">
                        Bu seçim panel, faturalar, channel manager ve raporlar dahil tüm tutarları etkiler.
                      </p>
                      <Select value={invoiceSettings.currency || 'TRY'} onValueChange={code => setInvoiceSettings(prev => ({
            ...prev,
            currency: code
          }))}>
                        <SelectTrigger data-testid="currency-select" className="w-full bg-white">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {CURRENCY_OPTIONS.map(opt => <SelectItem key={opt.code} value={opt.code}>
                              {t(opt.label) === opt.label ? opt.fallback : t(opt.label)} ({opt.sym})
                            </SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>

                    {/* Invoice Header/Footer */}
                    <div>
                      <Label>Fatura Üst Bilgi</Label>
                      <textarea value={invoiceSettings.invoice_header || ''} onChange={e => setInvoiceSettings(prev => ({
            ...prev,
            invoice_header: e.target.value
          }))} className="w-full border rounded-md px-3 py-2 text-sm min-h-[60px] focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="Fatura başlığı..." />
                    </div>
                    <div>
                      <Label>Fatura Alt Bilgi</Label>
                      <textarea value={invoiceSettings.invoice_footer || ''} onChange={e => setInvoiceSettings(prev => ({
            ...prev,
            invoice_footer: e.target.value
          }))} className="w-full border rounded-md px-3 py-2 text-sm min-h-[60px] focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="Fatura alt notu..." />
                    </div>
                    <div>
                      <Label>Ek Notlar</Label>
                      <textarea value={invoiceSettings.invoice_notes || ''} onChange={e => setInvoiceSettings(prev => ({
            ...prev,
            invoice_notes: e.target.value
          }))} className="w-full border rounded-md px-3 py-2 text-sm min-h-[60px] focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="Ek bilgiler..." />
                    </div>
                  </>}
              </CardContent>
            </Card>
          </TabsContent>
    );
}
