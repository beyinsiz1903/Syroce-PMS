import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Home, MessageCircle, Send, Bot, CheckCircle, Clock } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

const AIWhatsAppConcierge = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [conversations, setConversations] = useState([]);
  const [testMessage, setTestMessage] = useState('');
  const [testPhone, setTestPhone] = useState('+90 555 123 45 67');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadConversations();
  }, []);

  const loadConversations = async () => {
    try {
      const response = await axios.get('/ai-concierge/conversations');
      setConversations(response.data.conversations || []);
    } catch (error) {
      console.error('Conversations yüklenemedi');
    }
  };

  const sendTestMessage = async () => {
    if (!testMessage.trim()) return;
    
    setLoading(true);
    try {
      const response = await axios.post('/ai-concierge/whatsapp', {
        phone: testPhone,
        message: testMessage
      });
      
      toast.success('AI yanıtı: ' + response.data.response.substring(0, 100) + '...');
      setTestMessage('');
      loadConversations();
    } catch (error) {
      toast.error(t('messages.error.generic'));
    } finally {
      setLoading(false);
    }
  };

  const exampleMessages = [
    'Odama 2 havlu gönder',
    'Saat 20:00 için restoran rezervasyonu',
    'Check-out saatimi 16:00\'e uzat',
    'Yarın spa randevusu almak istiyorum'
  ];

  return (
    <div className="p-6">
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <Button 
            variant="outline" 
            size="icon"
            onClick={() => navigate('/')}
            className="hover:bg-green-50"
          >
            <Home className="w-5 h-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold">🤖 AI WhatsApp Concierge</h1>
            <p className="text-gray-600">24/7 Otomatik misafir hizmeti - Sıfır insan müdahalesi</p>
          </div>
        </div>
      </div>

      {/* Feature Highlights */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <Card className="bg-green-50 border-green-200">
          <CardContent className="pt-6 text-center">
            <Clock className="w-10 h-10 text-green-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">24/7</p>
            <p className="text-sm text-gray-600">Kesintisiz Hizmet</p>
          </CardContent>
        </Card>
        <Card className="bg-blue-50 border-blue-200">
          <CardContent className="pt-6 text-center">
            <Bot className="w-10 h-10 text-blue-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">AI</p>
            <p className="text-sm text-gray-600">GPT-4 Powered</p>
          </CardContent>
        </Card>
        <Card className="bg-indigo-50 border-indigo-200">
          <CardContent className="pt-6 text-center">
            <MessageCircle className="w-10 h-10 text-indigo-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">{conversations.length}</p>
            <p className="text-sm text-gray-600">Conversation</p>
          </CardContent>
        </Card>
        <Card className="bg-amber-50 border-amber-200">
          <CardContent className="pt-6 text-center">
            <CheckCircle className="w-10 h-10 text-amber-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">
              {conversations.filter(c => c.action_taken).length}
            </p>
            <p className="text-sm text-gray-600">Oto. Aksiyon</p>
          </CardContent>
        </Card>
      </div>

      {/* Test Interface */}
      <Card className="mb-6 bg-gradient-to-r from-green-50 to-blue-50">
        <CardHeader>
          <CardTitle>🧪 Test Interface - AI Concierge Deneyin</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium">Telefon Numarası</label>
              <Input
                value={testPhone}
                onChange={(e) => setTestPhone(e.target.value)}
                placeholder="+90 555 123 45 67"
              />
            </div>
            <div>
              <label className="text-sm font-medium">Mesaj</label>
              <Input
                value={testMessage}
                onChange={(e) => setTestMessage(e.target.value)}
                placeholder="Örn: Odama 2 havlu gönder"
                onKeyPress={(e) => e.key === 'Enter' && sendTestMessage()}
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <p className="text-xs text-gray-600 w-full mb-2">Hızlı test mesajları:</p>
              {exampleMessages.map((msg, idx) => (
                <Button
                  key={idx}
                  variant="outline"
                  size="sm"
                  onClick={() => setTestMessage(msg)}
                >
                  {msg}
                </Button>
              ))}
            </div>
            <Button 
              className="w-full bg-green-600 hover:bg-green-700"
              onClick={sendTestMessage}
              disabled={loading}
            >
              <Send className="w-4 h-4 mr-2" />
              {loading ? 'Gönderiliyor...' : 'AI Concierge\'a Gönder'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Conversation History */}
      <Card>
        <CardHeader>
          <CardTitle>Son Conversation'lar</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {conversations.length === 0 ? (
              <div className="text-center py-8">
                <MessageCircle className="w-16 h-16 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-600">Henüz conversation yok</p>
                <p className="text-sm text-gray-500 mt-2">Yukarıdaki test interface ile deneyin</p>
              </div>
            ) : (
              conversations.map((conv) => (
                <Card key={conv.id} className="bg-gray-50">
                  <CardContent className="pt-4">
                    <div className="space-y-3">
                      <div className="flex items-start gap-3">
                        <div className="bg-blue-100 p-2 rounded-lg">
                          <MessageCircle className="w-5 h-5 text-blue-600" />
                        </div>
                        <div className="flex-1">
                          <p className="text-sm text-gray-600 mb-1">Misafir:</p>
                          <p className="font-medium">{conv.user_message}</p>
                        </div>
                      </div>
                      <div className="flex items-start gap-3">
                        <div className="bg-green-100 p-2 rounded-lg">
                          <Bot className="w-5 h-5 text-green-600" />
                        </div>
                        <div className="flex-1">
                          <p className="text-sm text-gray-600 mb-1">AI Concierge:</p>
                          <p className="text-sm">{conv.ai_response}</p>
                          {conv.action_taken && (
                            <Badge className="mt-2 bg-green-600">
                              ✅ Aksiyon: {conv.action_taken}
                            </Badge>
                          )}
                        </div>
                      </div>
                      <p className="text-xs text-gray-500">
                        {new Date(conv.created_at).toLocaleString('tr-TR')}
                      </p>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default AIWhatsAppConcierge;