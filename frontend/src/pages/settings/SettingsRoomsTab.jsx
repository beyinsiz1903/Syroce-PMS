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

export default function SettingsRoomsTab({ loadRooms, roomsLoading, setShowBulkRoomsDialog, isSuperAdmin, setShowAddRoomDialog, roomsList, handleDeleteRoom }) {
    const { t } = useTranslation();
    return (
        <TabsContent value="rooms" className="space-y-4" data-testid="rooms-settings-content">
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="flex items-center gap-2">
                        <DoorOpen className="w-5 h-5" /> Oda Yönetimi
                      </CardTitle>
                      <CardDescription>Otel odalarını ekleyin, düzenleyin veya silin</CardDescription>
                    </div>
                    <div className="flex gap-2 flex-wrap">
                      <Button variant="outline" size="sm" onClick={loadRooms} disabled={roomsLoading}>
                        <RefreshCw className={`w-4 h-4 mr-1.5 ${roomsLoading ? 'animate-spin' : ''}`} /> Yenile
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => setShowBulkRoomsDialog(true)} data-testid="bulk-add-rooms-btn" disabled={!isSuperAdmin} title={!isSuperAdmin ? 'Yalnızca süper-admin' : undefined}>
                        <Plus className="w-4 h-4 mr-1" /> Toplu Oda Ekle
                      </Button>
                      <Button size="sm" onClick={() => setShowAddRoomDialog(true)} data-testid="add-room-btn" disabled={!isSuperAdmin} title={!isSuperAdmin ? 'Yalnızca süper-admin' : undefined}>
                        <Plus className="w-4 h-4 mr-1" /> Tek Oda Ekle
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  {roomsLoading ? <div className="text-center py-8 text-slate-400">Yükleniyor...</div> : roomsList.length === 0 ? <div className="text-center py-12 text-slate-400">
                      <DoorOpen className="w-12 h-12 mx-auto mb-3 opacity-30" />
                      <p className="text-lg font-medium">Henüz oda eklenmemiş</p>
                      <p className="text-sm mt-1">Yukarıdaki butonlarla oda ekleyebilirsiniz</p>
                    </div> : <div className="space-y-2">
                      <div className="text-sm text-slate-500 mb-3">Toplam {roomsList.length} oda</div>
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                        {roomsList.map(room => <div key={room.id} className="flex items-center justify-between p-3 border rounded-lg hover:bg-slate-50 transition-colors" data-testid={`settings-room-${room.room_number}`}>
                            <div className="flex items-center gap-3">
                              <div className="w-10 h-10 bg-indigo-100 rounded-lg flex items-center justify-center">
                                <span className="text-sm font-bold text-indigo-700">{room.room_number}</span>
                              </div>
                              <div>
                                <p className="text-sm font-medium">{room.room_type}</p>
                                <p className="text-xs text-slate-500">Kat {room.floor} - {room.capacity} kişi</p>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              <Badge variant="outline" className="text-xs">{room.status}</Badge>
                              <Button variant="ghost" size="sm" className="text-rose-500 hover:text-rose-700 hover:bg-rose-50" onClick={() => handleDeleteRoom(room.id, room.room_number)} data-testid={`delete-room-${room.room_number}`}>
                                <Trash2 className="w-4 h-4" />
                              </Button>
                            </div>
                          </div>)}
                      </div>
                    </div>}
                </CardContent>
              </Card>
            </TabsContent>
    );
}
