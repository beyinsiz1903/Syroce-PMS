import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Hotel, User, Smartphone } from 'lucide-react';
import LanguageSelector from '@/components/LanguageSelector';

const AuthPage = ({ onLogin }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
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
  
  const [hotelLoginData, setHotelLoginData] = useState({ email: '', password: '' });
  const [guestLoginData, setGuestLoginData] = useState({ email: '', password: '' });
  
  const [hotelRegisterData, setHotelRegisterData] = useState({
    property_name: '', email: '', password: '', name: '', phone: '', address: ''
  });
  
  const [guestRegisterData, setGuestRegisterData] = useState({
    email: '', password: '', name: '', phone: ''
  });

  const handleHotelLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      console.log('🔐 Attempting login with:', {
        email: hotelLoginData.email,
        passwordLength: hotelLoginData.password?.length
      });
      console.log('📡 Axios baseURL:', axios.defaults.baseURL);
      console.log('📡 Full URL will be:', axios.defaults.baseURL + '/auth/login');
      
      const response = await axios.post('/auth/login', hotelLoginData);
      console.log('✅ Login successful - FULL RESPONSE:', response.data);
      console.log('👤 User object from backend:', response.data.user);
      console.log('🎭 User role from backend:', response.data.user?.role);
      
      toast.success('Login successful! Redirecting...');
      
      // Call onLogin FIRST to update app state
      await onLogin(response.data.access_token, response.data.user, response.data.tenant);
      
      // Store auth data in localStorage
      localStorage.setItem('token', response.data.access_token);
      localStorage.setItem('user', JSON.stringify(response.data.user));
      localStorage.setItem('tenant', response.data.tenant ? JSON.stringify(response.data.tenant) : 'null');
      
      // Set axios header immediately
      axios.defaults.headers.common['Authorization'] = `Bearer ${response.data.access_token}`;
      
      console.log('✅ Auth data stored, redirecting to dashboard...');
      
      // Use hard redirect to ensure clean state
      setTimeout(() => {
        window.location.href = '/app/dashboard';
      }, 300);
    } catch (error) {
      console.error('❌ Login error:', error);
      console.error('❌ Error response:', error.response);
      console.error('❌ Error message:', error.message);
      console.error('❌ Error config:', error.config);
      
      const errorMessage = error.response?.data?.detail || error.message || 'Login failed';
      console.error('❌ Showing error to user:', errorMessage);
      toast.error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleGuestLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const response = await axios.post('/auth/login', guestLoginData);
      toast.success('Welcome back!');
      onLogin(response.data.access_token, response.data.user, response.data.tenant);
      // Navigate using React Router
      navigate('/guest-portal');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  const handleHotelRegister = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      console.log('📝 Register data being sent:', hotelRegisterData);
      const response = await axios.post('/auth/register', hotelRegisterData);
      console.log('✅ Register response:', response.data);
      toast.success('Registration successful!');
      onLogin(response.data.access_token, response.data.user, response.data.tenant);
      // Navigate using React Router
      navigate('/');
    } catch (error) {
      console.error('❌ Registration error:', error);
      console.error('❌ Error response:', error.response?.data);
      toast.error(error.response?.data?.detail || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  const handleGuestRegister = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const response = await axios.post('/auth/register-guest', guestRegisterData);
      toast.success('Account created! Welcome!');
      onLogin(response.data.access_token, response.data.user, response.data.tenant);
      // Navigate using React Router
      navigate('/guest-portal');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Registration failed');
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
      toast.success('Doğrulama kodu e-postanıza gönderildi!');
      setRegistrationStep('verification');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Hata oluştu');
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
      
      toast.success('Hesabınız başarıyla oluşturuldu!');
      onLogin(response.data.access_token, response.data.user, response.data.tenant);
      
      setTimeout(() => {
        window.location.href = '/';
      }, 500);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Doğrulama başarısız');
    } finally {
      setLoading(false);
    }
  };

  // Forgot password handlers
  const handleForgotPasswordRequest = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post('/auth/forgot-password', {
        email: hotelLoginData.email
      });
      toast.success('Şifre sıfırlama kodu e-postanıza gönderildi');
      setForgotPasswordStep('code');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Hata oluştu');
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post('/auth/reset-password', {
        email: hotelLoginData.email,
        code: resetCode,
        new_password: hotelLoginData.password
      });
      toast.success('Şifreniz başarıyla güncellendi!');
      setShowForgotPassword(false);
      setForgotPasswordStep('email');
      setResetCode('');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Sıfırlama başarısız');
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
            {isMobile ? 'Mobile Hotel Management' : 'Complete Hotel Management Platform'}
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
              {isMobile ? 'Mobile Login' : t('common.welcome')}
            </CardTitle>
            <CardDescription>
              {isMobile ? 'Access your hotel on the go' : t('auth.signIn')}
            </CardDescription>
          </CardHeader>
          <CardContent>
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
                        {isMobile && (
                          <div className="bg-blue-50 p-3 rounded-lg mb-4">
                            <p className="text-sm text-blue-800 font-medium">
                              📱 Mobile Quick Access
                            </p>
                            <p className="text-xs text-blue-600 mt-1">
                              Manage your hotel from anywhere
                            </p>
                          </div>
                        )}
                        <div>
                          <Label>{t('common.email')}</Label>
                          <Input
                            type="email"
                            value={hotelLoginData.email}
                            onChange={(e) => setHotelLoginData({...hotelLoginData, email: e.target.value})}
                            required
                            data-testid="hotel-login-email"
                            placeholder={isMobile ? "your@email.com" : ""}
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
                            Şifremi Unuttum
                          </button>
                        </div>
                        <Button 
                          type="submit" 
                          className="w-full" 
                          disabled={loading} 
                          data-testid="hotel-login-btn"
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
                          ← Giriş Sayfasına Dön
                        </button>
                        
                        {forgotPasswordStep === 'email' && (
                          <form onSubmit={handleForgotPasswordRequest} className="space-y-4">
                            <div>
                              <Label>E-posta Adresiniz</Label>
                              <Input
                                type="email"
                                value={hotelLoginData.email}
                                onChange={(e) => setHotelLoginData({...hotelLoginData, email: e.target.value})}
                                required
                                placeholder="ornek@hotel.com"
                              />
                              <p className="text-xs text-gray-500 mt-1">
                                Size bir doğrulama kodu göndereceğiz
                              </p>
                            </div>
                            <Button type="submit" className="w-full" disabled={loading}>
                              {loading ? 'Gönderiliyor...' : 'Kod Gönder'}
                            </Button>
                          </form>
                        )}
                        
                        {forgotPasswordStep === 'code' && (
                          <form onSubmit={(e) => { e.preventDefault(); setForgotPasswordStep('newpassword'); }} className="space-y-4">
                            <div>
                              <Label>Doğrulama Kodu</Label>
                              <Input
                                type="text"
                                value={resetCode}
                                onChange={(e) => setResetCode(e.target.value)}
                                required
                                placeholder="123456"
                                maxLength={6}
                              />
                              <p className="text-xs text-gray-500 mt-1">
                                E-postanıza gönderilen 6 haneli kodu girin
                              </p>
                            </div>
                            <Button type="submit" className="w-full" disabled={loading}>
                              Devam Et
                            </Button>
                          </form>
                        )}
                        
                        {forgotPasswordStep === 'newpassword' && (
                          <form onSubmit={handleResetPassword} className="space-y-4">
                            <div>
                              <Label>Yeni Şifreniz</Label>
                              <Input
                                type="password"
                                value={hotelLoginData.password}
                                onChange={(e) => setHotelLoginData({...hotelLoginData, password: e.target.value})}
                                required
                                placeholder="••••••••"
                                minLength={6}
                              />
                              <p className="text-xs text-gray-500 mt-1">
                                En az 6 karakter olmalı
                              </p>
                            </div>
                            <Button type="submit" className="w-full" disabled={loading}>
                              {loading ? 'Güncelleniyor...' : 'Şifremi Güncelle'}
                            </Button>
                          </form>
                        )}
                      </div>
                    )}
                  </TabsContent>
                  
                  <TabsContent value="register">
                    {registrationStep === 'form' ? (
                      <form onSubmit={handleRequestVerification} className="space-y-4">
                        <div>
                          <Label>Otel Adı</Label>
                          <Input
                            value={hotelRegisterData.property_name}
                            onChange={(e) => setHotelRegisterData({...hotelRegisterData, property_name: e.target.value})}
                            required
                            placeholder="Grand Hotel"
                          />
                        </div>
                        <div>
                          <Label>Yetkili Adı Soyadı</Label>
                          <Input
                            value={hotelRegisterData.name}
                            onChange={(e) => setHotelRegisterData({...hotelRegisterData, name: e.target.value})}
                            required
                            placeholder="Ahmet Yılmaz"
                          />
                        </div>
                        <div>
                          <Label>E-posta</Label>
                          <Input
                            type="email"
                            value={hotelRegisterData.email}
                            onChange={(e) => setHotelRegisterData({...hotelRegisterData, email: e.target.value})}
                            required
                            placeholder="ornek@hotel.com"
                          />
                        </div>
                        <div>
                          <Label>Telefon</Label>
                          <Input
                            value={hotelRegisterData.phone}
                            onChange={(e) => setHotelRegisterData({...hotelRegisterData, phone: e.target.value})}
                            required
                            placeholder="+90 555 123 45 67"
                          />
                        </div>
                        <div>
                          <Label>Şifre</Label>
                          <Input
                            type="password"
                            value={hotelRegisterData.password}
                            onChange={(e) => setHotelRegisterData({...hotelRegisterData, password: e.target.value})}
                            required
                            minLength={6}
                            placeholder="En az 6 karakter"
                          />
                        </div>
                        <Button type="submit" className="w-full" disabled={loading}>
                          {loading ? 'Gönderiliyor...' : 'Doğrulama Kodu Gönder'}
                        </Button>
                      </form>
                    ) : (
                      <div className="space-y-4">
                        <div className="bg-blue-50 p-4 rounded-lg">
                          <p className="text-sm text-blue-800 font-medium mb-2">
                            📧 E-posta Doğrulama
                          </p>
                          <p className="text-xs text-blue-600">
                            <strong>{hotelRegisterData.email}</strong> adresine 6 haneli bir doğrulama kodu gönderdik. 
                            Lütfen e-postanızı kontrol edin.
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
                              Kod 15 dakika geçerlidir
                            </p>
                          </div>
                          <Button type="submit" className="w-full" disabled={loading}>
                            {loading ? 'Doğrulanıyor...' : 'Hesabımı Oluştur'}
                          </Button>
                          <button
                            type="button"
                            onClick={() => setRegistrationStep('form')}
                            className="text-sm text-blue-600 hover:text-blue-800 w-full text-center"
                          >
                            ← Geri Dön
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
                    <TabsTrigger value="login">Login</TabsTrigger>
                    <TabsTrigger value="register">Register</TabsTrigger>
                  </TabsList>
                  
                  <TabsContent value="login">
                    <form onSubmit={handleGuestLogin} className="space-y-4" style={{ paddingTop: '1rem' }}>
                      {isMobile && (
                        <div className="bg-purple-50 p-3 rounded-lg mb-4">
                          <p className="text-sm text-purple-800 font-medium">
                            👤 Guest Mobile Access
                          </p>
                          <p className="text-xs text-purple-600 mt-1">
                            View bookings and manage your stay
                          </p>
                        </div>
                      )}
                      <div>
                        <Label>Email</Label>
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
                        <Label>Password</Label>
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
                        {loading ? 'Logging in...' : 'Login as Guest'}
                      </Button>
                    </form>
                  </TabsContent>
                  
                  <TabsContent value="register">
                    <form onSubmit={handleGuestRegister} className="space-y-4">
                      <div>
                        <Label>Name</Label>
                        <Input
                          value={guestRegisterData.name}
                          onChange={(e) => setGuestRegisterData({...guestRegisterData, name: e.target.value})}
                          required
                          data-testid="guest-register-name"
                        />
                      </div>
                      <div>
                        <Label>Email</Label>
                        <Input
                          type="email"
                          value={guestRegisterData.email}
                          onChange={(e) => setGuestRegisterData({...guestRegisterData, email: e.target.value})}
                          required
                          data-testid="guest-register-email"
                        />
                      </div>
                      <div>
                        <Label>Phone</Label>
                        <Input
                          value={guestRegisterData.phone}
                          onChange={(e) => setGuestRegisterData({...guestRegisterData, phone: e.target.value})}
                          required
                          data-testid="guest-register-phone"
                        />
                      </div>
                      <div>
                        <Label>Password</Label>
                        <Input
                          type="password"
                          value={guestRegisterData.password}
                          onChange={(e) => setGuestRegisterData({...guestRegisterData, password: e.target.value})}
                          required
                          data-testid="guest-register-password"
                        />
                      </div>
                      <Button type="submit" className="w-full" disabled={loading} data-testid="guest-register-btn">
                        {loading ? 'Creating Account...' : 'Create Guest Account'}
                      </Button>
                    </form>
                  </TabsContent>
                </Tabs>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default AuthPage;
