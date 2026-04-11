import React, { memo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { TabsContent } from '@/components/ui/tabs';
import { LogOut, Home, LogIn, Plus, Clock, CheckCircle } from 'lucide-react';

/**
 * Housekeeping main tab content extracted from PMSModule.
 */
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
  toast,
}) => {
  return (
    <TabsContent value="housekeeping" className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Housekeeping Management</h2>
        <div className="space-x-2">
          <Button onClick={() => setOpenDialog('hktask')}>
            <Plus className="w-4 h-4 mr-2" />
            Create Task
          </Button>
          <Button onClick={() => setOpenDialog('roomblock')} variant="outline">
            <Plus className="w-4 h-4 mr-2" />
            Block Room
          </Button>
        </div>
      </div>

      {/* Block Counters */}
      {roomBlocks.length > 0 && (
        <div className="flex gap-4 p-4 bg-gray-50 rounded-lg border">
          <div className="flex items-center gap-2">
            <span className="font-semibold">Room Blocks:</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-red-600 rounded"></div>
            <span className="text-sm">Out of Order: {roomBlocks.filter(b => b.type === 'out_of_order' && b.status === 'active').length}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-orange-500 rounded"></div>
            <span className="text-sm">Out of Service: {roomBlocks.filter(b => b.type === 'out_of_service' && b.status === 'active').length}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-yellow-500 rounded"></div>
            <span className="text-sm">Maintenance: {roomBlocks.filter(b => b.type === 'maintenance' && b.status === 'active').length}</span>
          </div>
        </div>
      )}

      {/* Status Overview */}
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
                <div className="text-xs capitalize font-semibold">{status.replace('_', ' ')}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Due Out / Stayover / Arrivals Lists */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Due Out Today */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center">
              <LogOut className="w-5 h-5 mr-2 text-red-600" />
              Due Out ({dueOutRooms.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 max-h-96 overflow-y-auto">
            {dueOutRooms.length === 0 ? (
              <div className="text-center text-gray-400 py-4">No departures</div>
            ) : (
              dueOutRooms.map((room, idx) => (
                <div key={idx} className={`p-3 rounded border ${room.is_today ? 'bg-red-50 border-red-200' : 'bg-orange-50 border-orange-200'}`}>
                  <div className="font-bold">Room {room.room_number}</div>
                  <div className="text-sm text-gray-600">{room.guest_name}</div>
                  <div className="text-xs text-gray-500">
                    {new Date(room.checkout_date).toLocaleDateString()}
                    {room.is_today && <span className="ml-2 text-red-600 font-semibold">TODAY</span>}
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Stayovers */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center">
              <Home className="w-5 h-5 mr-2 text-blue-600" />
              Stayovers ({stayoverRooms.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 max-h-96 overflow-y-auto">
            {stayoverRooms.length === 0 ? (
              <div className="text-center text-gray-400 py-4">No stayovers</div>
            ) : (
              stayoverRooms.map((room, idx) => (
                <div key={idx} className="p-3 rounded border bg-blue-50 border-blue-200">
                  <div className="font-bold">Room {room.room_number}</div>
                  <div className="text-sm text-gray-600">{room.guest_name}</div>
                  <div className="text-xs text-gray-500">
                    {room.nights_remaining} night(s) remaining
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Arrivals */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center">
              <LogIn className="w-5 h-5 mr-2 text-green-600" />
              Arrivals ({arrivalRooms.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 max-h-96 overflow-y-auto">
            {arrivalRooms.length === 0 ? (
              <div className="text-center text-gray-400 py-4">No arrivals</div>
            ) : (
              arrivalRooms.map((room, idx) => (
                <div key={idx} className={`p-3 rounded border ${
                  room.ready ? 'bg-green-50 border-green-200' : 'bg-yellow-50 border-yellow-200'
                }`}>
                  <div className="font-bold">Room {room.room_number}</div>
                  <div className="text-sm text-gray-600">{room.guest_name}</div>
                  <div className="text-xs flex items-center justify-between">
                    <span className={room.ready ? 'text-green-600 font-semibold' : 'text-yellow-600'}>
                      {room.ready ? '✓ Ready' : `⚠ ${room.room_status}`}
                    </span>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      {/* Room Status Board */}
      {roomStatusBoard && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>Room Status Board</span>
              {/* Legend removed for brevity in extracted component */}
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
                  occupied: 'bg-purple-100 border-purple-300',
                };

                return (
                  <Card
                    key={room.id}
                    className={`cursor-pointer hover:shadow-lg transition-shadow relative ${
                      statusColors[room.status] || 'bg-gray-100 border-gray-300'
                    }`}
                  >
                    <CardContent className="p-3">
                      <div className="font-bold text-lg">{room.room_number}</div>
                      <div className="text-xs capitalize">{room.room_type}</div>
                      <div className="text-xs font-semibold mt-1 capitalize">{room.status.replace('_', ' ')}</div>
                      {roomBlock && (
                        <div className="text-[10px] text-gray-600 mt-1 truncate" title={roomBlock.reason}>
                          {roomBlock.reason}
                        </div>
                      )}
                      <div className="flex gap-1 mt-2">
                        {room.status === 'dirty' && (
                          <Button
                            size="sm"
                            variant="outline"
                            className={`h-6 text-xs ${
                              needsCleaning ? 'bg-red-50 border-red-400 text-red-700 hover:bg-red-100' : ''
                            }`}
                            onClick={() => quickUpdateRoomStatus(room.id, 'cleaning')}
                          >
                            Clean {needsCleaning && '⚡'}
                          </Button>
                        )}
                        {room.status === 'cleaning' && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-6 text-xs"
                            onClick={() => quickUpdateRoomStatus(room.id, 'inspected')}
                          >
                            Done
                          </Button>
                        )}
                        {room.status === 'inspected' && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-6 text-xs"
                            onClick={() => quickUpdateRoomStatus(room.id, 'available')}
                          >
                            Ready
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-6 text-[10px] ml-auto"
                          onClick={(e) => {
                            e.stopPropagation();
                            setMaintenanceForm({
                              room_id: room.id,
                              room_number: room.room_number,
                              issue_type: 'housekeeping_damage',
                              priority: 'normal',
                              description: '',
                            });
                            setMaintenanceDialogOpen(true);
                          }}
                        >
                          MNT
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Task Priority Filter & Stats */}
      <div className="grid grid-cols-4 gap-4">
        <Card className="cursor-pointer hover:shadow-lg transition" onClick={() => toast.info('Showing all tasks')}>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-gray-700">{housekeepingTasks.length}</div>
            <div className="text-xs text-gray-600">Total Tasks</div>
          </CardContent>
        </Card>
        <Card className="cursor-pointer hover:shadow-lg transition border-red-200">
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-red-600">
              {housekeepingTasks.filter(t => t.priority === 'high').length}
            </div>
            <div className="text-xs text-gray-600">High Priority</div>
          </CardContent>
        </Card>
        <Card className="cursor-pointer hover:shadow-lg transition border-yellow-200">
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-yellow-600">
              {housekeepingTasks.filter(t => t.status === 'in_progress').length}
            </div>
            <div className="text-xs text-gray-600">In Progress</div>
          </CardContent>
        </Card>
        <Card className="cursor-pointer hover:shadow-lg transition border-green-200">
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-green-600">
              {housekeepingTasks.filter(t => t.status === 'completed').length}
            </div>
            <div className="text-xs text-gray-600">Completed Today</div>
          </CardContent>
        </Card>
      </div>

      {/* Task list */}
      <div className="space-y-4">
        {housekeepingTasks.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            No housekeeping tasks
          </div>
        ) : (
          housekeepingTasks
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
                        <div className="font-bold text-lg">Room {task.room?.room_number}</div>
                        <Badge
                          variant={
                            task.priority === 'high'
                              ? 'destructive'
                              : task.priority === 'medium'
                              ? 'default'
                              : 'outline'
                          }
                        >
                          {task.priority?.toUpperCase()} PRIORITY
                        </Badge>
                        <Badge variant="outline" className="text-xs">
                          {task.task_type}
                        </Badge>
                      </div>
                      <div className="text-sm text-gray-600 capitalize mb-1">
                        Assigned to: {task.assigned_to || 'Unassigned'}
                      </div>
                      {task.notes && (
                        <div className="text-sm text-gray-500 bg-gray-50 p-2 rounded mt-2">
                          💬 {task.notes}
                        </div>
                      )}
                      {task.estimated_duration && (
                        <div className="text-xs text-gray-500 mt-2">
                          ⏱️ Estimated: {task.estimated_duration} minutes
                        </div>
                      )}
                    </div>
                    <div className="space-x-2 flex items-center gap-2">
                      {task.status === 'pending' && (
                        <Button size="sm" onClick={() => handleUpdateHKTask(task.id, 'in_progress')}>
                          <Clock className="w-4 h-4 mr-2" />
                          Start
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
                          Complete
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
                          ? '✅ Done'
                          : task.status === 'in_progress'
                          ? '🔄 Working'
                          : '⏸️ Pending'}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))
        )}
      </div>
    </TabsContent>
  );
};

export default memo(HousekeepingTab);
