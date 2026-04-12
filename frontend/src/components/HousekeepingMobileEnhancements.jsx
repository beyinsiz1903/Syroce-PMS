import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Clock, User, TrendingUp, Award } from 'lucide-react';

const HousekeepingMobileEnhancements = () => {
  const [roomAssignments, setRoomAssignments] = useState([]);
  const [statistics, setStatistics] = useState([]);
  const [selectedStaff, setSelectedStaff] = useState('all');
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('assignments'); // assignments, statistics

  useEffect(() => {
    fetchRoomAssignments();
    fetchCleaningStatistics();
  }, [selectedStaff]);

  const fetchRoomAssignments = async () => {
    try {
      const token = localStorage.getItem('token');
      const url = selectedStaff === 'all' 
        ? `/api/housekeeping/mobile/room-assignments`
        : `/api/housekeeping/mobile/room-assignments?staff_name=${selectedStaff}`;
      
      const response = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setRoomAssignments(data.assignments || []);
      }
    } catch (error) {
      console.error('Error fetching room assignments:', error);
    }
  };

  const fetchCleaningStatistics = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `/api/housekeeping/cleaning-time-statistics`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setStatistics(data.statistics || []);
      }
    } catch (error) {
      console.error('Error fetching statistics:', error);
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status) => {
    const colors = {
      pending: 'bg-yellow-100 text-yellow-800',
      in_progress: 'bg-blue-100 text-blue-800',
      completed: 'bg-green-100 text-green-800'
    };
    return colors[status] || 'bg-gray-100 text-gray-800';
  };

  const getPriorityColor = (priority) => {
    const colors = {
      urgent: 'bg-red-100 text-red-800',
      high: 'bg-orange-100 text-orange-800',
      normal: 'bg-blue-100 text-blue-800',
      low: 'bg-gray-100 text-gray-800'
    };
    return colors[priority] || 'bg-gray-100 text-gray-800';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Tab Navigation */}
      <div className="flex gap-2 border-b">
        <Button
          variant={activeTab === 'assignments' ? 'default' : 'ghost'}
          onClick={() => setActiveTab('assignments')}
          className="rounded-b-none"
        >
          <User className="w-4 h-4 mr-2" />
          Room Assignments
        </Button>
        <Button
          variant={activeTab === 'statistics' ? 'default' : 'ghost'}
          onClick={() => setActiveTab('statistics')}
          className="rounded-b-none"
        >
          <TrendingUp className="w-4 h-4 mr-2" />
          Cleaning Statistics
        </Button>
      </div>

      {/* Room Assignments Tab */}
      {activeTab === 'assignments' && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Current Room Assignments</CardTitle>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-600">Filter by staff:</span>
                  <Select value={selectedStaff} onValueChange={setSelectedStaff}>
                    <SelectTrigger className="w-[180px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Staff</SelectItem>
                      {Array.from(new Set(roomAssignments.map(a => a.assigned_to))).map(staff => (
                        <SelectItem key={staff} value={staff}>{staff}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {roomAssignments.length === 0 ? (
                <div className="text-center text-gray-500 py-8">No active assignments</div>
              ) : (
                <div className="space-y-3">
                  {roomAssignments.map((assignment, idx) => (
                    <div key={idx} className="border rounded-lg p-4 hover:shadow-md transition-shadow">
                      <div className="flex items-start justify-between">
                        <div className="space-y-2 flex-1">
                          <div className="flex items-center gap-3">
                            <div className="text-2xl font-bold text-blue-600">
                              {assignment.room_number}
                            </div>
                            <Badge className={getStatusColor(assignment.status)}>
                              {assignment.status}
                            </Badge>
                            <Badge className={getPriorityColor(assignment.priority)}>
                              {assignment.priority}
                            </Badge>
                          </div>
                          <div className="flex items-center gap-4 text-sm text-gray-600">
                            <div className="flex items-center gap-1">
                              <User className="w-4 h-4" />
                              {assignment.assigned_to}
                            </div>
                            <div>Type: {assignment.task_type}</div>
                            <div>Room Type: {assignment.room_type}</div>
                          </div>
                          {assignment.duration_minutes && (
                            <div className="flex items-center gap-1 text-sm">
                              <Clock className="w-4 h-4 text-blue-600" />
                              <span className="font-medium">
                                {assignment.duration_minutes} minutes
                              </span>
                              <span className="text-gray-600">in progress</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Cleaning Statistics Tab */}
      {activeTab === 'statistics' && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Award className="w-5 h-5" />
                Staff Performance Statistics
              </CardTitle>
            </CardHeader>
            <CardContent>
              {statistics.length === 0 ? (
                <div className="text-center text-gray-500 py-8">No statistics available</div>
              ) : (
                <div className="space-y-4">
                  {statistics.map((stat, idx) => (
                    <Card key={idx} className="border-l-4 border-l-blue-500">
                      <CardContent className="p-4">
                        <div className="space-y-3">
                          <div className="flex items-center justify-between">
                            <h3 className="text-lg font-semibold flex items-center gap-2">
                              <User className="w-5 h-5 text-blue-600" />
                              {stat.staff_name}
                            </h3>
                            <Badge variant="outline">
                              {stat.total_tasks_completed} tasks
                            </Badge>
                          </div>

                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="bg-blue-50 p-3 rounded-lg">
                              <div className="text-sm text-gray-600">Avg Cleaning Time</div>
                              <div className="text-2xl font-bold text-blue-600">
                                {stat.avg_cleaning_time_minutes} min
                              </div>
                            </div>

                            <div className="bg-green-50 p-3 rounded-lg">
                              <div className="text-sm text-gray-600">Tasks Completed</div>
                              <div className="text-2xl font-bold text-green-600">
                                {stat.total_tasks_completed}
                              </div>
                            </div>
                          </div>

                          {stat.by_task_type && Object.keys(stat.by_task_type).length > 0 && (
                            <div>
                              <div className="text-sm font-medium text-gray-700 mb-2">By Task Type:</div>
                              <div className="grid grid-cols-1 gap-2">
                                {Object.entries(stat.by_task_type).map(([taskType, taskData]) => (
                                  <div key={taskType} className="flex items-center justify-between p-2 bg-gray-50 rounded">
                                    <span className="capitalize">{taskType}</span>
                                    <div className="flex items-center gap-3">
                                      <span className="text-sm text-gray-600">
                                        {taskData.count} tasks
                                      </span>
                                      <span className="font-medium text-blue-600">
                                        {taskData.avg_duration} min avg
                                      </span>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
};

export default HousekeepingMobileEnhancements;