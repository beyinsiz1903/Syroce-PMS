import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '@/api/axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '@/components/ui/dialog';
import { Home, MessageCircle, Send, Bot, CheckCircle, Clock, Settings } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const AIWhatsAppConcierge = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [conversations, setConversations] = useState([]);
  const [testMessage, setTestMessage] = useState('');
  const [testPhone, setTestPhone] = useState('+90 555 123 45 67');
  const [loading, setLoading] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
  const [configLoading, setConfigLoading] = useState(false);
  const [phoneSelectionData, setPhoneSelectionData] = useState(null);
  const [selectedPhoneId, setSelectedPhoneId] = useState('');
  const [config, setConfig] = useState({
    phone_number_id: '',
    access_token: '',
    verify_token: ''
  });

  useEffect(() => {
    loadConversations();
    
    // Load Facebook SDK
    window.fbAsyncInit = function() {
      window.FB.init({
        appId            : import.meta.env.VITE_FACEBOOK_APP_ID || '1234567890',
        autoLogAppEvents : true,
        xfbml            : true,
        version          : 'v19.0'
      });
    };

    if (!document.getElementById('facebook-jssdk')) {
      const script = document.createElement('script');
      script.id = 'facebook-jssdk';
      script.src = "https://connect.facebook.net/en_US/sdk.js";
      script.async = true;
      script.defer = true;
      document.body.appendChild(script);
    }
  }, []);

  const loadConversations = async () => {
    try {
      const response = await api.get('/ai-concierge/conversations');
      setConversations(response.data.conversations || []);
    } catch (error) {
      console.error('Conversations yüklenemedi');
    }
  };

  const loadConfig = async () => {
    try {
      const response = await api.get('/whatsapp/config');
      if (response.data.config) {
        setConfig({
          phone_number_id: response.data.config.phone_number_id || '',
          access_token: response.data.config.access_token || '',
          verify_token: response.data.config.verify_token || ''
        });
      }
    } catch (error) {
      console.error('Config yüklenemedi', error);
    }
  };

  useEffect(() => {
    if (configOpen) {
      loadConfig();
    }
  }, [configOpen]);

  const handleFacebookLogin = () => {
    if (!window.FB) {
      toast.error(t('ai.whatsapp.fastSetupDesc') /* Needs dedicated error key but skipping this specific one for simplicity, or we can use generic */);
      return;
    }
    
    window.FB.login((response) => {
      if (response.authResponse) {
        exchangeOAuthToken(response.authResponse.accessToken);
      } else {
        toast.error(t('messages.error.generic'));
      }
    }, {
      scope: 'whatsapp_business_management,whatsapp_business_messaging',
      return_scopes: true
    });
  };

  const exchangeOAuthToken = async (accessToken) => {
    setConfigLoading(true);
    try {
      const res = await api.post('/whatsapp/oauth', {
        access_token: accessToken,
        phone_number_id: config.phone_number_id || 'pending'
      });
      
      const { access_token, verify_token, phone_numbers } = res.data;
      
      if (!phone_numbers || phone_numbers.length === 0) {
        toast.error(t('messages.error.generic'));
        return;
      }
      
      if (phone_numbers.length === 1) {
        finalizeConfig(access_token, verify_token, phone_numbers[0].id);
      } else {
        setPhoneSelectionData({ access_token, verify_token, numbers: phone_numbers });
        setSelectedPhoneId(phone_numbers[0].id);
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || t('messages.error.generic'));
    } finally {
      setConfigLoading(false);
    }
  };

  const finalizeConfig = async (accessToken, verifyToken, phoneId) => {
    setConfigLoading(true);
    try {
      await api.post('/whatsapp/config', {
        access_token: accessToken,
        verify_token: verifyToken,
        phone_number_id: phoneId
      });
      toast.success(t('messages.success.saved'));
      setConfigOpen(false);
      setPhoneSelectionData(null);
      loadConfig();
    } catch (error) {
      toast.error(t('messages.error.generic'));
    } finally {
      setConfigLoading(false);
    }
  };

  const saveConfig = async () => {
    setConfigLoading(true);
    try {
      await api.post('/whatsapp/config', config);
      toast.success(t('messages.success.saved'));
      setConfigOpen(false);
    } catch (error) {
      toast.error(t('messages.error.generic'));
    } finally {
      setConfigLoading(false);
    }
  };

  const sendTestMessage = async () => {
    if (!testMessage.trim()) return;
    
    setLoading(true);
    try {
      const response = await api.post('/ai-concierge/whatsapp', {
        phone: testPhone,
        message: testMessage
      });
      
      const aiResponseText = response.data.response || response.data.message || 'Yanıt alınamadı';
      const toastMessage = aiResponseText.substring(0, 100) + (aiResponseText.length > 100 ? '...' : '');
      
      if (response.data.response) {
        toast.success('AI yanıtı: ' + toastMessage);
      } else {
        toast.info('Sistem Notu: ' + toastMessage);
      }

      setTestMessage('');
      loadConversations();
    } catch (error) {
      toast.error(t('messages.error.generic'));
    } finally {
      setLoading(false);
    }
  };

  const exampleMessages = [
    t('ai.whatsapp.examples.towel'),
    t('ai.whatsapp.examples.restaurant'),
    t('ai.whatsapp.examples.checkout'),
    t('ai.whatsapp.examples.spa')
  ];

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white/60 backdrop-blur-md p-6 rounded-2xl border border-gray-100 shadow-sm">
        <div className="flex items-center gap-4">
          <Button 
            variant="outline" 
            size="icon"
            onClick={() => navigate('/')}
            className="rounded-full w-12 h-12 border-gray-200 hover:bg-green-50 hover:text-green-600 transition-colors"
          >
            <Home className="w-5 h-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-gray-900 to-gray-600">
              {t('ai.whatsapp.title')}
            </h1>
            <p className="text-gray-500 font-medium mt-1">
              {t('ai.whatsapp.subtitle')}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200 px-3 py-1 text-sm rounded-full">
            {t('ai.whatsapp.moduleActive')}
          </Badge>
          <Dialog open={configOpen} onOpenChange={setConfigOpen}>
            <DialogTrigger asChild>
              <Button variant="outline" size="sm" className="gap-2">
                <Settings className="w-4 h-4" />
                {t('ai.whatsapp.integrationSettings')}
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[425px]">
              <DialogHeader>
                <DialogTitle>WhatsApp {t('ai.whatsapp.integrationSettings')}</DialogTitle>
              </DialogHeader>
              {phoneSelectionData ? (
                <div className="space-y-6 py-4">
                  <div className="flex flex-col items-center text-center mb-4">
                    <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center mb-4">
                      <CheckCircle className="w-6 h-6 text-green-600" />
                    </div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-1">{t('ai.whatsapp.accountsFound')}</h3>
                    <p className="text-sm text-gray-500">{t('ai.whatsapp.accountsFoundDesc')}</p>
                  </div>
                  
                  <div className="space-y-2">
                    <label className="text-sm font-medium">{t('ai.whatsapp.selectNumber')}</label>
                    <Select value={selectedPhoneId} onValueChange={setSelectedPhoneId}>
                      <SelectTrigger>
                        <SelectValue placeholder={t('ai.whatsapp.selectNumberPlaceholder')} />
                      </SelectTrigger>
                      <SelectContent>
                        {phoneSelectionData.numbers.map((pn) => (
                          <SelectItem key={pn.id} value={pn.id}>
                            {pn.verified_name ? `${pn.verified_name} (${pn.display_phone_number})` : pn.display_phone_number}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  
                  <DialogFooter className="mt-6">
                    <Button variant="outline" onClick={() => setPhoneSelectionData(null)}>{t('ai.whatsapp.goBack')}</Button>
                    <Button 
                      onClick={() => finalizeConfig(phoneSelectionData.access_token, phoneSelectionData.verify_token, selectedPhoneId)} 
                      disabled={configLoading}
                    >
                      {configLoading ? 'Kaydediliyor...' : 'Seçimi Tamamla'}
                    </Button>
                  </DialogFooter>
                </div>
              ) : (
                <>
                  <div className="space-y-6 py-4">
                    <div className="flex flex-col items-center justify-center p-6 border-2 border-dashed border-gray-200 rounded-xl bg-gray-50/50">
                      <div className="w-16 h-16 bg-[#1877F2]/10 rounded-full flex items-center justify-center mb-4">
                        <svg className="w-8 h-8 text-[#1877F2]" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.469h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.469h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
                        </svg>
                      </div>
                      <h3 className="text-lg font-semibold text-gray-900 mb-2">{t('ai.whatsapp.fastSetup')}</h3>
                      <p className="text-sm text-gray-500 text-center mb-6">
                        {t('ai.whatsapp.fastSetupDesc')}
                      </p>
                      <Button 
                        onClick={handleFacebookLogin} 
                        className="w-full bg-[#1877F2] hover:bg-[#166FE5] text-white h-12 text-base font-medium"
                        disabled={configLoading}
                      >
                        {configLoading ? 'Bağlanıyor...' : 'Facebook ile Bağlan'}
                      </Button>
                    </div>

                    <div className="relative">
                      <div className="absolute inset-0 flex items-center">
                        <span className="w-full border-t border-gray-200" />
                      </div>
                      <div className="relative flex justify-center text-xs uppercase">
                        <span className="bg-white px-2 text-gray-500">{t('ai.whatsapp.orManuel')}</span>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <div className="space-y-2">
                        <label className="text-sm font-medium">{t('ai.whatsapp.phoneNumberId')}</label>
                        <Input 
                          value={config.phone_number_id}
                          onChange={(e) => setConfig({ ...config, phone_number_id: e.target.value })}
                          placeholder="1059384729384"
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm font-medium">{t('ai.whatsapp.systemToken')}</label>
                        <Input 
                          value={config.access_token}
                          onChange={(e) => setConfig({ ...config, access_token: e.target.value })}
                          placeholder="EAAL..."
                          type="password"
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm font-medium">{t('ai.whatsapp.verifyToken')}</label>
                        <Input 
                          value={config.verify_token}
                          onChange={(e) => setConfig({ ...config, verify_token: e.target.value })}
                          placeholder="my_custom_verify_token"
                        />
                        <p className="text-xs text-gray-500 mt-1">{t('ai.whatsapp.verifyTokenDesc')}</p>
                      </div>
                    </div>
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setConfigOpen(false)}>{t('ai.whatsapp.cancel')}</Button>
                    <Button onClick={saveConfig} disabled={configLoading}>
                      {configLoading ? 'Kaydediliyor...' : 'Manuel Ayarları Kaydet'}
                    </Button>
                  </DialogFooter>
                </>
              )}
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Feature Highlights */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { icon: Clock, color: 'green', value: '24/7', label: t('ai.whatsapp.continuousService'), desc: t('ai.whatsapp.zeroWaitTime') },
          { icon: Bot, color: 'blue', value: 'AI', label: t('ai.whatsapp.gpt4Powered'), desc: t('ai.whatsapp.nlp') },
          { icon: MessageCircle, color: 'indigo', value: conversations.length, label: t('ai.whatsapp.totalDialogues'), desc: t('ai.whatsapp.recordedInSystem') },
          { icon: CheckCircle, color: 'amber', value: conversations.filter(c => c.action_taken).length, label: t('ai.whatsapp.autoAction'), desc: t('ai.whatsapp.reflectedInPMS') }
        ].map((stat, idx) => (
          <Card key={idx} className={`bg-${stat.color}-50/50 border-${stat.color}-100 hover:shadow-md transition-all duration-300 overflow-hidden relative group`}>
            <div className={`absolute top-0 right-0 -mr-4 -mt-4 w-24 h-24 bg-${stat.color}-500/10 rounded-full blur-2xl group-hover:bg-${stat.color}-500/20 transition-all`}></div>
            <CardContent className="p-6 flex flex-col items-center text-center relative z-10">
              <div className={`w-12 h-12 rounded-2xl bg-${stat.color}-100 flex items-center justify-center mb-4 text-${stat.color}-600 group-hover:scale-110 transition-transform`}>
                <stat.icon className="w-6 h-6" />
              </div>
              <p className="text-3xl font-bold text-gray-900 mb-1">{stat.value}</p>
              <p className="text-sm font-semibold text-gray-700">{stat.label}</p>
              <p className="text-xs text-gray-500 mt-1">{stat.desc}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Test Interface (Left / Top) */}
        <div className="lg:col-span-1 space-y-6">
          <Card className="border-gray-200 shadow-sm sticky top-24">
            <CardHeader className="bg-gradient-to-r from-gray-50 to-white border-b border-gray-100 rounded-t-xl pb-4">
              <CardTitle className="text-lg flex items-center gap-2">
                <Bot className="w-5 h-5 text-blue-600" />
                {t('ai.whatsapp.simulator')}
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-6 space-y-5">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  {t('ai.whatsapp.testNumber')}
                </label>
                <Input
                  value={testPhone}
                  onChange={(e) => setTestPhone(e.target.value)}
                  placeholder="+90 555 123 45 67"
                  className="bg-gray-50/50 border-gray-200 focus:bg-white"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  {t('ai.whatsapp.guestMessage')}
                </label>
                <Input
                  value={testMessage}
                  onChange={(e) => setTestMessage(e.target.value)}
                  placeholder="Odama havlu gönder..."
                  onKeyPress={(e) => e.key === 'Enter' && sendTestMessage()}
                  className="bg-gray-50/50 border-gray-200 focus:bg-white"
                />
              </div>
              <div className="space-y-2 pt-2">
                <p className="text-xs text-gray-500 font-medium">{t('ai.whatsapp.exampleScenarios')}</p>
                <div className="flex flex-col gap-2">
                  {exampleMessages.map((msg, idx) => (
                    <Button
                      key={idx}
                      variant="outline"
                      size="sm"
                      onClick={() => setTestMessage(msg)}
                      className="justify-start text-left h-auto py-2 text-sm text-gray-600 hover:text-gray-900 border-gray-200"
                    >
                      <span className="truncate">{msg}</span>
                    </Button>
                  ))}
                </div>
              </div>
              <Button 
                className="w-full bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white shadow-sm transition-all mt-4"
                onClick={sendTestMessage}
                disabled={loading || !testMessage.trim()}
              >
                <Send className="w-4 h-4 mr-2" />
                {loading ? 'İşleniyor...' : 'AI\'a İlet'}
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Conversation History (Right / Bottom) */}
        <div className="lg:col-span-2">
          <Card className="border-gray-200 shadow-sm h-full flex flex-col">
            <CardHeader className="bg-gradient-to-r from-gray-50 to-white border-b border-gray-100 rounded-t-xl pb-4">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg flex items-center gap-2">
                  <MessageCircle className="w-5 h-5 text-indigo-600" />
                  {t('ai.whatsapp.dialogueHistory')}
                </CardTitle>
                <Badge variant="secondary" className="bg-indigo-50 text-indigo-700">
                  {conversations.length} {t('ai.whatsapp.records')}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="pt-6 flex-1 bg-gray-50/30">
              <div className="space-y-4">
                {conversations.length === 0 ? (
                  <div className="text-center py-16 px-4 bg-white rounded-xl border border-dashed border-gray-300">
                    <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
                      <MessageCircle className="w-8 h-8 text-gray-400" />
                    </div>
                    <p className="text-gray-900 font-medium mb-1">{t('ai.whatsapp.noDialogueFound')}</p>
                    <p className="text-sm text-gray-500 max-w-sm mx-auto">
                      {t('ai.whatsapp.noDialogueDesc')}
                    </p>
                  </div>
                ) : (
                  conversations.map((conv) => (
                    <div key={conv.id} className="bg-white rounded-xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow p-5">
                      <div className="flex justify-between items-start mb-4">
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="text-xs font-medium text-gray-600">
                            {conv.phone}
                          </Badge>
                        </div>
                        <span className="text-xs font-medium text-gray-400 bg-gray-50 px-2 py-1 rounded">
                          {new Date(conv.created_at).toLocaleString('tr-TR', { 
                            day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
                          })}
                        </span>
                      </div>
                      
                      <div className="space-y-4">
                        {/* Guest Message Bubble */}
                        <div className="flex items-start gap-3 w-11/12">
                          <div className="flex-shrink-0 w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center border border-blue-200">
                            <span className="text-blue-700 font-bold text-xs">M</span>
                          </div>
                          <div className="bg-gray-100 text-gray-800 rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm">
                            {conv.user_message}
                          </div>
                        </div>

                        {/* AI Response Bubble */}
                        <div className="flex items-start gap-3 flex-row-reverse w-11/12 ml-auto">
                          <div className="flex-shrink-0 w-8 h-8 bg-gradient-to-br from-green-500 to-emerald-600 rounded-full flex items-center justify-center shadow-sm">
                            <Bot className="w-4 h-4 text-white" />
                          </div>
                          <div className="flex flex-col items-end gap-1">
                            <div className="bg-gradient-to-br from-green-50 to-emerald-50 border border-green-100 text-gray-800 rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm shadow-sm">
                              {conv.ai_response ? (
                                conv.ai_response
                              ) : (
                                <span className="text-gray-500 italic flex items-center gap-1.5">
                                  <Clock className="w-3.5 h-3.5" /> {t('ai.whatsapp.systemLogged')}
                                </span>
                              )}
                            </div>
                            {conv.action_taken && (
                              <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-200 border-none shadow-sm gap-1 mt-1 text-[10px] px-2">
                                <CheckCircle className="w-3 h-3" />
                                {conv.action_taken}
                              </Badge>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default AIWhatsAppConcierge;