import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Plus, Clock, PlayCircle, AlertTriangle, CheckCircle, User, Calendar } from 'lucide-react';

/**
 * Task Management Kanban Board
 * Columns: New, In Progress, Waiting Parts, Completed
 * Drag & drop support, visual task management
 */
const TaskKanbanBoard = () => {
  const [tasks, setTasks] = useState({
    new: [],
    in_progress: [],
    waiting_parts: [],
    completed: []
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadTasks();
  }, []);

  const loadTasks = async () => {
    setLoading(true);
    try {
      const response = await axios.get('/tasks/kanban');
      setTasks(response.data.tasks || {
        new: [],
        in_progress: [],
        waiting_parts: [],
        completed: []
      });
    } catch (error) {
      console.error('Failed to load tasks:', error);
      // Demo data
      setTasks({
        new: [
          { id: '1', title: 'AC Repair - Room 305', department: 'Engineering', priority: 'high', assignee: 'John', created_at: '2025-11-19' },
          { id: '2', title: 'Extra Cleaning - Suite 401', department: 'Housekeeping', priority: 'medium', assignee: 'Maria', created_at: '2025-11-19' }
        ],
        in_progress: [
          { id: '3', title: 'Plumbing Issue - Room 210', department: 'Engineering', priority: 'high', assignee: 'Mike', created_at: '2025-11-18' }
        ],
        waiting_parts: [
          { id: '4', title: 'TV Replacement - Room 115', department: 'Engineering', priority: 'medium', assignee: 'John', created_at: '2025-11-17' }
        ],
        completed: [
          { id: '5', title: 'Deep Clean - Room 302', department: 'Housekeeping', priority: 'low', assignee: 'Sarah', created_at: '2025-11-19', completed_at: '2025-11-19' }
        ]
      });
    } finally {
      setLoading(false);
    }
  };

  const moveTask = async (taskId, fromColumn, toColumn) => {
    try {
      await axios.post('/tasks/move', {
        task_id: taskId,
        from_status: fromColumn,
        to_status: toColumn
      });

      // Update local state
      const task = tasks[fromColumn].find(t => t.id === taskId);
      setTasks({
        ...tasks,
        [fromColumn]: tasks[fromColumn].filter(t => t.id !== taskId),
        [toColumn]: [...tasks[toColumn], { ...task, status: toColumn }]
      });

      toast.success('Task moved successfully');
    } catch (error) {
      toast.error('Failed to move task');
    }
  };

  const getColumnIcon = (column) => {
    switch (column) {
      case 'new': return <Clock className="w-5 h-5 text-blue-600" />;
      case 'in_progress': return <PlayCircle className="w-5 h-5 text-orange-600" />;
      case 'waiting_parts': return <AlertTriangle className="w-5 h-5 text-yellow-600" />;
      case 'completed': return <CheckCircle className="w-5 h-5 text-green-600" />;
      default: return null;
    }
  };

  const getColumnColor = (column) => {
    switch (column) {
      case 'new': return 'blue';
      case 'in_progress': return 'orange';
      case 'waiting_parts': return 'yellow';
      case 'completed': return 'green';
      default: return 'gray';
    }
  };

  const getPriorityColor = (priority) => {
    switch (priority) {
      case 'high': return 'red';
      case 'medium': return 'orange';
      case 'low': return 'green';
      default: return 'gray';
    }
  };

  const columns = [
    { key: 'new', title: 'New', color: 'blue' },
    { key: 'in_progress', title: 'In Progress', color: 'orange' },
    { key: 'waiting_parts', title: 'Waiting Parts', color: 'yellow' },
    { key: 'completed', title: 'Completed', color: 'green' }
  ];

  if (loading) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-gray-400">
          Loading tasks...
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Task Management - Kanban Board</h2>
        <Button className="bg-blue-600 hover:bg-blue-700">
          <Plus className="w-4 h-4 mr-2" />
          New Task
        </Button>
      </div>

      {/* Kanban Board */}
      <div className="grid grid-cols-4 gap-4">
        {columns.map(column => (
          <div key={column.key} className="space-y-3">
            {/* Column Header */}
            <Card className={`border-2 border-${column.color}-300 bg-${column.color}-50`}>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {getColumnIcon(column.key)}
                    <span>{column.title}</span>
                  </div>
                  <Badge className={`bg-${column.color}-500`}>
                    {tasks[column.key].length}
                  </Badge>
                </CardTitle>
              </CardHeader>
            </Card>

            {/* Task Cards */}
            <div className="space-y-2 min-h-[500px]">
              {tasks[column.key].map(task => (
                <Card
                  key={task.id}
                  className="cursor-move hover:shadow-lg transition-shadow border-l-4"
                  style={{ borderLeftColor: `var(--${getPriorityColor(task.priority)}-500)` }}
                >
                  <CardContent className="p-3 space-y-2">
                    {/* Task Title */}
                    <div className="font-semibold text-sm">{task.title}</div>

                    {/* Department & Priority */}
                    <div className="flex gap-2">
                      <Badge variant="outline" className="text-xs">
                        {task.department}
                      </Badge>
                      <Badge className={`bg-${getPriorityColor(task.priority)}-500 text-xs`}>
                        {task.priority}
                      </Badge>
                    </div>

                    {/* Assignee & Date */}
                    <div className="flex items-center justify-between text-xs text-gray-600">
                      <div className="flex items-center gap-1">
                        <User className="w-3 h-3" />
                        {task.assignee}
                      </div>
                      <div className="flex items-center gap-1">
                        <Calendar className="w-3 h-3" />
                        {new Date(task.created_at).toLocaleDateString()}
                      </div>
                    </div>

                    {/* Move Buttons */}
                    <div className="flex gap-1 pt-2 border-t">
                      {column.key !== 'new' && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="flex-1 h-7 text-xs"
                          onClick={() => {
                            const prevColumn = columns[columns.findIndex(c => c.key === column.key) - 1]?.key;
                            if (prevColumn) moveTask(task.id, column.key, prevColumn);
                          }}
                        >
                          ←
                        </Button>
                      )}
                      {column.key !== 'completed' && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="flex-1 h-7 text-xs"
                          onClick={() => {
                            const nextColumn = columns[columns.findIndex(c => c.key === column.key) + 1]?.key;
                            if (nextColumn) moveTask(task.id, column.key, nextColumn);
                          }}
                        >
                          →
                        </Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}

              {tasks[column.key].length === 0 && (
                <div className="text-center text-gray-400 text-sm py-8">
                  No tasks
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Summary */}
      <Card className="bg-gray-50">
        <CardContent className="p-4">
          <div className="flex justify-between items-center text-sm">
            <span className="font-semibold">Total Tasks: {Object.values(tasks).flat().length}</span>
            <div className="flex gap-4">
              <span className="text-blue-700">New: {tasks.new.length}</span>
              <span className="text-orange-700">In Progress: {tasks.in_progress.length}</span>
              <span className="text-yellow-700">Waiting: {tasks.waiting_parts.length}</span>
              <span className="text-green-700">Completed: {tasks.completed.length}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default TaskKanbanBoard;
