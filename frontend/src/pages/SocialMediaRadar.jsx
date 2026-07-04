import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { 
  Instagram, Twitter, Facebook, TrendingUp, AlertTriangle, Heart, 
  MessageCircle, Info, RefreshCw, Loader2, Shield, Bot, Sparkles, 
  CheckCircle2, CornerDownRight, Settings, Inbox, LayoutDashboard, 
  Send, Unlink, Link2, Search, CheckCircle, Clock, Activity, Zap, Plus, Edit2, Trash2 
} from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Input } from '@/components/ui/input';

const MOCK_INBOX_LIST = [
  { id: 1, platform: 'instagram', user: 'travel_lover99', name: 'Mark Smith', lastMessage: 'Odalarda wifi çekmiyor.', time: '09:15', unread: 1, status: 'open' },
  { id: 2, platform: 'instagram', user: 'jane_doe', name: 'Jane Doe', lastMessage: 'Harika bir tatildi, teşekkürler!', time: '10:42', unread: 0, status: 'resolved' },
  { id: 3, platform: 'facebook', user: 'ayse_k', name: 'Ayşe Kaya', lastMessage: 'Erken giriş (early check-in) yapabilir miyim?', time: 'Dün', unread: 2, status: 'open' },
  { id: 4, platform: 'twitter', user: 'tech_guy', name: 'John Doe', lastMessage: '@syroce_hotel harika bir deneyimdi', time: 'Dün', unread: 0, status: 'resolved' },
];

const MOCK_CHATS_DATA = {
  1: [
    { id: 101, sender: 'user', text: 'Merhaba, odalarda wifi neden bu kadar yavaş?', time: '09:10' },
    { id: 102, sender: 'hotel', text: 'Merhaba Mark Bey, yaşadığınız sorun için özür dileriz. Teknik ekibimizi hemen odanıza yönlendiriyorum.', time: '09:12' },
    { id: 103, sender: 'user', text: 'Teşekkürler, bekliyorum.', time: '09:15' },
  ],
  2: [
    { id: 201, sender: 'hotel', text: 'Merhaba Jane Hanım, konaklamanız nasıldı?', time: 'Dün' },
    { id: 202, sender: 'user', text: 'Harika bir tatildi, teşekkürler!', time: '10:42' },
  ],
  3: [
    { id: 301, sender: 'user', text: 'Merhaba, yarınki rezervasyonum için erken giriş (early check-in) yapabilir miyim?', time: 'Dün' },
    { id: 302, sender: 'user', text: 'Saat 10:00 gibi otelde olacağım.', time: 'Dün' },
  ],
  4: [
    { id: 401, sender: 'user', text: '@syroce_hotel harika bir deneyimdi', time: 'Dün' },
    { id: 402, sender: 'hotel', text: 'Bizi tercih ettiğiniz için çok teşekkür ederiz! Sizi tekrar ağırlamak dileğiyle.', time: 'Dün' },
  ]
};

