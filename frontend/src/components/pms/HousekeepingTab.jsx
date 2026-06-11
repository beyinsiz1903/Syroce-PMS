import React, { memo, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { TabsContent } from '@/components/ui/tabs';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { LogOut, Home, LogIn, Plus, Clock, CheckCircle, UserPlus, Bed, ListChecks, Wrench, MoreVertical, X } from 'lucide-react';
import HousekeepingRoomGrid from '@/components/pms/HousekeepingRoomGrid';

const AssignPopover = ({ task, staffOptions, currentUserId, currentUserName, onAssign, tc }) => {
  const [open, setOpen] = useState(false);
  const submit = (userId) => {
    if (!userId) return;
    onAssign(task.id, userId);
    setOpen(false);
  };
  const isAssigned = task.assigned_to && task.assigned_to.toLowerCase() !== 'unassigned';
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button size="sm" variant="outline" className="border-blue-300 text-blue-700 hover:bg-blue-50">
          <UserPlus className="w-4 h-4 mr-1" />
          {isAssigned ? tc('change') : tc('assign')}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-2 space-y-1" align="end">
        {currentUserId && currentUserName && (
          <Button size="sm" variant="ghost" className="w-full justify-start" onClick={() => submit(currentUserId)}>
            {tc('assignSelf')} ({currentUserName})
          </Button>
        )}
        <div className="border-t pt-1 mt-1">
          <div className="text-xs text-gray-500 px-2 py-1">{tc('availableStaff')}</div>
          {staffOptions.length === 0 ? (
            <div className="text-xs text-gray-400 px-2 py-1">{tc('noStaff')}</div>
          ) : (
            staffOptions.map((s) => (
              <Button key={s.id} size="sm" variant="ghost" className="w-full justify-start" onClick={() => submit(s.id)}>
                {s.name}
              </Button>
            ))
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
};

const HousekeepingTab = ({
  roomBlocks,
  roomStatusBoard,
  dueOutRooms,
  stayoverRooms,
  arrivalRooms,
  housekeepingTasks,
  quickUpdateRoomStatus,
  setOpenDialog,
  setSelectedRoom,
  setNewBooking,
  setMaintenanceForm,
  setMaintenanceDialogOpen,
  handleUpdateHKTask,
  handleAssignHKTask,
  currentUserName,
  currentUserId,
  onBookingCardClick,
  toast,
  loading,
  loadHousekeepingData,
}) => {
  const { t } = useTranslation();
  const tc = (k) => t(`pmsComponents.housekeeping.${k}`);
  const [view, setView] = useState('operations');
  const [taskFilter, setTaskFilter] = useState('all'); // 'all' | 'unassigned' | <assignee value>

  // Relational staff source: active tenant users (real user ids), not the
  // legacy free-text names derived from prior tasks.
  const [staffOptions, setStaffOptions] = useState([]);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await axios.get('/hr/staff', { params: { source: 'users' } });
        const rows = (res.data?.staff || [])
          .filter((s) => s.id && s.name)
          .map((s) => ({ id: s.id, name: s.name }));
        const seen = new Set();
        const unique = rows.filter((r) => (seen.has(r.id) ? false : seen.add(r.id)));
        unique.sort((a, b) => a.name.localeCompare(b.name));
        if (!cancelled) setStaffOptions(unique);
      } catch {
        if (!cancelled) setStaffOptions([]);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Translated room-status label with a readable fallback (never raw enum).
  const statusLabel = (status) => {
    if (!status) return '';
    const key = `statusLabels.${status}`;
    const translated = t(`pmsComponents.housekeeping.${key}`);
    if (translated && translated !== `pmsComponents.housekeeping.${key}`) return translated;
    return String(status).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  };

  // Assignee options for the task filter — derived from actually-assigned tasks
  // (keyed by relational user id when present, falling back to the name).
  const assigneeFilterOptions = useMemo(() => {
    const map = new Map();
    (housekeepingTasks || []).forEach((tk) => {
      const name = (tk.assigned_to || '').trim();
      if (name && name.toLowerCase() !== 'unassigned') {
        const value = tk.assigned_to_user_id || name;
        if (!map.has(value)) map.set(value, name);
      }
    });
    return Array.from(map, ([value, label]) => ({ value, label }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [housekeepingTasks]);

  const filteredTasks = useMemo(() => {
    const list = housekeepingTasks || [];
    if (taskFilter === 'all') return list;
    if (taskFilter === 'unassigned') {
      return list.filter((tk) => {
        const name = (tk.assigned_to || '').trim();
        return !name || name.toLowerCase() === 'unassigned';
      });
    }
    return list.filter((tk) => {
      const name = (tk.assigned_to || '').trim();
      const value = tk.assigned_to_user_id || name;
      return value === taskFilter;
    });
  }, [housekeepingTasks, taskFilter]);

  if (loading) {
    return (
      <TabsContent value="housekeeping" className="space-y-6">
        <div className="flex items-center justify-center py-16">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mr-3" />
          <span className="text-gray-500">{tc('loading')}</span>
        </div>
      </TabsContent>
    );
  }

  return (
    <TabsContent value="housekeeping" className="space-y-6">
      <div className="flex justify-between items-center flex-wrap gap-3">
        <h2 className="text-2xl font-bold">{tc('title')}</h2>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="inline-flex rounded-lg border bg-white p-0.5" data-testid="hk-view-toggle">
            <button
              type="button"
              onClick={() => setView('operations')}
              className={`px-3 py-1.5 text-sm font-medium rounded-md transition flex items-center gap-1.5 ${
                view === 'operations' ? 'bg-blue-600 text-white shadow-sm' : 'text-gray-600 hover:text-gray-900'
              }`}
              data-testid="hk-view-operations"
            >
              <ListChecks className="w-4 h-4" />
              {tc('viewOperations')}
            </button>
            <button
              type="button"
              onClick={() => setView('rooms')}
              className={`px-3 py-1.5 text-sm font-medium rounded-md transition flex items-center gap-1.5 ${
                view === 'rooms' ? 'bg-blue-600 text-white shadow-sm' : 'text-gray-600 hover:text-gray-900'
              }`}
              data-testid="hk-view-rooms"
            >
              <Bed className="w-4 h-4" />
              {tc('viewRooms')}
            </button>
          </div>
          {view === 'operations' && (
            <>
              <Button onClick={() => setOpenDialog('hktask')}>
                <Plus className="w-4 h-4 mr-2" />
                {tc('createTask')}
              </Button>
              <Button onClick={() => setOpenDialog('roomblock')} variant="outline">
                <Plus className="w-4 h-4 mr-2" />
                {tc('roomBlock')}
              </Button>
            </>
          )}
        </div>
      </div>

      {view === 'rooms' ? (
        <HousekeepingRoomGrid embedded={true} onChange={loadHousekeepingData} />
      ) : (
      <>
      {roomBlocks.length > 0 && (
        <div className="flex gap-4 p-4 bg-gray-50 rounded-lg border">
          <div className="flex items-center gap-2">
            <span className="font-semibold">{tc('roomBlocks')}:</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-red-600 rounded"></div>
            <span className="text-sm">{tc('outOfOrder')}: {roomBlocks.filter(b => b.type === 'out_of_order' && b.status === 'active').length}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-amber-500 rounded"></div>
            <span className="text-sm">{tc('outOfService')}: {roomBlocks.filter(b => b.type === 'out_of_service' && b.status === 'active').length}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-yellow-500 rounded"></div>
            <span className="text-sm">{tc('maintenance')}: {roomBlocks.filter(b => b.type === 'maintenance' && b.status === 'active').length}</span>
          </div>
        </div>
      )}

      {roomStatusBoard && (
        <div className="grid grid-cols-3 md:grid-cols-7 gap-4">
          {Object.entries(roomStatusBoard.status_counts).map(([status, count]) => (
            <Card key={status} className={`border-2 ${
              status === 'dirty' ? 'border-red-200 bg-red-50' :
              status === 'cleaning' ? 'border-yellow-200 bg-yellow-50' :
              status === 'inspected' ? 'border-green-200 bg-green-50' :
              status === 'available' ? 'border-blue-200 bg-blue-50' :
              'border-gray-200'
            }`}>
              <CardContent className="pt-4">
                <div className="text-3xl font-bold">{count}</div>
                <div className="text-xs font-semibold">{statusLabel(status)}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center">
              <LogOut className="w-5 h-5 mr-2 text-red-600" />
              {tc('dueOut')} ({dueOutRooms.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 max-h-96 overflow-y-auto">
            {dueOutRooms.length === 0 ? (
              <div className="text-center text-gray-400 py-4">{tc('noDueOut')}</div>
            ) : (
              dueOutRooms.map((room, idx) => (
                <div
                  key={idx}
                  role="button"
                  tabIndex={0}
                  onClick={() => onBookingCardClick && room.booking_id && onBookingCardClick(room.booking_id)}
                  onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && onBookingCardClick && room.booking_id) onBookingCardClick(room.booking_id); }}
                  className={`p-3 rounded border cursor-pointer transition hover:shadow-md hover:scale-[1.01] ${room.is_today ? 'bg-red-50 border-red-200 hover:bg-red-100' : 'bg-amber-50 border-amber-200 hover:bg-amber-100'}`}
                >
                  <div className="font-bold">{tc('roomPrefix')} {room.room_number}</div>
                  <div className="text-sm text-gray-600">{room.guest_name}</div>
                  <div className="text-xs text-gray-500">
                    {new Date(room.checkout_date).toLocaleDateString()}
                    {room.is_today && <span className="ml-2 text-red-600 font-semibold">{tc('today')}</span>}
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center">
              <Home className="w-5 h-5 mr-2 text-blue-600" />
              {tc('stayover')} ({stayoverRooms.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 max-h-96 overflow-y-auto">
            {stayoverRooms.length === 0 ? (
              <div className="text-center text-gray-400 py-4">{tc('noStayover')}</div>
            ) : (
              stayoverRooms.map((room, idx) => (
                <div
                  key={idx}
                  role="button"
                  tabIndex={0}
                  onClick={() => onBookingCardClick && room.booking_id && onBookingCardClick(room.booking_id)}
                  onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && onBookingCardClick && room.booking_id) onBookingCardClick(room.booking_id); }}
                  className="p-3 rounded border bg-blue-50 border-blue-200 cursor-pointer transition hover:shadow-md hover:scale-[1.01] hover:bg-blue-100"
                >
                  <div className="font-bold">{tc('roomPrefix')} {room.room_number}</div>
                  <div className="text-sm text-gray-600">{room.guest_name}</div>
                  <div className="text-xs text-gray-500">
                    {room.nights_remaining} {tc('nightsLeft')}
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center">
              <LogIn className="w-5 h-5 mr-2 text-green-600" />
              {tc('arrivals')} ({arrivalRooms.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 max-h-96 overflow-y-auto">
            {arrivalRooms.length === 0 ? (
              <div className="text-center text-gray-400 py-4">{tc('noArrivals')}</div>
            ) : (
              arrivalRooms.map((room, idx) => (
                <div
                  key={idx}
                  role="button"
                  tabIndex={0}
                  onClick={() => onBookingCardClick && room.booking_id && onBookingCardClick(room.booking_id)}
                  onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && onBookingCardClick && room.booking_id) onBookingCardClick(room.booking_id); }}
                  className={`p-3 rounded border cursor-pointer transition hover:shadow-md hover:scale-[1.01] ${
                    room.ready ? 'bg-green-50 border-green-200 hover:bg-green-100' : 'bg-yellow-50 border-yellow-200 hover:bg-yellow-100'
                  }`}
                >
                  <div className="font-bold">{tc('roomPrefix')} {room.room_number}</div>
                  <div className="text-sm text-gray-600">{room.guest_name}</div>
                  <div className="text-xs flex items-center justify-between">
                    <span className={room.ready ? 'text-green-600 font-semibold' : 'text-yellow-600'}>
                      {room.ready ? `${tc('ready')}` : statusLabel(room.room_status)}
                    </span>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      {roomStatusBoard && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>{tc('roomStatusBoard')}</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
              {roomStatusBoard.rooms.map((room) => {
                const roomBlock = roomBlocks.find(b => b.room_id === room.id && b.status === 'active');
                const isDueOutToday = dueOutRooms.some(r => r.room_number === room.room_number && r.is_today);
                const isArrivalToday = arrivalRooms.some(r => r.room_number === room.room_number && r.ready === false);
                const needsCleaning = room.status === 'dirty' && (isDueOutToday || isArrivalToday);

                const statusColors = {
                  dirty: 'bg-red-100 border-red-300',
                  cleaning: 'bg-yellow-100 border-yellow-300',
                  inspected: 'bg-green-100 border-green-300',
                  available: 'bg-green-100 border-green-300',
                  occupied: 'bg-indigo-100 border-indigo-300',
                };

                const openReportFault = () => {
                  setMaintenanceForm({
                    room_id: room.id,
                    room_number: room.room_number,
                    issue_type: 'housekeeping_damage',
                    priority: 'normal',
                    description: '',
                  });
                  setMaintenanceDialogOpen(true);
                };

                return (
                  <Card
                    key={room.id}
                    className={`hover:shadow-lg transition-shadow relative ${
                      statusColors[room.status] || 'bg-gray-100 border-gray-300'
                    }`}
                  >
                    {roomBlock && (
                      <span
                        className="absolute top-1.5 right-1.5 text-red-600"
                        title={roomBlock.reason || tc('maintenance')}
                      >
                        <Wrench className="w-4 h-4" />
                      </span>
                    )}
                    <CardContent className="p-3">
                      <div className="font-bold text-lg">{room.room_number}</div>
                      <div className="text-xs capitalize">{room.room_type}</div>
                      <div className="text-xs font-semibold mt-1">{statusLabel(room.status)}</div>
                      {roomBlock && (
                        <div className="text-[10px] text-gray-600 mt-1 truncate" title={roomBlock.reason}>
                          {roomBlock.reason}
                        </div>
                      )}
                      <div className="flex gap-1 mt-2 items-center">
                        {room.status === 'dirty' && (
                          <Button
                            size="sm"
                            variant="outline"
                            className={`h-6 text-xs ${
                              needsCleaning ? 'bg-red-50 border-red-400 text-red-700 hover:bg-red-100' : ''
                            }`}
                            onClick={() => quickUpdateRoomStatus(room.id, 'cleaning')}
                          >
                            {tc('clean')}
                          </Button>
                        )}
                        {room.status === 'cleaning' && (
                          <Button size="sm" variant="outline" className="h-6 text-xs"
                            onClick={() => quickUpdateRoomStatus(room.id, 'inspected')}>
                            {tc('done')}
                          </Button>
                        )}
                        {room.status === 'inspected' && (
                          <Button size="sm" variant="outline" className="h-6 text-xs"
                            onClick={() => quickUpdateRoomStatus(room.id, 'available')}>
                            {tc('ready')}
                          </Button>
                        )}
                        <Popover>
                          <PopoverTrigger asChild>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-6 w-6 p-0 ml-auto"
                              aria-label={tc('roomActions')}
                            >
                              <MoreVertical className="w-4 h-4" />
                            </Button>
                          </PopoverTrigger>
                          <PopoverContent className="w-44 p-1" align="end">
                            <Button
                              size="sm"
                              variant="ghost"
                              className="w-full justify-start text-red-700 hover:bg-red-50"
                              onClick={openReportFault}
                            >
                              <Wrench className="w-4 h-4 mr-2" />
                              {tc('reportFault')}
                            </Button>
                          </PopoverContent>
                        </Popover>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-4 gap-4">
        <Card title={tc('allTasks')}>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-gray-700">{housekeepingTasks.length}</div>
            <div className="text-xs text-gray-600">{tc('totalTasks')}</div>
          </CardContent>
        </Card>
        <Card className="cursor-pointer hover:shadow-lg transition border-red-200">
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-red-600">
              {housekeepingTasks.filter(t => t.priority === 'high').length}
            </div>
            <div className="text-xs text-gray-600">{tc('highPriority')}</div>
          </CardContent>
        </Card>
        <Card className="cursor-pointer hover:shadow-lg transition border-yellow-200">
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-yellow-600">
              {housekeepingTasks.filter(t => t.status === 'in_progress').length}
            </div>
            <div className="text-xs text-gray-600">{tc('inProgress')}</div>
          </CardContent>
        </Card>
        <Card className="cursor-pointer hover:shadow-lg transition border-green-200">
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-green-600">
              {housekeepingTasks.filter(t => t.status === 'completed').length}
            </div>
            <div className="text-xs text-gray-600">{tc('completedToday')}</div>
          </CardContent>
        </Card>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-medium text-gray-600">{tc('filterLabel')}:</span>
        <Select value={taskFilter} onValueChange={setTaskFilter}>
          <SelectTrigger className="w-56 h-9" data-testid="hk-task-filter">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{tc('filterAll')}</SelectItem>
            <SelectItem value="unassigned">{tc('filterUnassigned')}</SelectItem>
            {assigneeFilterOptions.map((o) => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {taskFilter !== 'all' && (
          <Button size="sm" variant="ghost" className="h-9" onClick={() => setTaskFilter('all')}>
            <X className="w-4 h-4 mr-1" />
            {tc('clearFilter')}
          </Button>
        )}
      </div>

      <div className="space-y-4">
        {housekeepingTasks.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            {tc('noTasks')}
          </div>
        ) : filteredTasks.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            {tc('noMatchingTasks')}
          </div>
        ) : (
          filteredTasks
            .slice()
            .sort((a, b) => {
              const priorityOrder = { high: 0, medium: 1, low: 2 };
              const statusOrder = { pending: 0, in_progress: 1, completed: 2 };
              const pDiff = (priorityOrder[a.priority] || 1) - (priorityOrder[b.priority] || 1);
              if (pDiff !== 0) return pDiff;
              return (statusOrder[a.status] || 0) - (statusOrder[b.status] || 0);
            })
            .map((task) => (
              <Card
                key={task.id}
                className={`${
                  task.priority === 'high'
                    ? 'border-l-4 border-l-red-500'
                    : task.priority === 'medium'
                    ? 'border-l-4 border-l-yellow-500'
                    : 'border-l-4 border-l-green-500'
                }`}
              >
                <CardContent className="pt-6">
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="font-bold text-lg">{tc('roomPrefix')} {task.room?.room_number}</div>
                        <Badge
                          variant={
                            task.priority === 'high'
                              ? 'destructive'
                              : task.priority === 'medium'
                              ? 'default'
                              : 'outline'
                          }
                        >
                          {task.priority === 'high' ? tc('high') : task.priority === 'medium' ? tc('medium') : tc('low')} {tc('priority')}
                        </Badge>
                        <Badge variant="outline" className="text-xs">
                          {task.task_type}
                        </Badge>
                      </div>
                      <div className="text-sm text-gray-600 capitalize mb-1">
                        {tc('assignedTo')}: {task.assigned_to || tc('unassigned')}
                      </div>
                      {task.notes && (
                        <div className="text-sm text-gray-500 bg-gray-50 p-2 rounded mt-2">
                          {task.notes}
                        </div>
                      )}
                      {task.estimated_duration && (
                        <div className="text-xs text-gray-500 mt-2">
                          {tc('estimated')}: {task.estimated_duration} {tc('minutes')}
                        </div>
                      )}
                    </div>
                    <div className="space-x-2 flex items-center gap-2">
                      {handleAssignHKTask && task.status !== 'completed' && (
                        <AssignPopover
                          task={task}
                          staffOptions={staffOptions}
                          currentUserId={currentUserId}
                          currentUserName={currentUserName}
                          onAssign={handleAssignHKTask}
                          tc={tc}
                        />
                      )}
                      {task.status === 'pending' && (
                        <Button size="sm" onClick={() => handleUpdateHKTask(task.id, 'in_progress')}>
                          <Clock className="w-4 h-4 mr-2" />
                          {tc('start')}
                        </Button>
                      )}
                      {task.status === 'in_progress' && (
                        <Button
                          size="sm"
                          variant="default"
                          className="bg-green-600"
                          onClick={() => handleUpdateHKTask(task.id, 'completed')}
                        >
                          <CheckCircle className="w-4 h-4 mr-2" />
                          {tc('complete')}
                        </Button>
                      )}
                      <span
                        className={`px-3 py-2 rounded-lg text-sm font-semibold ${
                          task.status === 'completed'
                            ? 'bg-green-100 text-green-700'
                            : task.status === 'in_progress'
                            ? 'bg-blue-100 text-blue-700'
                            : 'bg-gray-100 text-gray-700'
                        }`}
                      >
                        {task.status === 'completed'
                          ? `${tc('completed')}`
                          : task.status === 'in_progress'
                          ? `${tc('ongoing')}`
                          : `${tc('waiting')}`}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))
        )}
      </div>
      </>
      )}
    </TabsContent>
  );
};

export default memo(HousekeepingTab);
