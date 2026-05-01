import React, { useState, useEffect, lazy, Suspense } from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '@/components/Layout';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Bot, MessageCircle, Send, Brain, TrendingUp, Shield,
  Sparkles, BarChart3, Users, Zap, Clock, Star,
  Hotel, ChefHat, Wrench, DollarSign, Globe, Loader2,
  ArrowLeft, ChevronRight
} from 'lucide-react';

// Lazy load AI module components
const AIEnhancedPMS = lazy(() => import('@/pages/AIEnhancedPMS'));
const AIChatbot = lazy(() => import('@/pages/AIChatbot'));
const AIWhatsAppConcierge = lazy(() => import('@/pages/AIWhatsAppConcierge'));
const DynamicPricing = lazy(() => import('@/pages/DynamicPricing'));
const PredictiveAnalytics = lazy(() => import('@/pages/PredictiveAnalytics'));
const RevenueAutopilot = lazy(() => import('@/pages/RevenueAutopilot'));
const SocialMediaRadar = lazy(() => import('@/pages/SocialMediaRadar'));
import { useTranslation } from 'react-i18next';

// Module component map
const MODULE_COMPONENTS = {
  'ai-pms': AIEnhancedPMS,
  'ai-chatbot': AIChatbot,
  'ai-whatsapp-concierge': AIWhatsAppConcierge,
  'dynamic-pricing': DynamicPricing,
  'predictive-analytics': PredictiveAnalytics,
  'revenue-autopilot': RevenueAutopilot,
  'social-media-radar': SocialMediaRadar,
};

