import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import {
  MessageCircle, Send, User, Hotel, Clock, Check, CheckCheck,
  Loader2, ArrowLeft, Tag
} from 'lucide-react';

const API = "";

const TYPE_LABELS = {
  general: { tr: 'Genel', en: 'General', color: 'bg-blue-100 text-blue-700' },
  request: { tr: 'Talep', en: 'Request', color: 'bg-green-100 text-green-700' },
  complaint: { tr: 'Şikayet', en: 'Complaint', color: 'bg-red-100 text-red-700' },
  feedback: { tr: 'Geri Bildirim', en: 'Feedback', color: 'bg-indigo-100 text-indigo-700' },
};

const GuestMessaging = ({ user, bookingId, isStaff = false }) => {
  const { t, i18n } = useTranslation();
  const token = localStorage.getItem('token');
  const messagesEndRef = useRef(null);

  const [conversations, setConversations] = useState([]);
  const [selectedConv, setSelectedConv] = useState(null);
  const [newMessage, setNewMessage] = useState('');
  const [messageType, setMessageType] = useState('general');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  const lang = i18n.language?.startsWith('tr') ? 'tr' : 'en';

  useEffect(() => {
    fetchMessages();
    fetchUnreadCount();
    const interval = setInterval(fetchMessages, 15000);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [bookingId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [selectedConv]);

  const fetchMessages = async () => {
    try {
      const url = bookingId
        ? `/api/guest/messages?booking_id=${bookingId}`
        : `/api/guest/messages`;
      const res = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!res.ok) return;
      const data = await res.json();
      setConversations(data.conversations || []);
      setUnreadCount(data.unread_total || 0);

      // Auto-select if only one conversation or bookingId provided
      if (data.conversations?.length === 1 && !selectedConv) {
        setSelectedConv(data.conversations[0]);
      }
    } catch { /* silent */ } finally {
      setLoading(false);
    }
  };

  const fetchUnreadCount = async () => {
    try {
      const res = await fetch(`/api/guest/messages/unread-count`, { credentials: "include",
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setUnreadCount(data.unread_count || 0);
      }
    } catch { /* silent */ }
  };

  const sendMessage = async () => {
    if (!newMessage.trim()) return;
    setSending(true);
    try {
      const res = await fetch(`/api/guest/messages`, { credentials: "include",
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          booking_id: bookingId || selectedConv?.booking_id,
          message: newMessage,
          message_type: messageType,
        }),
      });
      if (!res.ok) throw new Error();
      setNewMessage('');
      toast.success(t('guestPortal.sent') || 'Gönderildi');
      fetchMessages();
    } catch {
      toast.error(t('messages.error.generic'));
    } finally {
      setSending(false);
    }
  };

  const markAllRead = async () => {
    try {
      await fetch(`/api/guest/messages/mark-all-read${bookingId ? `?booking_id=${bookingId}` : ''}`, { credentials: "include",
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      fetchMessages();
    } catch { /* silent */ }
  };

  const formatTime = (dateStr) => {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    const now = new Date();
    const diff = (now - d) / 1000 / 60;
    if (diff < 1) return lang === 'tr' ? 'Şimdi' : 'Now';
    if (diff < 60) return `${Math.floor(diff)} ${lang === 'tr' ? 'dk' : 'min'}`;
    if (diff < 1440) return d.toLocaleTimeString(lang === 'tr' ? 'tr-TR' : 'en-US', { hour: '2-digit', minute: '2-digit' });
    return d.toLocaleDateString(lang === 'tr' ? 'tr-TR' : 'en-US', { day: 'numeric', month: 'short' });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
      </div>
    );
  }

  // Chat view for selected conversation or direct messaging
  const messages = selectedConv?.messages || [];

  return (
    <div className="space-y-4" data-testid="guest-messaging">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {selectedConv && isStaff && conversations.length > 1 && (
            <Button size="sm" variant="ghost" onClick={() => setSelectedConv(null)}>
              <ArrowLeft className="w-4 h-4" />
            </Button>
          )}
          <MessageCircle className="w-5 h-5 text-blue-600" />
          <h3 className="font-semibold text-gray-900">
            {t('guestPortal.guestMessaging') || 'Mesajlar'}
          </h3>
          {unreadCount > 0 && (
            <Badge className="bg-red-500 text-white text-xs">{unreadCount}</Badge>
          )}
        </div>
        {unreadCount > 0 && (
          <Button size="sm" variant="ghost" className="text-xs" onClick={markAllRead} data-testid="mark-all-read-btn">
            <CheckCheck className="w-3.5 h-3.5 mr-1" />
            {lang === 'tr' ? 'Tümünü Oku' : 'Mark All Read'}
          </Button>
        )}
      </div>

      {/* Conversation List (Staff view with multiple conversations) */}
      {isStaff && !selectedConv && conversations.length > 0 && (
        <div className="space-y-2" data-testid="conversation-list">
          {conversations.map((conv, i) => (
            <button
              key={i}
              onClick={() => { setSelectedConv(conv); markAllRead(); }}
              className="w-full text-left p-3 rounded-lg border hover:bg-blue-50 transition-all flex items-center justify-between"
              data-testid={`conv-${conv.booking_id || i}`}
            >
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-blue-100 flex items-center justify-center">
                  <User className="w-4 h-4 text-blue-600" />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-900">{conv.guest_name}</p>
                  <p className="text-xs text-gray-500">
                    {conv.room_number && `Oda ${conv.room_number} | `}
                    {conv.messages?.[0]?.message?.substring(0, 40)}...
                  </p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-[10px] text-gray-400">{formatTime(conv.last_message_at)}</p>
                {conv.unread_count > 0 && (
                  <Badge className="bg-red-500 text-white text-[10px] mt-1">{conv.unread_count}</Badge>
                )}
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Message Thread */}
      {(selectedConv || !isStaff || conversations.length <= 1) && (
        <Card className="border-gray-200" data-testid="message-thread">
          <CardContent className="p-0">
            {/* Messages */}
            <div className="h-64 overflow-y-auto p-3 space-y-3 bg-gray-50/50">
              {messages.length === 0 ? (
                <div className="text-center py-8 text-gray-400">
                  <MessageCircle className="w-10 h-10 mx-auto mb-2 opacity-30" />
                  <p className="text-sm">{t('guestPortal.noMessages') || 'Henüz mesaj yok'}</p>
                  <p className="text-xs mt-1">{lang === 'tr' ? 'İlk mesajınızı gönderin' : 'Send your first message'}</p>
                </div>
              ) : (
                messages.slice().reverse().map((msg) => {
                  const isMe = (isStaff && msg.sender === 'staff') || (!isStaff && msg.sender === 'guest');
                  const typeInfo = TYPE_LABELS[msg.message_type] || TYPE_LABELS.general;
                  return (
                    <div key={msg.id} className={`flex ${isMe ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[75%] ${isMe ? 'order-1' : ''}`}>
                        <div className={`rounded-2xl px-3.5 py-2 ${
                          isMe
                            ? 'bg-blue-600 text-white rounded-br-sm'
                            : 'bg-white border border-gray-200 text-gray-800 rounded-bl-sm'
                        }`}>
                          {!isMe && (
                            <p className={`text-[10px] font-medium mb-0.5 ${isMe ? 'text-blue-200' : 'text-gray-400'}`}>
                              {msg.sender === 'staff' ? (
                                <span className="flex items-center gap-1"><Hotel className="w-2.5 h-2.5" />{msg.sender_name}</span>
                              ) : msg.sender_name}
                            </p>
                          )}
                          <p className="text-sm whitespace-pre-wrap">{msg.message}</p>
                        </div>
                        <div className={`flex items-center gap-1.5 mt-0.5 px-1 ${isMe ? 'justify-end' : ''}`}>
                          {msg.message_type && msg.message_type !== 'general' && (
                            <Badge className={`${typeInfo.color} text-[8px] px-1 py-0`}>{typeInfo[lang]}</Badge>
                          )}
                          <span className="text-[10px] text-gray-400">{formatTime(msg.created_at)}</span>
                          {isMe && (
                            msg.read
                              ? <CheckCheck className="w-3 h-3 text-blue-400" />
                              : <Check className="w-3 h-3 text-gray-300" />
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="p-3 border-t bg-white">
              <div className="flex items-center gap-2">
                <Select value={messageType} onValueChange={setMessageType}>
                  <SelectTrigger className="w-28 h-8 text-xs" data-testid="message-type-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(TYPE_LABELS).map(([key, val]) => (
                      <SelectItem key={key} value={key}>{val[lang]}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  value={newMessage}
                  onChange={e => setNewMessage(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage()}
                  placeholder={t('guestPortal.messagePlaceholder') || 'Mesajınızı yazın...'}
                  className="flex-1 h-8 text-sm"
                  data-testid="message-input"
                />
                <Button
                  size="sm"
                  onClick={sendMessage}
                  disabled={sending || !newMessage.trim()}
                  className="h-8 px-3 bg-blue-600 hover:bg-blue-700"
                  data-testid="send-message-btn"
                >
                  {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default GuestMessaging;
