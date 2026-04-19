import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Hotel, User, Smartphone, Shield } from 'lucide-react';
import LanguageSelector from '@/components/LanguageSelector';

const AuthPage = ({ onLogin }) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('hotel-login');
  const [loading, setLoading] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  
  // Registration flow states
  const [registrationStep, setRegistrationStep] = useState('form'); // 'form', 'verification'
  const [verificationCode, setVerificationCode] = useState('');
  
  // Forgot password states
  const [forgotPasswordStep, setForgotPasswordStep] = useState('email'); // 'email', 'code', 'newpassword'
  const [resetCode, setResetCode] = useState('');
  const [showForgotPassword, setShowForgotPassword] = useState(false);
  
  // Detect if device is mobile
  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth < 768 || /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
      setIsMobile(mobile);
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);
  
  const [hotelLoginData, setHotelLoginData] = useState({ hotel_id: '', username: '', password: '' });
  const [guestLoginData, setGuestLoginData] = useState({ email: '', password: '' });
  const [forgotEmail, setForgotEmail] = useState('');

  const [hotelRegisterData, setHotelRegisterData] = useState({
    property_name: '', email: '', username: '', password: '', name: '', phone: '', address: ''
  });

  // After successful registration, show generated hotel_id
  const [registrationSuccess, setRegistrationSuccess] = useState(null); // { hotel_id, username }
  
  const [guestRegisterData, setGuestRegisterData] = useState({
    email: '', password: '', name: '', phone: ''
  });

  // 2FA challenge state — when login returns requires_2fa, we hold the
  // challenge_token here and switch to the code-entry view.
  const [twoFAChallenge, setTwoFAChallenge] = useState(null); // {challenge_token, user_email}
  const [twoFACode, setTwoFACode] = useState('');

  const handleHotelLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        hotel_id: String(hotelLoginData.hotel_id || '').trim(),
        username: String(hotelLoginData.username || '').trim().toLowerCase(),
        password: hotelLoginData.password,
      };
      const response = await axios.post('/auth/login', payload);
      if (response.data?.requires_2fa) {
        setTwoFAChallenge({
          challenge_token: response.data.challenge_token,
          user_email: response.data.user?.email,
        });
        setTwoFACode('');
        setLoading(false);
        return;
      }
      onLogin(response.data.access_token, response.data.user, response.data.tenant);
    } catch (error) {
      const errorMessage = error.response?.data?.detail || error.message || t('auth.loginFailed');
      toast.error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleTwoFAVerify = async (e) => {
    e.preventDefault();
    if (!twoFAChallenge?.challenge_token) return;
    setLoading(true);
    try {
      const r = await axios.post('/auth/2fa/verify', {
        challenge_token: twoFAChallenge.challenge_token,
        code: twoFACode.trim(),
      });
      onLogin(r.data.access_token, r.data.user, r.data.tenant);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Doğrulama başarısız');
    } finally {
      setLoading(false);
    }
  };

  const handleGuestLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const response = await axios.post('/auth/login', guestLoginData);
      toast.success(t('auth.welcomeBack'));
      sessionStorage.setItem('postLoginRedirect', '/guest-portal');
      onLogin(response.data.access_token, response.data.user, response.data.tenant);
    } catch (error) {
      toast.error(error.response?.data?.detail || t('auth.loginFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleHotelRegister = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        ...hotelRegisterData,
        username: String(hotelRegisterData.username || '').trim().toLowerCase(),
      };
      const response = await axios.post('/auth/register', payload);
      const newHotelId = response.data?.tenant?.hotel_id;
      const newUsername = response.data?.user?.username || payload.username;
      // Show success screen with credentials, then auto-login after user dismisses
      setRegistrationSuccess({
        hotel_id: newHotelId,
        username: newUsername,
        token: response.data.access_token,
        user: response.data.user,
        tenant: response.data.tenant,
      });
      toast.success(t('auth.registerSuccess'));
    } catch (error) {
      toast.error(error.response?.data?.detail || t('auth.registerFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleGuestRegister = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const response = await axios.post('/auth/register-guest', guestRegisterData);
      toast.success(t('auth.accountCreatedWelcome'));
      sessionStorage.setItem('postLoginRedirect', '/guest-portal');
      onLogin(response.data.access_token, response.data.user, response.data.tenant);
    } catch (error) {
      toast.error(error.response?.data?.detail || t('auth.registerFailed'));
    } finally {
      setLoading(false);
    }
  };

  // New registration with email verification
  const handleRequestVerification = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const requestData = {
        email: hotelRegisterData.email,
        name: hotelRegisterData.name,
        password: hotelRegisterData.password,
        property_name: hotelRegisterData.property_name,
        phone: hotelRegisterData.phone,
        user_type: activeTab === 'hotel-login' ? 'hotel' : 'guest'
      };
      
      const response = await axios.post('/auth/request-verification', requestData);
      toast.success(t('auth.codeSentToEmail'));
      setRegistrationStep('verification');
    } catch (error) {
      toast.error(error.response?.data?.detail || t('auth.errorOccurred'));
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyCode = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const response = await axios.post('/auth/verify-email', {
        email: hotelRegisterData.email,
        code: verificationCode
      });
      
      toast.success(t('auth.accountCreated'));
      onLogin(response.data.access_token, response.data.user, response.data.tenant);
      
      setTimeout(() => {
        window.location.href = '/';
      }, 500);
    } catch (error) {
      toast.error(error.response?.data?.detail || t('auth.verificationFailed'));
    } finally {
      setLoading(false);
    }
  };

  // Forgot password handlers
  const handleForgotPasswordRequest = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post('/auth/forgot-password', { email: forgotEmail });
      toast.success(t('auth.resetCodeSent'));
      setForgotPasswordStep('code');
    } catch (error) {
      toast.error(error.response?.data?.detail || t('auth.errorOccurred'));
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post('/auth/reset-password', {
        email: forgotEmail,
        code: resetCode,
        new_password: hotelLoginData.password
      });
      toast.success(t('auth.passwordUpdated'));
      setShowForgotPassword(false);
      setForgotPasswordStep('email');
      setResetCode('');
    } catch (error) {
      toast.error(error.response?.data?.detail || t('auth.resetFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page" style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: isMobile 
        ? 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)' 
        : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      padding: isMobile ? '10px' : '20px'
    }}>
      <div style={{ width: '100%', maxWidth: isMobile ? '100%' : '500px' }}>
        <div style={{ textAlign: 'center', marginBottom: isMobile ? '1rem' : '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '0.75rem' }}>
            <img 
              src="/syroce-logo.svg"
              alt="Syroce Logo" 
              style={{ 
                height: isMobile ? '60px' : '70px', 
                width: 'auto',
                filter: 'brightness(0) invert(1)'
              }} 
            />
          </div>
          <p style={{ color: 'rgba(255,255,255,0.95)', fontSize: isMobile ? '0.875rem' : '1rem', marginBottom: '0.75rem', fontWeight: '500' }}>
            {isMobile ? t('auth.mobileHotelMgmt') : t('auth.completeHotelPlatform')}
          </p>
          
          {/* Language Selector */}
          <div className="flex justify-center">
            <LanguageSelector />
          </div>
        </div>

        <Card style={{ 
          borderRadius: isMobile ? '20px 20px 0 0' : '8px',
          ...(isMobile && {
            position: 'fixed',
            bottom: 0,
            left: 0,
            right: 0,
            maxHeight: '80vh',
            overflowY: 'auto'
          })
        }}>
          <CardHeader>
            <CardTitle style={{ fontSize: isMobile ? '1.25rem' : '1.5rem' }}>
              {isMobile ? t('auth.mobileLogin') : t('common.welcome')}
            </CardTitle>
            <CardDescription>
              {isMobile ? t('auth.mobileAccess') : t('auth.signIn')}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {twoFAChallenge ? (
              <div className="space-y-4">
                <div className="text-center">
                  <Shield className="w-10 h-10 mx-auto text-violet-600 mb-2" />
                  <h3 className="text-lg font-semibold">İki Adımlı Doğrulama</h3>
                  <p className="text-sm text-gray-500 mt-1">
                    {twoFAChallenge.user_email}
                  </p>
                  <p className="text-xs text-gray-500 mt-2">
                    Authenticator uygulamanızdan 6 haneli kodu veya bir
                    yedek kodu girin.
                  </p>
                </div>
                <form onSubmit={handleTwoFAVerify} className="space-y-3">
                  <Input
                    autoFocus
                    autoComplete="one-time-code"
                    inputMode="numeric"
                    placeholder="123 456"
                    value={twoFACode}
                    onChange={(e) => setTwoFACode(e.target.value)}
                    style={{ textAlign: 'center', letterSpacing: '0.3em', fontSize: '1.25rem' }}
                  />
                  <Button type="submit" className="w-full" disabled={loading || twoFACode.trim().length < 6}>
                    {loading ? 'Doğrulanıyor…' : 'Doğrula ve Giriş Yap'}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    className="w-full"
                    onClick={() => { setTwoFAChallenge(null); setTwoFACode(''); }}
                  >
                    İptal
                  </Button>
                </form>
              </div>
            ) : (
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList className="grid w-full grid-cols-2 mb-4">
                <TabsTrigger value="hotel-login" data-testid="hotel-login-tab">
                  <Hotel className="w-4 h-4 mr-2" />
                  {t('auth.hotel')}
                </TabsTrigger>
                <TabsTrigger value="guest-login" data-testid="guest-login-tab">
                  <User className="w-4 h-4 mr-2" />
                  {t('auth.guest')}
                </TabsTrigger>
              </TabsList>
              
              {/* Hotel Login */}
              <TabsContent value="hotel-login" className="space-y-4">
                <Tabs defaultValue="login">
                  <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="login">{t('common.login')}</TabsTrigger>
                    <TabsTrigger value="register">{t('common.register')}</TabsTrigger>
                  </TabsList>
                  
                  <TabsContent value="login">
                    {!showForgotPassword ? (
                      <form onSubmit={handleHotelLogin} className="space-y-4" style={{ paddingTop: '1rem' }}>
                        <div className="bg-amber-50 border border-amber-200 p-3 rounded-lg">
                          <p className="text-xs font-semibold text-amber-900 mb-1">🔑 Demo Hesabı</p>
                          <p className="text-xs text-amber-800 leading-relaxed">
                            Otel ID: <strong>100001</strong> &nbsp;|&nbsp;
                            Kullanıcı: <strong>demo</strong> &nbsp;|&nbsp;
                            Şifre: <strong>demo123</strong>
                          </p>
                          <button
                            type="button"
                            onClick={() => setHotelLoginData({ hotel_id: '100001', username: 'demo', password: 'demo123' })}
                            className="text-xs text-amber-700 hover:text-amber-900 underline mt-1"
                          >
                            Demo bilgileri otomatik doldur
                          </button>
                        </div>
                        <div>
                          <Label>Otel ID</Label>
                          <Input
                            type="text"
                            inputMode="numeric"
                            value={hotelLoginData.hotel_id}
                            onChange={(e) => setHotelLoginData({...hotelLoginData, hotel_id: e.target.value.replace(/\D/g, '').slice(0, 6)})}
                            required
                            data-testid="hotel-login-hotel-id"
                            placeholder="6 haneli otel kimliği"
                            maxLength={6}
                            style={isMobile ? { fontSize: '16px' } : {}}
                          />
                        </div>
                        <div>
                          <Label>Kullanıcı Adı</Label>
                          <Input
                            type="text"
                            value={hotelLoginData.username}
                            onChange={(e) => setHotelLoginData({...hotelLoginData, username: e.target.value})}
                            required
                            data-testid="hotel-login-username"
                            placeholder="ör. demo"
                            autoCapitalize="none"
                            autoCorrect="off"
                            style={isMobile ? { fontSize: '16px' } : {}}
                          />
                        </div>
                        <div>
                          <Label>{t('common.password')}</Label>
                          <Input
                            type="password"
                            value={hotelLoginData.password}
                            onChange={(e) => setHotelLoginData({...hotelLoginData, password: e.target.value})}
                            required
                            data-testid="hotel-login-password"
                            placeholder={isMobile ? "••••••••" : ""}
                            style={isMobile ? { fontSize: '16px' } : {}}
                          />
                        </div>
                        <div className="flex justify-end">
                          <button
                            type="button"
                            onClick={() => setShowForgotPassword(true)}
                            className="text-sm text-blue-600 hover:text-blue-800"
                          >
                            {t('auth.forgotPassword')}
                          </button>
                        </div>
                        <Button 
                          type="submit" 
                          className="w-full" 
                          disabled={loading} 
                          data-testid="hotel-login-btn"
                          onClick={(e) => {
                            if (!loading) {
                              const form = e.target.closest('form');
                              if (form) {
                                form.requestSubmit();
                              }
                            }
                          }}
                          style={isMobile ? { height: '48px', fontSize: '16px' } : {}}
                        >
                          {loading ? t('common.loading') : t('common.login')}
                        </Button>
                      </form>
                    ) : (
                      <div className="space-y-4" style={{ paddingTop: '1rem' }}>
                        <button
                          type="button"
                          onClick={() => {
                            setShowForgotPassword(false);
                            setForgotPasswordStep('email');
                          }}
                          className="text-sm text-blue-600 hover:text-blue-800 mb-4"
                        >
                          ← {t('auth.backToLogin')}
                        </button>
                        
                        {forgotPasswordStep === 'email' && (
                          <form onSubmit={handleForgotPasswordRequest} className="space-y-4">
                            <div>
                              <Label>{t('auth.yourEmail')}</Label>
                              <Input
                                type="email"
                                value={forgotEmail}
                                onChange={(e) => setForgotEmail(e.target.value)}
                                required
                                placeholder="ornek@hotel.com"
                              />
                              <p className="text-xs text-gray-500 mt-1">
                                {t('auth.sendVerificationCode')}
                              </p>
                            </div>
                            <Button type="submit" className="w-full" disabled={loading}>
                              {loading ? t('auth.sending') : t('auth.sendCode')}
                            </Button>
                          </form>
                        )}
                        
                        {forgotPasswordStep === 'code' && (
                          <form onSubmit={(e) => { e.preventDefault(); setForgotPasswordStep('newpassword'); }} className="space-y-4">
                            <div>
                              <Label>{t('auth.verificationCode')}</Label>
                              <Input
                                type="text"
                                value={resetCode}
                                onChange={(e) => setResetCode(e.target.value)}
                                required
                                placeholder="123456"
                                maxLength={6}
                              />
                              <p className="text-xs text-gray-500 mt-1">
                                {t('auth.enterSixDigitCode')}
                              </p>
                            </div>
                            <Button type="submit" className="w-full" disabled={loading}>
                              {t('auth.continue')}
                            </Button>
                          </form>
                        )}
                        
                        {forgotPasswordStep === 'newpassword' && (
                          <form onSubmit={handleResetPassword} className="space-y-4">
                            <div>
                              <Label>{t('auth.newPassword')}</Label>
                              <Input
                                type="password"
                                value={hotelLoginData.password}
                                onChange={(e) => setHotelLoginData({...hotelLoginData, password: e.target.value})}
                                required
                                placeholder="••••••••"
                                minLength={6}
                              />
                              <p className="text-xs text-gray-500 mt-1">
                                {t('auth.minSixChars')}
                              </p>
                            </div>
                            <Button type="submit" className="w-full" disabled={loading}>
                              {loading ? t('auth.updating') : t('auth.updatePassword')}
                            </Button>
                          </form>
                        )}
                      </div>
                    )}
                  </TabsContent>
                  
                  <TabsContent value="register">
                    {registrationSuccess ? (
                      <div className="space-y-4 py-4">
                        <div className="bg-green-50 border border-green-200 p-4 rounded-lg">
                          <p className="text-sm font-bold text-green-900 mb-2">✅ Hesabınız oluşturuldu!</p>
                          <p className="text-xs text-green-800 mb-3">
                            Bu bilgileri güvenli bir yere kaydedin. Bir sonraki girişinizde gerekecek.
                          </p>
                          <div className="bg-white border border-green-300 rounded p-3 space-y-2">
                            <div className="flex justify-between items-center">
                              <span className="text-xs text-gray-500">Otel ID</span>
                              <span className="text-lg font-mono font-bold text-green-700">{registrationSuccess.hotel_id || '—'}</span>
                            </div>
                            <div className="flex justify-between items-center">
                              <span className="text-xs text-gray-500">Kullanıcı Adı</span>
                              <span className="text-base font-mono font-semibold text-gray-900">{registrationSuccess.username}</span>
                            </div>
                          </div>
                        </div>
                        <Button
                          className="w-full"
                          onClick={() => {
                            const s = registrationSuccess;
                            setRegistrationSuccess(null);
                            onLogin(s.token, s.user, s.tenant);
                          }}
                        >
                          Devam Et
                        </Button>
                      </div>
                    ) : registrationStep === 'form' ? (
                      <form onSubmit={handleHotelRegister} className="space-y-4">
                        <div>
                          <Label>{t('auth.hotelName')}</Label>
                          <Input
                            value={hotelRegisterData.property_name}
                            onChange={(e) => setHotelRegisterData({...hotelRegisterData, property_name: e.target.value})}
                            required
                            placeholder="Grand Hotel"
                          />
                        </div>
                        <div>
                          <Label>{t('auth.authorizedPerson')}</Label>
                          <Input
                            value={hotelRegisterData.name}
                            onChange={(e) => setHotelRegisterData({...hotelRegisterData, name: e.target.value})}
                            required
                            placeholder="Ahmet Yılmaz"
                          />
                        </div>
                        <div>
                          <Label>{t('common.email')}</Label>
                          <Input
                            type="email"
                            value={hotelRegisterData.email}
                            onChange={(e) => setHotelRegisterData({...hotelRegisterData, email: e.target.value})}
                            required
                            placeholder="ornek@hotel.com"
                          />
                          <p className="text-xs text-gray-500 mt-1">Şifre sıfırlama e-postaları bu adrese gönderilir.</p>
                        </div>
                        <div>
                          <Label>Kullanıcı Adı</Label>
                          <Input
                            value={hotelRegisterData.username}
                            onChange={(e) => setHotelRegisterData({...hotelRegisterData, username: e.target.value.replace(/\s/g, '').toLowerCase()})}
                            required
                            minLength={3}
                            maxLength={32}
                            autoCapitalize="none"
                            autoCorrect="off"
                            pattern="[a-z0-9_.\-]{3,32}"
                            placeholder="ör. admin"
                          />
                          <p className="text-xs text-gray-500 mt-1">Sadece küçük harf, rakam ve _ . - (3-32 karakter).</p>
                        </div>
                        <div>
                          <Label>{t('common.phone')}</Label>
                          <Input
                            value={hotelRegisterData.phone}
                            onChange={(e) => setHotelRegisterData({...hotelRegisterData, phone: e.target.value})}
                            required
                            placeholder="+90 555 123 45 67"
                          />
                        </div>
                        <div>
                          <Label>{t('common.password')}</Label>
                          <Input
                            type="password"
                            value={hotelRegisterData.password}
                            onChange={(e) => setHotelRegisterData({...hotelRegisterData, password: e.target.value})}
                            required
                            minLength={6}
                            placeholder={t('auth.minSixCharsPlaceholder')}
                          />
                        </div>
                        <Button type="submit" className="w-full" disabled={loading}>
                          {loading ? t('common.loading') : 'Hesabımı Oluştur'}
                        </Button>
                      </form>
                    ) : (
                      <div className="space-y-4">
                        <div className="bg-blue-50 p-4 rounded-lg">
                          <p className="text-sm text-blue-800 font-medium mb-2">
                            📧 {t('auth.emailVerification')}
                          </p>
                          <p className="text-xs text-blue-600">
                            <strong>{hotelRegisterData.email}</strong> {t('auth.verificationSentTo')}
                          </p>
                        </div>
                        <form onSubmit={handleVerifyCode} className="space-y-4">
                          <div>
                            <Label>Doğrulama Kodu</Label>
                            <Input
                              type="text"
                              value={verificationCode}
                              onChange={(e) => setVerificationCode(e.target.value)}
                              required
                              placeholder="123456"
                              maxLength={6}
                              style={{ fontSize: '18px', letterSpacing: '4px', textAlign: 'center' }}
                            />
                            <p className="text-xs text-gray-500 mt-1">
                              {t('auth.codeValidFor')}
                            </p>
                          </div>
                          <Button type="submit" className="w-full" disabled={loading}>
                            {loading ? t('auth.verifying') : t('auth.createMyAccount')}
                          </Button>
                          <button
                            type="button"
                            onClick={() => setRegistrationStep('form')}
                            className="text-sm text-blue-600 hover:text-blue-800 w-full text-center"
                          >
                            ← {t('auth.goBack')}
                          </button>
                        </form>
                      </div>
                    )}
                  </TabsContent>
                </Tabs>
              </TabsContent>

              {/* Guest Login */}
              <TabsContent value="guest-login" className="space-y-4">
                <Tabs defaultValue="login">
                  <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="login">{t('common.login')}</TabsTrigger>
                    <TabsTrigger value="register">{t('common.register')}</TabsTrigger>
                  </TabsList>
                  
                  <TabsContent value="login">
                    <form onSubmit={handleGuestLogin} className="space-y-4" style={{ paddingTop: '1rem' }}>
                      {isMobile && (
                        <div className="bg-purple-50 p-3 rounded-lg mb-4">
                          <p className="text-sm text-purple-800 font-medium">
                            👤 {t('auth.guestMobileAccess')}
                          </p>
                          <p className="text-xs text-purple-600 mt-1">
                            {t('auth.viewBookingsManageStay')}
                          </p>
                        </div>
                      )}
                      <div>
                        <Label>{t('common.email')}</Label>
                        <Input
                          type="email"
                          value={guestLoginData.email}
                          onChange={(e) => setGuestLoginData({...guestLoginData, email: e.target.value})}
                          required
                          data-testid="guest-login-email"
                          placeholder={isMobile ? "your@email.com" : ""}
                          style={isMobile ? { fontSize: '16px' } : {}}
                        />
                      </div>
                      <div>
                        <Label>{t('common.password')}</Label>
                        <Input
                          type="password"
                          value={guestLoginData.password}
                          onChange={(e) => setGuestLoginData({...guestLoginData, password: e.target.value})}
                          required
                          data-testid="guest-login-password"
                          placeholder={isMobile ? "••••••••" : ""}
                          style={isMobile ? { fontSize: '16px' } : {}}
                        />
                      </div>
                      <Button 
                        type="submit" 
                        className="w-full" 
                        disabled={loading} 
                        data-testid="guest-login-btn"
                        onClick={(e) => {
                          // Ensure form submits when button is clicked
                          if (!loading) {
                            const form = e.target.closest('form');
                            if (form) {
                              form.requestSubmit();
                            }
                          }
                        }}
                        style={isMobile ? { height: '48px', fontSize: '16px' } : {}}
                      >
                        {loading ? t('auth.loggingIn') : t('auth.loginAsGuest')}
                      </Button>
                    </form>
                  </TabsContent>
                  
                  <TabsContent value="register">
                    <form onSubmit={handleGuestRegister} className="space-y-4">
                      <div>
                        <Label>{t('common.name')}</Label>
                        <Input
                          value={guestRegisterData.name}
                          onChange={(e) => setGuestRegisterData({...guestRegisterData, name: e.target.value})}
                          required
                          data-testid="guest-register-name"
                        />
                      </div>
                      <div>
                        <Label>{t('common.email')}</Label>
                        <Input
                          type="email"
                          value={guestRegisterData.email}
                          onChange={(e) => setGuestRegisterData({...guestRegisterData, email: e.target.value})}
                          required
                          data-testid="guest-register-email"
                        />
                      </div>
                      <div>
                        <Label>{t('common.phone')}</Label>
                        <Input
                          value={guestRegisterData.phone}
                          onChange={(e) => setGuestRegisterData({...guestRegisterData, phone: e.target.value})}
                          required
                          data-testid="guest-register-phone"
                        />
                      </div>
                      <div>
                        <Label>{t('common.password')}</Label>
                        <Input
                          type="password"
                          value={guestRegisterData.password}
                          onChange={(e) => setGuestRegisterData({...guestRegisterData, password: e.target.value})}
                          required
                          data-testid="guest-register-password"
                        />
                      </div>
                      <Button type="submit" className="w-full" disabled={loading} data-testid="guest-register-btn">
                        {loading ? t('auth.creatingAccount') : t('auth.createGuestAccount')}
                      </Button>
                    </form>
                  </TabsContent>
                </Tabs>
              </TabsContent>
            </Tabs>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default AuthPage;