const AIModule = ({ user, tenant, onLogout, embedded = false }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedModule, setSelectedModule] = useState(null);
  const [chatMessages, setChatMessages] = useState([
    { sender: 'bot', message: t('aiModule.chatbotDesc'), timestamp: new Date() }
  ]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [briefing, setBriefing] = useState(null);
  const [briefingLoading, setBriefingLoading] = useState(false);
  const [pricingRec, setPricingRec] = useState(null);

  useEffect(() => {
    loadBriefing();
    loadPricingRecommendation();
  }, []);

  const loadBriefing = async () => {
    try {
      setBriefingLoading(true);
      const res = await axios.get('/ai/dashboard/briefing');
      setBriefing(res.data);
    } catch (err) {
      console.warn('AI briefing not available');
    } finally {
      setBriefingLoading(false);
    }
  };

  const loadPricingRecommendation = async () => {
    try {
      const res = await axios.get('/pricing/ai-recommendation');
      setPricingRec(res.data);
    } catch (err) {
      console.warn('AI pricing not available');
    }
  };

  const handleSendChat = async (e) => {
    e.preventDefault();
    if (!chatInput.trim()) return;

    const userMsg = { sender: 'user', message: chatInput, timestamp: new Date() };
    setChatMessages(prev => [...prev, userMsg]);
    setChatInput('');
    setChatLoading(true);

    try {
      const res = await axios.post('/ai/chat', { message: chatInput });
      const botMsg = { sender: 'bot', message: res.data.response || res.data.message || 'Yanıt alındı.', timestamp: new Date() };
      setChatMessages(prev => [...prev, botMsg]);
    } catch (err) {
      const errorMsg = { sender: 'bot', message: 'Üzgünüm, şu anda yanıt veremedim. Lütfen tekrar deneyin.', timestamp: new Date() };
      setChatMessages(prev => [...prev, errorMsg]);
    } finally {
      setChatLoading(false);
    }
  };

  const openModule = (moduleId) => {
    setSelectedModule(moduleId);
  };

  const closeModule = () => {
    setSelectedModule(null);
  };

  const tabs = [
    { id: 'overview', label: t('aiModule.title'), icon: Brain },
    { id: 'chatbot', label: t('aiModule.chatbot'), icon: MessageCircle },
    { id: 'modules', label: t('aiModule.title'), icon: Sparkles },
  ];

  const aiFeatures = [
    { 
      id: 'ai-pms',
      title: 'AI-Powered PMS', 
      description: t('aiModule.enhancedPMSDesc'),
      icon: Hotel, 
      color: 'from-purple-500 to-blue-500',
    },
    { 
      id: 'ai-chatbot',
      title: 'AI Chatbot', 
      description: t('aiModule.chatbotDesc'),
      icon: Bot, 
      color: 'from-cyan-500 to-blue-500',
    },
    { 
      id: 'ai-whatsapp-concierge',
      title: 'WhatsApp Concierge', 
      description: t('aiModule.whatsappDesc'),
      icon: MessageCircle, 
      color: 'from-green-500 to-emerald-500',
    },
    { 
      id: 'dynamic-pricing',
      title: 'Dynamic Pricing', 
      description: t('aiModule.dynamicPricingDesc'),
      icon: DollarSign, 
      color: 'from-amber-500 to-orange-500',
    },
    { 
      id: 'predictive-analytics',
      title: 'Predictive Analytics', 
      description: t('aiModule.predictiveDesc'),
      icon: TrendingUp, 
      color: 'from-pink-500 to-rose-500',
    },
    { 
      id: 'revenue-autopilot',
      title: 'Revenue Autopilot', 
      description: t('aiModule.revenueAutopilotDesc'),
      icon: Zap, 
      color: 'from-indigo-500 to-violet-500',
    },
    { 
      id: 'social-media-radar',
      title: 'Social Media Radar', 
      description: t('aiModule.socialRadarDesc'),
      icon: Globe, 
      color: 'from-sky-500 to-blue-500',
    },
  ];

  // Get selected module info
  const selectedFeature = aiFeatures.find(f => f.id === selectedModule);

  const renderInlineModule = () => {
    const ModuleComponent = MODULE_COMPONENTS[selectedModule];
    if (!ModuleComponent) return null;

    return (
      <div>
        {/* Back header */}
        <div className="flex items-center gap-3 mb-4 pb-4 border-b">
          <Button
            variant="outline"
            size="sm"
            onClick={closeModule}
            className="flex items-center gap-2 hover:bg-gray-100"
          >
            <ArrowLeft className="w-4 h-4" />
            {t('common.back')}
          </Button>
          {selectedFeature && (
            <div className="flex items-center gap-2">
              <div className={`p-2 bg-gradient-to-r ${selectedFeature.color} rounded-lg text-white`}>
                <selectedFeature.icon className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-semibold text-lg">{selectedFeature.title}</h3>
                <p className="text-xs text-gray-500">{selectedFeature.description}</p>
              </div>
            </div>
          )}
        </div>

        {/* Module content */}
        <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
          <Suspense fallback={
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
              <span className="ml-3 text-gray-500">Modül yükleniyor...</span>
            </div>
          }>
            <ModuleComponent user={user} tenant={tenant} onLogout={onLogout} />
          </Suspense>
        </div>
      </div>
    );
  };

  const renderOverview = () => (
    <div className="space-y-6">
      {/* AI Daily Briefing */}
      <Card className="border-0 shadow-lg bg-gradient-to-r from-purple-600 to-blue-600 text-white">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-white">
            <Brain className="w-6 h-6" />
            AI Günlük Brifing
            <Button 
              variant="ghost" 
              size="sm" 
              className="ml-auto text-white hover:bg-white/20"
              onClick={loadBriefing}
            >
              Yenile
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {briefingLoading ? (
            <div className="flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>AI analiz yapıyor...</span>
            </div>
          ) : briefing ? (
            <div className="space-y-3">
              <p className="text-lg opacity-95">{briefing.summary || briefing.text || 'Günlük brifing hazırlanıyor...'}</p>
              {briefing.insights && briefing.insights.length > 0 && (
                <div className="space-y-2 mt-4">
                  {briefing.insights.map((insight, i) => (
                    <div key={i} className="flex items-start gap-2 bg-white/10 rounded-lg p-3">
                      <Sparkles className="w-4 h-4 mt-0.5 flex-shrink-0" />
                      <span className="text-sm">{insight.text || insight}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p className="opacity-80">AI brifing yüklenemedi. Yeniden deneyin.</p>
          )}
        </CardContent>
      </Card>

      {/* AI Stats - Real Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="border shadow-sm hover:shadow-md transition-shadow">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="p-3 bg-purple-100 rounded-xl">
              <Hotel className="w-6 h-6 text-purple-600" />
            </div>
            <div>
              <div className="text-2xl font-bold">{briefing?.metrics?.total_rooms || '-'}</div>
              <div className="text-sm text-gray-500">Toplam Oda</div>
            </div>
          </CardContent>
        </Card>
        <Card className="border shadow-sm hover:shadow-md transition-shadow">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="p-3 bg-blue-100 rounded-xl">
              <BarChart3 className="w-6 h-6 text-blue-600" />
            </div>
            <div>
              <div className="text-2xl font-bold">{briefing?.metrics?.occupancy_rate != null ? `%${briefing.metrics.occupancy_rate}` : '-'}</div>
              <div className="text-sm text-gray-500">Doluluk Oranı</div>
            </div>
          </CardContent>
        </Card>
        <Card className="border shadow-sm hover:shadow-md transition-shadow">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="p-3 bg-green-100 rounded-xl">
              <TrendingUp className="w-6 h-6 text-green-600" />
            </div>
            <div>
              <div className="text-2xl font-bold">{briefing?.metrics?.confirmed_bookings ?? '-'}</div>
              <div className="text-sm text-gray-500">Aktif Rezervasyon</div>
            </div>
          </CardContent>
        </Card>
        <Card className="border shadow-sm hover:shadow-md transition-shadow">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="p-3 bg-amber-100 rounded-xl">
              <Users className="w-6 h-6 text-amber-600" />
            </div>
            <div>
              <div className="text-2xl font-bold">{briefing?.metrics?.today_checkins ?? '-'}</div>
              <div className="text-sm text-gray-500">Bugün Giriş</div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* AI Pricing Recommendation */}
      {pricingRec && (
        <Card className="border shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <DollarSign className="w-5 h-5 text-amber-500" />
              AI Fiyatlandırma Önerisi
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-3 bg-green-50 rounded-lg">
                <div className="text-sm text-gray-500">Önerilen Fiyat</div>
                <div className="text-xl font-bold text-green-600">
                  ${pricingRec.recommended_rate || pricingRec.suggested_price || 'N/A'}
                </div>
              </div>
              <div className="p-3 bg-blue-50 rounded-lg">
                <div className="text-sm text-gray-500">Mevcut Fiyat</div>
                <div className="text-xl font-bold text-blue-600">
                  ${pricingRec.current_rate || pricingRec.current_price || 'N/A'}
                </div>
              </div>
              <div className="p-3 bg-purple-50 rounded-lg">
                <div className="text-sm text-gray-500">Güven Skoru</div>
                <div className="text-xl font-bold text-purple-600">
                  {pricingRec.confidence ? `${Math.round(pricingRec.confidence * 100)}%` : 'N/A'}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Quick Access to AI Features */}
      <div>
        <h3 className="text-lg font-semibold mb-4">AI Modüllerine Hızlı Erişim</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {aiFeatures.slice(0, 4).map((feature) => (
            <Card
              key={feature.id}
              className="border shadow-sm hover:shadow-lg transition-all cursor-pointer group"
              onClick={() => { setActiveTab('modules'); openModule(feature.id); }}
            >
              <CardContent className="p-4">
                <div className={`p-3 bg-gradient-to-r ${feature.color} rounded-xl w-fit mb-3 text-white group-hover:scale-110 transition-transform`}>
                  <feature.icon className="w-6 h-6" />
                </div>
                <h4 className="font-semibold text-sm">{feature.title}</h4>
                <p className="text-xs text-gray-500 mt-1">{feature.description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );

  const renderChatbot = () => (
    <Card className="border-0 shadow-lg h-[calc(100vh-220px)]">
      <CardHeader className="bg-gradient-to-r from-cyan-500 to-blue-600 text-white rounded-t-lg">
        <CardTitle className="flex items-center gap-2 text-white">
          <Bot className="w-6 h-6" />
          AI Hotel Asistan
          <span className="ml-2 text-xs bg-white/20 px-2 py-0.5 rounded-full">Online</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col h-[calc(100%-80px)] p-0">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {chatMessages.map((msg, i) => (
            <div key={i} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[70%] rounded-2xl px-4 py-3 ${
                msg.sender === 'user'
                  ? 'bg-blue-600 text-white rounded-br-sm'
                  : 'bg-gray-100 text-gray-800 rounded-bl-sm'
              }`}>
                {msg.sender === 'bot' && (
                  <div className="flex items-center gap-1 mb-1">
                    <Bot className="w-3 h-3 text-blue-500" />
                    <span className="text-xs font-medium text-blue-500">Syroce AI</span>
                  </div>
                )}
                <p className="text-sm whitespace-pre-wrap">{msg.message}</p>
                <p className={`text-xs mt-1 ${msg.sender === 'user' ? 'text-blue-200' : 'text-gray-400'}`}>
                  {new Date(msg.timestamp).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}
                </p>
              </div>
            </div>
          ))}
          {chatLoading && (
            <div className="flex justify-start">
              <div className="bg-gray-100 rounded-2xl rounded-bl-sm px-4 py-3">
                <div className="flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                  <span className="text-sm text-gray-500">Düşünüyor...</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Input */}
        <form onSubmit={handleSendChat} className="p-4 border-t flex gap-2">
          <Input
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            placeholder="Mesajınızı yazın..."
            className="flex-1"
            disabled={chatLoading}
          />
          <Button type="submit" disabled={chatLoading || !chatInput.trim()} className="bg-blue-600 hover:bg-blue-700">
            <Send className="w-4 h-4" />
          </Button>
        </form>
      </CardContent>
    </Card>
  );

  const renderModules = () => {
    // If a module is selected, render it inline
    if (selectedModule) {
      return renderInlineModule();
    }

    // Otherwise show the module grid
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
          {aiFeatures.map((feature) => (
            <Card
              key={feature.id}
              className="border shadow-sm hover:shadow-xl transition-all cursor-pointer group overflow-hidden"
              onClick={() => openModule(feature.id)}
            >
              <div className={`h-2 bg-gradient-to-r ${feature.color}`} />
              <CardContent className="p-5">
                <div className={`p-3 bg-gradient-to-r ${feature.color} rounded-xl w-fit mb-4 text-white group-hover:scale-110 transition-transform`}>
                  <feature.icon className="w-7 h-7" />
                </div>
                <h4 className="font-bold text-base mb-1">{feature.title}</h4>
                <p className="text-sm text-gray-500">{feature.description}</p>
                <div className="mt-4 flex items-center text-xs text-blue-600 font-medium group-hover:translate-x-1 transition-transform">
                  Modülü Aç <ChevronRight className="w-3 h-3 ml-1" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  };

  const wrap = (content) => embedded ? content : (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="ai">{content}</Layout>
  );

  return wrap(
    <div className="p-6 max-w-[1400px] mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <div className="p-2 bg-gradient-to-r from-purple-500 to-blue-500 rounded-xl text-white">
              <Brain className="w-7 h-7" />
            </div>
            AI Hub
          </h1>
          <p className="text-gray-500 mt-1">Yapay zeka destekli otel yönetim araçları</p>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 mb-6 border-b pb-3">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => { setActiveTab(tab.id); if (tab.id !== 'modules') setSelectedModule(null); }}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                activeTab === tab.id
                  ? 'bg-blue-600 text-white shadow-md'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        {activeTab === 'overview' && renderOverview()}
        {activeTab === 'chatbot' && renderChatbot()}
        {activeTab === 'modules' && renderModules()}
      </div>
  );
};

export default AIModule;
