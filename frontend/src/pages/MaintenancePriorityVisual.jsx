import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ArrowLeft, AlertCircle, Clock, Wrench, CheckCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const MaintenancePriorityVisual = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({
    urgent: 0,
    high: 0,
    normal: 0,
    low: 0
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const res = await axios.get('/maintenance/tasks');
      const tasksData = res.data || [];
      setTasks(tasksData);
      
      // Calculate stats
      const stats = {
        urgent: tasksData.filter(t => t.priority === 'urgent').length,
        high: tasksData.filter(t => t.priority === 'high').length,
        normal: tasksData.filter(t => t.priority === 'normal').length,
        low: tasksData.filter(t => t.priority === 'low').length
      };
      setStats(stats);
    } catch (error) {
      console.error('Error loading tasks:', error);
      toast.error('Görevler yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  const getPriorityColor = (priority) => {
    const colors = {
      urgent: 'bg-red-600',
      high: 'bg-amber-500',
      normal: 'bg-blue-500',
      low: 'bg-gray-500'
    };
    return colors[priority] || 'bg-gray-500';
  };

  const getPriorityIcon = (priority) => {
    if (priority === 'urgent' || priority === 'high') {
      return <AlertCircle className="w-4 h-4" />;
    }
    return <Clock className="w-4 h-4" />;
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-600">{t("common.loading")}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-gradient-to-r from-indigo-600 to-indigo-500 text-white p-4 sticky top-0 z-50 shadow-lg">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/mobile/maintenance')}
              className="text-white hover:bg-white/20 p-2"
            >
              <ArrowLeft className="w-5 h-5" />
            </Button>
            <div>
              <h1 className="text-xl font-bold">Öncelik Görseli</h1>
              <p className="text-xs text-indigo-100">Priority Visual Dashboard</p>
            </div>
          </div>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Priority Stats */}
        <div className="grid grid-cols-4 gap-2">
          <Card className="bg-red-50 border-red-200">
            <CardContent className="p-3 text-center">
              <AlertCircle className="w-6 h-6 mx-auto text-red-600 mb-1" />
              <p className="text-2xl font-bold text-red-700">{stats.urgent}</p>
              <p className="text-xs text-red-600">Acil</p>
            </CardContent>
          </Card>
          
          <Card className="bg-amber-50 border-amber-200">
            <CardContent className="p-3 text-center">
              <AlertCircle className="w-6 h-6 mx-auto text-amber-600 mb-1" />
              <p className="text-2xl font-bold text-amber-700">{stats.high}</p>
              <p className="text-xs text-amber-600">Yüksek</p>
            </CardContent>
          </Card>
          
          <Card className="bg-blue-50 border-blue-200">
            <CardContent className="p-3 text-center">
              <Clock className="w-6 h-6 mx-auto text-blue-600 mb-1" />
              <p className="text-2xl font-bold text-blue-700">{stats.normal}</p>
              <p className="text-xs text-blue-600">Normal</p>
            </CardContent>
          </Card>
          
          <Card className="bg-gray-50 border-gray-200">
            <CardContent className="p-3 text-center">
              <Clock className="w-6 h-6 mx-auto text-gray-600 mb-1" />
              <p className="text-2xl font-bold text-gray-700">{stats.low}</p>
              <p className="text-xs text-gray-600">Düşük</p>
            </CardContent>
          </Card>
        </div>

        {/* Visual Priority Matrix */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Öncelik Matrisi</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {['urgent', 'high', 'normal', 'low'].map(priority => {
              const priorityTasks = tasks.filter(t => t.priority === priority);
              const barWidth = tasks.length > 0 ? (priorityTasks.length / tasks.length) * 100 : 0;
              
              return (
                <div key={priority}>
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center space-x-2">
                      {getPriorityIcon(priority)}
                      <span className="text-sm font-medium capitalize">{
                        priority === 'urgent' ? 'Acil' :
                        priority === 'high' ? 'Yüksek' :
                        priority === 'normal' ? 'Normal' : 'Düşük'
                      }</span>
                    </div>
                    <span className="text-sm text-gray-600">{priorityTasks.length}</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-3">
                    <div 
                      className={`h-3 rounded-full ${getPriorityColor(priority)}`}
                      style={{ width: `${barWidth}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>

        {/* Tasks by Priority */}
        {['urgent', 'high', 'normal', 'low'].map(priority => {
          const priorityTasks = tasks.filter(t => t.priority === priority && t.status !== 'completed');
          if (priorityTasks.length === 0) return null;

          return (
            <Card key={priority}>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center justify-between">
                  <span className="capitalize">
                    {priority === 'urgent' ? '🔴 Acil Görevler' :
                     priority === 'high' ? '🟠 Yüksek Öncelik' :
                     priority === 'normal' ? '🔵 Normal Görevler' : '⚪ Düşük Öncelik'}
                  </span>
                  <Badge className={getPriorityColor(priority)}>
                    {priorityTasks.length}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {priorityTasks.map(task => (
                  <div key={task.id} className="p-3 bg-gray-50 rounded-lg border">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <p className="font-bold text-sm text-gray-900">
                          Oda {task.room_number}
                        </p>
                        <p className="text-xs text-gray-600 mt-1">{task.description}</p>
                        <div className="flex items-center space-x-2 mt-2">
                          <Badge variant="outline" className="text-xs">
                            {task.issue_type}
                          </Badge>
                          {task.status === 'in_progress' && (
                            <Wrench className="w-3 h-3 text-blue-600" />
                          )}
                          {task.status === 'completed' && (
                            <CheckCircle className="w-3 h-3 text-green-600" />
                          )}
                        </div>
                      </div>
                      <Badge className={getPriorityColor(task.priority)}>
                        {task.priority}
                      </Badge>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          );
        })}

        {tasks.length === 0 && (
          <Card>
            <CardContent className="p-12 text-center">
              <CheckCircle className="w-16 h-16 mx-auto text-green-300 mb-3" />
              <p className="text-gray-600 font-medium">Bakım görevi yok</p>
              <p className="text-sm text-gray-500 mt-1">Tüm görevler tamamlandı!</p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
};

export default MaintenancePriorityVisual;
