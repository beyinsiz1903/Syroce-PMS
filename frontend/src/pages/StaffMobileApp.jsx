import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { CheckCircle, Clock, AlertCircle, Camera, MessageSquare } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const StaffMobileApp = ({ user }) => {
  const { t } = useTranslation();
  const [tasks, setTasks] = useState([]);
  const [selectedTask, setSelectedTask] = useState(null);
  const [notes, setNotes] = useState('');
  const [filter, setFilter] = useState('all'); // all, pending, in_progress, completed
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadTasks();
  }, [filter]);

  const loadTasks = async () => {
    try {
      const params = {};
      if (filter !== 'all') {
        params.status = filter;
      }
      
      const response = await axios.get('/pms/staff-tasks', { params });
      setTasks(response.data?.tasks || response.data || []);
    } catch (error) {
      console.error('Failed to load tasks:', error);
    }
  };

  const handleStatusUpdate = async (taskId, newStatus) => {
    setLoading(true);
    try {
      await axios.put(`/pms/staff-tasks/${taskId}`, {
        status: newStatus,
        updated_by: user?.id,
        updated_at: new Date().toISOString()
      });
      
      toast.success(`Task status updated to ${newStatus}`);
      loadTasks();
      setSelectedTask(null);
    } catch (error) {
      toast.error('Görev güncellenemedi');
    } finally {
      setLoading(false);
    }
  };

  const handleAddNotes = async (taskId) => {
    if (!notes.trim()) return;
    
    try {
      await axios.put(`/pms/staff-tasks/${taskId}`, {
        notes: notes,
        notes_added_at: new Date().toISOString(),
        notes_added_by: user?.id
      });
      
      toast.success('Notes added');
      setNotes('');
      setSelectedTask(null);
      loadTasks();
    } catch (error) {
      toast.error('Notlar eklenemedi');
    }
  };

  const getPriorityColor = (priority) => {
    const colors = {
      urgent: 'bg-red-100 text-red-700',
      high: 'bg-orange-100 text-orange-700',
      normal: 'bg-blue-100 text-blue-700',
      low: 'bg-gray-100 text-gray-700'
    };
    return colors[priority] || colors.normal;
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="w-5 h-5 text-green-500" />;
      case 'in_progress':
        return <Clock className="w-5 h-5 text-blue-500" />;
      case 'pending':
        return <AlertCircle className="w-5 h-5 text-orange-500" />;
      default:
        return <Clock className="w-5 h-5 text-gray-500" />;
    }
  };

  return (
    <div className="max-w-md mx-auto bg-gray-50 min-h-screen">
      {/* Header */}
      <div className="bg-blue-600 text-white p-4 sticky top-0 z-10">
        <h1 className="text-xl font-bold">Staff Tasks</h1>
        <p className="text-sm text-blue-100">{user?.name || 'Staff Member'}</p>
      </div>

      {/* Filter Tabs */}
      <div className="bg-white border-b p-2 sticky top-16 z-10">
        <div className="flex gap-2 overflow-x-auto">
          {['all', 'pending', 'in_progress', 'completed'].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-4 py-2 rounded-full text-sm font-semibold whitespace-nowrap ${
                filter === f
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {f.replace('_', ' ').toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Tasks List */}
      <div className="p-4 space-y-3">
        {tasks.map((task) => (
          <Card key={task.id} className="hover:shadow-md transition">
            <CardContent className="p-4">
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  {getStatusIcon(task.status)}
                  <div>
                    <h3 className="font-semibold">{task.title || task.task_type}</h3>
                    <p className="text-xs text-gray-600">{task.department}</p>
                  </div>
                </div>
                <Badge className={getPriorityColor(task.priority)}>
                  {task.priority}
                </Badge>
              </div>

              <p className="text-sm text-gray-700 mb-2">{task.description}</p>

              {task.room_number && (
                <div className="text-sm bg-blue-50 p-2 rounded mb-2">
                  📍 Room {task.room_number}
                </div>
              )}

              {task.assigned_to && (
                <div className="text-xs text-gray-600 mb-2">
                  Assigned to: {task.assigned_to}
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex gap-2 mt-3">
                {task.status === 'pending' && (
                  <Button
                    size="sm"
                    onClick={() => handleStatusUpdate(task.id, 'in_progress')}
                    disabled={loading}
                    className="flex-1"
                  >
                    Start
                  </Button>
                )}
                {task.status === 'in_progress' && (
                  <>
                    <Button
                      size="sm"
                      onClick={() => handleStatusUpdate(task.id, 'completed')}
                      disabled={loading}
                      className="flex-1 bg-green-600 hover:bg-green-700"
                    >
                      Complete
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setSelectedTask(task)}
                    >
                      <MessageSquare className="w-4 h-4" />
                    </Button>
                  </>
                )}
                {task.status === 'completed' && (
                  <div className="flex-1 text-center text-green-600 font-semibold text-sm">
                    ✓ Completed
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        ))}

        {tasks.length === 0 && (
          <Card>
            <CardContent className="text-center py-12">
              <CheckCircle className="w-16 h-16 mx-auto text-gray-400 mb-4" />
              <p className="text-gray-600">No tasks found</p>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Notes Modal */}
      {selectedTask && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-end z-50">
          <div className="bg-white w-full rounded-t-2xl p-6 space-y-4">
            <h3 className="font-bold text-lg">Add Notes</h3>
            <Textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add notes about this task..."
              rows={4}
            />
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setSelectedTask(null)} className="flex-1">
                Cancel
              </Button>
              <Button onClick={() => handleAddNotes(selectedTask.id)} className="flex-1">
                Save Notes
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default StaffMobileApp;