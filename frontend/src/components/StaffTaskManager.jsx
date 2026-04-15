import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  Wrench, CheckCircle, Clock, AlertCircle, Plus, Search,
  ClipboardList, Filter, RefreshCw, Trash2, User, BedDouble
} from 'lucide-react';

const TASK_TYPES = [
  { value: 'maintenance', label: 'Bakım', icon: '🔧' },
  { value: 'cleaning', label: 'Temizlik', icon: '🧹' },
  { value: 'repair', label: 'Onarım', icon: '🔨' },
  { value: 'inspection', label: 'Denetim', icon: '👁️' },
  { value: 'setup', label: 'Hazırlık', icon: '📦' },
  { value: 'delivery', label: 'Teslimat', icon: '🚚' },
];

const DEPARTMENTS = [
  { value: 'engineering', label: 'Teknik Servis' },
  { value: 'housekeeping', label: 'Kat Hizmetleri' },
  { value: 'maintenance', label: 'Bakım' },
  { value: 'frontdesk', label: 'Ön Büro' },
  { value: 'fb', label: 'Yiyecek & İçecek' },
];

const PRIORITIES = [
  { value: 'urgent', label: 'Acil', color: 'bg-red-100 text-red-700 border-red-200' },
  { value: 'high', label: 'Yüksek', color: 'bg-orange-100 text-orange-700 border-orange-200' },
  { value: 'normal', label: 'Normal', color: 'bg-blue-100 text-blue-700 border-blue-200' },
  { value: 'low', label: 'Düşük', color: 'bg-gray-100 text-gray-600 border-gray-200' },
];

const STATUS_MAP = {
  pending: { label: 'Bekliyor', icon: AlertCircle, color: 'text-orange-500', bg: 'bg-orange-50' },
  in_progress: { label: 'Devam Ediyor', icon: Clock, color: 'text-blue-500', bg: 'bg-blue-50' },
  completed: { label: 'Tamamlandı', icon: CheckCircle, color: 'text-green-500', bg: 'bg-green-50' },
};

