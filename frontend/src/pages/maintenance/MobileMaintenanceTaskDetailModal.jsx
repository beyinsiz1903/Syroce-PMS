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

export default function MobileMaintenanceTaskDetailModal({ taskDetailModalOpen, setTaskDetailModalOpen, selectedTask, getPriorityColor, getStatusColor, handleTaskStatusUpdate, taskPhotos, setPhotoUploadModalOpen, setPartsUsageModalOpen }) {
    const { t } = useTranslation();
    return (
        <Dialog open={taskDetailModalOpen} onOpenChange={setTaskDetailModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Görev Detayı</DialogTitle>
          </DialogHeader>
          
          {selectedTask && <div className="space-y-4">
              {/* Task Info */}
              <Card className="bg-gradient-to-r from-indigo-50 to-indigo-50">
                <CardContent className="p-4">
                  <h3 className="font-bold text-lg mb-2">{selectedTask.title}</h3>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <span className="text-gray-600">Oda:</span>
                      <span className="font-semibold ml-2">{selectedTask.room_number}</span>
                    </div>
                    <div>
                      <span className="text-gray-600">Öncelik:</span>
                      <Badge className={`ml-2 ${getPriorityColor(selectedTask.priority)}`}>
                        {selectedTask.priority}
                      </Badge>
                    </div>
                    <div>
                      <span className="text-gray-600">Durum:</span>
                      <Badge className={`ml-2 ${getStatusColor(selectedTask.status)}`}>
                        {selectedTask.status}
                      </Badge>
                    </div>
                    <div>
                      <span className="text-gray-600">Atanan:</span>
                      <span className="font-semibold ml-2">{selectedTask.assigned_to || 'Atanmadı'}</span>
                    </div>
                  </div>
                  <p className="text-sm text-gray-700 mt-3">{selectedTask.description}</p>
                </CardContent>
              </Card>

              {/* Status Actions */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Durum Değiştir</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="grid grid-cols-2 gap-2">
                    <Button size="sm" className="bg-blue-600" onClick={() => handleTaskStatusUpdate(selectedTask.id, 'in_progress')}>
                      Başla
                    </Button>
                    <Button size="sm" className="bg-amber-600" onClick={() => handleTaskStatusUpdate(selectedTask.id, 'on_hold', 'Beklemede')}>
                      Beklet
                    </Button>
                    <Button size="sm" className="bg-indigo-600" onClick={() => handleTaskStatusUpdate(selectedTask.id, 'waiting_parts', 'Parça bekleniyor')}>
                      Parça Bekliyor
                    </Button>
                    <Button size="sm" className="bg-green-600" onClick={() => handleTaskStatusUpdate(selectedTask.id, 'completed')}>
                      Tamamla
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {/* Photos */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <Camera className="w-4 h-4" />
                      <span>Fotoğraflar ({taskPhotos.length})</span>
                    </div>
                    <Button size="sm" onClick={() => setPhotoUploadModalOpen(true)}>
                      <Upload className="w-4 h-4 mr-1" />
                      Yükle
                    </Button>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {taskPhotos.length > 0 ? <div className="grid grid-cols-2 gap-2">
                      {taskPhotos.map(photo => <div key={photo.id} className="relative">
                          <img src={photo.photo_url} alt={photo.photo_type} className="w-full h-32 object-cover rounded border" />
                          <Badge className="absolute top-1 left-1 text-xs">
                            {photo.photo_type}
                          </Badge>
                          <p className="text-xs text-gray-600 mt-1">
                            {new Date(photo.uploaded_at).toLocaleString('tr-TR')}
                          </p>
                        </div>)}
                    </div> : <p className="text-center text-gray-500 py-4">Henüz fotoğraf eklenmemiş</p>}
                </CardContent>
              </Card>

              {/* Spare Parts Usage */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <Wrench className="w-4 h-4" />
                      <span>Kullanılan Parçalar</span>
                    </div>
                    <Button size="sm" onClick={() => setPartsUsageModalOpen(true)}>
                      <Plus className="w-4 h-4 mr-1" />
                      Ekle
                    </Button>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {selectedTask.parts_list && selectedTask.parts_list.length > 0 ? <div className="space-y-1">
                      {selectedTask.parts_list.map((part, idx) => <div key={idx} className="flex items-center justify-between p-2 bg-gray-50 rounded text-sm">
                          <span>{part}</span>
                        </div>)}
                    </div> : <p className="text-center text-gray-500 py-4">Henüz parça kullanılmamış</p>}
                </CardContent>
              </Card>
            </div>}
        </DialogContent>
      </Dialog>
    );
}
