import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { MessageSquare, Send, Inbox, Archive, User, FileText } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const OTAMessagingHub = () => {
  const { t } = useTranslation();
  const [conversations, setConversations] = useState([]);
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState('');
  const [filter, setFilter] = useState('all'); // all, booking.com, airbnb, expedia
  const [loading, setLoading] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [showTemplates, setShowTemplates] = useState(false);
  const [upsellData, setUpsellData] = useState(null);

  useEffect(() => {
    loadConversations();
    loadTemplates();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [filter]);

  useEffect(() => {
    if (selectedConversation) {
      loadMessages(selectedConversation.id);
      loadUpsellForGuest(selectedConversation.guest_id);
    }
  }, [selectedConversation]);

  const loadTemplates = async () => {
    try {
      const response = await axios.get('/messaging-center/templates');
      const raw = response.data?.templates || response.data || [];
      // Backend {channel, body_template} → bileşen {type, content} bekliyor
      const normalized = (Array.isArray(raw) ? raw : []).map((t) => ({
        ...t,
        type: t.type ?? t.channel,
        content: t.content ?? t.body_template ?? '',
      }));
      setTemplates(normalized);
    } catch (error) {
      console.error('Failed to load templates:', error);
    }
  };

  const loadUpsellForGuest = async (guestId) => {
    if (!guestId) return;
    try {
      // Get AI upsell recommendations for this guest
      const response = await axios.get(`/ai/upsell/recommendations?guest_id=${guestId}`);
      setUpsellData(response.data);
    } catch (error) {
      console.error('Failed to load upsell data:', error);
      setUpsellData(null);
    }
  };

  const applyTemplate = (template) => {
    let message = template.content;
    
    // If it's an upgrade offer template and we have upsell data, auto-fill
    if (template.name.toLowerCase().includes('upgrade') && upsellData) {
      const bestOffer = upsellData.offers?.[0]; // Get highest priority offer
      if (bestOffer) {
        message = message
          .replace('{UPGRADE_TYPE}', bestOffer.type || 'Room Upgrade')
          .replace('{PRICE}', bestOffer.price || '99')
          .replace('{BENEFITS}', bestOffer.description || 'Enhanced comfort and amenities');
      }
    }
    
    // Replace other placeholders
    message = message
      .replace('{GUEST_NAME}', selectedConversation?.guest_name || 'Guest')
      .replace('{HOTEL_NAME}', 'Finance Test Hotel');
    
    setNewMessage(message);
    setShowTemplates(false);
    toast.success('Template applied with AI upsell data!');
  };

  const loadConversations = async () => {
    try {
      const params = filter !== 'all' ? { ota: filter } : {};
      const response = await axios.get('/ota/conversations', { params });
      setConversations(response.data.conversations || []);
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  };

  const loadMessages = async (conversationId) => {
    try {
      const response = await axios.get(`/ota/conversations/${conversationId}/messages`);
      setMessages(response.data.messages || []);
    } catch (error) {
      console.error('Failed to load messages:', error);
    }
  };

  const handleSendMessage = async () => {
    if (!newMessage.trim() || !selectedConversation) return;

    setLoading(true);
    try {
      await axios.post(`/ota/conversations/${selectedConversation.id}/messages`, {
        message: newMessage,
        channel: selectedConversation.ota_platform
      });

      toast.success('Message sent');
      setNewMessage('');
      loadMessages(selectedConversation.id);
    } catch (error) {
      toast.error('Mesaj gönderilemedi');
    } finally {
      setLoading(false);
    }
  };

  const getOTABadge = (ota) => {
    const colors = {
      'booking.com': 'bg-blue-100 text-blue-700',
      'airbnb': 'bg-red-100 text-red-700',
      'expedia': 'bg-yellow-100 text-yellow-700',
      'whatsapp': 'bg-green-100 text-green-700'
    };
    return colors[ota] || 'bg-gray-100 text-gray-700';
  };

  return (
    <div className="h-screen flex flex-col">
      <div className="bg-white border-b p-4">
        <h1 className="text-2xl font-bold mb-2">{t('nav.messaging')}</h1>
        <div className="flex gap-2">
          <Button
            variant={filter === 'all' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setFilter('all')}
          >
            All
          </Button>
          <Button
            variant={filter === 'booking.com' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setFilter('booking.com')}
          >
            Booking.com
          </Button>
          <Button
            variant={filter === 'airbnb' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setFilter('airbnb')}
          >
            Airbnb
          </Button>
          <Button
            variant={filter === 'expedia' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setFilter('expedia')}
          >
            Expedia
          </Button>
          <Button
            variant={filter === 'whatsapp' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setFilter('whatsapp')}
          >
            WhatsApp
          </Button>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Conversations List */}
        <div className="w-1/3 border-r overflow-y-auto">
          {conversations.map((conv) => (
            <div
              key={conv.id}
              onClick={() => setSelectedConversation(conv)}
              className={`p-4 border-b cursor-pointer hover:bg-gray-50 ${
                selectedConversation?.id === conv.id ? 'bg-blue-50' : ''
              }`}
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  <User className="w-5 h-5 text-gray-600" />
                  <span className="font-semibold">{conv.guest_name}</span>
                </div>
                <Badge className={getOTABadge(conv.ota_platform)}>
                  {conv.ota_platform}
                </Badge>
              </div>
              <p className="text-sm text-gray-600 truncate">{conv.last_message}</p>
              <div className="flex items-center justify-between mt-2">
                <span className="text-xs text-gray-500">
                  {new Date(conv.last_message_at).toLocaleDateString()}
                </span>
                {conv.unread_count > 0 && (
                  <Badge className="bg-red-500 text-white">{conv.unread_count}</Badge>
                )}
              </div>
            </div>
          ))}

          {conversations.length === 0 && (
            <div className="text-center py-12 text-gray-500">
              <Inbox className="w-16 h-16 mx-auto mb-4 text-gray-400" />
              No conversations
            </div>
          )}
        </div>

        {/* Messages Area */}
        <div className="flex-1 flex flex-col">
          {selectedConversation ? (
            <>
              {/* Header */}
              <div className="bg-white border-b p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="font-bold">{selectedConversation.guest_name}</h2>
                    <p className="text-sm text-gray-600">
                      Booking: {selectedConversation.booking_id?.slice(0, 8)}
                    </p>
                  </div>
                  <Badge className={getOTABadge(selectedConversation.ota_platform)}>
                    {selectedConversation.ota_platform}
                  </Badge>
                </div>
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex ${msg.sender === 'hotel' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-md p-3 rounded-lg ${
                        msg.sender === 'hotel'
                          ? 'bg-blue-600 text-white'
                          : 'bg-gray-100 text-gray-800'
                      }`}
                    >
                      <p>{msg.message}</p>
                      <span className="text-xs opacity-75">
                        {new Date(msg.sent_at).toLocaleTimeString()}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Message Input */}
              <div className="border-t p-4">
                {/* Template Selector - NEW */}
                <div className="mb-3">
                  <Button 
                    size="sm" 
                    variant="outline"
                    onClick={() => setShowTemplates(!showTemplates)}
                    className="text-xs"
                  >
                    <FileText className="w-3 h-3 mr-2" />
                    Message Templates {upsellData && '(Upsell Available)'}
                  </Button>
                  
                  {showTemplates && (
                    <div className="mt-2 p-3 bg-gray-50 rounded-lg border space-y-2 max-h-48 overflow-y-auto">
                      {/* Upgrade Offer Template (AI-Powered) */}
                      <div 
                        onClick={() => applyTemplate({
                          name: 'Upgrade Offer',
                          content: `Dear {GUEST_NAME},\n\nWe have an exclusive upgrade opportunity for you! \n\nUpgrade Type: {UPGRADE_TYPE}\nSpecial Price: ${upsellData?.offers?.[0]?.price || '99'}\n\n{BENEFITS}\n\nThis offer is valid for 24 hours. Reply YES to confirm!\n\nBest regards,\n{HOTEL_NAME}`
                        })}
                        className="p-3 bg-white rounded border hover:border-green-500 cursor-pointer hover:shadow-md transition"
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-semibold text-sm">Upgrade Offer</span>
                          {upsellData && (
                            <Badge className="bg-green-500 text-xs">AI-Powered</Badge>
                          )}
                        </div>
                        <p className="text-xs text-gray-600">
                          {upsellData ? 
                            `Auto-filled with AI upsell: ${upsellData.offers?.[0]?.type || 'Room Upgrade'} - $${upsellData.offers?.[0]?.price || '99'}` :
                            'Exclusive upgrade offer template'
                          }
                        </p>
                      </div>

                      {/* Other Templates */}
                      {templates.map((template, idx) => (
                        <div 
                          key={idx}
                          onClick={() => applyTemplate(template)}
                          className="p-3 bg-white rounded border hover:border-blue-500 cursor-pointer hover:shadow-md transition"
                        >
                          <span className="font-semibold text-sm">{template.name}</span>
                          <p className="text-xs text-gray-600 truncate">{template.content.substring(0, 60)}...</p>
                        </div>
                      ))}
                      
                      {templates.length === 0 && (
                        <div className="text-xs text-gray-500 text-center py-2">
                          No templates found. Create templates in Settings.
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div className="flex gap-2">
                  <Textarea
                    value={newMessage}
                    onChange={(e) => setNewMessage(e.target.value)}
                    placeholder="Type your message..."
                    rows={3}
                    onKeyPress={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleSendMessage();
                      }
                    }}
                    className={upsellData ? 'border-green-300' : ''}
                  />
                  <Button onClick={handleSendMessage} disabled={loading || !newMessage.trim()}>
                    <Send className="w-4 h-4" />
                  </Button>
                </div>
                
                {/* Upsell Data Indicator */}
                {upsellData && upsellData.offers?.length > 0 && (
                  <div className="mt-2 p-2 bg-green-50 border border-green-200 rounded text-xs">
                    AI Upsell Available: {upsellData.offers[0].type} - ${upsellData.offers[0].price} 
                    <span className="text-green-700 ml-2">({Math.round(upsellData.offers[0].confidence * 100)}% confidence)</span>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-gray-500">
              <div className="text-center">
                <MessageSquare className="w-16 h-16 mx-auto mb-4 text-gray-400" />
                <p>Select a conversation to start messaging</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default OTAMessagingHub;