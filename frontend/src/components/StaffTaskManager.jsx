import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
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
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Wrench, CheckCircle, Clock, AlertCircle, Plus, Search,
  ClipboardList, Filter, RefreshCw, Trash2, User, BedDouble
} from 'lucide-react';

const TASK_TYPE_KEYS = ['maintenance', 'cleaning', 'repair', 'inspection', 'setup', 'delivery'];
const TASK_ICONS = { maintenance: '', cleaning: '', repair: '', inspection: '', setup: '', delivery: '' };
const DEPT_KEYS = ['engineering', 'housekeeping', 'maintenance', 'frontdesk', 'fb'];
const PRIORITY_KEYS = ['urgent', 'high', 'normal', 'low'];
const PRIORITY_COLORS = {
  urgent: 'bg-red-100 text-red-700 border-red-200',
  high: 'bg-amber-100 text-amber-700 border-amber-200',
  normal: 'bg-blue-100 text-blue-700 border-blue-200',
  low: 'bg-gray-100 text-gray-600 border-gray-200',
};

const STATUS_ICONS = { pending: AlertCircle, in_progress: Clock, completed: CheckCircle };
const STATUS_COLORS = { pending: 'text-amber-500', in_progress: 'text-blue-500', completed: 'text-green-500' };

const StaffTaskManager = ({ currentUser }) => {
  const { t } = useTranslation();
  const ts = useCallback((k) => t(`pmsComponents.staff.${k}`), [t]);

  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showDialog, setShowDialog] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterPriority, setFilterPriority] = useState('all');
  const [filterSource, setFilterSource] = useState(() => {
    if (typeof window === 'undefined') return 'all';
    return new URLSearchParams(window.location.search).get('source') === 'guest_qr'
      ? 'guest_qr'
      : 'all';
  });
  const [taskToDelete, setTaskToDelete] = useState(null);
  const [taskToComplete, setTaskToComplete] = useState(null);
  const [resolutionNote, setResolutionNote] = useState('');
  const [cleanupConfirmOpen, setCleanupConfirmOpen] = useState(false);
  const emptyForm = {
    task_type: 'maintenance', department: 'engineering', title: '', room_id: '',
    priority: 'normal', description: '', assigned_to: ''
  };
  const [formData, setFormData] = useState(emptyForm);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      const response = await axios.get('/pms/staff-tasks');
      setTasks(response.data?.tasks || response.data || []);
    } catch {
      toast.error(ts('loadError'));
    }
    setLoading(false);
  }, [ts]);

  useEffect(() => { loadTasks(); }, [loadTasks]);

  const createTask = async () => {
    if (formData.title.trim().length < 3) { toast.error(ts('titleRequired')); return; }
    if (!formData.room_id.trim()) { toast.error(ts('roomRequired')); return; }
    try {
      await axios.post('/pms/staff-tasks', formData);
      toast.success(ts('taskCreated'));
      loadTasks();
      setShowDialog(false);
      setFormData(emptyForm);
    } catch (err) {
      const msg = err?.response?.data?.detail || ts('createError');
      toast.error(msg);
    }
  };

  const cleanupEmpty = async () => {
    try {
      const res = await axios.delete('/pms/staff-tasks/cleanup-empty');
      toast.success(ts('cleanupDone', { count: res.data?.deleted_count ?? 0 }));
      setCleanupConfirmOpen(false);
      loadTasks();
    } catch {
      toast.error(ts('cleanupError'));
    }
  };

  const updateTaskStatus = async (taskOrId, newStatus) => {
    const task = typeof taskOrId === 'string'
      ? tasks.find((item) => item.id === taskOrId)
      : taskOrId;
    const taskId = task?.id || taskOrId;
    try {
      const payload = { status: newStatus };
      if (task?.source === 'guest_qr' && newStatus === 'in_progress' && !task.assigned_to) {
        payload.assigned_to = currentUser?.name || currentUser?.email || 'Personel';
      }
      await axios.put(`/pms/staff-tasks/${taskId}`, payload);
      toast.success(newStatus === 'completed' ? ts('taskCompleted') : ts('taskStarted'));
      loadTasks();
    } catch {
      toast.error(ts('updateError'));
    }
  };

  const completeGuestRequest = async () => {
    const note = resolutionNote.trim();
    if (note.length < 3) {
      toast.error('Misafire iletilecek sonuç bilgisini yazın');
      return;
    }
    try {
      await axios.put(`/pms/staff-tasks/${taskToComplete.id}`, {
        status: 'completed',
        resolution_note: note,
        assigned_to: taskToComplete.assigned_to || currentUser?.name || currentUser?.email || 'Personel',
      });
      toast.success('Talep tamamlandı ve sonuç misafire iletildi');
      setTaskToComplete(null);
      setResolutionNote('');
      loadTasks();
    } catch (err) {
      toast.error(err?.response?.data?.detail || ts('updateError'));
    }
  };

  const deleteTask = async (taskId) => {
    try {
      await axios.delete(`/pms/staff-tasks/${taskId}`);
      toast.success(ts('taskDeleted'));
      setTaskToDelete(null);
      loadTasks();
    } catch {
      toast.error(ts('deleteError'));
    }
  };

  const filtered = tasks.filter(t => {
    if (filterStatus !== 'all' && t.status !== filterStatus) return false;
    if (filterPriority !== 'all' && t.priority !== filterPriority) return false;
    if (filterSource === 'guest_qr' && t.source !== 'guest_qr') return false;
    if (filterSource === 'manual' && t.source === 'guest_qr') return false;
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

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-2xl font-bold flex items-center gap-2">
            <ClipboardList className="w-6 h-6" /> {ts('title')}
          </h3>
          <p className="text-gray-600 text-sm">{ts('subtitle')}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={loadTasks} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> {ts('refresh')}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setCleanupConfirmOpen(true)} className="text-red-600 hover:text-red-700">
            <Trash2 className="w-4 h-4 mr-1" /> {ts('cleanupEmpty')}
          </Button>
          <Button onClick={() => setShowDialog(true)}>
            <Plus className="w-4 h-4 mr-2" /> {ts('newTask')}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card className="bg-gray-50 border-gray-200 cursor-pointer" onClick={() => setFilterStatus('all')}>
          <CardContent className="p-4 text-center">
            <ClipboardList className="w-5 h-5 mx-auto mb-1 text-gray-600" />
            <p className="text-xs text-gray-500">{ts('total')}</p>
            <p className="text-2xl font-bold text-gray-700">{counts.total}</p>
          </CardContent>
        </Card>
        <Card className="bg-amber-50 border-amber-200 cursor-pointer" onClick={() => setFilterStatus('pending')}>
          <CardContent className="p-4 text-center">
            <AlertCircle className="w-5 h-5 mx-auto mb-1 text-amber-500" />
            <p className="text-xs text-amber-600">{ts('pending')}</p>
            <p className="text-2xl font-bold text-amber-700">{counts.pending}</p>
          </CardContent>
        </Card>
        <Card className="bg-blue-50 border-blue-200 cursor-pointer" onClick={() => setFilterStatus('in_progress')}>
          <CardContent className="p-4 text-center">
            <Clock className="w-5 h-5 mx-auto mb-1 text-blue-500" />
            <p className="text-xs text-blue-600">{ts('inProgress')}</p>
            <p className="text-2xl font-bold text-blue-700">{counts.in_progress}</p>
          </CardContent>
        </Card>
        <Card className="bg-green-50 border-green-200 cursor-pointer" onClick={() => setFilterStatus('completed')}>
          <CardContent className="p-4 text-center">
            <CheckCircle className="w-5 h-5 mx-auto mb-1 text-green-500" />
            <p className="text-xs text-green-600">{ts('completed')}</p>
            <p className="text-2xl font-bold text-green-700">{counts.completed}</p>
          </CardContent>
        </Card>
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input className="pl-9" placeholder={ts('searchPlaceholder')} value={searchTerm} onChange={e => setSearchTerm(e.target.value)} />
        </div>
        <Select value={filterStatus} onValueChange={setFilterStatus}>
          <SelectTrigger className="w-[160px]">
            <Filter className="w-3 h-3 mr-1" />
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{ts('allStatuses')}</SelectItem>
            <SelectItem value="pending">{ts('pending')}</SelectItem>
            <SelectItem value="in_progress">{ts('inProgress')}</SelectItem>
            <SelectItem value="completed">{ts('completed')}</SelectItem>
          </SelectContent>
        </Select>
        <Select value={filterPriority} onValueChange={setFilterPriority}>
          <SelectTrigger className="w-[160px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{ts('allPriorities')}</SelectItem>
            {PRIORITY_KEYS.map(p => (
              <SelectItem key={p} value={p}>{ts(p)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={filterSource} onValueChange={setFilterSource}>
          <SelectTrigger className="w-[170px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tüm Kaynaklar</SelectItem>
            <SelectItem value="guest_qr">Misafir QR</SelectItem>
            <SelectItem value="manual">Manuel Görev</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {filtered.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-gray-500">
            <Wrench className="w-12 h-12 mx-auto mb-3 text-gray-300" />
            <p className="font-medium">{tasks.length === 0 ? ts('noTasks') : ts('noMatch')}</p>
            <p className="text-sm mt-1">{tasks.length === 0 ? ts('noTasksHint') : ts('noMatchHint')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((task) => {
            const ttLabel = ts(`taskTypes.${task.task_type}`) || task.task_type;
            const ttIcon = TASK_ICONS[task.task_type] || '';
            const StIcon = STATUS_ICONS[task.status] || AlertCircle;
            const stColor = STATUS_COLORS[task.status] || 'text-gray-500';
            const prColor = PRIORITY_COLORS[task.priority] || PRIORITY_COLORS.normal;
            const dash = '—';
            const taskTitle = (task.title || '').trim() || dash;
            const roomLabel = (task.room_number || task.room_id || dash);
            const descLabel = (task.description || '').trim() || dash;
            const assignedLabel = (task.assigned_to || '').trim() || dash;
            return (
              <Card key={task.id} className="hover:shadow-lg transition">
                <CardHeader className="pb-2">
                    <div className="flex justify-between items-start">
                    <div className="flex items-center gap-2 min-w-0">
                      <StIcon className={`w-5 h-5 ${stColor} shrink-0`} />
                      <CardTitle className="text-base truncate" title={taskTitle}>{ttIcon} {taskTitle}</CardTitle>
                    </div>
                    <Badge variant="outline" className={prColor}>{ts(task.priority)}</Badge>
                    </div>
                  <div className="mt-1 flex items-center gap-2">
                    <p className="text-xs text-gray-500">{ttLabel}</p>
                    {task.source === 'guest_qr' && (
                      <Badge variant="outline" className="border-violet-200 bg-violet-50 text-violet-700">Misafir QR</Badge>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <div className="text-sm flex items-center gap-1.5">
                      <BedDouble className={`w-3.5 h-3.5 ${roomLabel === dash ? 'text-gray-300' : 'text-gray-400'}`} />
                      <span className="font-medium">{ts('room')}</span>
                      <span className={roomLabel === dash ? 'text-gray-400 italic' : ''}>{roomLabel}</span>
                    </div>
                    <div className="text-sm flex items-center gap-1.5">
                      <Wrench className="w-3.5 h-3.5 text-gray-400" />
                      <span className="font-medium">{ts('dept')}</span> {ts(`departments.${task.department}`) || task.department}
                    </div>
                    <div className="text-sm">
                      <span className="font-medium">{ts('descLabel')}</span>
                      <p className={`line-clamp-2 ${descLabel === dash ? 'text-gray-400 italic' : 'text-gray-600'}`}>{descLabel}</p>
                    </div>
                    <div className="text-sm flex items-center gap-1.5">
                      <User className={`w-3.5 h-3.5 ${assignedLabel === dash ? 'text-gray-300' : 'text-gray-400'}`} />
                      <span className="font-medium">{ts('assigned')}</span>
                      <span className={assignedLabel === dash ? 'text-gray-400 italic' : ''}>{assignedLabel}</span>
                    </div>
                    {task.created_at && (
                      <p className="text-xs text-gray-400">{new Date(task.created_at).toLocaleString()}</p>
                    )}
                    <div className="flex gap-2 mt-3 pt-2 border-t">
                      {task.status === 'pending' && (
                        <Button size="sm" onClick={() => updateTaskStatus(task, 'in_progress')}>{ts('start')}</Button>
                      )}
                      {task.status === 'in_progress' && (
                        <Button
                          size="sm"
                          className="bg-green-600 hover:bg-green-700"
                          onClick={() => task.source === 'guest_qr'
                            ? setTaskToComplete(task)
                            : updateTaskStatus(task, 'completed')}
                        >
                          {ts('complete')}
                        </Button>
                      )}
                      {task.status === 'completed' && (
                        <Badge className="bg-green-100 text-green-700">{ts('completed')}</Badge>
                      )}
                      {task.source !== 'guest_qr' && <Button
                        size="sm"
                        variant="ghost"
                        className="ml-auto text-red-500 hover:text-red-700"
                        aria-label={ts('deleteTaskAria')}
                        onClick={() => setTaskToDelete(task)}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>}
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
            <DialogTitle>{ts('createTaskTitle')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>{ts('taskType')}</Label>
                <Select value={formData.task_type} onValueChange={(v) => setFormData({ ...formData, task_type: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {TASK_TYPE_KEYS.map(k => (
                      <SelectItem key={k} value={k}>{TASK_ICONS[k]} {ts(`taskTypes.${k}`)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>{ts('department')}</Label>
                <Select value={formData.department} onValueChange={(v) => setFormData({ ...formData, department: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {DEPT_KEYS.map(k => (
                      <SelectItem key={k} value={k}>{ts(`departments.${k}`)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label>{ts('titleField')}</Label>
              <Input
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                placeholder={ts('titlePlaceholder')}
                maxLength={120}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>{ts('priority')}</Label>
                <Select value={formData.priority} onValueChange={(v) => setFormData({ ...formData, priority: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {PRIORITY_KEYS.map(p => (
                      <SelectItem key={p} value={p}>{ts(p)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>{ts('roomFieldRequired')}</Label>
                <Input
                  value={formData.room_id}
                  onChange={(e) => setFormData({ ...formData, room_id: e.target.value })}
                  placeholder={ts('roomPlaceholder')}
                />
              </div>
            </div>
            <div>
              <Label>{ts('assignedStaff')}</Label>
              <Input value={formData.assigned_to} onChange={(e) => setFormData({ ...formData, assigned_to: e.target.value })} placeholder={ts('staffPlaceholder')} />
            </div>
            <div>
              <Label>{ts('descriptionField')}</Label>
              <Textarea value={formData.description} onChange={(e) => setFormData({ ...formData, description: e.target.value })} rows={3} placeholder={ts('descriptionPlaceholder')} />
            </div>
            <Button onClick={createTask} className="w-full">{ts('createTask')}</Button>
          </div>
        </DialogContent>
      </Dialog>

      <AlertDialog open={Boolean(taskToDelete)} onOpenChange={(open) => !open && setTaskToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{ts('deleteConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {ts('deleteConfirmDescription', { title: taskToDelete?.title || ts('untitledTask') })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{ts('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-600 text-white hover:bg-red-700"
              onClick={() => taskToDelete && deleteTask(taskToDelete.id)}
            >
              {ts('deleteConfirmAction')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={Boolean(taskToComplete)} onOpenChange={(open) => {
        if (!open) {
          setTaskToComplete(null);
          setResolutionNote('');
        }
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Misafir talebini sonuçlandır</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="rounded-lg border bg-slate-50 p-3 text-sm">
              <div className="font-semibold">Oda {taskToComplete?.room_number || taskToComplete?.room_id}</div>
              <div className="text-slate-600">{taskToComplete?.title}</div>
            </div>
            <div>
              <Label>Çözüm / misafire gönderilecek bilgi *</Label>
              <Textarea
                value={resolutionNote}
                onChange={(event) => setResolutionNote(event.target.value)}
                rows={4}
                maxLength={2000}
                placeholder="Örn. Talep edilen havlular odaya teslim edildi."
              />
              <p className="mt-1 text-xs text-slate-500">Bu açıklama görev geçmişine kaydedilir ve misafirin QR mesajlaşmasında görünür.</p>
            </div>
            <Button className="w-full bg-green-600 hover:bg-green-700" onClick={completeGuestRequest}>
              Tamamla ve misafire bildir
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <AlertDialog open={cleanupConfirmOpen} onOpenChange={setCleanupConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{ts('cleanupConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{ts('cleanupConfirmDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{ts('cancel')}</AlertDialogCancel>
            <AlertDialogAction className="bg-red-600 text-white hover:bg-red-700" onClick={cleanupEmpty}>
              {ts('cleanupConfirmAction')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};

export default StaffTaskManager;