const SocialMediaRadar = () => {
  const { t } = useTranslation();
  
  // Tab State
  const [activeTab, setActiveTab] = useState('radar');
  
  // Connection State
  const [connections, setConnections] = useState({
    instagram: false,
    facebook: false,
    twitter: false
  });
  const [showConnectModal, setShowConnectModal] = useState(false);
  const [connectingProvider, setConnectingProvider] = useState(null);
  
  // Radar State
  const [mentions, setMentions] = useState([]);
  const [sentiment, setSentiment] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [replyingTo, setReplyingTo] = useState(null);
  const [replyText, setReplyText] = useState('');
  const [isSendingReply, setIsSendingReply] = useState(false);

  // Inbox State
  const [inboxList, setInboxList] = useState(MOCK_INBOX_LIST);
  const [selectedChat, setSelectedChat] = useState(inboxList[0]);
  const [chatHistories, setChatHistories] = useState(MOCK_CHATS_DATA);
  const [chatMessage, setChatMessage] = useState('');
  const [isAiGenerating, setIsAiGenerating] = useState(false);
  
  const currentChatHistory = chatHistories[selectedChat.id] || [];
  const [isAddRuleModalOpen, setIsAddRuleModalOpen] = useState(false);
  const [newRule, setNewRule] = useState({ name: '', keywords: '', reply: '' });

  const [automationRules, setAutomationRules] = useState([
    { id: 1, name: 'Wi-Fi Şifresi', keywords: ['wifi', 'internet', 'şifre', 'bağlan'], reply: 'Değerli misafirimiz, geçerli Wi-Fi ağımız "Syroce Guest", şifremiz ise "Syroce2026"dır.', active: true },
    { id: 2, name: 'Check-in / Check-out', keywords: ['check-in', 'giriş saati', 'çıkış saati', 'erken giriş'], reply: 'Giriş (check-in) saatimiz 14:00, çıkış (check-out) saatimiz 12:00\'dir.', active: true },
    { id: 3, name: 'Kahvaltı Saatleri', keywords: ['kahvaltı', 'sabah', 'yemek'], reply: 'Kahvaltımız her sabah 07:00 - 10:30 arasında servis edilmektedir.', active: false },
  ]);


  const anyConnected = connections.instagram || connections.facebook || connections.twitter;

  const loadMockData = () => {
    setSentiment({
      total_mentions: 1243,
      positive: 856,
      neutral: 312,
      negative: 75,
      data_available: true
    });
    setMentions([
      { id: 1, platform: 'instagram', username: 'travel_lover99', sentiment: 'positive', text: 'This hotel is absolutely stunning! Best vacation ever. 🌴✨', engagement: 450, posted_at: new Date().toISOString() },
      { id: 2, platform: 'facebook', username: 'foodie_explorer', sentiment: 'positive', text: 'The breakfast buffet here is out of this world.', engagement: 120, posted_at: new Date(Date.now() - 3600000).toISOString() },
      { id: 3, platform: 'twitter', username: 'business_traveler', sentiment: 'neutral', text: 'Good location, but the wifi was a bit slow in the lobby.', engagement: 15, posted_at: new Date(Date.now() - 7200000).toISOString() }
    ]);
    setAlerts([
      { description: 'Birden fazla platformda Wi-Fi şikayeti', recommended_action: 'Teknik ekibi bilgilendirin' }
    ]);
  };

  const getPlatformIcon = (platform, size="w-4 h-4") => {
    switch(platform) {
      case 'instagram': return <Instagram className={`${size} text-pink-600`} />;
      case 'twitter': return <Twitter className={`${size} text-blue-500`} />;
      case 'facebook': return <Facebook className={`${size} text-blue-700`} />;
      default: return <MessageCircle className={`${size} text-slate-400`} />;
    }
  };

  const handleConnect = (provider) => {
    setConnectingProvider(provider);
    setTimeout(() => {
      setConnectingProvider(null);
      setShowConnectModal(false);
      setConnections(prev => ({ ...prev, [provider]: true }));
      toast.success(`${provider.charAt(0).toUpperCase() + provider.slice(1)} hesabı başarıyla bağlandı!`);
      if (!anyConnected) {
        loadMockData(); // Load data on first connection
      }
    }, 1500);
  };

  const handleDisconnect = (provider) => {
    setConnections(prev => ({ ...prev, [provider]: false }));
    toast.success(`${provider.charAt(0).toUpperCase() + provider.slice(1)} hesabı bağlantısı kesildi.`);
    // If all disconnected, clear data
    if (Object.values({ ...connections, [provider]: false }).every(v => !v)) {
      setMentions([]);
      setSentiment(null);
      setAlerts([]);
    }
  };

  const handleSendReply = () => {
    if (!replyText.trim()) return;
    setIsSendingReply(true);
    setTimeout(() => {
      setMentions(prev => prev.map(m => 
        m.id === replyingTo.id ? { ...m, replied: true, replyText: replyText, replyDate: new Date().toISOString() } : m
      ));
      setIsSendingReply(false);
      setReplyingTo(null);
      setReplyText('');
      toast.success('Cevabınız ilgili platform üzerinden misafire iletildi!');
    }, 1200);
  };

  const handleSendChat = () => {
    if (!chatMessage.trim()) return;
    const newMsg = { id: Date.now(), sender: 'hotel', text: chatMessage, time: new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }) };
    setChatHistories(prev => ({
      ...prev,
      [selectedChat.id]: [...(prev[selectedChat.id] || []), newMsg]
    }));
    setChatMessage('');
    toast.success('Mesaj iletildi');
  };

  const generateAIResponse = (contextMessage, setterFunction) => {
    setIsAiGenerating(true);
    setterFunction("AI yanıt oluşturuyor...");
    
    setTimeout(() => {
      let aiResponse = "";
      const lowerMsg = (contextMessage || "").toLowerCase();
      
      if (lowerMsg.includes("wifi") || lowerMsg.includes("yavaş") || lowerMsg.includes("çekmiyor")) {
        aiResponse = "Merhaba, yaşadığınız bağlantı sorunu için içtenlikle özür dileriz. Teknik ekibimizi hemen bilgilendirdik, sorun en kısa sürede çözülecektir.";
      } else if (lowerMsg.includes("harika") || lowerMsg.includes("teşekkür") || lowerMsg.includes("stunning") || lowerMsg.includes("süper")) {
        aiResponse = "Güzel sözleriniz için çok teşekkür ederiz! Sizi otelimizde ağırlamaktan büyük mutluluk duyduk. Bir sonraki tatilinizde tekrar görüşmek üzere.";
      } else if (lowerMsg.includes("erken") || lowerMsg.includes("check-in") || lowerMsg.includes("giriş")) {
        aiResponse = "Merhaba, erken giriş (early check-in) talebinizi not aldık. Oda müsaitliğine göre size yardımcı olmaktan memnuniyet duyarız. Geldiğinizde resepsiyona başvurabilirsiniz.";
      } else {
        aiResponse = "Geri bildiriminiz için teşekkür ederiz. Size nasıl daha fazla yardımcı olabiliriz?";
      }
      
      setterFunction(aiResponse);
      setIsAiGenerating(false);
    }, 1500);
  };


  const handleSaveRule = () => {
    if (!newRule.name || !newRule.keywords || !newRule.reply) {
      toast.error('Lütfen tüm alanları doldurun.');
      return;
    }
    const keywordArray = newRule.keywords.split(',').map(k => k.trim()).filter(k => k);
    const ruleObj = {
      id: Date.now(),
      name: newRule.name,
      keywords: keywordArray,
      reply: newRule.reply,
      active: true
    };
    setAutomationRules([ruleObj, ...automationRules]);
    setIsAddRuleModalOpen(false);
    setNewRule({ name: '', keywords: '', reply: '' });
    toast.success('Yeni kural başarıyla eklendi ve aktif edildi!');
  };

  const toggleChatStatus = () => {
    const newStatus = selectedChat.status === 'open' ? 'resolved' : 'open';
    const updatedChat = { ...selectedChat, status: newStatus };
    
    setInboxList(prev => prev.map(chat => chat.id === selectedChat.id ? updatedChat : chat));
    setSelectedChat(updatedChat);
    
    if (newStatus === 'resolved') {
      toast.success('Mesaj arşive kaldırıldı ve kapatıldı olarak işaretlendi.');
    } else {
      toast.success('Mesaj yeniden açıldı.');
    }
  };

  const renderRadarTab = () => (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* Crisis Alerts */}
      {alerts.length > 0 && (
        <Card className="border border-red-200 bg-gradient-to-r from-red-50 to-white shadow-sm">
          <CardHeader className="pb-3 border-b border-red-100">
            <CardTitle className="flex items-center gap-2 text-red-700 text-sm uppercase tracking-wider font-bold">
              <AlertTriangle className="w-5 h-5 text-red-500" />
              Kriz Uyarısı Tespit Edildi
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            <div className="space-y-3">
              {alerts.map((alert, idx) => (
                <div key={idx} className="bg-white border border-red-100 p-4 rounded-xl shadow-sm">
                  <p className="font-semibold text-slate-800">{alert.description}</p>
                  <div className="mt-3 flex items-start gap-2 bg-red-50/50 p-3 rounded-lg text-sm text-red-800">
                    <TrendingUp className="w-4 h-4 shrink-0 mt-0.5" />
                    <span><strong>Önerilen Aksiyon:</strong> {alert.recommended_action}</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Sentiment Summary */}
      {sentiment && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Card className="shadow-sm border-slate-200 hover:shadow-md transition-shadow group">
            <CardContent className="p-6 text-center">
              <div className="w-12 h-12 bg-indigo-50 rounded-2xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform">
                <MessageCircle className="w-6 h-6 text-indigo-600" />
              </div>
              <p className="text-3xl font-bold text-slate-800 tracking-tight">{sentiment.total_mentions}</p>
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mt-1">Toplam Mention</p>
            </CardContent>
          </Card>
          <Card className="shadow-sm border-slate-200 hover:shadow-md transition-shadow group">
            <CardContent className="p-6 text-center">
              <div className="w-12 h-12 bg-emerald-50 rounded-2xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform">
                <Heart className="w-6 h-6 text-emerald-600" />
              </div>
              <p className="text-3xl font-bold text-slate-800 tracking-tight">{sentiment.positive}</p>
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mt-1">Pozitif Etkileşim</p>
            </CardContent>
          </Card>
          <Card className="shadow-sm border-slate-200 hover:shadow-md transition-shadow group">
            <CardContent className="p-6 text-center">
              <div className="w-12 h-12 bg-amber-50 rounded-2xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform">
                <MessageCircle className="w-6 h-6 text-amber-600" />
              </div>
              <p className="text-3xl font-bold text-slate-800 tracking-tight">{sentiment.neutral}</p>
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mt-1">Nötr</p>
            </CardContent>
          </Card>
          <Card className="shadow-sm border-slate-200 hover:shadow-md transition-shadow group">
            <CardContent className="p-6 text-center">
              <div className="w-12 h-12 bg-red-50 rounded-2xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform">
                <AlertTriangle className="w-6 h-6 text-red-600" />
              </div>
              <p className="text-3xl font-bold text-slate-800 tracking-tight">{sentiment.negative}</p>
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mt-1">Negatif Risk</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Recent Mentions */}
      <Card className="shadow-sm border-slate-200">
        <CardHeader className="border-b border-slate-100 bg-slate-50/50 pb-4">
          <CardTitle className="text-base font-semibold text-slate-800 flex justify-between items-center">
            Son Mention'lar (24 Saat)
            <Badge variant="outline" className="bg-white text-slate-600 shadow-sm">
              {mentions.length} Kayıt
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-slate-100">
            {mentions.map((mention) => (
              <div key={mention.id} className="p-6 flex flex-col md:flex-row items-start justify-between gap-6 hover:bg-slate-50/80 transition-colors">
                <div className="flex-1 w-full">
                  <div className="flex flex-wrap items-center gap-3 mb-2">
                    <div className="flex items-center gap-1.5 bg-white border border-slate-200 px-2.5 py-1 rounded-full text-xs font-semibold text-slate-700 shadow-sm">
                      {getPlatformIcon(mention.platform)}
                      @{mention.username}
                    </div>
                    <Badge className={`px-2 py-0.5 shadow-sm text-[10px] uppercase font-bold tracking-wider ${
                      mention.sentiment === 'positive' ? 'bg-emerald-100 text-emerald-700' :
                      mention.sentiment === 'negative' ? 'bg-red-100 text-red-700' :
                      'bg-slate-100 text-slate-700'
                    }`}>
                      {mention.sentiment}
                    </Badge>
                    <span className="text-xs text-slate-400 font-medium ml-auto md:ml-0">
                      {new Date(mention.posted_at).toLocaleString('tr-TR')}
                    </span>
                  </div>
                  <p className="text-sm text-slate-700 leading-relaxed bg-white border border-slate-100 p-3 rounded-lg shadow-sm">
                    "{mention.text}"
                  </p>
                  {mention.replied && (
                    <div className="mt-3 ml-4 flex items-start gap-2">
                      <CornerDownRight className="w-4 h-4 text-slate-400 mt-1 shrink-0" />
                      <div className="bg-indigo-50 border border-indigo-100 p-3 rounded-lg text-sm text-indigo-900 flex-1 shadow-sm">
                        <strong>Yanıtınız:</strong> {mention.replyText}
                        <div className="text-[10px] text-indigo-400 mt-1 font-medium">{new Date(mention.replyDate).toLocaleString('tr-TR')}</div>
                      </div>
                    </div>
                  )}
                  <div className="flex items-center gap-4 mt-3 text-xs text-slate-500 font-medium">
                    <div className="flex items-center gap-1">
                      <TrendingUp className="w-3.5 h-3.5 text-slate-400" />
                      {mention.engagement} Etkileşim
                    </div>
                  </div>
                </div>
                {mention.replied ? (
                  <div className="shrink-0 w-full md:w-auto text-emerald-600 flex items-center gap-1.5 text-sm font-semibold bg-emerald-50 px-3 py-2 rounded-lg border border-emerald-100">
                    <CheckCircle2 className="w-4 h-4" />
                    Yanıtlandı
                  </div>
                ) : (
                  <Button size="sm" variant="outline" className="shrink-0 w-full md:w-auto shadow-sm" onClick={() => setReplyingTo(mention)}>
                    Yanıtla
                  </Button>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );

  const renderInboxTab = () => (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm flex h-[600px] overflow-hidden animate-in fade-in duration-500">
      {/* Sidebar */}
      <div className="w-1/3 border-r border-slate-200 flex flex-col bg-slate-50/50">
        <div className="p-4 border-b border-slate-200 bg-white">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
            <Input placeholder="Mesajlarda ara..." className="pl-9 h-10 bg-slate-50 border-slate-200 text-sm" />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          {inboxList.map((chat) => (
            <div 
              key={chat.id} 
              onClick={() => setSelectedChat(chat)}
              className={`p-4 border-b border-slate-100 cursor-pointer transition-colors ${selectedChat.id === chat.id ? 'bg-indigo-50/80 border-indigo-100' : 'hover:bg-white'} ${chat.status === 'resolved' ? 'opacity-70 grayscale-[0.2]' : ''}`}
            >
              <div className="flex justify-between items-start mb-1">
                <div className="flex items-center gap-2">
                  {getPlatformIcon(chat.platform, "w-3.5 h-3.5")}
                  <span className={`font-semibold text-sm truncate ${chat.status === 'resolved' ? 'text-slate-500 line-through' : 'text-slate-900'}`}>{chat.name}</span>
                </div>
                <span className="text-[10px] text-slate-400 whitespace-nowrap">{chat.time}</span>
              </div>
              <div className="flex justify-between items-center gap-2">
                <p className={`text-xs truncate ${chat.unread > 0 ? 'font-semibold text-slate-800' : 'text-slate-500'}`}>
                  {chat.lastMessage}
                </p>
                {chat.unread > 0 && (
                  <Badge className="bg-indigo-600 hover:bg-indigo-600 shrink-0 w-5 h-5 p-0 flex items-center justify-center text-[10px]">
                    {chat.unread}
                  </Badge>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
      
      {/* Chat Area */}
      <div className="flex-1 flex flex-col bg-slate-50/30">
        <div className="p-4 border-b border-slate-200 bg-white flex justify-between items-center shadow-sm z-10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center border border-slate-200">
              {getPlatformIcon(selectedChat.platform, "w-5 h-5")}
            </div>
            <div>
              <h3 className="font-bold text-slate-900 text-sm">{selectedChat.name}</h3>
              <p className="text-xs text-slate-500">@{selectedChat.user}</p>
            </div>
          </div>
          <Button 
            variant={selectedChat.status === 'resolved' ? 'secondary' : 'outline'} 
            size="sm" 
            className={`h-8 text-xs shadow-sm ${selectedChat.status === 'resolved' ? 'bg-slate-100 text-slate-600' : 'border-slate-200'}`}
            onClick={toggleChatStatus}
          >
            <CheckCircle className="w-3.5 h-3.5 mr-1.5" /> 
            {selectedChat.status === 'resolved' ? 'Yeniden Aç' : 'Kapatıldı İşaretle'}
          </Button>
        </div>
        
        <div className="flex-1 p-4 overflow-y-auto space-y-4">
          {currentChatHistory.map((msg) => (
            <div key={msg.id} className={`flex ${msg.sender === 'hotel' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[70%] rounded-2xl px-4 py-2.5 text-sm shadow-sm relative ${
                msg.sender === 'hotel' 
                  ? 'bg-indigo-600 text-white rounded-br-none' 
                  : 'bg-white border border-slate-200 text-slate-800 rounded-bl-none'
              }`}>
                {msg.text}
                <div className={`text-[9px] mt-1 text-right ${msg.sender === 'hotel' ? 'text-indigo-200' : 'text-slate-400'}`}>
                  {msg.time}
                </div>
              </div>
            </div>
          ))}
        </div>
        
        <div className="p-4 bg-white border-t border-slate-200">
           <div className="flex items-center gap-2 mb-3">
             <Button variant="outline" size="sm" className="h-7 text-[11px] bg-slate-50" onClick={() => setChatMessage("Merhaba, size nasıl yardımcı olabilirim?")}>
                <Sparkles className="w-3 h-3 mr-1" /> Karşılama Şablonu
             </Button>
             <Button 
               variant="outline" 
               size="sm" 
               className="h-7 text-[11px] text-indigo-600 bg-indigo-50 border-indigo-200" 
               onClick={() => generateAIResponse(selectedChat.lastMessage, setChatMessage)}
               disabled={isAiGenerating}
             >
                {isAiGenerating ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Bot className="w-3 h-3 mr-1" />} AI ile Yanıtla
             </Button>
           </div>
           <div className="flex items-end gap-2">
            <textarea
              className="flex-1 border border-slate-200 rounded-xl p-3 text-sm resize-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 shadow-sm min-h-[60px]"
              placeholder="Mesajınızı yazın..."
              value={chatMessage}
              onChange={(e) => setChatMessage(e.target.value)}
            />
            <Button className="h-12 w-12 rounded-xl bg-indigo-600 hover:bg-indigo-700 shadow-sm shrink-0" onClick={handleSendChat}>
              <Send className="w-5 h-5 text-white ml-1" />
            </Button>
           </div>
        </div>
      </div>
    </div>
  );

  
  const renderAutomationTab = () => (
    <div className="max-w-4xl mx-auto space-y-6 animate-in fade-in duration-500">
      <div className="flex justify-between items-center bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <div>
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <Zap className="w-5 h-5 text-amber-500" /> Kural Tabanlı Otomasyon
          </h2>
          <p className="text-sm text-slate-500 mt-1">Sık sorulan soruları yapay zeka maliyeti ödemeden, belirlediğiniz anahtar kelimelere göre otomatik yanıtlayın.</p>
        </div>
        <Button onClick={() => setIsAddRuleModalOpen(true)} className="bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm">
          <Plus className="w-4 h-4 mr-2" /> Yeni Kural Ekle
        </Button>
      </div>

      <div className="space-y-4">
        {automationRules.map((rule) => (
          <Card key={rule.id} className={`border-slate-200 shadow-sm transition-all ${rule.active ? 'border-l-4 border-l-emerald-500' : 'opacity-75 grayscale-[0.5]'}`}>
            <CardContent className="p-5 flex flex-col md:flex-row gap-6">
              <div className="flex-1 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="font-bold text-slate-900 text-base">{rule.name}</h3>
                  <Badge variant="outline" className={rule.active ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-slate-100 text-slate-500'}>
                    {rule.active ? 'Aktif (Dinliyor)' : 'Pasif'}
                  </Badge>
                </div>
                <div>
                  <div className="text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wider">Tetikleyici Kelimeler (Keywords)</div>
                  <div className="flex flex-wrap gap-1.5">
                    {rule.keywords.map(kw => (
                      <span key={kw} className="bg-slate-100 border border-slate-200 text-slate-700 text-xs px-2 py-0.5 rounded-md font-medium">
                        "{kw}"
                      </span>
                    ))}
                  </div>
                </div>
                <div className="pt-2">
                  <div className="text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wider">Otomatik Gönderilecek Yanıt</div>
                  <div className="bg-indigo-50/50 border border-indigo-100 text-indigo-900 text-sm p-3 rounded-lg flex items-start gap-2 relative">
                     <CornerDownRight className="w-4 h-4 text-indigo-300 mt-0.5 shrink-0" />
                     {rule.reply}
                  </div>
                </div>
              </div>
              <div className="flex flex-row md:flex-col items-center justify-center gap-2 border-t md:border-t-0 md:border-l border-slate-100 pt-4 md:pt-0 md:pl-6 shrink-0">
                <Button variant="outline" size="sm" className="w-full md:w-auto text-slate-600 hover:text-indigo-600">
                  <Edit2 className="w-3.5 h-3.5 md:mr-0 lg:mr-2" /> <span className="hidden lg:inline">Düzenle</span>
                </Button>
                <Button variant="outline" size="sm" className="w-full md:w-auto text-slate-600 hover:text-red-600">
                  <Trash2 className="w-3.5 h-3.5 md:mr-0 lg:mr-2" /> <span className="hidden lg:inline">Sil</span>
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );

  const renderSettingsTab = () => (
    <div className="max-w-3xl mx-auto space-y-6 animate-in fade-in duration-500">
      <Card className="border-slate-200 shadow-sm">
        <CardHeader className="bg-slate-50/50 border-b border-slate-100">
          <CardTitle className="flex items-center gap-2 text-slate-800 text-lg">
            <Shield className="w-5 h-5 text-indigo-600" /> Hesap Bağlantıları (OAuth)
          </CardTitle>
          <CardDescription>Sosyal medya hesaplarınızı yetkilendirerek mesajlarınızı ve mentionları senkronize edin.</CardDescription>
        </CardHeader>
        <CardContent className="p-6">
          <div className="space-y-4">
            {/* Instagram */}
            <div className="flex items-center justify-between p-4 border border-slate-200 rounded-xl bg-white shadow-sm hover:border-pink-200 transition-colors">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 bg-pink-50 rounded-full flex items-center justify-center shrink-0">
                  <Instagram className="w-6 h-6 text-pink-600" />
                </div>
                <div>
                  <h4 className="font-bold text-slate-900">Instagram Graph API</h4>
                  <p className="text-sm text-slate-500">Post yorumları, hikaye mentionları ve DM'ler</p>
                </div>
              </div>
              <div>
                {connections.instagram ? (
                  <Button variant="outline" className="border-red-200 text-red-600 hover:bg-red-50" onClick={() => handleDisconnect('instagram')}>
                    <Unlink className="w-4 h-4 mr-2" /> Bağlantıyı Kes
                  </Button>
                ) : (
                  <Button className="bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white" onClick={() => handleConnect('instagram')} disabled={connectingProvider}>
                    {connectingProvider === 'instagram' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Link2 className="w-4 h-4 mr-2" />} Bağlan
                  </Button>
                )}
              </div>
            </div>

            {/* Facebook */}
            <div className="flex items-center justify-between p-4 border border-slate-200 rounded-xl bg-white shadow-sm hover:border-blue-200 transition-colors">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 bg-blue-50 rounded-full flex items-center justify-center shrink-0">
                  <Facebook className="w-6 h-6 text-blue-600" />
                </div>
                <div>
                  <h4 className="font-bold text-slate-900">Facebook Messenger API</h4>
                  <p className="text-sm text-slate-500">Sayfa mesajları ve yorum takibi</p>
                </div>
              </div>
              <div>
                {connections.facebook ? (
                  <Button variant="outline" className="border-red-200 text-red-600 hover:bg-red-50" onClick={() => handleDisconnect('facebook')}>
                    <Unlink className="w-4 h-4 mr-2" /> Bağlantıyı Kes
                  </Button>
                ) : (
                  <Button className="bg-blue-600 hover:bg-blue-700 text-white" onClick={() => handleConnect('facebook')} disabled={connectingProvider}>
                     {connectingProvider === 'facebook' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Link2 className="w-4 h-4 mr-2" />} Bağlan
                  </Button>
                )}
              </div>
            </div>

            {/* Twitter */}
            <div className="flex items-center justify-between p-4 border border-slate-200 rounded-xl bg-white shadow-sm hover:border-slate-300 transition-colors">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 bg-slate-100 rounded-full flex items-center justify-center shrink-0">
                  <Twitter className="w-6 h-6 text-slate-800" />
                </div>
                <div>
                  <h4 className="font-bold text-slate-900">X (Twitter) API v2</h4>
                  <p className="text-sm text-slate-500">Bahsetmeler ve Direkt Mesajlar</p>
                </div>
              </div>
              <div>
                {connections.twitter ? (
                  <Button variant="outline" className="border-red-200 text-red-600 hover:bg-red-50" onClick={() => handleDisconnect('twitter')}>
                    <Unlink className="w-4 h-4 mr-2" /> Bağlantıyı Kes
                  </Button>
                ) : (
                  <Button className="bg-slate-900 hover:bg-black text-white" onClick={() => handleConnect('twitter')} disabled={connectingProvider}>
                     {connectingProvider === 'twitter' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Link2 className="w-4 h-4 mr-2" />} Bağlan
                  </Button>
                )}
              </div>
            </div>

          </div>
        </CardContent>
      </Card>
    </div>
  );

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-2">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <LayoutDashboard className="w-6 h-6 text-indigo-600" />
            Omnichannel Sosyal Medya Merkezi
          </h1>
          <p className="text-sm text-slate-500 mt-1">Tüm hesaplarınızı ve mesajlarınızı tek bir merkezden profesyonelce yönetin.</p>
        </div>
      </div>

      {!anyConnected && activeTab !== 'settings' ? (
        <Card className="shadow-sm border-indigo-100 overflow-hidden bg-gradient-to-br from-indigo-50/50 to-purple-50/30 mt-8">
          <CardContent className="flex flex-col items-center justify-center text-center p-16 space-y-4">
            <div className="w-20 h-20 bg-indigo-100 rounded-full flex items-center justify-center mb-2 shadow-sm">
              <Shield className="w-10 h-10 text-indigo-600" />
            </div>
            <h3 className="text-2xl font-bold text-slate-800 tracking-tight">Sosyal Medya Radarı Pasif</h3>
            <p className="text-slate-600 max-w-md mx-auto text-sm leading-relaxed">
              Veri toplamaya ve mesajları yönetmeye başlamak için en az bir sosyal medya hesabınızı (Instagram, Facebook veya X) bağlamanız gerekmektedir.
            </p>
            <div className="mt-6 pt-6 border-t border-indigo-200/50 w-full max-w-sm flex justify-center">
              <Button onClick={() => setActiveTab('settings')} className="bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm transition-colors h-11 px-8 text-base">
                <Settings className="w-5 h-5 mr-2" /> Ayarlar ve Bağlantılar
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full mt-4">
          <TabsList className="bg-slate-100/60 p-1 mb-6 rounded-xl border border-slate-200 inline-flex h-auto gap-1">
            <TabsTrigger value="radar" className="rounded-lg data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-indigo-600 px-6 py-2.5 transition-all font-semibold">
              <Activity className="w-4 h-4 mr-2" /> Genel Bakış (Radar)
            </TabsTrigger>
            <TabsTrigger value="inbox" className="rounded-lg data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-indigo-600 px-6 py-2.5 transition-all font-semibold relative">
              <Inbox className="w-4 h-4 mr-2" /> Gelen Kutusu (Inbox)
              {anyConnected && <span className="absolute top-2.5 right-3.5 w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>}
            </TabsTrigger>
            <TabsTrigger value="settings" className="rounded-lg data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-indigo-600 px-6 py-2.5 transition-all font-semibold">
              <Settings className="w-4 h-4 mr-2" /> Bağlantılar
            </TabsTrigger>
                      <TabsTrigger value="automation" className="rounded-lg data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-indigo-600 px-6 py-2.5 transition-all font-semibold">
              <Zap className="w-4 h-4 mr-2" /> Otomasyon
            </TabsTrigger>
          </TabsList>

          <TabsContent value="radar" className="outline-none">
            {renderRadarTab()}
          </TabsContent>

          <TabsContent value="inbox" className="outline-none">
            {renderInboxTab()}
          </TabsContent>

          <TabsContent value="settings" className="outline-none">
            {renderSettingsTab()}
          </TabsContent>
                  <TabsContent value="automation" className="outline-none">
            {renderAutomationTab()}
          </TabsContent>
        </Tabs>
      )}

      {/* Omnichannel Reply Modal for Radar Tab */}
      <Dialog open={!!replyingTo} onOpenChange={(open) => { if(!open) { setReplyingTo(null); setReplyText(''); } }}>
        <DialogContent className="bg-white border-slate-200 text-slate-900 sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-xl font-bold">
              <MessageCircle className="w-5 h-5 text-indigo-600" /> 
              Omnichannel Yanıt Merkezi
            </DialogTitle>
          </DialogHeader>
          {replyingTo && (
            <div className="space-y-4 pt-2">
              <div className="bg-slate-50 p-4 rounded-lg border border-slate-100 text-sm text-slate-700 italic relative">
                <div className="absolute top-2 right-2 text-slate-300">
                  <CornerDownRight className="w-4 h-4" />
                </div>
                "{replyingTo.text}"
                <div className="mt-3 flex items-center gap-2 text-xs font-semibold not-italic text-slate-500">
                  {getPlatformIcon(replyingTo.platform)} @{replyingTo.username}
                </div>
              </div>
              
              <div className="space-y-3">
                <textarea 
                  className="w-full min-h-[120px] p-3 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none resize-none shadow-sm"
                  placeholder="Misafire yanıtınızı buraya yazın..."
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                />
                
                <div className="flex flex-wrap items-center gap-2">
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className="text-xs bg-indigo-50 text-indigo-700 border-indigo-200 hover:bg-indigo-100 hover:text-indigo-800"
                    onClick={() => setReplyText(`Harika yorumunuz için teşekkür ederiz @${replyingTo.username}! Sizi tekrar ağırlamayı sabırsızlıkla bekliyoruz. ✨`)}
                  >
                    <Sparkles className="w-3.5 h-3.5 mr-1.5" /> Pozitif Şablon
                  </Button>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className="text-xs text-slate-600 hover:bg-slate-100 border-slate-200"
                    onClick={() => generateAIResponse(replyingTo.text, setReplyText)}
                    disabled={isAiGenerating}
                  >
                    {isAiGenerating ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Bot className="w-3.5 h-3.5 mr-1.5" />} AI ile Yanıtla
                  </Button>
                </div>
              </div>

              <div className="pt-4 flex justify-end gap-3 border-t border-slate-100">
                <Button variant="ghost" onClick={() => { setReplyingTo(null); setReplyText(''); }}>İptal</Button>
                <Button 
                  className="bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm" 
                  onClick={handleSendReply}
                  disabled={!replyText.trim() || isSendingReply}
                >
                  {isSendingReply ? <><Loader2 className="w-4 h-4 mr-2 animate-spin"/> Gönderiliyor...</> : 'Yanıtı Gönder'}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={isAddRuleModalOpen} onOpenChange={setIsAddRuleModalOpen}>
        <DialogContent className="bg-white border-slate-200 text-slate-900 sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-xl font-bold">
              <Zap className="w-5 h-5 text-amber-500" /> Yeni Otomasyon Kuralı Ekle
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <label className="text-sm font-semibold text-slate-700">Kural Adı</label>
              <Input 
                placeholder="Örn: Wi-Fi Şifresi, Check-in Saati" 
                value={newRule.name}
                onChange={(e) => setNewRule({...newRule, name: e.target.value})}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-semibold text-slate-700">Tetikleyici Kelimeler (Virgülle ayırın)</label>
              <Input 
                placeholder="Örn: wifi, şifre, internet" 
                value={newRule.keywords}
                onChange={(e) => setNewRule({...newRule, keywords: e.target.value})}
              />
              <p className="text-xs text-slate-500">Müşteri mesajında bu kelimelerden biri geçerse otomatik yanıt tetiklenir.</p>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-semibold text-slate-700">Otomatik Yanıt Şablonu</label>
              <textarea 
                className="w-full flex min-h-[100px] rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                placeholder="Bu kural tetiklendiğinde müşteriye gönderilecek otomatik mesajı yazın..."
                value={newRule.reply}
                onChange={(e) => setNewRule({...newRule, reply: e.target.value})}
              />
            </div>
          </div>
          <div className="flex justify-end gap-3 mt-4">
            <Button variant="outline" onClick={() => setIsAddRuleModalOpen(false)}>İptal</Button>
            <Button className="bg-indigo-600 hover:bg-indigo-700 text-white" onClick={handleSaveRule}>Kaydet ve Aktifleştir</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default SocialMediaRadar;
