import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { MessageCircle, Mail, Phone, Send, FileText, Zap } from 'lucide-react';

const MessagingModuleAdvanced = () => {
  const [activeTab, setActiveTab] = useState('send'); // send, templates, auto
  const [templates, setTemplates] = useState([]);
  const [messageData, setMessageData] = useState({
    guest_id: '',
    message_type: 'whatsapp',
    recipient: '',
    message_content: '',
    booking_id: ''
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchTemplates();
  }, []);

  const fetchTemplates = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${import.meta.env.VITE_BACKEND_URL}/api/messaging/templates`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setTemplates(data.templates || []);
      }
    } catch (error) {
      console.error('Error fetching templates:', error);
    }
  };

  const handleSendMessage = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${import.meta.env.VITE_BACKEND_URL}/api/messaging/send-message`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(messageData)
        }
      );

      if (response.ok) {
        alert('Message sent successfully!');
        setMessageData({
          guest_id: '',
          message_type: 'whatsapp',
          recipient: '',
          message_content: '',
          booking_id: ''
        });
      }
    } catch (error) {
      console.error('Error sending message:', error);
      alert('Failed to send message');
    } finally {
      setLoading(false);
    }
  };

  const handleTriggerAutoMessages = async (triggerType) => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${import.meta.env.VITE_BACKEND_URL}/api/messaging/auto-messages/trigger?trigger_type=${triggerType}`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );

      if (response.ok) {
        const data = await response.json();
        alert(`Auto-messages triggered: ${data.messages_sent} messages sent`);
      }
    } catch (error) {
      console.error('Error triggering auto-messages:', error);
    } finally {
      setLoading(false);
    }
  };

  const getMessageTypeIcon = (type) => {
    const icons = {
      whatsapp: MessageCircle,
      sms: Phone,
      email: Mail
    };
    return icons[type] || MessageCircle;
  };

  const getMessageTypeColor = (type) => {
    const colors = {
      whatsapp: 'bg-green-500',
      sms: 'bg-blue-500',
      email: 'bg-purple-500'
    };
    return colors[type] || 'bg-gray-500';
  };

  return (
    <div className="space-y-4">
      {/* Tab Navigation */}
      <div className="flex gap-2 border-b">
        <Button
          variant={activeTab === 'send' ? 'default' : 'ghost'}
          onClick={() => setActiveTab('send')}
          className="rounded-b-none"
        >
          <Send className="w-4 h-4 mr-2" />
          Send Message
        </Button>
        <Button
          variant={activeTab === 'templates' ? 'default' : 'ghost'}
          onClick={() => setActiveTab('templates')}
          className="rounded-b-none"
        >
          <FileText className="w-4 h-4 mr-2" />
          Templates
        </Button>
        <Button
          variant={activeTab === 'auto' ? 'default' : 'ghost'}
          onClick={() => setActiveTab('auto')}
          className="rounded-b-none"
        >
          <Zap className="w-4 h-4 mr-2" />
          Auto-Messages
        </Button>
      </div>

      {/* Send Message Tab */}
      {activeTab === 'send' && (
        <Card>
          <CardHeader>
            <CardTitle>Send Message to Guest</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label>Guest ID</Label>
                  <Input
                    value={messageData.guest_id}
                    onChange={(e) => setMessageData({ ...messageData, guest_id: e.target.value })}
                    placeholder="Enter guest ID"
                  />
                </div>
                <div>
                  <Label>Booking ID (Optional)</Label>
                  <Input
                    value={messageData.booking_id}
                    onChange={(e) => setMessageData({ ...messageData, booking_id: e.target.value })}
                    placeholder="Enter booking ID"
                  />
                </div>
              </div>

              <div>
                <Label>Message Type</Label>
                <Select
                  value={messageData.message_type}
                  onValueChange={(value) => setMessageData({ ...messageData, message_type: value })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="whatsapp">
                      <div className="flex items-center gap-2">
                        <MessageCircle className="w-4 h-4" /> WhatsApp
                      </div>
                    </SelectItem>
                    <SelectItem value="sms">
                      <div className="flex items-center gap-2">
                        <Phone className="w-4 h-4" /> SMS
                      </div>
                    </SelectItem>
                    <SelectItem value="email">
                      <div className="flex items-center gap-2">
                        <Mail className="w-4 h-4" /> Email
                      </div>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label>Recipient (Phone/Email)</Label>
                <Input
                  value={messageData.recipient}
                  onChange={(e) => setMessageData({ ...messageData, recipient: e.target.value })}
                  placeholder="Enter phone number or email"
                />
              </div>

              <div>
                <Label>Message Content</Label>
                <Textarea
                  value={messageData.message_content}
                  onChange={(e) => setMessageData({ ...messageData, message_content: e.target.value })}
                  placeholder="Type your message here..."
                  rows={6}
                />
              </div>

              <Button onClick={handleSendMessage} disabled={loading} className="w-full">
                <Send className="w-4 h-4 mr-2" />
                {loading ? 'Sending...' : 'Send Message'}
              </Button>

              <div className="bg-blue-50 border-l-4 border-blue-500 p-4 text-sm">
                <strong>Note:</strong> Production integration with Twilio/WhatsApp Business API required.
                This is a simulated implementation.
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Templates Tab */}
      {activeTab === 'templates' && (
        <Card>
          <CardHeader>
            <CardTitle>Message Templates</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {templates.length === 0 ? (
                <div className="text-center text-gray-500 py-8">No templates available</div>
              ) : (
                templates.map((template, idx) => {
                  const Icon = getMessageTypeIcon(template.message_type);
                  return (
                    <Card key={idx} className="border-l-4 border-l-blue-500">
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between">
                          <div className="space-y-2 flex-1">
                            <div className="flex items-center gap-2">
                              <h3 className="font-semibold">{template.template_name}</h3>
                              <Badge className={getMessageTypeColor(template.message_type)}>
                                <Icon className="w-3 h-3 mr-1" />
                                {template.message_type}
                              </Badge>
                              {template.active && (
                                <Badge variant="outline" className="bg-green-50 text-green-700">
                                  Active
                                </Badge>
                              )}
                            </div>
                            <div className="text-sm text-gray-600">
                              <strong>Trigger:</strong> {template.trigger}
                            </div>
                            <div className="bg-gray-50 p-3 rounded text-sm">
                              {template.message_content}
                            </div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Auto-Messages Tab */}
      {activeTab === 'auto' && (
        <Card>
          <CardHeader>
            <CardTitle>Automatic Message Triggers</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <Card className="border-l-4 border-l-blue-500">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold mb-1">Pre-Arrival Messages</h3>
                      <p className="text-sm text-gray-600">
                        Send welcome messages to guests checking in tomorrow
                      </p>
                    </div>
                    <Button
                      onClick={() => handleTriggerAutoMessages('pre_arrival')}
                      disabled={loading}
                    >
                      <Zap className="w-4 h-4 mr-2" />
                      Trigger
                    </Button>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-l-4 border-l-green-500">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold mb-1">Check-in Reminders</h3>
                      <p className="text-sm text-gray-600">
                        Send check-in reminders to guests arriving today
                      </p>
                    </div>
                    <Button
                      onClick={() => handleTriggerAutoMessages('check_in_reminder')}
                      disabled={loading}
                    >
                      <Zap className="w-4 h-4 mr-2" />
                      Trigger
                    </Button>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-l-4 border-l-purple-500">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold mb-1">Post-Checkout Thank You</h3>
                      <p className="text-sm text-gray-600">
                        Send thank you messages to guests who checked out
                      </p>
                    </div>
                    <Button
                      onClick={() => handleTriggerAutoMessages('post_checkout')}
                      disabled={loading}
                    >
                      <Zap className="w-4 h-4 mr-2" />
                      Trigger
                    </Button>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-l-4 border-l-yellow-500">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold mb-1">Birthday Greetings</h3>
                      <p className="text-sm text-gray-600">
                        Send birthday wishes to guests celebrating today
                      </p>
                    </div>
                    <Button
                      onClick={() => handleTriggerAutoMessages('birthday')}
                      disabled={loading}
                    >
                      <Zap className="w-4 h-4 mr-2" />
                      Trigger
                    </Button>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-l-4 border-l-pink-500">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold mb-1">Anniversary Messages</h3>
                      <p className="text-sm text-gray-600">
                        Send anniversary greetings to celebrating guests
                      </p>
                    </div>
                    <Button
                      onClick={() => handleTriggerAutoMessages('anniversary')}
                      disabled={loading}
                    >
                      <Zap className="w-4 h-4 mr-2" />
                      Trigger
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default MessagingModuleAdvanced;