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

export default function MobileMaintenanceAssetHistoryModal({ assetHistoryModalOpen, setAssetHistoryModalOpen, allRooms, loadAssetHistory, assetHistory, selectedAsset, getPriorityColor }) {
    const { t } = useTranslation();
    return (
        <Dialog open={assetHistoryModalOpen} onOpenChange={setAssetHistoryModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <History className="w-5 h-5 text-blue-600" />
              <span>Bakım Geçmişi - Tüm Varlıklar</span>
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4">
            {/* Asset Selection */}
            <Card className="bg-blue-50">
              <CardContent className="p-4">
                <p className="text-sm text-blue-900 mb-3 font-medium">
                  <Wrench className="w-4 h-4 inline mr-1" />
                  Tüm odaların bakım geçmişini görebilirsiniz
                </p>
                <div className="grid gap-2">
                  {allRooms.slice(0, 10).map(room => <Button key={room.id} variant="outline" className="w-full justify-start" onClick={() => loadAssetHistory(room.id, room.room_number)}>
                      <span className="font-bold">Oda {room.room_number}</span>
                      <span className="text-gray-500 ml-2">- {room.room_type}</span>
                    </Button>)}
                </div>
              </CardContent>
            </Card>

            {/* History Display */}
            {assetHistory && <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">
                    Bakım Geçmişi: {selectedAsset}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    <div className="grid grid-cols-3 gap-2 text-xs">
                      <div className="text-center p-2 bg-blue-50 rounded">
                        <p className="text-blue-900 font-bold text-lg">
                          {assetHistory.total_maintenances || 0}
                        </p>
                        <p className="text-blue-600">Toplam Bakım</p>
                      </div>
                      <div className="text-center p-2 bg-green-50 rounded">
                        <p className="text-green-900 font-bold text-lg">
                          {assetHistory.last_maintenance_days_ago || 'N/A'}
                        </p>
                        <p className="text-green-600">Gün Önce</p>
                      </div>
                      <div className="text-center p-2 bg-indigo-50 rounded">
                        <p className="text-indigo-900 font-bold text-lg">
                          {assetHistory.avg_cost?.toFixed(0) || 0} ₺
                        </p>
                        <p className="text-indigo-600">Ort. Maliyet</p>
                      </div>
                    </div>

                    {/* Maintenance History List */}
                    {assetHistory.history && assetHistory.history.length > 0 ? <div className="space-y-2 mt-4">
                        <p className="font-bold text-sm text-gray-700 mb-2">Son Bakımlar:</p>
                        {assetHistory.history.slice(0, 5).map((item, idx) => <div key={idx} className="p-3 bg-gray-50 rounded border text-xs">
                            <div className="flex items-start justify-between">
                              <div className="flex-1">
                                <p className="font-bold text-gray-900">{item.issue_type || item.title}</p>
                                <p className="text-gray-600 mt-1">{item.description || 'Açıklama yok'}</p>
                                <div className="flex items-center space-x-2 mt-2 text-gray-500">
                                  <Calendar className="w-3 h-3" />
                                  <span>{new Date(item.created_at || item.date).toLocaleDateString('tr-TR')}</span>
                                </div>
                              </div>
                              <Badge className={getPriorityColor(item.priority || 'normal')}>
                                {item.priority || 'normal'}
                              </Badge>
                            </div>
                            {item.cost && <p className="text-indigo-700 font-bold mt-2">{item.cost} ₺</p>}
                          </div>)}
                      </div> : <div className="text-center py-8 text-gray-500">
                        <History className="w-12 h-12 mx-auto mb-2 opacity-30" />
                        <p>Bu varlık için bakım kaydı bulunamadı</p>
                      </div>}

                    {/* Most Common Issues */}
                    {assetHistory.most_common_issues && assetHistory.most_common_issues.length > 0 && <div className="mt-4">
                        <p className="font-bold text-sm text-gray-700 mb-2">En Yaygın Sorunlar:</p>
                        <div className="space-y-1">
                          {assetHistory.most_common_issues.map((issue, idx) => <div key={idx} className="flex items-center justify-between p-2 bg-amber-50 rounded text-xs">
                              <span className="text-gray-900">{issue.type}</span>
                              <Badge variant="outline" className="bg-amber-100">
                                {issue.count}x
                              </Badge>
                            </div>)}
                        </div>
                      </div>}
                  </div>
                </CardContent>
              </Card>}
          </div>
        </DialogContent>
      </Dialog>
    );
}