const StaffTaskManager = () => {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showDialog, setShowDialog] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterPriority, setFilterPriority] = useState('all');
  const [formData, setFormData] = useState({
    task_type: 'maintenance',
    department: 'engineering',
    room_id: '',
    priority: 'normal',
    description: '',
    assigned_to: ''
  });

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      const response = await axios.get('/pms/staff-tasks');
      setTasks(response.data?.tasks || response.data || []);
    } catch {
      toast.error('Görevler yüklenemedi');
    }
    setLoading(false);
  }, []);

  useEffect(() => { loadTasks(); }, [loadTasks]);

  const createTask = async () => {
    if (!formData.description.trim()) {
      toast.error('Görev açıklaması gerekli');
      return;
    }
    try {
      await axios.post('/pms/staff-tasks', formData);
      toast.success('Görev oluşturuldu');
      loadTasks();
      setShowDialog(false);
      setFormData({ task_type: 'maintenance', department: 'engineering', room_id: '', priority: 'normal', description: '', assigned_to: '' });
    } catch {
      toast.error('Görev oluşturulamadı');
    }
  };

  const updateTaskStatus = async (taskId, newStatus) => {
    try {
      await axios.put(`/pms/staff-tasks/${taskId}`, { status: newStatus });
      toast.success(newStatus === 'completed' ? 'Görev tamamlandı' : 'Görev başlatıldı');
      loadTasks();
    } catch {
      toast.error('Görev güncellenemedi');
    }
  };

  const deleteTask = async (taskId) => {
    try {
      await axios.delete(`/pms/staff-tasks/${taskId}`);
      toast.success('Görev silindi');
      loadTasks();
    } catch {
      toast.error('Görev silinemedi');
    }
  };

  const filtered = tasks.filter(t => {
    if (filterStatus !== 'all' && t.status !== filterStatus) return false;
    if (filterPriority !== 'all' && t.priority !== filterPriority) return false;
    if (searchTerm) {
      const s = searchTerm.toLowerCase();
      return (t.description || '').toLowerCase().includes(s)
        || (t.room_number || t.room_id || '').toString().toLowerCase().includes(s)
        || (t.assigned_to || '').toLowerCase().includes(s);
    }
    return true;
  });

  const counts = {
    total: tasks.length,
    pending: tasks.filter(t => t.status === 'pending').length,
    in_progress: tasks.filter(t => t.status === 'in_progress').length,
    completed: tasks.filter(t => t.status === 'completed').length,
  };

  const getTaskType = (val) => TASK_TYPES.find(t => t.value === val) || { label: val, icon: '📋' };
  const getDept = (val) => DEPARTMENTS.find(d => d.value === val)?.label || val;
  const getPriority = (val) => PRIORITIES.find(p => p.value === val) || PRIORITIES[2];

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-2xl font-bold flex items-center gap-2">
            <ClipboardList className="w-6 h-6" /> Görev Yönetimi
          </h3>
          <p className="text-gray-600 text-sm">Teknik servis ve kat hizmetleri görev takibi</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={loadTasks} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> Yenile
          </Button>
          <Button onClick={() => setShowDialog(true)}>
            <Plus className="w-4 h-4 mr-2" /> Yeni Görev
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card className="bg-gray-50 border-gray-200 cursor-pointer" onClick={() => setFilterStatus('all')}>
          <CardContent className="p-4 text-center">
            <ClipboardList className="w-5 h-5 mx-auto mb-1 text-gray-600" />
            <p className="text-xs text-gray-500">Toplam</p>
            <p className="text-2xl font-bold text-gray-700">{counts.total}</p>
          </CardContent>
        </Card>
        <Card className="bg-orange-50 border-orange-200 cursor-pointer" onClick={() => setFilterStatus('pending')}>
          <CardContent className="p-4 text-center">
            <AlertCircle className="w-5 h-5 mx-auto mb-1 text-orange-500" />
            <p className="text-xs text-orange-600">Bekleyen</p>
            <p className="text-2xl font-bold text-orange-700">{counts.pending}</p>
          </CardContent>
        </Card>
        <Card className="bg-blue-50 border-blue-200 cursor-pointer" onClick={() => setFilterStatus('in_progress')}>
          <CardContent className="p-4 text-center">
            <Clock className="w-5 h-5 mx-auto mb-1 text-blue-500" />
            <p className="text-xs text-blue-600">Devam Eden</p>
            <p className="text-2xl font-bold text-blue-700">{counts.in_progress}</p>
          </CardContent>
        </Card>
        <Card className="bg-green-50 border-green-200 cursor-pointer" onClick={() => setFilterStatus('completed')}>
          <CardContent className="p-4 text-center">
            <CheckCircle className="w-5 h-5 mx-auto mb-1 text-green-500" />
            <p className="text-xs text-green-600">Tamamlanan</p>
            <p className="text-2xl font-bold text-green-700">{counts.completed}</p>
          </CardContent>
        </Card>
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input
            className="pl-9"
            placeholder="Görev, oda veya personel ara..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
          />
        </div>
        <Select value={filterStatus} onValueChange={setFilterStatus}>
          <SelectTrigger className="w-[160px]">
            <Filter className="w-3 h-3 mr-1" />
            <SelectValue placeholder="Durum" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tüm Durumlar</SelectItem>
            <SelectItem value="pending">Bekliyor</SelectItem>
            <SelectItem value="in_progress">Devam Ediyor</SelectItem>
            <SelectItem value="completed">Tamamlandı</SelectItem>
          </SelectContent>
        </Select>
        <Select value={filterPriority} onValueChange={setFilterPriority}>
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="Öncelik" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tüm Öncelikler</SelectItem>
            {PRIORITIES.map(p => (
              <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {filtered.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-gray-500">
            <Wrench className="w-12 h-12 mx-auto mb-3 text-gray-300" />
            <p className="font-medium">
              {tasks.length === 0 ? 'Henüz görev oluşturulmamış' : 'Filtrelere uygun görev bulunamadı'}
            </p>
            <p className="text-sm mt-1">
              {tasks.length === 0 ? '"Yeni Görev" butonuyla görev oluşturabilirsiniz' : 'Filtreleri değiştirmeyi deneyin'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((task) => {
            const tt = getTaskType(task.task_type);
            const st = STATUS_MAP[task.status] || STATUS_MAP.pending;
            const pr = getPriority(task.priority);
            const StIcon = st.icon;
            return (
              <Card key={task.id} className="hover:shadow-lg transition">
                <CardHeader className="pb-2">
                  <div className="flex justify-between items-start">
                    <div className="flex items-center gap-2">
                      <StIcon className={`w-5 h-5 ${st.color}`} />
                      <CardTitle className="text-base">
                        {tt.icon} {tt.label}
                      </CardTitle>
                    </div>
                    <Badge variant="outline" className={pr.color}>{pr.label}</Badge>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {(task.room_number || task.room_id) && (
                      <div className="text-sm flex items-center gap-1.5">
                        <BedDouble className="w-3.5 h-3.5 text-gray-400" />
                        <span className="font-medium">Oda:</span> {task.room_number || task.room_id}
                      </div>
                    )}
                    <div className="text-sm flex items-center gap-1.5">
                      <Wrench className="w-3.5 h-3.5 text-gray-400" />
                      <span className="font-medium">Departman:</span> {getDept(task.department)}
                    </div>
                    <p className="text-sm text-gray-600 line-clamp-2">{task.description}</p>
                    {task.assigned_to && (
                      <div className="text-sm flex items-center gap-1.5">
                        <User className="w-3.5 h-3.5 text-gray-400" />
                        <span className="font-medium">Atanan:</span> {task.assigned_to}
                      </div>
                    )}
                    {task.created_at && (
                      <p className="text-xs text-gray-400">{new Date(task.created_at).toLocaleString('tr-TR')}</p>
                    )}
                    <div className="flex gap-2 mt-3 pt-2 border-t">
                      {task.status === 'pending' && (
                        <Button size="sm" onClick={() => updateTaskStatus(task.id, 'in_progress')}>
                          Başlat
                        </Button>
                      )}
                      {task.status === 'in_progress' && (
                        <Button size="sm" className="bg-green-600 hover:bg-green-700" onClick={() => updateTaskStatus(task.id, 'completed')}>
                          Tamamla
                        </Button>
                      )}
                      {task.status === 'completed' && (
                        <Badge className="bg-green-100 text-green-700">Tamamlandı</Badge>
                      )}
                      <Button size="sm" variant="ghost" className="ml-auto text-red-500 hover:text-red-700" onClick={() => deleteTask(task.id)}>
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Yeni Görev Oluştur</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Görev Tipi</Label>
                <Select value={formData.task_type} onValueChange={(v) => setFormData({ ...formData, task_type: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {TASK_TYPES.map(t => (
                      <SelectItem key={t.value} value={t.value}>{t.icon} {t.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Departman</Label>
                <Select value={formData.department} onValueChange={(v) => setFormData({ ...formData, department: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {DEPARTMENTS.map(d => (
                      <SelectItem key={d.value} value={d.value}>{d.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Öncelik</Label>
                <Select value={formData.priority} onValueChange={(v) => setFormData({ ...formData, priority: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {PRIORITIES.map(p => (
                      <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Oda (Opsiyonel)</Label>
                <Input
                  value={formData.room_id}
                  onChange={(e) => setFormData({ ...formData, room_id: e.target.value })}
                  placeholder="Oda numarası"
                />
              </div>
            </div>
            <div>
              <Label>Atanan Personel</Label>
              <Input
                value={formData.assigned_to}
                onChange={(e) => setFormData({ ...formData, assigned_to: e.target.value })}
                placeholder="Personel adı"
              />
            </div>
            <div>
              <Label>Açıklama *</Label>
              <Textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                rows={3}
                placeholder="Görev detaylarını yazın..."
              />
            </div>
            <Button onClick={createTask} className="w-full">Görev Oluştur</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default StaffTaskManager;
