import { useState, useEffect } from 'react';
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useTranslation } from 'react-i18next';
import GuestMessaging from '@/components/GuestMessaging';
import {
  Home,
  Calendar,
  Award,
  Settings,
  LogOut,
  User,
  QrCode,
  Bell,
  Utensils,
  Hotel,
  MapPin,
  Clock,
  Phone,
  Mail,
  Star,
  Sparkles,
  CheckCircle,
  AlertCircle,
  MessageCircle
} from 'lucide-react';

const GuestPortal = ({ user, onLogout }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [activeBookings, setActiveBookings] = useState([]);
  const [pastBookings, setPastBookings] = useState([]);
  const [loyaltyPrograms, setLoyaltyPrograms] = useState([]);
  const [totalPoints, setTotalPoints] = useState(0);
  const [notificationPrefs, setNotificationPrefs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [openDialog, setOpenDialog] = useState(null);
  const [selectedBooking, setSelectedBooking] = useState(null);
  const [cleaningRequests, setCleaningRequests] = useState([]);
  const [cleaningRequestModalOpen, setCleaningRequestModalOpen] = useState(false);
  const [cleaningRequestType, setCleaningRequestType] = useState('regular');
  const [cleaningNotes, setCleaningNotes] = useState('');
  const [roomServices, setRoomServices] = useState({});

  const [roomServiceRequest, setRoomServiceRequest] = useState({
    booking_id: '',
    service_type: 'housekeeping',
    description: '',
    notes: ''
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [bookingsRes, loyaltyRes, prefsRes, cleaningRes] = await Promise.all([
        axios.get('/guest/bookings'),
        axios.get('/guest/loyalty'),
        axios.get('/guest/notification-preferences'),
        axios.get('/guest/my-cleaning-requests').catch(() => ({ data: { requests: [] } }))
      ]);

      setActiveBookings(bookingsRes.data.active_bookings);
      setPastBookings(bookingsRes.data.past_bookings);
      setLoyaltyPrograms(loyaltyRes.data.loyalty_programs);
      setTotalPoints(loyaltyRes.data.total_points);
      setNotificationPrefs(prefsRes.data);
      setCleaningRequests(cleaningRes.data.requests || []);
    } catch (error) {
      toast.error('Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  const handleCleaningRequest = async () => {
    try {
      if (activeBookings.length === 0) {
        toast.error('Aktif rezervasyonunuz bulunmuyor');
        return;
      }

      const response = await axios.post('/guest/request-cleaning', {
        room_number: activeBookings[0].room_number,
        request_type: cleaningRequestType,
        notes: cleaningNotes
      });

      toast.success(response.data.message);
      setCleaningRequestModalOpen(false);
      setCleaningNotes('');
      
      // Reload cleaning requests
      const cleaningRes = await axios.get('/guest/my-cleaning-requests');
      setCleaningRequests(cleaningRes.data.requests || []);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Temizlik talebi gönderilemedi');
    }
  };

  const loadRoomServices = async (bookingId) => {
    try {
      const response = await axios.get(`/guest/room-service/${bookingId}`);
      setRoomServices(prev => ({ ...prev, [bookingId]: response.data }));
    } catch (error) {
      console.error('Failed to load room services');
    }
  };

  const handleRoomServiceRequest = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/guest/room-service', roomServiceRequest);
      toast.success('Room service request submitted');
      setOpenDialog(null);
      loadRoomServices(roomServiceRequest.booking_id);
      setRoomServiceRequest({ booking_id: '', service_type: 'housekeeping', description: '', notes: '' });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to submit request');
    }
  };

  const updateNotificationPref = async (key, value) => {
    try {
      await axios.put('/guest/notification-preferences', { [key]: value });
      setNotificationPrefs(prev => ({ ...prev, [key]: value }));
      toast.success('Preference updated');
    } catch (error) {
      toast.error('Failed to update preference');
    }
  };

  const getTierColor = (tier) => {
    switch(tier) {
      case 'platinum': return 'bg-purple-100 text-purple-700 border-purple-300';
      case 'gold': return 'bg-yellow-100 text-yellow-700 border-yellow-300';
      case 'silver': return 'bg-gray-100 text-gray-700 border-gray-300';
      default: return 'bg-orange-100 text-orange-700 border-orange-300';
    }
  };

  const getTierStars = (tier) => {
    const count = tier === 'platinum' ? 4 : tier === 'gold' ? 3 : tier === 'silver' ? 2 : 1;
    return Array(count).fill(0).map((_, i) => <Star key={i} className="w-3 h-3 fill-current" />);
  };

  const navigation = [
    { name: 'Home', path: '/', icon: Home, id: 'home' },
    { name: 'Bookings', path: '/bookings', icon: Calendar, id: 'bookings' },
    { name: t('guestPortal.messages') || 'Messages', path: '/messages', icon: MessageCircle, id: 'messages' },
    { name: 'Loyalty', path: '/loyalty', icon: Award, id: 'loyalty' },
    { name: 'Settings', path: '/settings', icon: Settings, id: 'settings' },
  ];

  const currentPath = location.pathname === '/' ? 'home' : location.pathname.slice(1);

  if (loading) {
    return <div className="loading-screen">{t("common.loading")}</div>;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
        <div className="px-4 py-3">
          <div className="flex items-center justify-between max-w-7xl mx-auto">
            <div className="flex items-center space-x-4">
              <h1
                className="text-2xl font-bold cursor-pointer"
                style={{ fontFamily: 'Space Grotesk', color: '#667eea' }}
                onClick={() => navigate('/')}
                data-testid="guest-logo"
              >
                RoomOps Guest
              </h1>
            </div>

            {/* Desktop Navigation */}
            <nav className="hidden md:flex items-center space-x-1">
              {navigation.map((item) => {
                const Icon = item.icon;
                const isActive = currentPath === item.id;
                return (
                  <Button
                    key={item.path}
                    variant={isActive ? 'default' : 'ghost'}
                    onClick={() => navigate(item.path)}
                    className="flex items-center space-x-2"
                    data-testid={`guest-nav-${item.id}`}
                  >
                    <Icon className="w-4 h-4" />
                    <span>{item.name}</span>
                  </Button>
                );
              })}
            </nav>

            {/* User Menu */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" data-testid="guest-user-menu">
                  <User className="w-4 h-4 mr-2" />
                  {user.name}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuLabel>My Account</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem className="text-sm">{user.email}</DropdownMenuItem>
                <DropdownMenuItem className="text-sm">{user.phone}</DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={onLogout} data-testid="guest-logout">
                  <LogOut className="w-4 h-4 mr-2" />
                  Logout
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto p-6">
        <Routes>
          {/* Home / Overview */}
          <Route
            path="/"
            element={
              <div className="space-y-6">
                <div>
                  <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Space Grotesk' }}>
                    Welcome, {user.name}
                  </h1>
                  <p className="text-gray-600">Your personalized travel hub</p>
                </div>

                {/* Quick Stats */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium text-gray-600">Active Bookings</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex items-center">
                        <Calendar className="w-8 h-8 mr-3 text-blue-500" />
                        <div className="text-3xl font-bold">{activeBookings.length}</div>
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium text-gray-600">Total Loyalty Points</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex items-center">
                        <Award className="w-8 h-8 mr-3 text-yellow-500" />
                        <div className="text-3xl font-bold">{totalPoints}</div>
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium text-gray-600">Hotels Visited</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex items-center">
                        <Hotel className="w-8 h-8 mr-3 text-purple-500" />
                        <div className="text-3xl font-bold">{loyaltyPrograms.length}</div>
                      </div>
                    </CardContent>
                  </Card>
                </div>

                {/* Active Bookings */}
                {activeBookings.length > 0 && (
                  <div>
                    <h2 className="text-2xl font-bold mb-4">Your Upcoming Stays</h2>
                    <div className="grid grid-cols-1 gap-4">
                      {activeBookings.slice(0, 3).map((booking) => (
                        <Card key={booking.id} className="card-hover">
                          <CardContent className="pt-6">
                            <div className="flex flex-wrap justify-between items-start gap-4">
                              <div className="flex-1">
                                <h3 className="text-xl font-bold mb-2">{booking.hotel?.property_name}</h3>
                                <div className="space-y-1 text-sm text-gray-600">
                                  <div className="flex items-center">
                                    <MapPin className="w-4 h-4 mr-2" />
                                    {booking.hotel?.address}
                                  </div>
                                  <div className="flex items-center">
                                    <Calendar className="w-4 h-4 mr-2" />
                                    {new Date(booking.check_in).toLocaleDateString()} - {new Date(booking.check_out).toLocaleDateString()}
                                  </div>
                                  <div className="flex items-center">
                                    <Hotel className="w-4 h-4 mr-2" />
                                    Room {booking.room?.room_number} ({booking.room?.room_type})
                                  </div>
                                </div>
                              </div>
                              <div className="flex flex-col items-end space-y-2">
                                {booking.status === 'confirmed' && (
                                  <Button
                                    onClick={() => navigate(`/checkin/${booking.id}`)}
                                    className="bg-green-600 hover:bg-green-700"
                                  >
                                    \ud83c\udfcb Check-in Now
                                  </Button>
                                )}
                                {booking.status === 'checked_in' && (
                                  <Button
                                    onClick={() => navigate(`/digital-key/${booking.id}`)}
                                  >
                                    <QrCode className="w-4 h-4 mr-2" />
                                    Digital Key
                                  </Button>
                                )}
                                <Button
                                  variant="outline"
                                  onClick={() => navigate(`/upsell/${booking.id}`)}
                                >
                                  \u2728 Enhance Stay
                                </Button>
                                <Button
                                  variant="outline"
                                  onClick={() => {
                                    setRoomServiceRequest({ ...roomServiceRequest, booking_id: booking.id });
                                    loadRoomServices(booking.id);
                                    setOpenDialog('room-service');
                                  }}
                                >
                                  <Utensils className="w-4 h-4 mr-2" />
                                  Room Service
                                </Button>
                              </div>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                    {activeBookings.length > 3 && (
                      <Button variant="outline" className="mt-4" onClick={() => navigate('/bookings')}>
                        View All Bookings
                      </Button>
                    )}
                  </div>
                )}
              </div>
            }
          />


          {/* Messages Page */}
          <Route
            path="/messages"
            element={
              <div className="space-y-6">
                <h1 className="text-3xl font-bold" style={{ fontFamily: 'Space Grotesk' }}>
                  {t('guestPortal.messages') || 'Mesajlar'}
                </h1>
                <p className="text-gray-600">{t('guestPortal.guestMessaging') || 'Otel ile mesajlaşın'}</p>
                <GuestMessaging
                  user={user}
                  bookingId={activeBookings[0]?.id}
                  isStaff={false}
                />
              </div>
            }
          />

          {/* Bookings Page */}
          <Route
            path="/bookings"
            element={
              <div className="space-y-6">
                <h1 className="text-4xl font-bold" style={{ fontFamily: 'Space Grotesk' }}>My Bookings</h1>
                
                <Tabs defaultValue="active">
                  <TabsList>
                    <TabsTrigger value="active">Active ({activeBookings.length})</TabsTrigger>
                    <TabsTrigger value="past">Past ({pastBookings.length})</TabsTrigger>
                  </TabsList>

                  <TabsContent value="active" className="space-y-4 mt-4">
                    {activeBookings.map((booking) => (
                      <Card key={booking.id}>
                        <CardContent className="pt-6">
                          <div className="flex flex-wrap justify-between items-start gap-4">
                            <div className="flex-1">
                              <h3 className="text-xl font-bold mb-2">{booking.hotel?.property_name}</h3>
                              <div className="space-y-1 text-sm text-gray-600">
                                <div className="flex items-center">
                                  <MapPin className="w-4 h-4 mr-2" />
                                  {booking.hotel?.address}
                                </div>
                                <div className="flex items-center">
                                  <Calendar className="w-4 h-4 mr-2" />
                                  Check-in: {new Date(booking.check_in).toLocaleDateString()}
                                </div>
                                <div className="flex items-center">
                                  <Calendar className="w-4 h-4 mr-2" />
                                  Check-out: {new Date(booking.check_out).toLocaleDateString()}
                                </div>
                                <div className="flex items-center">
                                  <Hotel className="w-4 h-4 mr-2" />
                                  Room {booking.room?.room_number} - {booking.room?.room_type}
                                </div>
                                <div className="flex items-center">
                                  <User className="w-4 h-4 mr-2" />
                                  {booking.guests_count} guest(s)
                                </div>
                              </div>
                            </div>
                            <div className="flex flex-col items-end space-y-2">
                              <div className="text-2xl font-bold text-blue-600">${booking.total_amount}</div>
                              <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                                booking.status === 'confirmed' ? 'bg-green-100 text-green-700' :
                                booking.status === 'checked_in' ? 'bg-blue-100 text-blue-700' :
                                'bg-yellow-100 text-yellow-700'
                              }`}>
                                {booking.status.replace('_', ' ').toUpperCase()}
                              </span>
                              <Button
                                size="sm"
                                onClick={() => {
                                  setSelectedBooking(booking);
                                  setOpenDialog('qr');
                                }}
                              >
                                <QrCode className="w-4 h-4 mr-2" />
                                QR Code
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => {
                                  setRoomServiceRequest({ ...roomServiceRequest, booking_id: booking.id });
                                  loadRoomServices(booking.id);
                                  setOpenDialog('room-service');
                                }}
                              >
                                <Utensils className="w-4 h-4 mr-2" />
                                Room Service
                              </Button>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </TabsContent>

                  <TabsContent value="past" className="space-y-4 mt-4">
                    {pastBookings.map((booking) => (
                      <Card key={booking.id}>
                        <CardContent className="pt-6">
                          <div className="flex flex-wrap justify-between items-start gap-4">
                            <div className="flex-1">
                              <h3 className="text-xl font-bold mb-2">{booking.hotel?.property_name}</h3>
                              <div className="space-y-1 text-sm text-gray-600">
                                <div className="flex items-center">
                                  <Calendar className="w-4 h-4 mr-2" />
                                  {new Date(booking.check_in).toLocaleDateString()} - {new Date(booking.check_out).toLocaleDateString()}
                                </div>
                                <div className="flex items-center">
                                  <Hotel className="w-4 h-4 mr-2" />
                                  Room {booking.room?.room_number} - {booking.room?.room_type}
                                </div>
                              </div>
                            </div>
                            <div className="text-right">
                              <div className="text-xl font-bold text-gray-600">${booking.total_amount}</div>
                              <span className="text-xs text-gray-500">{booking.status.toUpperCase()}</span>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </TabsContent>
                </Tabs>
              </div>
            }
          />

          {/* Loyalty Page */}
          <Route
            path="/loyalty"
            element={
              <div className="space-y-6">
                <div>
                  <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Space Grotesk' }}>Loyalty Rewards</h1>
                  <p className="text-gray-600">Your points across all hotels</p>
                </div>

                <Card className="bg-gradient-to-r from-blue-500 to-purple-600 text-white">
                  <CardContent className="pt-6 pb-6">
                    <div className="text-center">
                      <div className="text-6xl font-bold mb-2">{totalPoints}</div>
                      <div className="text-xl">Total Points</div>
                    </div>
                  </CardContent>
                </Card>

                {/* Cleaning Request Section */}
                {activeBookings.length > 0 && (
                  <Card className="bg-gradient-to-r from-teal-50 to-cyan-50 border-teal-200">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <Sparkles className="w-6 h-6 text-teal-600" />
                        Oda Temizlik Hizmeti
                      </CardTitle>
                      <CardDescription>
                        Otel odanızın temizlenmesini talep edin
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="font-semibold">Oda: {activeBookings[0]?.room_number}</p>
                          <p className="text-sm text-gray-600">Aktif Konaklama</p>
                        </div>
                        <Button 
                          onClick={() => setCleaningRequestModalOpen(true)}
                          className="bg-teal-600 hover:bg-teal-700"
                        >
                          <Sparkles className="w-4 h-4 mr-2" />
                          Temizlik Talep Et
                        </Button>
                      </div>

                      {/* Recent Cleaning Requests */}
                      {cleaningRequests.length > 0 && (
                        <div className="border-t pt-4 space-y-2">
                          <p className="text-sm font-semibold">Son Talepleriniz:</p>
                          {cleaningRequests.slice(0, 3).map((req) => (
                            <div key={req.id} className="flex items-center justify-between p-2 bg-white rounded border">
                              <div className="flex items-center gap-2">
                                {req.status === 'pending' && <Clock className="w-4 h-4 text-orange-500" />}
                                {req.status === 'in_progress' && <AlertCircle className="w-4 h-4 text-blue-500" />}
                                {req.status === 'completed' && <CheckCircle className="w-4 h-4 text-green-500" />}
                                <span className="text-sm">
                                  {req.request_type === 'urgent' ? 'Acil' : 'Normal'} Temizlik
                                </span>
                              </div>
                              <span className={`text-xs px-2 py-1 rounded ${
                                req.status === 'pending' ? 'bg-orange-100 text-orange-700' :
                                req.status === 'in_progress' ? 'bg-blue-100 text-blue-700' :
                                'bg-green-100 text-green-700'
                              }`}>
                                {req.status === 'pending' ? 'Bekliyor' :
                                 req.status === 'in_progress' ? 'Yapılıyor' : 'Tamamlandı'}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {loyaltyPrograms.map((program) => (
                    <Card key={program.id}>
                      <CardHeader>
                        <div className="flex justify-between items-start">
                          <div>
                            <CardTitle>{program.hotel?.property_name}</CardTitle>
                            <CardDescription>{program.hotel?.address}</CardDescription>
                          </div>
                          <Award className="w-6 h-6 text-yellow-500" />
                        </div>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-gray-600">Tier</span>
                          <div className={`px-3 py-1 rounded-full text-xs font-medium flex items-center space-x-1 border ${getTierColor(program.tier)}`}>
                            {getTierStars(program.tier)}
                            <span className="ml-1 capitalize">{program.tier}</span>
                          </div>
                        </div>

                        <div className="text-center py-4 border-t border-b">
                          <div className="text-4xl font-bold text-blue-600">{program.points}</div>
                          <div className="text-sm text-gray-600 mt-1">Available Points</div>
                        </div>

                        <div className="text-sm">
                          <div className="flex justify-between">
                            <span className="text-gray-600">Lifetime Points</span>
                            <span className="font-medium">{program.lifetime_points}</span>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>

                {/* Cleaning Request Modal */}
                <Dialog open={cleaningRequestModalOpen} onOpenChange={setCleaningRequestModalOpen}>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle className="flex items-center gap-2">
                        <Sparkles className="w-5 h-5 text-teal-600" />
                        Oda Temizlik Talebi
                      </DialogTitle>
                      <DialogDescription>
                        Otel odanızın temizlenmesini talep edin
                      </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4">
                      <div>
                        <Label>Temizlik Türü</Label>
                        <Select value={cleaningRequestType} onValueChange={setCleaningRequestType}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="regular">Normal Temizlik</SelectItem>
                            <SelectItem value="urgent">Acil Temizlik</SelectItem>
                            <SelectItem value="turndown">Akşam Servisi</SelectItem>
                            <SelectItem value="do_not_disturb">Rahatsız Etmeyin</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div>
                        <Label>Özel Notlar (Opsiyonel)</Label>
                        <Textarea
                          value={cleaningNotes}
                          onChange={(e) => setCleaningNotes(e.target.value)}
                          placeholder="Ek talepleriniz varsa buraya yazabilirsiniz..."
                          rows={3}
                        />
                      </div>

                      <div className="bg-teal-50 border border-teal-200 rounded p-3">
                        <p className="text-sm text-teal-800">
                          {cleaningRequestType === 'urgent' 
                            ? '⚡ Acil temizlik: 30-60 dakika içinde'
                            : '⏰ Normal temizlik: 2-3 saat içinde'}
                        </p>
                      </div>

                      <div className="flex gap-2">
                        <Button 
                          variant="outline" 
                          onClick={() => setCleaningRequestModalOpen(false)}
                          className="flex-1"
                        >
                          İptal
                        </Button>
                        <Button 
                          onClick={handleCleaningRequest}
                          className="flex-1 bg-teal-600 hover:bg-teal-700"
                        >
                          Talep Gönder
                        </Button>
                      </div>
                    </div>
                  </DialogContent>
                </Dialog>
              </div>
            }
          />

          {/* Self Check-in Page */}
          <Route
            path="/checkin/:bookingId"
            element={
              <div className="space-y-6">
                <h1 className="text-4xl font-bold" style={{ fontFamily: 'Space Grotesk' }}>Self Check-in</h1>
                
                <Card>
                  <CardHeader>
                    <CardTitle>Complete Your Check-in</CardTitle>
                    <CardDescription>Review your booking details and check-in online</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                        <p className="text-sm text-blue-800">
                          ✅ Your check-in is almost complete! Please review your details below.
                        </p>
                      </div>
                      
                      {(() => {
                        const bookingId = window.location.pathname.split('/').pop();
                        const booking = activeBookings.find(b => b.id === bookingId);
                        
                        if (!booking) {
                          return <p className="text-gray-500">Booking not found</p>;
                        }
                        
                        return (
                          <div className="space-y-6">
                            <div>
                              <h3 className="font-semibold mb-3">Booking Details</h3>
                              <div className="grid grid-cols-2 gap-4 text-sm">
                                <div>
                                  <Label className="text-gray-500">Hotel</Label>
                                  <p className="font-medium">{booking.hotel?.property_name}</p>
                                </div>
                                <div>
                                  <Label className="text-gray-500">Room</Label>
                                  <p className="font-medium">Room {booking.room?.room_number} - {booking.room?.room_type}</p>
                                </div>
                                <div>
                                  <Label className="text-gray-500">Check-in</Label>
                                  <p className="font-medium">{new Date(booking.check_in).toLocaleDateString()}</p>
                                </div>
                                <div>
                                  <Label className="text-gray-500">Check-out</Label>
                                  <p className="font-medium">{new Date(booking.check_out).toLocaleDateString()}</p>
                                </div>
                                <div>
                                  <Label className="text-gray-500">Guests</Label>
                                  <p className="font-medium">{booking.guests_count} guest(s)</p>
                                </div>
                                <div>
                                  <Label className="text-gray-500">Total Amount</Label>
                                  <p className="font-medium text-blue-600">${booking.total_amount}</p>
                                </div>
                              </div>
                            </div>
                            
                            <div className="border-t pt-4">
                              <Button 
                                className="w-full bg-green-600 hover:bg-green-700"
                                onClick={async () => {
                                  try {
                                    await axios.post(`/guest/self-checkin/${booking.id}`);
                                    toast.success('Check-in successful! Welcome!');
                                    loadData();
                                    navigate('/');
                                  } catch (error) {
                                    toast.error('Check-in failed. Please try again or contact reception.');
                                  }
                                }}
                              >
                                Confirm Check-in
                              </Button>
                              <Button 
                                variant="outline"
                                className="w-full mt-2"
                                onClick={() => navigate('/')}
                              >
                                Back to Home
                              </Button>
                            </div>
                          </div>
                        );
                      })()}
                    </div>
                  </CardContent>
                </Card>
              </div>
            }
          />

          {/* Digital Key Page */}
          <Route
            path="/digital-key/:bookingId"
            element={
              <div className="space-y-6">
                <h1 className="text-4xl font-bold" style={{ fontFamily: 'Space Grotesk' }}>Digital Key</h1>
                
                <Card>
                  <CardHeader>
                    <CardTitle>Your Digital Room Key</CardTitle>
                    <CardDescription>Use this QR code to access your room</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {(() => {
                      const bookingId = window.location.pathname.split('/').pop();
                      const booking = activeBookings.find(b => b.id === bookingId);
                      
                      if (!booking) {
                        return <p className="text-gray-500">Booking not found</p>;
                      }
                      
                      return (
                        <div className="space-y-6">
                          <div className="bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl p-8 text-white text-center">
                            <div className="mb-4">
                              <h3 className="text-2xl font-bold">{booking.hotel?.property_name}</h3>
                              <p className="text-blue-100">Room {booking.room?.room_number}</p>
                            </div>
                            
                            {booking.qr_code_data ? (
                              <div className="bg-white rounded-lg p-6 mx-auto inline-block">
                                <div className="text-6xl">🔑</div>
                                <p className="text-gray-800 font-mono text-sm mt-2">{booking.confirmation_number}</p>
                              </div>
                            ) : (
                              <div className="bg-white rounded-lg p-6 mx-auto inline-block">
                                <QrCode className="w-32 h-32 text-gray-400" />
                              </div>
                            )}
                            
                            <p className="mt-4 text-sm text-blue-100">
                              Show this code at the door lock to access your room
                            </p>
                          </div>
                          
                          <div className="grid grid-cols-2 gap-4 text-sm">
                            <div className="bg-gray-50 rounded-lg p-4">
                              <Label className="text-gray-500">Check-in</Label>
                              <p className="font-medium">{new Date(booking.check_in).toLocaleString()}</p>
                            </div>
                            <div className="bg-gray-50 rounded-lg p-4">
                              <Label className="text-gray-500">Check-out</Label>
                              <p className="font-medium">{new Date(booking.check_out).toLocaleString()}</p>
                            </div>
                          </div>
                          
                          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                            <p className="text-sm text-yellow-800">
                              <strong>Note:</strong> This digital key is valid only during your stay. 
                              Keep your phone charged to ensure access to your room.
                            </p>
                          </div>
                          
                          <Button 
                            variant="outline"
                            className="w-full"
                            onClick={() => navigate('/')}
                          >
                            Back to Home
                          </Button>
                        </div>
                      );
                    })()}
                  </CardContent>
                </Card>
              </div>
            }
          />

          {/* Upsell / Enhance Stay Page */}
          <Route
            path="/upsell/:bookingId"
            element={
              <div className="space-y-6">
                <h1 className="text-4xl font-bold" style={{ fontFamily: 'Space Grotesk' }}>Enhance Your Stay</h1>
                <p className="text-gray-600">Make your stay even more special with our exclusive offers</p>
                
                {(() => {
                  const bookingId = window.location.pathname.split('/').pop();
                  const booking = activeBookings.find(b => b.id === bookingId);
                  
                  if (!booking) {
                    return <p className="text-gray-500">Booking not found</p>;
                  }
                  
                  const upsellOffers = [
                    {
                      id: 1,
                      title: 'Room Upgrade',
                      description: 'Upgrade to a deluxe suite with panoramic city views',
                      price: 50,
                      icon: '🏆',
                      category: 'Room'
                    },
                    {
                      id: 2,
                      title: 'Late Checkout',
                      description: 'Extend your stay until 4 PM (subject to availability)',
                      price: 30,
                      icon: '🕐',
                      category: 'Service'
                    },
                    {
                      id: 3,
                      title: 'Breakfast Package',
                      description: 'Daily continental breakfast for 2 guests',
                      price: 25,
                      icon: '🍳',
                      category: 'Dining'
                    },
                    {
                      id: 4,
                      title: 'Spa Treatment',
                      description: '60-minute relaxing massage at our wellness center',
                      price: 80,
                      icon: '💆',
                      category: 'Wellness'
                    },
                    {
                      id: 5,
                      title: 'Airport Transfer',
                      description: 'Private car service to/from the airport',
                      price: 45,
                      icon: '🚗',
                      category: 'Transport'
                    },
                    {
                      id: 6,
                      title: 'Welcome Package',
                      description: 'Champagne, chocolates, and fresh flowers in your room',
                      price: 35,
                      icon: '🍾',
                      category: 'Amenity'
                    }
                  ];
                  
                  return (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {upsellOffers.map((offer) => (
                        <Card key={offer.id} className="card-hover">
                          <CardContent className="pt-6">
                            <div className="flex items-start justify-between mb-4">
                              <div className="text-4xl">{offer.icon}</div>
                              <span className="bg-blue-100 text-blue-700 text-xs font-medium px-2 py-1 rounded">
                                {offer.category}
                              </span>
                            </div>
                            
                            <h3 className="text-xl font-bold mb-2">{offer.title}</h3>
                            <p className="text-gray-600 text-sm mb-4">{offer.description}</p>
                            
                            <div className="flex items-center justify-between">
                              <div className="text-2xl font-bold text-blue-600">
                                ${offer.price}
                              </div>
                              <Button
                                onClick={async () => {
                                  try {
                                    await axios.post(`/guest/purchase-upsell/${booking.id}`, {
                                      offer_id: offer.id,
                                      offer_name: offer.title,
                                      price: offer.price
                                    });
                                    toast.success(`${offer.title} added to your booking!`);
                                  } catch (error) {
                                    toast.error('Failed to add offer. Please try again.');
                                  }
                                }}
                              >
                                Add to Stay
                              </Button>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  );
                })()}
                
                <Button 
                  variant="outline"
                  onClick={() => navigate('/')}
                >
                  Back to Home
                </Button>
              </div>
            }
          />

          {/* Settings Page */}
          <Route
            path="/settings"
            element={
              <div className="space-y-6">
                <h1 className="text-4xl font-bold" style={{ fontFamily: 'Space Grotesk' }}>Settings</h1>

                <Card>
                  <CardHeader>
                    <CardTitle>Notification Preferences</CardTitle>
                    <CardDescription>Manage how you receive updates</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {notificationPrefs && (
                      <>
                        <div className="flex items-center justify-between">
                          <div className="space-y-0.5">
                            <Label>Email Notifications</Label>
                            <p className="text-sm text-gray-500">Receive updates via email</p>
                          </div>
                          <Switch
                            checked={notificationPrefs.email_notifications}
                            onCheckedChange={(checked) => updateNotificationPref('email_notifications', checked)}
                          />
                        </div>

                        <div className="flex items-center justify-between">
                          <div className="space-y-0.5">
                            <Label>WhatsApp Notifications</Label>
                            <p className="text-sm text-gray-500">Get messages on WhatsApp</p>
                          </div>
                          <Switch
                            checked={notificationPrefs.whatsapp_notifications}
                            onCheckedChange={(checked) => updateNotificationPref('whatsapp_notifications', checked)}
                          />
                        </div>

                        <div className="flex items-center justify-between">
                          <div className="space-y-0.5">
                            <Label>In-App Notifications</Label>
                            <p className="text-sm text-gray-500">See updates in the app</p>
                          </div>
                          <Switch
                            checked={notificationPrefs.in_app_notifications}
                            onCheckedChange={(checked) => updateNotificationPref('in_app_notifications', checked)}
                          />
                        </div>

                        <div className="border-t pt-4 mt-4">
                          <h3 className="font-semibold mb-3">Notification Types</h3>
                          
                          <div className="flex items-center justify-between mb-3">
                            <Label>Booking Updates</Label>
                            <Switch
                              checked={notificationPrefs.booking_updates}
                              onCheckedChange={(checked) => updateNotificationPref('booking_updates', checked)}
                            />
                          </div>

                          <div className="flex items-center justify-between mb-3">
                            <Label>Room Service Updates</Label>
                            <Switch
                              checked={notificationPrefs.room_service_updates}
                              onCheckedChange={(checked) => updateNotificationPref('room_service_updates', checked)}
                            />
                          </div>

                          <div className="flex items-center justify-between">
                            <Label>Promotional Offers</Label>
                            <Switch
                              checked={notificationPrefs.promotional}
                              onCheckedChange={(checked) => updateNotificationPref('promotional', checked)}
                            />
                          </div>
                        </div>
                      </>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Account Information</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div>
                      <Label>Name</Label>
                      <div className="text-sm text-gray-700 mt-1">{user.name}</div>
                    </div>
                    <div>
                      <Label>Email</Label>
                      <div className="text-sm text-gray-700 mt-1">{user.email}</div>
                    </div>
                    <div>
                      <Label>Phone</Label>
                      <div className="text-sm text-gray-700 mt-1">{user.phone}</div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            }
          />
        </Routes>
      </main>

      {/* QR Code Dialog */}
      <Dialog open={openDialog === 'qr'} onOpenChange={(open) => !open && setOpenDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Your Booking QR Code</DialogTitle>
            <DialogDescription>Show this at the hotel for quick check-in</DialogDescription>
          </DialogHeader>
          {selectedBooking && (
            <div className="space-y-4">
              <div className="text-center">
                <h3 className="font-semibold text-lg mb-2">{selectedBooking.hotel?.property_name}</h3>
                <p className="text-sm text-gray-600 mb-4">
                  Room {selectedBooking.room?.room_number}
                </p>
                {selectedBooking.qr_code && (
                  <img 
                    src={selectedBooking.qr_code} 
                    alt="Booking QR Code" 
                    className="mx-auto border rounded-lg p-4"
                    style={{ maxWidth: '300px' }}
                  />
                )}
                <p className="text-xs text-gray-500 mt-4">
                  This QR code is valid for your entire stay
                </p>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Room Service Dialog */}
      <Dialog open={openDialog === 'room-service'} onOpenChange={(open) => !open && setOpenDialog(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Room Service Request</DialogTitle>
            <DialogDescription>Request services for your room</DialogDescription>
          </DialogHeader>
          
          <Tabs defaultValue="request">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="request">New Request</TabsTrigger>
              <TabsTrigger value="history">My Requests</TabsTrigger>
            </TabsList>

            <TabsContent value="request">
              <form onSubmit={handleRoomServiceRequest} className="space-y-4">
                <div>
                  <Label htmlFor="service-type">Service Type</Label>
                  <Select 
                    value={roomServiceRequest.service_type} 
                    onValueChange={(v) => setRoomServiceRequest({...roomServiceRequest, service_type: v})}
                  >
                    <SelectTrigger id="service-type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="housekeeping">Housekeeping</SelectItem>
                      <SelectItem value="food">Food & Beverage</SelectItem>
                      <SelectItem value="maintenance">Maintenance</SelectItem>
                      <SelectItem value="laundry">Laundry</SelectItem>
                      <SelectItem value="concierge">Concierge</SelectItem>
                      <SelectItem value="other">Other</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label htmlFor="description">Description</Label>
                  <Input
                    id="description"
                    value={roomServiceRequest.description}
                    onChange={(e) => setRoomServiceRequest({...roomServiceRequest, description: e.target.value})}
                    placeholder="Brief description of your request"
                    required
                  />
                </div>

                <div>
                  <Label htmlFor="notes">Additional Notes</Label>
                  <Textarea
                    id="notes"
                    value={roomServiceRequest.notes}
                    onChange={(e) => setRoomServiceRequest({...roomServiceRequest, notes: e.target.value})}
                    placeholder="Any special instructions..."
                    rows={3}
                  />
                </div>

                <Button type="submit" className="w-full">Submit Request</Button>
              </form>
            </TabsContent>

            <TabsContent value="history">
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {roomServices[roomServiceRequest.booking_id]?.map((service) => (
                  <Card key={service.id}>
                    <CardContent className="pt-4">
                      <div className="flex justify-between items-start">
                        <div>
                          <div className="font-semibold capitalize">{service.service_type}</div>
                          <div className="text-sm text-gray-600">{service.description}</div>
                          {service.notes && (
                            <div className="text-xs text-gray-500 mt-1">{service.notes}</div>
                          )}
                          <div className="text-xs text-gray-400 mt-2">
                            {new Date(service.created_at).toLocaleString()}
                          </div>
                        </div>
                        <span className={`px-2 py-1 rounded text-xs font-medium ${
                          service.status === 'completed' ? 'bg-green-100 text-green-700' :
                          service.status === 'in_progress' ? 'bg-blue-100 text-blue-700' :
                          service.status === 'cancelled' ? 'bg-red-100 text-red-700' :
                          'bg-yellow-100 text-yellow-700'
                        }`}>
                          {service.status.replace('_', ' ')}
                        </span>
                      </div>
                    </CardContent>
                  </Card>
                ))}
                {(!roomServices[roomServiceRequest.booking_id] || roomServices[roomServiceRequest.booking_id].length === 0) && (
                  <p className="text-center text-gray-500 py-8">No requests yet</p>
                )}
              </div>
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default GuestPortal;
