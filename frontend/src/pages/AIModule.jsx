import React, { useState, useEffect, lazy, Suspense } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { 
  Bot, MessageCircle, Send, Brain, TrendingUp, Sparkles, BarChart3, Users, 
  Zap, Clock, Star, Hotel, ChefHat, Wrench, DollarSign, Globe, Loader2, ArrowLeft, ChevronRight, Menu
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

// Lazy load AI module components
const AIEnhancedPMS = lazy(() => import('@/pages/AIEnhancedPMS'));
const AIChatbot = lazy(() => import('@/pages/AIChatbot'));
const AIWhatsAppConcierge = lazy(() => import('@/pages/AIWhatsAppConcierge'));
const DynamicPricing = lazy(() => import('@/pages/DynamicPricing'));
const PredictiveAnalytics = lazy(() => import('@/pages/PredictiveAnalytics'));
const RevenueAutopilot = lazy(() => import('@/pages/RevenueAutopilot'));
const SocialMediaRadar = lazy(() => import('@/pages/SocialMediaRadar'));

const MODULE_COMPONENTS = {
  'ai-pms': AIEnhancedPMS,
  'ai-chatbot': AIChatbot,
  'ai-whatsapp-concierge': AIWhatsAppConcierge,
  'dynamic-pricing': DynamicPricing,
  'predictive-analytics': PredictiveAnalytics,
  'revenue-autopilot': RevenueAutopilot,
  'social-media-radar': SocialMediaRadar
};

const AIModule = ({ user, tenant, onLogout, embedded = false }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  
  // Use URL parameter 'module' if present, otherwise default to 'overview'
  const initialModule = searchParams.get('module') || 'overview';
  const [activeItem, setActiveItem] = useState(initialModule);
  
  // Update URL when activeItem changes
  useEffect(() => {
    if (activeItem !== (searchParams.get('module') || 'overview')) {
      setSearchParams({ module: activeItem }, { replace: true });
    }
  }, [activeItem, setSearchParams, searchParams]);
  
  // States for overview widgets
  const [briefing, setBriefing] = useState(null);
  const [briefingLoading, setBriefingLoading] = useState(false);
  const [pricingRec, setPricingRec] = useState(null);

  useEffect(() => {
    if (activeItem === 'overview') {
      loadBriefing();
      loadPricingRecommendation();
    }
  }, [activeItem]);

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

  const aiFeatures = [
    {
      id: 'overview',
      title: 'Genel Bakış',
      icon: Brain,
      color: 'from-indigo-500 to-blue-500',
      iconColor: 'text-indigo-600'
    },
    {
      id: 'ai-pms',
      title: 'AI-Powered PMS',
      icon: Hotel,
      color: 'from-blue-500 to-cyan-500',
      iconColor: 'text-blue-600'
    },
    {
      id: 'ai-chatbot',
      title: 'AI Chatbot',
      icon: Bot,
      color: 'from-cyan-500 to-blue-500',
      iconColor: 'text-cyan-600'
    },
    {
      id: 'ai-whatsapp-concierge',
      title: 'WhatsApp Concierge',
      icon: MessageCircle,
      color: 'from-green-500 to-emerald-500',
      iconColor: 'text-green-600'
    },
    {
      id: 'dynamic-pricing',
      title: 'Dynamic Pricing',
      icon: DollarSign,
      color: 'from-amber-500 to-orange-500',
      iconColor: 'text-amber-600'
    },
    {
      id: 'predictive-analytics',
      title: 'Predictive Analytics',
      icon: TrendingUp,
      color: 'from-pink-500 to-rose-500',
      iconColor: 'text-pink-600'
    },
    {
      id: 'revenue-autopilot',
      title: 'Revenue Autopilot',
      icon: Zap,
      color: 'from-indigo-500 to-violet-500',
      iconColor: 'text-violet-600'
    },
    {
      id: 'social-media-radar',
      title: 'Social Media Radar',
      icon: Globe,
      color: 'from-sky-500 to-blue-500',
      iconColor: 'text-sky-600'
    }
  ];

  const renderOverview = () => (
    <div className="space-y-6">
      <Card className="border-0 shadow-lg bg-gradient-to-r from-indigo-600 to-blue-600 text-white rounded-2xl overflow-hidden">
        <CardHeader className="pb-4">
          <CardTitle className="flex items-center gap-2 text-white">
            <Brain className="w-6 h-6" />
            AI Günlük Brifing
            <Button variant="ghost" size="sm" className="ml-auto text-white hover:bg-white/20" onClick={loadBriefing}>
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
                    <div key={insight.id || i} className="flex items-start gap-2 bg-white/10 rounded-lg p-3">
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

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="border-0 shadow-sm hover:shadow-md transition-shadow rounded-2xl">
          <CardContent className="p-5 flex items-center gap-4">
            <div className="p-3 bg-indigo-50 rounded-xl">
              <Hotel className="w-6 h-6 text-indigo-600" />
            </div>
            <div>
              <div className="text-3xl font-bold text-slate-800">{briefing?.metrics?.total_rooms || '-'}</div>
              <div className="text-sm font-medium text-gray-500">Toplam Oda</div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-0 shadow-sm hover:shadow-md transition-shadow rounded-2xl">
          <CardContent className="p-5 flex items-center gap-4">
            <div className="p-3 bg-blue-50 rounded-xl">
              <BarChart3 className="w-6 h-6 text-blue-600" />
            </div>
            <div>
              <div className="text-3xl font-bold text-slate-800">{briefing?.metrics?.occupancy_rate != null ? `%${briefing.metrics.occupancy_rate}` : '-'}</div>
              <div className="text-sm font-medium text-gray-500">Doluluk Oranı</div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-0 shadow-sm hover:shadow-md transition-shadow rounded-2xl">
          <CardContent className="p-5 flex items-center gap-4">
            <div className="p-3 bg-green-50 rounded-xl">
              <TrendingUp className="w-6 h-6 text-green-600" />
            </div>
            <div>
              <div className="text-3xl font-bold text-slate-800">{briefing?.metrics?.confirmed_bookings ?? '-'}</div>
              <div className="text-sm font-medium text-gray-500">Aktif Rezervasyon</div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-0 shadow-sm hover:shadow-md transition-shadow rounded-2xl">
          <CardContent className="p-5 flex items-center gap-4">
            <div className="p-3 bg-amber-50 rounded-xl">
              <Users className="w-6 h-6 text-amber-600" />
            </div>
            <div>
              <div className="text-3xl font-bold text-slate-800">{briefing?.metrics?.today_checkins ?? '-'}</div>
              <div className="text-sm font-medium text-gray-500">Bugün Giriş</div>
            </div>
          </CardContent>
        </Card>
      </div>

      {pricingRec && (
        <Card className="border-0 shadow-sm rounded-2xl">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg text-slate-800">
              <DollarSign className="w-5 h-5 text-amber-500" />
              AI Fiyatlandırma Önerisi
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-4 bg-green-50 rounded-xl border border-green-100">
                <div className="text-sm font-medium text-gray-500">Önerilen Fiyat</div>
                <div className="text-2xl font-bold text-green-700">
                  ${pricingRec.recommended_rate || pricingRec.suggested_price || 'N/A'}
                </div>
              </div>
              <div className="p-4 bg-blue-50 rounded-xl border border-blue-100">
                <div className="text-sm font-medium text-gray-500">Mevcut Fiyat</div>
                <div className="text-2xl font-bold text-blue-700">
                  ${pricingRec.current_rate || pricingRec.current_price || 'N/A'}
                </div>
              </div>
              <div className="p-4 bg-indigo-50 rounded-xl border border-indigo-100">
                <div className="text-sm font-medium text-gray-500">Güven Skoru</div>
                <div className="text-2xl font-bold text-indigo-700">
                  {pricingRec.confidence ? `${Math.round(pricingRec.confidence * 100)}%` : 'N/A'}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );

  const renderContent = () => {
    if (activeItem === 'overview') {
      return renderOverview();
    }
    const ModuleComponent = MODULE_COMPONENTS[activeItem];
    if (!ModuleComponent) return <div className="p-10 text-center text-gray-500">Modül bulunamadı.</div>;
    
    return (
      <div className="h-full bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden flex flex-col relative">
        <Suspense fallback={
          <div className="flex flex-col items-center justify-center h-[400px]">
            <Loader2 className="w-8 h-8 animate-spin text-indigo-500 mb-4" />
            <span className="text-slate-500 font-medium">Modül yükleniyor...</span>
          </div>
        }>
          <div className="absolute inset-0 overflow-y-auto">
            <ModuleComponent user={user} tenant={tenant} onLogout={onLogout} />
          </div>
        </Suspense>
      </div>
    );
  };

  return (
    <div className={`h-full flex flex-col bg-slate-50 ${embedded ? '' : ''}`}>
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar */}
        <div className="w-72 bg-white border-r border-slate-200 flex flex-col shadow-sm z-10 flex-shrink-0">
          <div className="p-6 pb-4 border-b border-slate-100">
            <h1 className="text-2xl font-extrabold flex items-center gap-3 text-slate-800 tracking-tight">
              <div className="p-2.5 bg-gradient-to-br from-indigo-600 to-blue-600 rounded-xl text-white shadow-md">
                <Sparkles className="w-5 h-5" />
              </div>
              AI Hub
            </h1>
            <p className="text-sm text-slate-500 mt-2 font-medium">Akıllı Yönetim Merkezi</p>
          </div>
          
          <div className="flex-1 overflow-y-auto p-4 space-y-1">
            {aiFeatures.map(feature => {
              const isActive = activeItem === feature.id;
              return (
                <button
                  key={feature.id}
                  onClick={() => setActiveItem(feature.id)}
                  className={`w-full flex items-center gap-3 px-4 py-3.5 rounded-xl transition-all duration-200 group ${
                    isActive 
                      ? 'bg-indigo-50 text-indigo-700 shadow-sm border border-indigo-100/50' 
                      : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900 border border-transparent'
                  }`}
                >
                  <feature.icon className={`w-5 h-5 transition-colors ${isActive ? feature.iconColor : 'text-slate-400 group-hover:text-slate-600'}`} />
                  <span className={`text-sm font-semibold tracking-wide ${isActive ? '' : 'font-medium'}`}>{feature.title}</span>
                  {isActive && <ChevronRight className="w-4 h-4 ml-auto text-indigo-400" />}
                </button>
              );
            })}
          </div>
        </div>

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col h-full bg-slate-50">
          <div className="p-6 md:p-8 w-full h-full flex flex-col relative">
            {renderContent()}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AIModule;