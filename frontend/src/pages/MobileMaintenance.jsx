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
import { 
  ArrowLeft, 
  Wrench, 
  AlertTriangle, 
  CheckCircle,
  Clock,
  TrendingUp,
  RefreshCw,
  Settings,
  History,
  FileText,
  BarChart3,
  Eye,
  Calendar,
  Package,
  ShoppingCart,
  Camera,
  Upload,
  Filter,
  X,
  Plus,
  Minus,
  QrCode,
  Activity,
  Home,
  Snowflake,
  Zap,
  Droplet,
  Hammer,
  Sofa
} from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useTranslation } from 'react-i18next';

const MobileMaintenance = ({ user }) => {
  const { t } = useTranslation();
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
      
      const [tasksRes, slaRes, repeatRes, roomsRes, slaConfigRes, partsRes, plannedRes] = await Promise.all([
        axios.get('/tasks/department/maintenance'),
        axios.get('/maintenance/sla-metrics'),
        axios.get('/maintenance/repeat-issues'),
        axios.get('/housekeeping/room-status'),
        axios.get('/maintenance/mobile/sla-configurations').catch(() => ({ data: { sla_configurations: [] } })),
        axios.get('/maintenance/mobile/spare-parts').catch(() => ({ data: { spare_parts: [] } })),
        axios.get('/maintenance/mobile/planned-maintenance').catch(() => ({ data: { planned_maintenance: [] } }))
      ]);

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
      await axios.put(`/tasks/${taskId}`, { status: newStatus });
      toast.success('Görev durumu güncellendi');
      loadData();
    } catch (error) {
      toast.error('Güncelleme başarısız');
    }
  };

  const handleCreateTask = async (formData) => {
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
        params: { new_status: newStatus, reason }
      });
      toast.success(`Görev durumu "${newStatus}" olarak güncellendi`);
      loadData();
      if (selectedTask && selectedTask.id === taskId) {
        setSelectedTask({ ...selectedTask, status: newStatus });
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

  const loadTaskPhotos = async (taskId) => {
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

  const loadTaskDetail = async (task) => {
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
        params: { upcoming_days: 30 }
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

  const getPriorityColor = (priority) => {
    const colors = {
      emergency: 'bg-red-100 text-red-800 border-red-300',
      urgent: 'bg-amber-100 text-amber-800 border-amber-300',
      high: 'bg-yellow-100 text-yellow-800 border-yellow-300',
      normal: 'bg-blue-100 text-blue-800 border-blue-300',
      low: 'bg-gray-100 text-gray-800 border-gray-300'
    };
    return colors[priority] || colors.normal;
  };

  const getStatusColor = (status) => {
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
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-8 h-8 animate-spin text-indigo-600 mx-auto mb-2" />
          <p className="text-gray-600">{t("common.loading")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 pb-20">
      {/* Header */}
      <div className="bg-gradient-to-r from-indigo-600 to-indigo-500 text-white p-4 sticky top-0 z-50 shadow-lg">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/mobile')}
              className="text-white hover:bg-white/20 p-2"
            >
              <ArrowLeft className="w-5 h-5" />
            </Button>
            <div>
              <h1 className="text-xl font-bold">Teknik Servis</h1>
              <p className="text-xs text-indigo-100">Maintenance Dashboard</p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/')}
              className="text-white hover:bg-white/20 p-2"
              title="Ana Sayfa"
            >
              <Home className="w-5 h-5" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRefresh}
              disabled={refreshing}
              className="text-white hover:bg-white/20 p-2"
            >
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
        {slaMetrics && (
          <Card>
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
          </Card>
        )}

        {/* Active Tasks - Urgent Priority */}
        {tasks.filter(t => t.priority === 'urgent' && t.status !== 'completed').length > 0 && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center">
                <AlertTriangle className="w-5 h-5 mr-2 text-red-600" />
                Acil Görevler ({tasks.filter(t => t.priority === 'urgent' && t.status !== 'completed').length})
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {tasks
                .filter(t => t.priority === 'urgent' && t.status !== 'completed')
                .slice(0, 5)
                .map((task) => (
                  <div key={task.id} className="p-3 bg-red-50 rounded-lg border border-red-200">
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex-1">
                        <p className="font-bold text-gray-900">{task.title}</p>
                        <p className="text-sm text-gray-600">{task.description}</p>
                        {task.room_id && (
                          <p className="text-xs text-gray-500 mt-1">
                            Oda: {task.room_number || task.room_id}
                          </p>
                        )}
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
                        {task.room_id && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => loadAssetHistory(task.room_id, task.room_number || task.room_id)}
                          >
                            <History className="w-3 h-3" />
                          </Button>
                        )}
                      </div>
                      {task.status !== 'completed' && (
                        <Button
                          size="sm"
                          onClick={() => handleTaskUpdate(task.id, task.status === 'new' ? 'in_progress' : 'completed')}
                          className="bg-indigo-600 hover:bg-indigo-700"
                        >
                          {task.status === 'new' ? 'Başla' : 'Tamamla'}
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
            </CardContent>
          </Card>
        )}

        {/* All Active Tasks */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg flex items-center">
              <Settings className="w-5 h-5 mr-2 text-blue-600" />
              Aktif Görevler ({tasks.filter(t => t.status !== 'completed').length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {tasks
              .filter(t => t.status !== 'completed')
              .slice(0, 10)
              .map((task) => (
                <div 
                  key={task.id} 
                  className="p-3 bg-gray-50 rounded-lg border cursor-pointer hover:bg-gray-100 transition-colors"
                  onClick={() => loadTaskDetail(task)}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1">
                      <p className="font-bold text-gray-900">{task.title}</p>
                      <p className="text-sm text-gray-600">{task.description}</p>
                      <div className="flex items-center space-x-2 mt-1">
                        {task.room_id && (
                          <span className="text-xs text-gray-500">
                            Oda: {task.room_number || task.room_id}
                          </span>
                        )}
                        {task.assigned_to && (
                          <span className="text-xs text-gray-500">
                            • Atanan: {task.assigned_to}
                          </span>
                        )}
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
                    {task.status !== 'completed' && (
                      <Button
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleTaskUpdate(task.id, task.status === 'new' ? 'in_progress' : 'completed');
                        }}
                        variant="outline"
                      >
                        {task.status === 'new' ? 'Başla' : 'Tamamla'}
                      </Button>
                    )}
                  </div>
                </div>
              ))}
          </CardContent>
        </Card>

        {/* Repeat Issues */}
        {repeatIssues.length > 0 && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center">
                <AlertTriangle className="w-5 h-5 mr-2 text-amber-600" />
                Tekrarlayan Sorunlar
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {repeatIssues.slice(0, 5).map((issue, idx) => (
                <div key={idx} className="p-3 bg-amber-50 rounded-lg border border-amber-200">
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
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Quick Actions - Enhanced */}
        <div className="grid grid-cols-2 gap-3">
          <Button
            className="h-20 flex flex-col items-center justify-center space-y-1 bg-indigo-600 hover:bg-indigo-700"
            onClick={() => setNewTaskModalOpen(true)}
          >
            <Wrench className="w-6 h-6" />
            <span className="text-xs">Yeni Görev</span>
          </Button>
          
          <Button
            className="h-20 flex flex-col items-center justify-center space-y-1 bg-cyan-600 hover:bg-cyan-700"
            onClick={loadSlaConfigurations}
          >
            <Settings className="w-6 h-6" />
            <span className="text-xs">SLA Ayarları</span>
          </Button>
          
          <Button
            className="h-20 flex flex-col items-center justify-center space-y-1 bg-green-600 hover:bg-green-700"
            onClick={loadPartsInventory}
          >
            <Package className="w-6 h-6" />
            <span className="text-xs">Parça Stok</span>
          </Button>
          
          <Button
            className="h-20 flex flex-col items-center justify-center space-y-1 bg-indigo-600 hover:bg-indigo-700"
            onClick={loadPlannedMaintenanceDetail}
          >
            <Calendar className="w-6 h-6" />
            <span className="text-xs">Planlı Bakım</span>
          </Button>
          
          <Button
            className="h-20 flex flex-col items-center justify-center space-y-1 bg-blue-600 hover:bg-blue-700"
            onClick={() => setAssetHistoryModalOpen(true)}
          >
            <History className="w-6 h-6" />
            <span className="text-xs">Bakım Geçmişi</span>
          </Button>
          
          <Button
            className="h-20 flex flex-col items-center justify-center space-y-1 bg-amber-600 hover:bg-amber-700"
            onClick={() => setFilterModalOpen(true)}
          >
            <Filter className="w-6 h-6" />
            <span className="text-xs">Filtreleme</span>
          </Button>
        </div>
      </div>

      {/* New Task Modal */}
      <Dialog open={newTaskModalOpen} onOpenChange={setNewTaskModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Yeni Bakım Görevi Oluştur</DialogTitle>
          </DialogHeader>
          <form onSubmit={(e) => {
            e.preventDefault();
            handleCreateTask(new FormData(e.target));
          }}>
            <div className="space-y-4">
              <div>
                <Label>Oda Seçin *</Label>
                <select name="room_id" className="w-full p-2 border rounded mt-1" required>
                  <option value="">Seçin...</option>
                  {allRooms.map(room => (
                    <option key={room.id} value={room.id}>
                      Oda {room.room_number} - {room.room_type}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <Label>Arıza Tipi *</Label>
                <select name="issue_type" className="w-full p-2 border rounded mt-1" required>
                  <option value="">Seçin...</option>
                  <option value="electrical">Elektrik</option>
                  <option value="plumbing">Tesisat</option>
                  <option value="hvac">HVAC / Klima</option>
                  <option value="furniture">Mobilya</option>
                  <option value="appliance">Cihaz</option>
                  <option value="structural">Yapısal</option>
                  <option value="other">Diğer</option>
                </select>
              </div>

              <div>
                <Label>Açıklama *</Label>
                <Textarea 
                  name="description" 
                  rows={4}
                  placeholder="Arıza detaylarını yazın..."
                  required
                />
              </div>

              <div>
                <Label>Öncelik *</Label>
                <select name="priority" className="w-full p-2 border rounded mt-1" required>
                  <option value="normal">Normal</option>
                  <option value="high">Yüksek</option>
                  <option value="urgent">Acil</option>
                </select>
              </div>

              <Button type="submit" className="w-full bg-indigo-600 hover:bg-indigo-700">
                Görev Oluştur
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Asset History Modal */}
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
                  {allRooms.slice(0, 10).map(room => (
                    <Button
                      key={room.id}
                      variant="outline"
                      className="w-full justify-start"
                      onClick={() => loadAssetHistory(room.id, room.room_number)}
                    >
                      <span className="font-bold">Oda {room.room_number}</span>
                      <span className="text-gray-500 ml-2">- {room.room_type}</span>
                    </Button>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* History Display */}
            {assetHistory && (
              <Card>
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
                    {assetHistory.history && assetHistory.history.length > 0 ? (
                      <div className="space-y-2 mt-4">
                        <p className="font-bold text-sm text-gray-700 mb-2">Son Bakımlar:</p>
                        {assetHistory.history.slice(0, 5).map((item, idx) => (
                          <div key={idx} className="p-3 bg-gray-50 rounded border text-xs">
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
                            {item.cost && (
                              <p className="text-indigo-700 font-bold mt-2">{item.cost} ₺</p>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-center py-8 text-gray-500">
                        <History className="w-12 h-12 mx-auto mb-2 opacity-30" />
                        <p>Bu varlık için bakım kaydı bulunamadı</p>
                      </div>
                    )}

                    {/* Most Common Issues */}
                    {assetHistory.most_common_issues && assetHistory.most_common_issues.length > 0 && (
                      <div className="mt-4">
                        <p className="font-bold text-sm text-gray-700 mb-2">En Yaygın Sorunlar:</p>
                        <div className="space-y-1">
                          {assetHistory.most_common_issues.map((issue, idx) => (
                            <div key={idx} className="flex items-center justify-between p-2 bg-amber-50 rounded text-xs">
                              <span className="text-gray-900">{issue.type}</span>
                              <Badge variant="outline" className="bg-amber-100">
                                {issue.count}x
                              </Badge>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Parts Inventory Modal */}
      <Dialog open={partsInventoryModalOpen} onOpenChange={setPartsInventoryModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <Package className="w-5 h-5 text-green-600" />
              <span>Parça & Malzeme Stok Kartı</span>
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-3">
            {/* Stock Summary */}
            <div className="grid grid-cols-3 gap-2">
              <Card className="bg-blue-50">
                <CardContent className="p-3 text-center">
                  <p className="text-2xl font-bold text-blue-900">{partsInventory.length}</p>
                  <p className="text-xs text-blue-600">Toplam Kalem</p>
                </CardContent>
              </Card>
              <Card className="bg-red-50">
                <CardContent className="p-3 text-center">
                  <p className="text-2xl font-bold text-red-900">
                    {partsInventory.filter(p => p.stock < p.min_stock).length}
                  </p>
                  <p className="text-xs text-red-600">Düşük Stok</p>
                </CardContent>
              </Card>
              <Card className="bg-green-50">
                <CardContent className="p-3 text-center">
                  <p className="text-2xl font-bold text-green-900">
                    {partsInventory.filter(p => p.stock >= p.min_stock).length}
                  </p>
                  <p className="text-xs text-green-600">Yeterli Stok</p>
                </CardContent>
              </Card>
            </div>

            {/* Low Stock Alert */}
            {partsInventory.filter(p => p.stock < p.min_stock).length > 0 && (
              <Card className="bg-red-50 border-red-200">
                <CardContent className="p-3">
                  <div className="flex items-center space-x-2">
                    <AlertTriangle className="w-5 h-5 text-red-600" />
                    <p className="text-sm font-bold text-red-900">
                      {partsInventory.filter(p => p.stock < p.min_stock).length} kalem kritik seviyede!
                    </p>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Parts List by Category */}
            {['HVAC', 'Elektrik', 'Tesisat', 'Yapısal', 'Mobilya', 'Genel'].map(category => {
              const categoryParts = partsInventory.filter(p => p.category === category);
              if (categoryParts.length === 0) return null;

              return (
                <Card key={category}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center justify-between">
                      <span className="flex items-center gap-1.5">
                        {category === 'HVAC' ? <><Snowflake className="w-3.5 h-3.5 text-sky-600" /> HVAC</> :
                         category === 'Elektrik' ? <><Zap className="w-3.5 h-3.5 text-amber-600" /> Elektrik</> :
                         category === 'Tesisat' ? <><Droplet className="w-3.5 h-3.5 text-sky-500" /> Tesisat</> :
                         category === 'Yapısal' ? <><Hammer className="w-3.5 h-3.5 text-slate-600" /> Yapısal</> :
                         category === 'Mobilya' ? <><Sofa className="w-3.5 h-3.5 text-amber-700" /> Mobilya</> :
                         <><Wrench className="w-3.5 h-3.5 text-slate-600" /> Genel Malzeme</>}
                      </span>
                      <Badge variant="outline">{categoryParts.length}</Badge>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {categoryParts.map(part => {
                      const isLowStock = part.stock < part.min_stock;
                      const stockPercentage = (part.stock / part.min_stock) * 100;
                      
                      return (
                        <div 
                          key={part.id} 
                          className={`p-3 rounded-lg border ${
                            isLowStock ? 'bg-red-50 border-red-200' : 'bg-gray-50 border-gray-200'
                          }`}
                        >
                          <div className="flex items-start justify-between mb-2">
                            <div className="flex-1">
                              <div className="flex items-center space-x-2">
                                <p className="font-bold text-gray-900">{part.name}</p>
                                {isLowStock && (
                                  <Badge className="bg-red-500 text-xs">DİKKAT</Badge>
                                )}
                              </div>
                              <p className="text-xs text-gray-500 mt-1">📍 {part.location}</p>
                            </div>
                            <div className="text-right">
                              <p className="font-bold text-lg text-indigo-700">{part.unit_price} ₺</p>
                              <p className="text-xs text-gray-500">/{part.unit}</p>
                            </div>
                          </div>
                          
                          {/* Stock Bar */}
                          <div className="space-y-1">
                            <div className="flex items-center justify-between text-xs">
                              <span className="text-gray-600">Stok Durumu:</span>
                              <span className={`font-bold ${
                                isLowStock ? 'text-red-700' : 'text-green-700'
                              }`}>
                                {part.stock} / {part.min_stock} {part.unit}
                              </span>
                            </div>
                            <div className="w-full bg-gray-200 rounded-full h-2">
                              <div 
                                className={`h-2 rounded-full transition-all ${
                                  stockPercentage < 50 ? 'bg-red-500' :
                                  stockPercentage < 100 ? 'bg-yellow-500' :
                                  'bg-green-500'
                                }`}
                                style={{ width: `${Math.min(stockPercentage, 100)}%` }}
                              />
                            </div>
                          </div>

                          {isLowStock && (
                            <div className="mt-2 flex items-center justify-between p-2 bg-red-100 rounded">
                              <span className="text-xs text-red-900 flex items-center gap-1">
                                <AlertTriangle className="w-3 h-3" />
                                {part.min_stock - part.stock} {part.unit} sipariş gerekli
                              </span>
                              <Button 
                                size="sm" 
                                className="bg-red-600 hover:bg-red-700 h-6 text-xs"
                                onClick={() => toast.success(`${part.name} sipariş listesine eklendi`)}
                              >
                                <ShoppingCart className="w-3 h-3 mr-1" />
                                Sipariş
                              </Button>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </CardContent>
                </Card>
              );
            })}

            {/* Total Value */}
            <Card className="bg-gradient-to-r from-indigo-50 to-indigo-50 border-indigo-200">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-indigo-700 font-medium">Toplam Stok Değeri</p>
                    <p className="text-xs text-indigo-600 mt-1">Tüm malzemeler</p>
                  </div>
                  <p className="text-3xl font-bold text-indigo-700">
                    {partsInventory.reduce((sum, p) => sum + (p.stock * p.unit_price), 0).toLocaleString('tr-TR')} ₺
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>
        </DialogContent>
      </Dialog>


      {/* SLA Configuration Modal - NEW */}
      <Dialog open={slaConfigModalOpen} onOpenChange={setSlaConfigModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <Settings className="w-5 h-5" />
              <span>SLA Ayarları</span>
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4">
            <p className="text-sm text-gray-600">
              Her öncelik seviyesi için yanıt ve çözüm sürelerini ayarlayın (dakika cinsinden)
            </p>
            
            {slaConfigurations.map((config) => (
              <Card key={config.priority} className="border-2">
                <CardContent className="p-4">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <Badge className={getPriorityColor(config.priority)}>
                        {config.priority.toUpperCase()}
                      </Badge>
                    </div>
                    
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label className="text-xs">Yanıt Süresi (dk)</Label>
                        <Input
                          type="number"
                          defaultValue={config.response_time_minutes}
                          id={`response-${config.priority}`}
                          className="mt-1"
                        />
                      </div>
                      <div>
                        <Label className="text-xs">Çözüm Süresi (dk)</Label>
                        <Input
                          type="number"
                          defaultValue={config.resolution_time_minutes}
                          id={`resolution-${config.priority}`}
                          className="mt-1"
                        />
                      </div>
                    </div>
                    
                    <Button 
                      size="sm" 
                      className="w-full"
                      onClick={() => {
                        const response = document.getElementById(`response-${config.priority}`).value;
                        const resolution = document.getElementById(`resolution-${config.priority}`).value;
                        handleSlaUpdate(config.priority, response, resolution);
                      }}
                    >
                      Kaydet
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      {/* Task Detail Modal with Photos and Parts - NEW */}
      <Dialog open={taskDetailModalOpen} onOpenChange={setTaskDetailModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Görev Detayı</DialogTitle>
          </DialogHeader>
          
          {selectedTask && (
            <div className="space-y-4">
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
                    <Button
                      size="sm"
                      className="bg-blue-600"
                      onClick={() => handleTaskStatusUpdate(selectedTask.id, 'in_progress')}
                    >
                      Başla
                    </Button>
                    <Button
                      size="sm"
                      className="bg-amber-600"
                      onClick={() => handleTaskStatusUpdate(selectedTask.id, 'on_hold', 'Beklemede')}
                    >
                      Beklet
                    </Button>
                    <Button
                      size="sm"
                      className="bg-indigo-600"
                      onClick={() => handleTaskStatusUpdate(selectedTask.id, 'waiting_parts', 'Parça bekleniyor')}
                    >
                      Parça Bekliyor
                    </Button>
                    <Button
                      size="sm"
                      className="bg-green-600"
                      onClick={() => handleTaskStatusUpdate(selectedTask.id, 'completed')}
                    >
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
                    <Button
                      size="sm"
                      onClick={() => setPhotoUploadModalOpen(true)}
                    >
                      <Upload className="w-4 h-4 mr-1" />
                      Yükle
                    </Button>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {taskPhotos.length > 0 ? (
                    <div className="grid grid-cols-2 gap-2">
                      {taskPhotos.map((photo) => (
                        <div key={photo.id} className="relative">
                          <img
                            src={photo.photo_url}
                            alt={photo.photo_type}
                            className="w-full h-32 object-cover rounded border"
                          />
                          <Badge className="absolute top-1 left-1 text-xs">
                            {photo.photo_type}
                          </Badge>
                          <p className="text-xs text-gray-600 mt-1">
                            {new Date(photo.uploaded_at).toLocaleString('tr-TR')}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-center text-gray-500 py-4">Henüz fotoğraf eklenmemiş</p>
                  )}
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
                    <Button
                      size="sm"
                      onClick={() => setPartsUsageModalOpen(true)}
                    >
                      <Plus className="w-4 h-4 mr-1" />
                      Ekle
                    </Button>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {selectedTask.parts_list && selectedTask.parts_list.length > 0 ? (
                    <div className="space-y-1">
                      {selectedTask.parts_list.map((part, idx) => (
                        <div key={idx} className="flex items-center justify-between p-2 bg-gray-50 rounded text-sm">
                          <span>{part}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-center text-gray-500 py-4">Henüz parça kullanılmamış</p>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Photo Upload Modal - NEW */}
      <Dialog open={photoUploadModalOpen} onOpenChange={setPhotoUploadModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Fotoğraf Yükle</DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4">
            <div>
              <Label>Fotoğraf Türü</Label>
              <Select value={photoType} onValueChange={setPhotoType}>
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="before">Öncesi</SelectItem>
                  <SelectItem value="during">Süreç</SelectItem>
                  <SelectItem value="after">Sonrası</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <div>
              <Label>Fotoğraf Seç</Label>
              <Input
                type="file"
                accept="image/*"
                capture="environment"
                onChange={(e) => setPhotoFile(e.target.files[0])}
                className="mt-1"
              />
            </div>
            
            {photoFile && (
              <div className="p-2 bg-green-50 rounded text-sm">
                <p className="font-semibold">Seçilen dosya:</p>
                <p>{photoFile.name}</p>
              </div>
            )}
            
            <Button 
              className="w-full" 
              onClick={handlePhotoUpload}
              disabled={!photoFile}
            >
              <Upload className="w-4 h-4 mr-2" />
              Yükle
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Parts Usage Modal - NEW */}
      <Dialog open={partsUsageModalOpen} onOpenChange={setPartsUsageModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Parça Kullanımı</DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4">
            <div>
              <Label>Parça Seçin</Label>
              <select
                className="w-full p-2 border rounded mt-1"
                onChange={(e) => {
                  const part = partsInventory.find(p => p.id === e.target.value);
                  setSelectedPart(part);
                }}
              >
                <option value="">Seçin...</option>
                {partsInventory.filter(p => p.current_stock > 0).map(part => (
                  <option key={part.id} value={part.id}>
                    {part.part_name} - Stok: {part.current_stock}
                  </option>
                ))}
              </select>
            </div>
            
            {selectedPart && (
              <>
                <Card className="bg-blue-50">
                  <CardContent className="p-3 text-sm">
                    <p><strong>Parça:</strong> {selectedPart.part_name}</p>
                    <p><strong>Kategori:</strong> {selectedPart.category}</p>
                    <p><strong>Mevcut Stok:</strong> {selectedPart.current_stock}</p>
                    <p><strong>Birim Fiyat:</strong> {selectedPart.unit_price} ₺</p>
                    <p><strong>Depo:</strong> {selectedPart.warehouse_location}</p>
                  </CardContent>
                </Card>
                
                <div>
                  <Label>Miktar</Label>
                  <div className="flex items-center space-x-2 mt-1">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setUsageQuantity(Math.max(1, usageQuantity - 1))}
                    >
                      <Minus className="w-4 h-4" />
                    </Button>
                    <Input
                      type="number"
                      value={usageQuantity}
                      onChange={(e) => setUsageQuantity(parseInt(e.target.value) || 1)}
                      min="1"
                      max={selectedPart.current_stock}
                      className="text-center"
                    />
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setUsageQuantity(Math.min(selectedPart.current_stock, usageQuantity + 1))}
                    >
                      <Plus className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
                
                <div className="p-3 bg-gray-100 rounded">
                  <p className="text-sm">
                    <strong>Toplam Maliyet:</strong> {(selectedPart.unit_price * usageQuantity).toFixed(2)} ₺
                  </p>
                </div>
              </>
            )}
            
            <Button 
              className="w-full" 
              onClick={handlePartUsage}
              disabled={!selectedPart || usageQuantity < 1}
            >
              Parça Kullan
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Planned Maintenance Modal - NEW */}
      <Dialog open={plannedMaintenanceModalOpen} onOpenChange={setPlannedMaintenanceModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <Calendar className="w-5 h-5" />
              <span>Planlı Bakım Takvimi (30 Gün)</span>
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4">
            {plannedMaintenance.length > 0 ? (
              <>
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
                  {plannedMaintenance.map((item) => (
                    <Card key={item.id} className={`border-2 ${
                      item.is_overdue ? 'bg-red-50 border-red-300' :
                      item.days_until <= 7 ? 'bg-yellow-50 border-yellow-300' :
                      'bg-white border-gray-200'
                    }`}>
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
                            {item.is_overdue ? (
                              <Badge className="bg-red-600">
                                {Math.abs(item.days_until)} gün gecikti
                              </Badge>
                            ) : (
                              <Badge className={
                                item.days_until <= 7 ? 'bg-yellow-500' : 'bg-blue-500'
                              }>
                                {item.days_until} gün kaldı
                              </Badge>
                            )}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </>
            ) : (
              <p className="text-center text-gray-500 py-8">Planlı bakım bulunamadı</p>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Filter Modal - NEW */}
      <Dialog open={filterModalOpen} onOpenChange={setFilterModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <Filter className="w-5 h-5" />
              <span>Görev Filtreleme</span>
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4">
            <div>
              <Label>Durum</Label>
              <Select value={filters.status || "__all__"} onValueChange={(val) => setFilters({...filters, status: val === "__all__" ? "" : val})}>
                <SelectTrigger className="mt-1">
                  <SelectValue placeholder={t("common.all")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">{t("common.all")}</SelectItem>
                  <SelectItem value="open">Açık</SelectItem>
                  <SelectItem value="in_progress">Devam Ediyor</SelectItem>
                  <SelectItem value="on_hold">Beklemede</SelectItem>
                  <SelectItem value="waiting_parts">Parça Bekliyor</SelectItem>
                  <SelectItem value="completed">Tamamlandı</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <div>
              <Label>Öncelik</Label>
              <Select value={filters.priority || "__all__"} onValueChange={(val) => setFilters({...filters, priority: val === "__all__" ? "" : val})}>
                <SelectTrigger className="mt-1">
                  <SelectValue placeholder={t("common.all")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">{t("common.all")}</SelectItem>
                  <SelectItem value="emergency">Acil</SelectItem>
                  <SelectItem value="urgent">Çok Acil</SelectItem>
                  <SelectItem value="high">Yüksek</SelectItem>
                  <SelectItem value="normal">Normal</SelectItem>
                  <SelectItem value="low">Düşük</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <div>
              <Label>Başlangıç Tarihi</Label>
              <Input
                type="date"
                value={filters.start_date}
                onChange={(e) => setFilters({...filters, start_date: e.target.value})}
                className="mt-1"
              />
            </div>
            
            <div>
              <Label>Bitiş Tarihi</Label>
              <Input
                type="date"
                value={filters.end_date}
                onChange={(e) => setFilters({...filters, end_date: e.target.value})}
                className="mt-1"
              />
            </div>
            
            <div className="flex space-x-2">
              <Button className="flex-1" onClick={applyFilters}>
                <Filter className="w-4 h-4 mr-2" />
                Uygula
              </Button>
              <Button variant="outline" onClick={clearFilters}>
                <X className="w-4 h-4 mr-2" />
                Temizle
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

    </div>
  );
};

export default MobileMaintenance;
