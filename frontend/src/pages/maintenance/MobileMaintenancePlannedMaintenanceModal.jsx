import { useTranslation } from 'react-i18next';
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { ArrowLeft, Wrench, AlertTriangle, CheckCircle, Clock, TrendingUp, RefreshCw, Settings, History, FileText, BarChart3, Eye, Calendar, Package, ShoppingCart, Camera, Upload, Filter, X, Plus, Minus, QrCode, Activity, Home, Snowflake, Zap, Droplet, Hammer, Sofa } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export default function MobileMaintenancePlannedMaintenanceModal({ plannedMaintenanceModalOpen, setPlannedMaintenanceModalOpen, plannedMaintenance }) {
    const { t } = useTranslation();
    return (
        <Dialog open={plannedMaintenanceModalOpen} onOpenChange={setPlannedMaintenanceModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <Calendar className="w-5 h-5" />
              <span>Planlı Bakım Takvimi (30 Gün)</span>
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4">
            {plannedMaintenance.length > 0 ? <>
                <div className="grid grid-cols-3 gap-2 text-sm">
                  <Card className="bg-red-50">
                    <CardContent className="p-3 text-center">
                      <p className="text-2xl font-bold text-red-700">
                        {plannedMaintenance.filter(p => p.is_overdue).length}
                      </p>
                      <p className="text-xs text-red-600">Gecikmiş</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-yellow-50">
                    <CardContent className="p-3 text-center">
                      <p className="text-2xl font-bold text-yellow-700">
                        {plannedMaintenance.filter(p => !p.is_overdue && p.days_until <= 7).length}
                      </p>
                      <p className="text-xs text-yellow-600">Bu Hafta</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-blue-50">
                    <CardContent className="p-3 text-center">
                      <p className="text-2xl font-bold text-blue-700">
                        {plannedMaintenance.filter(p => p.days_until > 7 && p.days_until <= 30).length}
                      </p>
                      <p className="text-xs text-blue-600">Bu Ay</p>
                    </CardContent>
                  </Card>
                </div>
                
                <div className="space-y-2">
                  {plannedMaintenance.map(item => <Card key={item.id} className={`border-2 ${item.is_overdue ? 'bg-red-50 border-red-300' : item.days_until <= 7 ? 'bg-yellow-50 border-yellow-300' : 'bg-white border-gray-200'}`}>
                      <CardContent className="p-3">
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <p className="font-bold text-gray-900">{item.asset_name}</p>
                            <p className="text-sm text-gray-600">{item.maintenance_type}</p>
                            <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                              <div>
                                <span className="text-gray-500">Sonraki Bakım:</span>
                                <p className="font-semibold">
                                  {new Date(item.next_maintenance).toLocaleDateString('tr-TR')}
                                </p>
                              </div>
                              <div>
                                <span className="text-gray-500">Periyot:</span>
                                <p className="font-semibold">{item.frequency_days} gün</p>
                              </div>
                              <div>
                                <span className="text-gray-500">Süre:</span>
                                <p className="font-semibold">{item.estimated_duration_minutes} dk</p>
                              </div>
                              <div>
                                <span className="text-gray-500">Atanan:</span>
                                <p className="font-semibold">{item.assigned_to || '-'}</p>
                              </div>
                            </div>
                          </div>
                          <div className="text-right">
                            {item.is_overdue ? <Badge className="bg-red-600">
                                {Math.abs(item.days_until)} gün gecikti
                              </Badge> : <Badge className={item.days_until <= 7 ? 'bg-yellow-500' : 'bg-blue-500'}>
                                {item.days_until} gün kaldı
                              </Badge>}
                          </div>
                        </div>
                      </CardContent>
                    </Card>)}
                </div>
              </> : <p className="text-center text-gray-500 py-8">Planlı bakım bulunamadı</p>}
          </div>
        </DialogContent>
      </Dialog>
    );
}
