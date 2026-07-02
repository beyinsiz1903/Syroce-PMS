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
import { useTranslation } from 'react-i18next';
import MobileMaintenanceNewTaskModal from './MobileMaintenanceNewTaskModal';
import MobileMaintenanceAssetHistoryModal from './MobileMaintenanceAssetHistoryModal';
import MobileMaintenancePartsInventoryModal from './MobileMaintenancePartsInventoryModal';
import MobileMaintenanceSlaConfigModal from './MobileMaintenanceSlaConfigModal';
import MobileMaintenanceTaskDetailModal from './MobileMaintenanceTaskDetailModal';
import MobileMaintenancePhotoUploadModal from './MobileMaintenancePhotoUploadModal';
import MobileMaintenancePartsUsageModal from './MobileMaintenancePartsUsageModal';
import MobileMaintenancePlannedMaintenanceModal from './MobileMaintenancePlannedMaintenanceModal';
import MobileMaintenanceFilterModal from './MobileMaintenanceFilterModal';
const MobileMaintenance = ({
  user
}) => {
  const {
    t
  } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [tasks, setTasks] = useState([]);
  const [stats, setStats] = useState(null);
  const [slaMetrics, setSlaMetrics] = useState(null);
  const [repeatIssues, setRepeatIssues] = useState([]);
  const [refreshing, setRefreshing] = useState(false);
  const [newTaskModalOpen, setNewTaskModalOpen] = useState(false);
  const [allRooms, setAllRooms] = useState([]);
  const [assetHistoryModalOpen, setAssetHistoryModalOpen] = useState(false);
  const [selectedAsset, setSelectedAsset] = useState(null);
  const [assetHistory, setAssetHistory] = useState(null);
  const [partsInventoryModalOpen, setPartsInventoryModalOpen] = useState(false);
  const [partsInventory, setPartsInventory] = useState([]);

  // New state for enhanced features
  const [slaConfigModalOpen, setSlaConfigModalOpen] = useState(false);
  const [slaConfigurations, setSlaConfigurations] = useState([]);
  const [taskDetailModalOpen, setTaskDetailModalOpen] = useState(false);
  const [selectedTask, setSelectedTask] = useState(null);
  const [taskPhotos, setTaskPhotos] = useState([]);
  const [photoUploadModalOpen, setPhotoUploadModalOpen] = useState(false);
  const [photoType, setPhotoType] = useState('before');
  const [photoFile, setPhotoFile] = useState(null);
  const [partsUsageModalOpen, setPartsUsageModalOpen] = useState(false);
  const [selectedPart, setSelectedPart] = useState(null);
  const [usageQuantity, setUsageQuantity] = useState(1);
  const [plannedMaintenanceModalOpen, setPlannedMaintenanceModalOpen] = useState(false);
  const [plannedMaintenance, setPlannedMaintenance] = useState([]);
  const [filterModalOpen, setFilterModalOpen] = useState(false);
  const [filters, setFilters] = useState({
    status: '',
    priority: '',
    assigned_to: '',
    start_date: '',
    end_date: ''
  });
  useEffect(() => {
    loadData();
  }, []);
  const loadData = async () => {
    try {
      setLoading(true);
      const [tasksRes, slaRes, repeatRes, roomsRes, slaConfigRes, partsRes, plannedRes] = await Promise.all([axios.get('/tasks/department/maintenance'), axios.get('/maintenance/sla-metrics'), axios.get('/maintenance/repeat-issues'), axios.get('/housekeeping/room-status'), axios.get('/maintenance/mobile/sla-configurations').catch(() => ({
        data: {
          sla_configurations: []
        }
      })), axios.get('/maintenance/mobile/spare-parts').catch(() => ({
        data: {
          spare_parts: []
        }
      })), axios.get('/maintenance/mobile/planned-maintenance').catch(() => ({
        data: {
          planned_maintenance: []
        }
      }))]);
      const allTasks = tasksRes.data.tasks || [];
      setTasks(allTasks);
      setStats(tasksRes.data.statistics);
      setSlaMetrics(slaRes.data);
      setRepeatIssues(repeatRes.data.repeat_issues || []);
      setAllRooms(roomsRes.data.rooms || []);
      setSlaConfigurations(slaConfigRes.data.sla_configurations || []);
      setPartsInventory(partsRes.data.spare_parts || []);
      setPlannedMaintenance(plannedRes.data.planned_maintenance || []);
    } catch (error) {
      console.error('Failed to load maintenance data:', error);
      toast.error('Veri yüklenemedi');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };
  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };
  const handleTaskUpdate = async (taskId, newStatus) => {
    try {
      await axios.put(`/tasks/${taskId}`, {
        status: newStatus
      });
      toast.success('Görev durumu güncellendi');
      loadData();
    } catch (error) {
      toast.error('Güncelleme başarısız');
    }
  };
  const handleCreateTask = async formData => {
    try {
      await axios.post('/maintenance/mobile/quick-issue', {
        room_id: formData.get('room_id'),
        issue_type: formData.get('issue_type'),
        description: formData.get('description'),
        priority: formData.get('priority')
      });
      toast.success('Yeni görev oluşturuldu!');
      setNewTaskModalOpen(false);
      loadData();
    } catch (error) {
      toast.error('Görev oluşturulamadı: ' + (error.response?.data?.detail || 'Hata'));
    }
  };

  // New helper functions for enhanced features
  const handleTaskStatusUpdate = async (taskId, newStatus, reason = null) => {
    try {
      await axios.post(`/maintenance/mobile/task/${taskId}/status`, null, {
        params: {
          new_status: newStatus,
          reason
        }
      });
      toast.success(`Görev durumu "${newStatus}" olarak güncellendi`);
      loadData();
      if (selectedTask && selectedTask.id === taskId) {
        setSelectedTask({
          ...selectedTask,
          status: newStatus
        });
      }
    } catch (error) {
      toast.error('Durum güncellenemedi: ' + (error.response?.data?.detail || 'Hata'));
    }
  };
  const handlePhotoUpload = async () => {
    if (!photoFile || !selectedTask) {
      toast.error('Lütfen bir fotoğraf seçin');
      return;
    }
    try {
      const reader = new FileReader();
      reader.onloadend = async () => {
        const base64Data = reader.result;
        await axios.post(`/maintenance/mobile/task/${selectedTask.id}/photo`, null, {
          params: {
            photo_data: base64Data,
            photo_type: photoType,
            description: `${photoType} photo`
          }
        });
        toast.success('Fotoğraf yüklendi!');
        setPhotoUploadModalOpen(false);
        setPhotoFile(null);
        await loadTaskPhotos(selectedTask.id);
      };
      reader.readAsDataURL(photoFile);
    } catch (error) {
      toast.error('Fotoğraf yüklenemedi: ' + (error.response?.data?.detail || 'Hata'));
    }
  };
  const loadTaskPhotos = async taskId => {
    try {
      const res = await axios.get(`/maintenance/mobile/task/${taskId}/photos`);
      setTaskPhotos(res.data.photos || []);
    } catch (error) {
      console.error('Failed to load photos:', error);
    }
  };
  const handlePartUsage = async () => {
    if (!selectedPart || !selectedTask || usageQuantity < 1) {
      toast.error('Lütfen parça ve miktar seçin');
      return;
    }
    try {
      await axios.post(`/maintenance/mobile/spare-parts/use`, null, {
        params: {
          task_id: selectedTask.id,
          spare_part_id: selectedPart.id,
          quantity: usageQuantity,
          notes: `${selectedTask.title} görevi için kullanıldı`
        }
      });
      toast.success(`${selectedPart.part_name} parçası kullanıldı (${usageQuantity} adet)`);
      setPartsUsageModalOpen(false);
      setUsageQuantity(1);
      setSelectedPart(null);
      loadData();
    } catch (error) {
      toast.error('Parça kullanımı kaydedilemedi: ' + (error.response?.data?.detail || 'Hata'));
    }
  };
  const loadTaskDetail = async task => {
    try {
      setSelectedTask(task);
      await loadTaskPhotos(task.id);
      setTaskDetailModalOpen(true);
    } catch (error) {
      toast.error('Görev detayı yüklenemedi');
    }
  };
  const loadPlannedMaintenanceDetail = async () => {
    try {
      const res = await axios.get('/maintenance/mobile/planned-maintenance', {
        params: {
          upcoming_days: 30
        }
      });
      setPlannedMaintenance(res.data.planned_maintenance || []);
      setPlannedMaintenanceModalOpen(true);
    } catch (error) {
      toast.error('Planlı bakım yüklenemedi');
    }
  };
  const loadSlaConfigurations = async () => {
    try {
      const res = await axios.get('/maintenance/mobile/sla-configurations');
      setSlaConfigurations(res.data.sla_configurations || []);
      setSlaConfigModalOpen(true);
    } catch (error) {
      toast.error('SLA ayarları yüklenemedi');
    }
  };
  const handleSlaUpdate = async (priority, responseTime, resolutionTime) => {
    try {
      await axios.post('/maintenance/mobile/sla-configurations', null, {
        params: {
          priority,
          response_time_minutes: parseInt(responseTime),
          resolution_time_minutes: parseInt(resolutionTime)
        }
      });
      toast.success('SLA ayarları güncellendi');
      loadData();
    } catch (error) {
      toast.error('SLA güncellenemedi: ' + (error.response?.data?.detail || 'Hata'));
    }
  };
  const applyFilters = async () => {
    try {
      const params = new URLSearchParams();
      if (filters.status) params.append('status', filters.status);
      if (filters.priority) params.append('priority', filters.priority);
      if (filters.assigned_to) params.append('assigned_to', filters.assigned_to);
      if (filters.start_date) params.append('start_date', filters.start_date);
      if (filters.end_date) params.append('end_date', filters.end_date);
      const res = await axios.get(`/maintenance/mobile/tasks/filtered?${params.toString()}`);
      setTasks(res.data.tasks || []);
      setFilterModalOpen(false);
      toast.success(`${res.data.count} görev bulundu`);
    } catch (error) {
      toast.error('Filtreleme yapılamadı');
    }
  };
  const clearFilters = () => {
    setFilters({
      status: '',
      priority: '',
      assigned_to: '',
      start_date: '',
      end_date: ''
    });
    loadData();
  };
  const getPriorityColor = priority => {
    const colors = {
      emergency: 'bg-red-100 text-red-800 border-red-300',
      urgent: 'bg-amber-100 text-amber-800 border-amber-300',
      high: 'bg-yellow-100 text-yellow-800 border-yellow-300',
      normal: 'bg-blue-100 text-blue-800 border-blue-300',
      low: 'bg-gray-100 text-gray-800 border-gray-300'
    };
    return colors[priority] || colors.normal;
  };
  const getStatusColor = status => {
    const colors = {
      open: 'bg-blue-100 text-blue-800',
      in_progress: 'bg-yellow-100 text-yellow-800',
      on_hold: 'bg-amber-100 text-amber-800',
      waiting_parts: 'bg-indigo-100 text-indigo-800',
      completed: 'bg-green-100 text-green-800',
      cancelled: 'bg-gray-100 text-gray-800'
    };
    return colors[status] || colors.open;
  };
  const loadAssetHistory = async (assetId, assetName) => {
    try {
      const res = await axios.get(`/maintenance/asset-history/${assetId}`);
      setAssetHistory(res.data);
      setSelectedAsset(assetName);
      setAssetHistoryModalOpen(true);
    } catch (error) {
      toast.error('Bakım geçmişi yüklenemedi');
    }
  };
  const loadPartsInventory = async () => {
    try {
      const res = await axios.get('/maintenance/parts-inventory');
      setPartsInventory(res.data.parts || []);
      setPartsInventoryModalOpen(true);
    } catch (error) {
      console.error('Parts inventory load failed:', error);
      toast.error(error?.response?.data?.detail || 'Parça envanteri yüklenemedi');
      setPartsInventory([]);
      setPartsInventoryModalOpen(true);
    }
  };
  if (loading) {
    return <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-8 h-8 animate-spin text-indigo-600 mx-auto mb-2" />
          <p className="text-gray-600">{t("common.loading")}</p>
        </div>
      </div>;
  }
  return <div className="min-h-screen bg-gray-50 pb-20">
      {/* Header */}
      <div className="bg-gradient-to-r from-indigo-600 to-indigo-500 text-white p-4 sticky top-0 z-50 shadow-lg">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Button variant="ghost" size="sm" onClick={() => navigate('/mobile')} className="text-white hover:bg-white/20 p-2">
              <ArrowLeft className="w-5 h-5" />
            </Button>
            <div>
              <h1 className="text-xl font-bold">Teknik Servis</h1>
              <p className="text-xs text-indigo-100">Maintenance Dashboard</p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <Button variant="ghost" size="sm" onClick={() => navigate('/')} className="text-white hover:bg-white/20 p-2" title="Ana Sayfa">
              <Home className="w-5 h-5" />
            </Button>
            <Button variant="ghost" size="sm" onClick={handleRefresh} disabled={refreshing} className="text-white hover:bg-white/20 p-2">
              <RefreshCw className={`w-5 h-5 ${refreshing ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Quick Stats */}
        <div className="grid grid-cols-2 gap-3">
          <Card className="bg-gradient-to-br from-red-50 to-red-100 border-red-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-red-600 font-medium">ACİL</p>
                  <p className="text-3xl font-bold text-red-700">{stats?.by_priority?.urgent || 0}</p>
                </div>
                <AlertTriangle className="w-10 h-10 text-red-300" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-yellow-50 to-yellow-100 border-yellow-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-yellow-600 font-medium">DEVAM EDEN</p>
                  <p className="text-3xl font-bold text-yellow-700">{stats?.by_status?.in_progress || 0}</p>
                </div>
                <Clock className="w-10 h-10 text-yellow-300" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-green-50 to-green-100 border-green-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-green-600 font-medium">TAMAMLANAN</p>
                  <p className="text-3xl font-bold text-green-700">{stats?.by_status?.completed || 0}</p>
                </div>
                <CheckCircle className="w-10 h-10 text-green-300" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-blue-50 to-blue-100 border-blue-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-blue-600 font-medium">TOPLAM</p>
                  <p className="text-3xl font-bold text-blue-700">{tasks.length}</p>
                </div>
                <Settings className="w-10 h-10 text-blue-300" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* SLA Metrics */}
        {slaMetrics && <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center">
                <TrendingUp className="w-5 h-5 mr-2 text-indigo-600" />
                SLA Performansı
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4">
                <div className="text-center p-3 bg-indigo-50 rounded-lg">
                  <p className="text-xs text-indigo-600 mb-1">Ortalama Yanıt Süresi</p>
                  <p className="text-2xl font-bold text-indigo-700">
                    {slaMetrics.avg_response_time_minutes?.toFixed(0) || 0} dk
                  </p>
                </div>
                <div className="text-center p-3 bg-blue-50 rounded-lg">
                  <p className="text-xs text-blue-600 mb-1">Ortalama Çözüm Süresi</p>
                  <p className="text-2xl font-bold text-blue-700">
                    {slaMetrics.avg_resolution_time_minutes?.toFixed(0) || 0} dk
                  </p>
                </div>
                <div className="text-center p-3 bg-green-50 rounded-lg">
                  <p className="text-xs text-green-600 mb-1">SLA Uyum Oranı</p>
                  <p className="text-2xl font-bold text-green-700">
                    {slaMetrics.sla_compliance_rate?.toFixed(1) || 0}%
                  </p>
                </div>
                <div className="text-center p-3 bg-red-50 rounded-lg">
                  <p className="text-xs text-red-600 mb-1">Geçikmiş Görevler</p>
                  <p className="text-2xl font-bold text-red-700">
                    {stats?.overdue || 0}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>}

        {/* Active Tasks - Urgent Priority */}
        {tasks.filter(t => t.priority === 'urgent' && t.status !== 'completed').length > 0 && <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center">
                <AlertTriangle className="w-5 h-5 mr-2 text-red-600" />
                Acil Görevler ({tasks.filter(t => t.priority === 'urgent' && t.status !== 'completed').length})
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {tasks.filter(t => t.priority === 'urgent' && t.status !== 'completed').slice(0, 5).map(task => <div key={task.id} className="p-3 bg-red-50 rounded-lg border border-red-200">
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex-1">
                        <p className="font-bold text-gray-900">{task.title}</p>
                        <p className="text-sm text-gray-600">{task.description}</p>
                        {task.room_id && <p className="text-xs text-gray-500 mt-1">
                            Oda: {task.room_number || task.room_id}
                          </p>}
                      </div>
                      <Badge className={getPriorityColor(task.priority)}>
                        {task.priority}
                      </Badge>
                    </div>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <Badge className={getStatusColor(task.status)}>
                          {task.status}
                        </Badge>
                        {task.room_id && <Button size="sm" variant="outline" onClick={() => loadAssetHistory(task.room_id, task.room_number || task.room_id)}>
                            <History className="w-3 h-3" />
                          </Button>}
                      </div>
                      {task.status !== 'completed' && <Button size="sm" onClick={() => handleTaskUpdate(task.id, task.status === 'new' ? 'in_progress' : 'completed')} className="bg-indigo-600 hover:bg-indigo-700">
                          {task.status === 'new' ? 'Başla' : 'Tamamla'}
                        </Button>}
                    </div>
                  </div>)}
            </CardContent>
          </Card>}

        {/* All Active Tasks */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg flex items-center">
              <Settings className="w-5 h-5 mr-2 text-blue-600" />
              Aktif Görevler ({tasks.filter(t => t.status !== 'completed').length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {tasks.filter(t => t.status !== 'completed').slice(0, 10).map(task => <div key={task.id} className="p-3 bg-gray-50 rounded-lg border cursor-pointer hover:bg-gray-100 transition-colors" onClick={() => loadTaskDetail(task)}>
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1">
                      <p className="font-bold text-gray-900">{task.title}</p>
                      <p className="text-sm text-gray-600">{task.description}</p>
                      <div className="flex items-center space-x-2 mt-1">
                        {task.room_id && <span className="text-xs text-gray-500">
                            Oda: {task.room_number || task.room_id}
                          </span>}
                        {task.assigned_to && <span className="text-xs text-gray-500">
                            • Atanan: {task.assigned_to}
                          </span>}
                      </div>
                    </div>
                    <div className="flex flex-col items-end space-y-1">
                      <Badge className={getPriorityColor(task.priority)}>
                        {task.priority}
                      </Badge>
                      <Eye className="w-4 h-4 text-gray-400" />
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <Badge className={getStatusColor(task.status)}>
                      {task.status}
                    </Badge>
                    {task.status !== 'completed' && <Button size="sm" onClick={e => {
                e.stopPropagation();
                handleTaskUpdate(task.id, task.status === 'new' ? 'in_progress' : 'completed');
              }} variant="outline">
                        {task.status === 'new' ? 'Başla' : 'Tamamla'}
                      </Button>}
                  </div>
                </div>)}
          </CardContent>
        </Card>

        {/* Repeat Issues */}
        {repeatIssues.length > 0 && <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center">
                <AlertTriangle className="w-5 h-5 mr-2 text-amber-600" />
                Tekrarlayan Sorunlar
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {repeatIssues.slice(0, 5).map((issue, idx) => <div key={idx} className="p-3 bg-amber-50 rounded-lg border border-amber-200">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <p className="font-bold text-gray-900">Oda {issue.room_number}</p>
                      <p className="text-sm text-gray-600">{issue.issue_type}</p>
                      <p className="text-xs text-gray-500 mt-1">
                        {issue.occurrences} kez tekrarlandı
                      </p>
                    </div>
                    <Badge variant="outline" className="bg-amber-100">
                      {issue.occurrences}x
                    </Badge>
                  </div>
                </div>)}
            </CardContent>
          </Card>}

        {/* Quick Actions - Enhanced */}
        <div className="grid grid-cols-2 gap-3">
          <Button className="h-20 flex flex-col items-center justify-center space-y-1 bg-indigo-600 hover:bg-indigo-700" onClick={() => setNewTaskModalOpen(true)}>
            <Wrench className="w-6 h-6" />
            <span className="text-xs">Yeni Görev</span>
          </Button>
          
          <Button className="h-20 flex flex-col items-center justify-center space-y-1 bg-cyan-600 hover:bg-cyan-700" onClick={loadSlaConfigurations}>
            <Settings className="w-6 h-6" />
            <span className="text-xs">SLA Ayarları</span>
          </Button>
          
          <Button className="h-20 flex flex-col items-center justify-center space-y-1 bg-green-600 hover:bg-green-700" onClick={loadPartsInventory}>
            <Package className="w-6 h-6" />
            <span className="text-xs">Parça Stok</span>
          </Button>
          
          <Button className="h-20 flex flex-col items-center justify-center space-y-1 bg-indigo-600 hover:bg-indigo-700" onClick={loadPlannedMaintenanceDetail}>
            <Calendar className="w-6 h-6" />
            <span className="text-xs">Planlı Bakım</span>
          </Button>
          
          <Button className="h-20 flex flex-col items-center justify-center space-y-1 bg-blue-600 hover:bg-blue-700" onClick={() => setAssetHistoryModalOpen(true)}>
            <History className="w-6 h-6" />
            <span className="text-xs">Bakım Geçmişi</span>
          </Button>
          
          <Button className="h-20 flex flex-col items-center justify-center space-y-1 bg-amber-600 hover:bg-amber-700" onClick={() => setFilterModalOpen(true)}>
            <Filter className="w-6 h-6" />
            <span className="text-xs">Filtreleme</span>
          </Button>
        </div>
      </div>

      {/* New Task Modal */}
      <MobileMaintenanceNewTaskModal newTaskModalOpen={newTaskModalOpen} setNewTaskModalOpen={setNewTaskModalOpen} handleCreateTask={handleCreateTask} FormData={FormData} allRooms={allRooms} />

      {/* Asset History Modal */}
      <MobileMaintenanceAssetHistoryModal assetHistoryModalOpen={assetHistoryModalOpen} setAssetHistoryModalOpen={setAssetHistoryModalOpen} allRooms={allRooms} loadAssetHistory={loadAssetHistory} assetHistory={assetHistory} selectedAsset={selectedAsset} getPriorityColor={getPriorityColor} />

      {/* Parts Inventory Modal */}
      <MobileMaintenancePartsInventoryModal partsInventoryModalOpen={partsInventoryModalOpen} setPartsInventoryModalOpen={setPartsInventoryModalOpen} partsInventory={partsInventory} toast={toast} />


      {/* SLA Configuration Modal - NEW */}
      <MobileMaintenanceSlaConfigModal slaConfigModalOpen={slaConfigModalOpen} setSlaConfigModalOpen={setSlaConfigModalOpen} slaConfigurations={slaConfigurations} getPriorityColor={getPriorityColor} handleSlaUpdate={handleSlaUpdate} />

      {/* Task Detail Modal with Photos and Parts - NEW */}
      <MobileMaintenanceTaskDetailModal taskDetailModalOpen={taskDetailModalOpen} setTaskDetailModalOpen={setTaskDetailModalOpen} selectedTask={selectedTask} getPriorityColor={getPriorityColor} getStatusColor={getStatusColor} handleTaskStatusUpdate={handleTaskStatusUpdate} taskPhotos={taskPhotos} setPhotoUploadModalOpen={setPhotoUploadModalOpen} setPartsUsageModalOpen={setPartsUsageModalOpen} />

      {/* Photo Upload Modal - NEW */}
      <MobileMaintenancePhotoUploadModal photoUploadModalOpen={photoUploadModalOpen} setPhotoUploadModalOpen={setPhotoUploadModalOpen} photoType={photoType} setPhotoType={setPhotoType} setPhotoFile={setPhotoFile} photoFile={photoFile} handlePhotoUpload={handlePhotoUpload} />

      {/* Parts Usage Modal - NEW */}
      <MobileMaintenancePartsUsageModal partsUsageModalOpen={partsUsageModalOpen} setPartsUsageModalOpen={setPartsUsageModalOpen} partsInventory={partsInventory} setSelectedPart={setSelectedPart} selectedPart={selectedPart} setUsageQuantity={setUsageQuantity} usageQuantity={usageQuantity} parseInt={parseInt} handlePartUsage={handlePartUsage} />

      {/* Planned Maintenance Modal - NEW */}
      <MobileMaintenancePlannedMaintenanceModal plannedMaintenanceModalOpen={plannedMaintenanceModalOpen} setPlannedMaintenanceModalOpen={setPlannedMaintenanceModalOpen} plannedMaintenance={plannedMaintenance} />

      {/* Filter Modal - NEW */}
      <MobileMaintenanceFilterModal filterModalOpen={filterModalOpen} setFilterModalOpen={setFilterModalOpen} filters={filters} setFilters={setFilters} applyFilters={applyFilters} clearFilters={clearFilters} />

    </div>;
};
export default MobileMaintenance;