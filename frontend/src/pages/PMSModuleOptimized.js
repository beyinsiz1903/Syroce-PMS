import { useState, useMemo } from 'react';
import Layout from '@/components/Layout';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import VirtualizedBookingList from '@/components/VirtualizedBookingList';
import { DashboardLoadingSkeleton, TableLoadingSkeleton } from '@/utils/lazyLoad';
import { 
  useRooms, 
  useGuests, 
  useBookings, 
  useFrontDeskData,
  useHousekeepingTasks 
} from '@/hooks/usePMSData';
import { debounce } from '@/utils/performanceUtils';
import { 
  Bed, Users, Calendar, Home, ClipboardList, 
  BarChart3, Plus, Search, Filter, RefreshCw 
} from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

const PMSModuleOptimized = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('frontdesk');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedBooking, setSelectedBooking] = useState(null);

  // Fetch data with React Query
  const { data: rooms = [], isLoading: roomsLoading } = useRooms();
  const { data: guests = [], isLoading: guestsLoading } = useGuests({ limit: 100 });
  const { data: bookings = [], isLoading: bookingsLoading } = useBookings({ limit: 500 });
  
  // Front desk data (only loaded when needed)
  const { arrivals, departures, inhouse } = useFrontDeskData();
  
  // Housekeeping data (only loaded when tab is active)
  const { data: housekeepingTasks = [], isLoading: tasksLoading } = useHousekeepingTasks(
    activeTab === 'housekeeping' ? {} : undefined
  );

  // Debounced search
  const debouncedSearch = useMemo(
    () => debounce((query) => {
      console.log('Searching for:', query);
      // Implement search logic
    }, 300),
    []
  );

  const handleSearch = (e) => {
    const query = e.target.value;
    setSearchQuery(query);
    debouncedSearch(query);
  };

  // Filter bookings based on search
  const filteredBookings = useMemo(() => {
    if (!searchQuery) return bookings;
    
    const query = searchQuery.toLowerCase();
    return bookings.filter(booking => 
      booking.guest_name?.toLowerCase().includes(query) ||
      booking.room_number?.toLowerCase().includes(query) ||
      booking.id?.toLowerCase().includes(query)
    );
  }, [bookings, searchQuery]);

  // Statistics
  const stats = useMemo(() => {
    const totalRooms = rooms.length;
    const occupiedRooms = bookings.filter(b => b.status === 'checked_in').length;
    const cleanRooms = rooms.filter(r => r.status === 'clean').length;
    const dirtyRooms = rooms.filter(r => r.status === 'dirty').length;

    return {
      totalRooms,
      occupiedRooms,
      availableRooms: totalRooms - occupiedRooms,
      occupancyRate: totalRooms > 0 ? ((occupiedRooms / totalRooms) * 100).toFixed(1) : 0,
      cleanRooms,
      dirtyRooms,
      totalGuests: guests.length,
      totalBookings: bookings.length,
    };
  }, [rooms, bookings, guests]);

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="pms">
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Property Management System</h1>
            <p className="text-gray-600">Manage rooms, bookings, guests and operations</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm">
              <Plus className="w-4 h-4 mr-2" />
              New Booking
            </Button>
            <Button variant="outline" size="sm">
              <Filter className="w-4 h-4 mr-2" />
              Filters
            </Button>
          </div>
        </div>

        {/* Quick Stats */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Bed className="w-4 h-4" />
                Occupancy
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.occupancyRate}%</div>
              <p className="text-xs text-gray-600">
                {stats.occupiedRooms} / {stats.totalRooms} rooms
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Calendar className="w-4 h-4" />
                Today's Arrivals
              </CardTitle>
            </CardHeader>
            <CardContent>
              {arrivals.isLoading ? (
                <div className="h-8 bg-gray-200 rounded animate-pulse"></div>
              ) : (
                <>
                  <div className="text-2xl font-bold">{arrivals.data?.length || 0}</div>
                  <p className="text-xs text-gray-600">Expected check-ins</p>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Users className="w-4 h-4" />
                In-House Guests
              </CardTitle>
            </CardHeader>
            <CardContent>
              {inhouse.isLoading ? (
                <div className="h-8 bg-gray-200 rounded animate-pulse"></div>
              ) : (
                <>
                  <div className="text-2xl font-bold">{inhouse.data?.length || 0}</div>
                  <p className="text-xs text-gray-600">Currently staying</p>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Home className="w-4 h-4" />
                Room Status
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex gap-2 text-sm">
                <Badge variant="outline" className="bg-green-50">
                  {stats.cleanRooms} Clean
                </Badge>
                <Badge variant="outline" className="bg-orange-50">
                  {stats.dirtyRooms} Dirty
                </Badge>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Search Bar */}
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
            <Input
              placeholder="Search bookings, guests, rooms..."
              value={searchQuery}
              onChange={handleSearch}
              className="pl-10"
            />
          </div>
        </div>

        {/* Main Content Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
          <TabsList className="grid grid-cols-5 w-full max-w-3xl">
            <TabsTrigger value="frontdesk">
              <Calendar className="w-4 h-4 mr-2" />
              Front Desk
            </TabsTrigger>
            <TabsTrigger value="rooms">
              <Bed className="w-4 h-4 mr-2" />
              Rooms
            </TabsTrigger>
            <TabsTrigger value="guests">
              <Users className="w-4 h-4 mr-2" />
              Guests
            </TabsTrigger>
            <TabsTrigger value="housekeeping">
              <ClipboardList className="w-4 h-4 mr-2" />
              Housekeeping
            </TabsTrigger>
            <TabsTrigger value="reports">
              <BarChart3 className="w-4 h-4 mr-2" />
              Reports
            </TabsTrigger>
          </TabsList>

          {/* Front Desk Tab */}
          <TabsContent value="frontdesk" className="space-y-4">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Arrivals */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center justify-between">
                    <span>Arrivals</span>
                    <Badge>{arrivals.data?.length || 0}</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {arrivals.isLoading ? (
                    <TableLoadingSkeleton rows={3} cols={2} />
                  ) : arrivals.data?.length > 0 ? (
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {arrivals.data.map((booking, idx) => (
                        <div key={idx} className="p-2 bg-blue-50 rounded text-sm">
                          <div className="font-medium">{booking.guest_name}</div>
                          <div className="text-xs text-gray-600">
                            Room {booking.room_number} • {booking.adults} guests
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-gray-500 text-center py-4">No arrivals today</p>
                  )}
                </CardContent>
              </Card>

              {/* Departures */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center justify-between">
                    <span>Departures</span>
                    <Badge>{departures.data?.length || 0}</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {departures.isLoading ? (
                    <TableLoadingSkeleton rows={3} cols={2} />
                  ) : departures.data?.length > 0 ? (
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {departures.data.map((booking, idx) => (
                        <div key={idx} className="p-2 bg-orange-50 rounded text-sm">
                          <div className="font-medium">{booking.guest_name}</div>
                          <div className="text-xs text-gray-600">
                            Room {booking.room_number} • Check-out
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-gray-500 text-center py-4">No departures today</p>
                  )}
                </CardContent>
              </Card>

              {/* In-House */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center justify-between">
                    <span>In-House</span>
                    <Badge>{inhouse.data?.length || 0}</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {inhouse.isLoading ? (
                    <TableLoadingSkeleton rows={3} cols={2} />
                  ) : inhouse.data?.length > 0 ? (
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {inhouse.data.slice(0, 10).map((booking, idx) => (
                        <div key={idx} className="p-2 bg-green-50 rounded text-sm">
                          <div className="font-medium">{booking.guest_name}</div>
                          <div className="text-xs text-gray-600">
                            Room {booking.room_number}
                          </div>
                        </div>
                      ))}
                      {inhouse.data.length > 10 && (
                        <div className="text-xs text-center text-gray-500 pt-2">
                          +{inhouse.data.length - 10} more guests
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-gray-500 text-center py-4">No guests in-house</p>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Rooms Tab */}
          <TabsContent value="rooms">
            <Card>
              <CardHeader>
                <CardTitle>All Rooms ({rooms.length})</CardTitle>
              </CardHeader>
              <CardContent>
                {roomsLoading ? (
                  <DashboardLoadingSkeleton />
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                    {rooms.map((room) => (
                      <Card key={room._id} className="hover:shadow-lg transition-shadow">
                        <CardContent className="pt-6">
                          <div className="text-center">
                            <div className="text-2xl font-bold mb-2">{room.room_number}</div>
                            <Badge className={
                              room.status === 'clean' ? 'bg-green-100 text-green-800' :
                              room.status === 'dirty' ? 'bg-orange-100 text-orange-800' :
                              'bg-gray-100 text-gray-800'
                            }>
                              {room.status}
                            </Badge>
                            <div className="mt-2 text-sm text-gray-600">
                              {room.room_type} • Floor {room.floor}
                            </div>
                            <div className="mt-1 text-sm font-medium">
                              ${room.base_price}/night
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Guests Tab */}
          <TabsContent value="guests">
            <Card>
              <CardHeader>
                <CardTitle>All Guests ({guests.length})</CardTitle>
              </CardHeader>
              <CardContent>
                {guestsLoading ? (
                  <TableLoadingSkeleton rows={10} cols={4} />
                ) : (
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Email</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Phone</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tags</th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-200">
                        {guests.slice(0, 50).map((guest) => (
                          <tr key={guest._id} className="hover:bg-gray-50">
                            <td className="px-6 py-4 whitespace-nowrap">{guest.name}</td>
                            <td className="px-6 py-4 whitespace-nowrap">{guest.email}</td>
                            <td className="px-6 py-4 whitespace-nowrap">{guest.phone || '-'}</td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              {guest.tags?.length > 0 ? (
                                <div className="flex gap-1">
                                  {guest.tags.map((tag, idx) => (
                                    <Badge key={idx} variant="outline">{tag}</Badge>
                                  ))}
                                </div>
                              ) : '-'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Housekeeping Tab */}
          <TabsContent value="housekeeping">
            <Card>
              <CardHeader>
                <CardTitle>Housekeeping Tasks</CardTitle>
              </CardHeader>
              <CardContent>
                {tasksLoading ? (
                  <TableLoadingSkeleton rows={5} cols={4} />
                ) : housekeepingTasks.length > 0 ? (
                  <div className="space-y-2">
                    {housekeepingTasks.map((task, idx) => (
                      <div key={idx} className="p-3 border rounded hover:bg-gray-50">
                        <div className="flex justify-between items-start">
                          <div>
                            <div className="font-medium">Room {task.room_number}</div>
                            <div className="text-sm text-gray-600">{task.task_type}</div>
                          </div>
                          <Badge>{task.status}</Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-gray-500 text-center py-8">No housekeeping tasks</p>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Reports Tab */}
          <TabsContent value="reports">
            <Card>
              <CardHeader>
                <CardTitle>All Bookings ({filteredBookings.length})</CardTitle>
              </CardHeader>
              <CardContent>
                {bookingsLoading ? (
                  <TableLoadingSkeleton rows={10} cols={5} />
                ) : filteredBookings.length > 0 ? (
                  <VirtualizedBookingList
                    bookings={filteredBookings}
                    onSelectBooking={setSelectedBooking}
                    height={600}
                  />
                ) : (
                  <p className="text-gray-500 text-center py-8">No bookings found</p>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
};

export default PMSModuleOptimized;
