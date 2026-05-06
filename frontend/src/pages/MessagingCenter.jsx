import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import MessagingTemplates from '../components/MessagingTemplates';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../components/ui/dialog';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { toast } from 'sonner';
import { 
  Mail, 
  MessageSquare, 
  Phone, 
  Bell,
  Send,
  Users,
  FileText,
  Clock,
  CheckCircle,
  Smartphone
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { alertDialog } from '@/lib/dialogs';

const MessagingCenter = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [selectedChannel, setSelectedChannel] = useState('email');
  const [selectedTemplate, setSelectedTemplate] = useState('');
  const [recipients, setRecipients] = useState('');
  const [message, setMessage] = useState('');
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [scheduleAt, setScheduleAt] = useState(() => {
    const d = new Date(Date.now() + 60 * 60 * 1000);
    d.setSeconds(0, 0);
    return d.toISOString().slice(0, 16);
  });
  const [scheduling, setScheduling] = useState(false);

  const confirmSchedule = async () => {
    if (!recipients || !message) {
      toast.error('Recipients and message are required');
      return;
    }
    const when = new Date(scheduleAt);
    if (Number.isNaN(when.getTime()) || when.getTime() <= Date.now()) {
      toast.error('Pick a future date/time');
      return;
    }
    setScheduling(true);
    try {
      toast.success(`Scheduled ${selectedChannel.toUpperCase()} message for ${when.toLocaleString()}`);
      setScheduleOpen(false);
    } finally {
      setScheduling(false);
    }
  };

  const channels = [
    { id: 'email', name: 'Email', icon: Mail, color: 'blue', active: true },
    { id: 'whatsapp', name: 'WhatsApp', icon: MessageSquare, color: 'green', active: true },
    { id: 'sms', name: 'SMS', icon: Phone, color: 'purple', active: true },
    { id: 'push', name: 'Push Notification', icon: Bell, color: 'orange', active: true },
    { id: 'app', name: 'Hotel App', icon: Smartphone, color: 'indigo', active: false }
  ];

  const templates = {
    'front-desk': [
      { id: 'checkin-ready', name: 'Check-in Ready', text: 'Dear {guest_name}, your room is ready for early check-in. Please visit the front desk.' },
      { id: 'welcome', name: 'Welcome Message', text: 'Welcome to {hotel_name}! We hope you enjoy your stay. Room {room_number} is ready.' },
      { id: 'checkout-reminder', name: 'Check-out Reminder', text: 'Check-out time is 12:00 PM. Need late checkout? Call ext. 100.' }
    ],
    'sales': [
      { id: 'group-quote', name: 'Group Quote', text: 'Thank you for your group inquiry. Please find attached our proposal for {group_size} rooms.' },
      { id: 'contract-renewal', name: 'Contract Renewal', text: 'Your corporate rate contract expires on {date}. Let\'s discuss renewal terms.' },
      { id: 'event-proposal', name: 'Event Proposal', text: 'We\'d love to host your event! Our {venue_name} can accommodate {capacity} guests.' }
    ],
    'crm': [
      { id: 'birthday', name: 'Birthday Wishes', text: 'Happy Birthday {guest_name}! Enjoy a complimentary dessert on your next visit. Code: BDAY2025' },
      { id: 'loyalty-milestone', name: 'Loyalty Milestone', text: 'Congratulations! You\'ve reached {tier} status. Enjoy exclusive benefits.' },
      { id: 'winback', name: 'Win-back Campaign', text: 'We miss you! Book before {date} and get 20% off. We\'d love to welcome you back.' }
    ],
    'housekeeping': [
      { id: 'room-ready', name: 'Room Ready Notification', text: 'Room {room_number} is clean and ready for check-in.' },
      { id: 'service-delay', name: 'Service Delay', text: 'We apologize for the delay. Your room will be ready by {time}.' }
    ]
  };

  const recentMessages = [
    { id: 1, recipient: 'Richard Anderson', channel: 'whatsapp', message: 'Check-in ready - Room 116', status: 'delivered', time: '10 mins ago' },
    { id: 2, recipient: 'Group: Tech Conference', channel: 'email', message: 'Event proposal for 50 attendees', status: 'sent', time: '1 hour ago' },
    { id: 3, recipient: 'Amelia Gonzalez', channel: 'sms', message: 'Welcome message', status: 'delivered', time: '2 hours ago' },
    { id: 4, recipient: 'VIP Guests (25)', channel: 'push', message: 'Special offer: Spa 30% off', status: 'read', time: '1 day ago' }
  ];

  const handleSendMessage = () => {
    alertDialog({ message: `Sending ${selectedChannel} message to: ${recipients}\n\nMessage: ${message}` });
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="messaging">
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold" style={{ fontFamily: 'Space Grotesk' }}>
              {t('messagingCenter.title')}
            </h1>
            <p className="text-gray-600 mt-1">{t('messagingCenter.subtitle')}</p>
          </div>
          <Button onClick={() => navigate('/pms')}>
            {t('messagingCenter.backToPms')}
          </Button>
        </div>

        {/* Tabs */}
        <Tabs defaultValue="compose" className="w-full">
          <TabsList className="grid w-full grid-cols-2 max-w-md">
            <TabsTrigger value="compose">{t('messagingCenter.composeMessage')}</TabsTrigger>
            <TabsTrigger value="templates">
              <MessageSquare className="w-4 h-4 mr-2" />
              {t('messagingCenter.whatsappSmsTemplates')}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="compose" className="mt-6">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Compose Message */}
          <div className="lg:col-span-2 space-y-6">
            {/* Channel Selection */}
            <Card>
              <CardHeader>
                <CardTitle>{t('messagingCenter.selectChannel')}</CardTitle>
                <CardDescription>{t('messagingCenter.selectChannelDesc')}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                  {channels.map((channel) => {
                    const Icon = channel.icon;
                    return (
                      <button
                        key={channel.id}
                        onClick={() => channel.active && setSelectedChannel(channel.id)}
                        disabled={!channel.active}
                        className={`p-4 rounded-lg border-2 transition-all ${
                          selectedChannel === channel.id
                            ? `border-${channel.color}-500 bg-${channel.color}-50`
                            : 'border-gray-200 hover:border-gray-300'
                        } ${!channel.active ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                      >
                        <Icon className={`w-6 h-6 mx-auto mb-2 ${
                          selectedChannel === channel.id ? `text-${channel.color}-600` : 'text-gray-600'
                        }`} />
                        <div className="text-xs font-semibold text-center">{channel.name}</div>
                        {!channel.active && (
                          <Badge className="mt-1 text-xs">Soon</Badge>
                        )}
                      </button>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            {/* Templates */}
            <Card>
              <CardHeader>
                <CardTitle>Quick Templates</CardTitle>
                <CardDescription>Department-specific message templates</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {Object.entries(templates).map(([dept, temps]) => (
                    <div key={dept}>
                      <h3 className="font-semibold text-sm mb-2 capitalize flex items-center space-x-2">
                        <FileText className="w-4 h-4" />
                        <span>{dept.replace('-', ' ')}</span>
                      </h3>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                        {temps.map((template) => (
                          <button
                            key={template.id}
                            onClick={() => {
                              setSelectedTemplate(template.id);
                              setMessage(template.text);
                            }}
                            className={`p-2 text-left rounded border text-sm ${
                              selectedTemplate === template.id
                                ? 'border-blue-500 bg-blue-50'
                                : 'border-gray-200 hover:border-blue-300'
                            }`}
                          >
                            {template.name}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Compose */}
            <Card>
              <CardHeader>
                <CardTitle>{t('messagingCenter.composeMessage')}</CardTitle>
                <CardDescription>
                  Sending via {channels.find(c => c.id === selectedChannel)?.name}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium mb-2">Recipients</label>
                    <input
                      type="text"
                      value={recipients}
                      onChange={(e) => setRecipients(e.target.value)}
                      placeholder="Guest name, room number, or segment (e.g., 'VIP Guests', 'Room 205')"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    />
                    <div className="flex gap-2 mt-2">
                      <Button size="sm" variant="outline" onClick={() => setRecipients('Today\'s Arrivals')}>
                        <Users className="w-3 h-3 mr-1" />
                        Today's Arrivals
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => setRecipients('In-House Guests')}>
                        <Users className="w-3 h-3 mr-1" />
                        In-House
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => setRecipients('VIP Guests')}>
                        <Users className="w-3 h-3 mr-1" />
                        VIP Guests
                      </Button>
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium mb-2">Message</label>
                    <textarea
                      value={message}
                      onChange={(e) => setMessage(e.target.value)}
                      rows="6"
                      placeholder="Type your message here..."
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    />
                    <div className="text-xs text-gray-500 mt-1">
                      Available variables: {'{guest_name}'}, {'{room_number}'}, {'{hotel_name}'}, {'{date}'}, {'{time}'}
                    </div>
                  </div>

                  <div className="flex space-x-2">
                    <Button 
                      onClick={handleSendMessage}
                      disabled={!recipients || !message}
                      className="flex-1"
                    >
                      <Send className="w-4 h-4 mr-2" />
                      Send Message
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => setScheduleOpen(true)}
                      disabled={!recipients || !message}
                    >
                      <Clock className="w-4 h-4 mr-2" />
                      Schedule
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Right: Recent Messages */}
          <div>
            <Card>
              <CardHeader>
                <CardTitle>Recent Messages</CardTitle>
                <CardDescription>Last 24 hours</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {recentMessages.map((msg) => (
                    <div key={msg.id} className="p-3 border rounded-lg hover:bg-gray-50">
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex-1">
                          <div className="font-semibold text-sm">{msg.recipient}</div>
                          <div className="text-xs text-gray-600 truncate">{msg.message}</div>
                        </div>
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          {msg.channel === 'whatsapp' && <MessageSquare className="w-3 h-3 text-green-600" />}
                          {msg.channel === 'email' && <Mail className="w-3 h-3 text-blue-600" />}
                          {msg.channel === 'sms' && <Phone className="w-3 h-3 text-indigo-600" />}
                          {msg.channel === 'push' && <Bell className="w-3 h-3 text-amber-600" />}
                          <span className="text-xs text-gray-500">{msg.channel}</span>
                        </div>
                        <div className="flex items-center space-x-2">
                          <Badge 
                            className={`text-xs ${
                              msg.status === 'read' ? 'bg-green-500' :
                              msg.status === 'delivered' ? 'bg-blue-500' :
                              'bg-gray-500'
                            }`}
                          >
                            {msg.status === 'read' && <CheckCircle className="w-3 h-3 mr-1" />}
                            {msg.status}
                          </Badge>
                          <span className="text-xs text-gray-500">{msg.time}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Stats */}
            <Card className="mt-6">
              <CardHeader>
                <CardTitle>Today's Stats</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">Messages Sent</span>
                    <span className="font-bold text-lg">47</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">Delivery Rate</span>
                    <Badge className="bg-green-500">98.5%</Badge>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">Read Rate</span>
                    <Badge className="bg-blue-500">76.2%</Badge>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">Avg Response Time</span>
                    <span className="font-semibold">8 mins</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
          </TabsContent>

          <TabsContent value="templates" className="mt-6">
            <MessagingTemplates />
          </TabsContent>
        </Tabs>
      </div>

      <Dialog open={scheduleOpen} onOpenChange={setScheduleOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Schedule Message</DialogTitle>
            <DialogDescription>
              Pick a date and time to send your {selectedChannel.toUpperCase()} message.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label htmlFor="schedule-at">Send at</Label>
              <Input
                id="schedule-at"
                type="datetime-local"
                value={scheduleAt}
                onChange={(e) => setScheduleAt(e.target.value)}
                min={new Date().toISOString().slice(0, 16)}
              />
            </div>
            <div className="text-xs text-gray-500">
              To: {recipients || '—'} · {message?.length || 0} chars
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setScheduleOpen(false)} disabled={scheduling}>
              Cancel
            </Button>
            <Button onClick={confirmSchedule} disabled={scheduling}>
              {scheduling ? 'Scheduling…' : 'Schedule'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Layout>
  );
};

export default MessagingCenter;
