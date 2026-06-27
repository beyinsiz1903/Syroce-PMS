import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Shield } from 'lucide-react';
import { cn } from '@/lib/utils';
import LanguageSelector from '@/components/LanguageSelector';

// Marka diline (LandingPage) uygun ortak alan/etiket sinifleri.
const fieldClass =
  'mt-1.5 border-white/15 bg-white/[0.05] text-white placeholder:text-slate-500 ' +
  'focus-visible:border-cyan-400/50 focus-visible:ring-cyan-400/30';
const labelClass = 'text-sm font-medium text-slate-300';
const linkClass = 'text-sm font-medium text-cyan-300 transition hover:text-cyan-200';

// Birincil eylem butonu — LandingPage hero CTA'si ile ayni cyan/teal gradyan.
const CtaButton = ({ className = '', children, ...props }) => (
  <Button
    {...props}
    className={cn(
      'w-full border-0 bg-gradient-to-r from-cyan-400 to-teal-300 font-semibold text-[#05070f] ' +
        'shadow-[0_12px_40px_-10px_rgba(34,211,238,0.6)] transition ' +
        'hover:from-cyan-300 hover:to-teal-200 hover:text-[#05070f] disabled:opacity-60',
      className,
    )}
  >
    {children}
  </Button>
);

const AuthPage = ({ onLogin }) => {
  const { t } = useTranslation();
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
  const [forgotEmail, setForgotEmail] = useState('');

  const [hotelRegisterData, setHotelRegisterData] = useState({
    property_name: '', email: '', username: '', password: '', name: '', phone: '', address: ''
  });

  // After successful registration, show generated hotel_id
  const [registrationSuccess, setRegistrationSuccess] = useState(null); // { hotel_id, username }

  // 2FA challenge state — when login returns requires_2fa, we hold the
  // challenge_token here and switch to the code-entry view.
  const [twoFAChallenge, setTwoFAChallenge] = useState(null); // {challenge_token, user_email}
  const [twoFACode, setTwoFACode] = useState('');

  const handleHotelLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        email: String(hotelLoginData.email || '').trim().toLowerCase(),
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
      onLogin(response.data.access_token, response.data.user, response.data.tenant, response.data.refresh_token);
      if (response.data?.user?.requires_password_change) {
        toast.info('Devam etmek icin sifrenizi degistirmelisiniz.');
        setTimeout(() => { window.location.href = '/profile'; }, 300);
        return;
      }
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
      onLogin(r.data.access_token, r.data.user, r.data.tenant, r.data.refresh_token);
      if (r.data?.user?.requires_password_change) {
        toast.info('Devam etmek icin sifrenizi degistirmelisiniz.');
        setTimeout(() => { window.location.href = '/profile'; }, 300);
        return;
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Doğrulama başarısız');
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
        user_type: 'hotel'
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
      onLogin(response.data.access_token, response.data.user, response.data.tenant, response.data.refresh_token);

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

  const mobileInputStyle = isMobile ? { fontSize: '16px' } : {};

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#05070f] px-4 py-10 text-slate-100 antialiased">
      {/* Arka plan: LandingPage marka gradyan + neon bloblar */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(34,211,238,0.10),_transparent_60%),radial-gradient(ellipse_at_bottom,_rgba(99,102,241,0.10),_transparent_60%)]" />
        <div className="absolute left-[-10%] top-[6%] h-[420px] w-[420px] rounded-full bg-cyan-500/25 blur-3xl" />
        <div className="absolute right-[-8%] top-[14%] h-[480px] w-[480px] rounded-full bg-indigo-500/30 blur-3xl" />
        <div className="absolute bottom-[-6%] right-[18%] h-[360px] w-[360px] rounded-full bg-teal-400/20 blur-3xl" />
      </div>

      <div className="relative z-10 w-full max-w-md">
        {/* Logo + tagline + dil seçici */}
        <div className="mb-6 text-center">
          <a href="/" title="Ana sayfaya dön" className="inline-block">
            <picture>
              <source
                type="image/webp"
                srcSet="/syroce-circle-128.webp 1x, /syroce-circle-256.webp 2x"
              />
              <img
                src="/syroce-circle.png"
                alt="Syroce Logo"
                width={isMobile ? 88 : 104}
                height={isMobile ? 88 : 104}
                className="mx-auto rounded-full object-contain shadow-[0_18px_50px_-12px_rgba(34,211,238,0.45)]"
                style={{ height: isMobile ? '88px' : '104px', width: isMobile ? '88px' : '104px' }}
              />
            </picture>
          </a>
          <p className="mt-4 text-sm font-medium text-slate-300 sm:text-base">
            {isMobile ? t('auth.mobileHotelMgmt') : t('auth.completeHotelPlatform')}
          </p>
          <div className="mt-3 flex justify-center">
            <LanguageSelector />
          </div>
        </div>

        {/* Cam kart */}
        <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-6 shadow-[0_24px_70px_-24px_rgba(8,18,46,0.85)] backdrop-blur-xl sm:p-8">
          <div className="mb-6">
            <h2 className="text-xl font-semibold text-white" style={{ fontFamily: 'Space Grotesk' }}>
              {isMobile ? t('auth.mobileLogin') : t('common.welcome')}
            </h2>
            <p className="mt-1 text-sm text-slate-400">
              {isMobile ? t('auth.mobileAccess') : t('auth.signIn')}
            </p>
          </div>

          {twoFAChallenge ? (
            <div className="space-y-4">
              <div className="text-center">
                <Shield className="mx-auto mb-2 h-10 w-10 text-cyan-300" />
                <h3 className="text-lg font-semibold text-white">{t('auth.twoFATitle')}</h3>
                <p className="mt-1 text-sm text-slate-300">{twoFAChallenge.user_email}</p>
                <p className="mt-2 text-xs text-slate-400">{t('auth.twoFAHint')}</p>
              </div>
              <form onSubmit={handleTwoFAVerify} className="space-y-3">
                <Input
                  autoFocus
                  autoComplete="one-time-code"
                  inputMode="text"
                  placeholder="123 456"
                  value={twoFACode}
                  onChange={(e) => setTwoFACode(e.target.value)}
                  className={cn(fieldClass, 'mt-0 text-center text-xl tracking-[0.3em]')}
                />
                <CtaButton type="submit" disabled={loading || twoFACode.trim().length < 6}>
                  {loading ? t('auth.twoFAVerifying') : t('auth.twoFAVerifyButton')}
                </CtaButton>
                <Button
                  type="button"
                  variant="ghost"
                  className="w-full text-slate-300 hover:bg-white/5 hover:text-white"
                  onClick={() => { setTwoFAChallenge(null); setTwoFACode(''); }}
                >
                  {t('auth.twoFACancel')}
                </Button>
              </form>
            </div>
          ) : (
            <Tabs defaultValue="login">
              <TabsList className="mb-5 grid w-full grid-cols-2 rounded-xl border border-white/10 bg-white/[0.04] p-1">
                <TabsTrigger
                  value="login"
                  className="rounded-lg text-slate-300 data-[state=active]:bg-white/10 data-[state=active]:text-white data-[state=active]:shadow-none"
                >
                  {t('common.login')}
                </TabsTrigger>
                <TabsTrigger
                  value="register"
                  className="rounded-lg text-slate-300 data-[state=active]:bg-white/10 data-[state=active]:text-white data-[state=active]:shadow-none"
                >
                  {t('common.register')}
                </TabsTrigger>
              </TabsList>

              {/* Otel Girişi */}
              <TabsContent value="login" className="space-y-4">
                {!showForgotPassword ? (
                  <form onSubmit={handleHotelLogin} className="space-y-4">
                    <div>
                      <Label className={labelClass}>{t('common.email')}</Label>
                      <Input
                        type="email"
                        value={hotelLoginData.email}
                        onChange={(e) => setHotelLoginData({ ...hotelLoginData, email: e.target.value })}
                        required
                        data-testid="hotel-login-email"
                        placeholder={t('auth.emailPlaceholder')}
                        autoCapitalize="none"
                        autoCorrect="off"
                        autoComplete="email"
                        className={fieldClass}
                        style={mobileInputStyle}
                      />
                    </div>
                    <div>
                      <Label className={labelClass}>{t('common.password')}</Label>
                      <Input
                        type="password"
                        value={hotelLoginData.password}
                        onChange={(e) => setHotelLoginData({ ...hotelLoginData, password: e.target.value })}
                        required
                        data-testid="hotel-login-password"
                        placeholder="••••••••"
                        autoComplete="current-password"
                        className={fieldClass}
                        style={mobileInputStyle}
                      />
                    </div>
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={() => setShowForgotPassword(true)}
                        className={linkClass}
                      >
                        {t('auth.forgotPassword')}
                      </button>
                    </div>
                    <CtaButton
                      type="submit"
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
                    </CtaButton>
                  </form>
                ) : (
                  <div className="space-y-4">
                    <button
                      type="button"
                      onClick={() => {
                        setShowForgotPassword(false);
                        setForgotPasswordStep('email');
                      }}
                      className={cn(linkClass, 'mb-2 inline-block')}
                    >
                      ← {t('auth.backToLogin')}
                    </button>

                    {forgotPasswordStep === 'email' && (
                      <form onSubmit={handleForgotPasswordRequest} className="space-y-4">
                        <div>
                          <Label className={labelClass}>{t('auth.yourEmail')}</Label>
                          <Input
                            type="email"
                            value={forgotEmail}
                            onChange={(e) => setForgotEmail(e.target.value)}
                            required
                            autoComplete="email"
                            placeholder={t('auth.emailPlaceholder')}
                            className={fieldClass}
                            style={mobileInputStyle}
                          />
                          <p className="mt-1 text-xs text-slate-500">{t('auth.sendVerificationCode')}</p>
                        </div>
                        <CtaButton type="submit" disabled={loading}>
                          {loading ? t('auth.sending') : t('auth.sendCode')}
                        </CtaButton>
                      </form>
                    )}

                    {forgotPasswordStep === 'code' && (
                      <form onSubmit={(e) => { e.preventDefault(); setForgotPasswordStep('newpassword'); }} className="space-y-4">
                        <div>
                          <Label className={labelClass}>{t('auth.verificationCode')}</Label>
                          <Input
                            type="text"
                            value={resetCode}
                            onChange={(e) => setResetCode(e.target.value)}
                            required
                            placeholder="123456"
                            maxLength={6}
                            className={fieldClass}
                            style={mobileInputStyle}
                          />
                          <p className="mt-1 text-xs text-slate-500">{t('auth.enterSixDigitCode')}</p>
                        </div>
                        <CtaButton type="submit" disabled={loading}>
                          {t('auth.continue')}
                        </CtaButton>
                      </form>
                    )}

                    {forgotPasswordStep === 'newpassword' && (
                      <form onSubmit={handleResetPassword} className="space-y-4">
                        <div>
                          <Label className={labelClass}>{t('auth.newPassword')}</Label>
                          <Input
                            type="password"
                            value={hotelLoginData.password}
                            onChange={(e) => setHotelLoginData({ ...hotelLoginData, password: e.target.value })}
                            required
                            placeholder="••••••••"
                            autoComplete="new-password"
                            minLength={6}
                            className={fieldClass}
                            style={mobileInputStyle}
                          />
                          <p className="mt-1 text-xs text-slate-500">{t('auth.minSixChars')}</p>
                        </div>
                        <CtaButton type="submit" disabled={loading}>
                          {loading ? t('auth.updating') : t('auth.updatePassword')}
                        </CtaButton>
                      </form>
                    )}
                  </div>
                )}
              </TabsContent>

              {/* Otel Kaydı */}
              <TabsContent value="register" className="space-y-4">
                {registrationSuccess ? (
                  <div className="space-y-4">
                    <div className="rounded-xl border border-emerald-400/30 bg-emerald-400/10 p-4">
                      <p className="mb-2 text-sm font-bold text-emerald-200">{t('auth.accountCreatedTitle')}</p>
                      <p className="mb-3 text-xs text-emerald-100/80">{t('auth.accountCreatedNote')}</p>
                      <div className="space-y-2 rounded-lg border border-white/10 bg-white/[0.05] p-3">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-slate-400">{t('auth.hotelIdLabel')}</span>
                          <span className="font-mono text-lg font-bold text-cyan-300">{registrationSuccess.hotel_id || '—'}</span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-slate-400">{t('auth.username')}</span>
                          <span className="font-mono text-base font-semibold text-white">{registrationSuccess.username}</span>
                        </div>
                      </div>
                    </div>
                    <CtaButton
                      onClick={() => {
                        const s = registrationSuccess;
                        setRegistrationSuccess(null);
                        onLogin(s.token, s.user, s.tenant);
                      }}
                    >
                      {t('auth.continueButton')}
                    </CtaButton>
                  </div>
                ) : registrationStep === 'form' ? (
                  <form onSubmit={handleHotelRegister} className="space-y-4">
                    <div>
                      <Label className={labelClass}>{t('auth.hotelName')}</Label>
                      <Input
                        value={hotelRegisterData.property_name}
                        onChange={(e) => setHotelRegisterData({ ...hotelRegisterData, property_name: e.target.value })}
                        required
                        placeholder={t('auth.hotelNamePlaceholder')}
                        className={fieldClass}
                        style={mobileInputStyle}
                      />
                    </div>
                    <div>
                      <Label className={labelClass}>{t('auth.authorizedPerson')}</Label>
                      <Input
                        value={hotelRegisterData.name}
                        onChange={(e) => setHotelRegisterData({ ...hotelRegisterData, name: e.target.value })}
                        required
                        placeholder={t('auth.authorizedPersonPlaceholder')}
                        className={fieldClass}
                        style={mobileInputStyle}
                      />
                    </div>
                    <div>
                      <Label className={labelClass}>{t('common.email')}</Label>
                      <Input
                        type="email"
                        value={hotelRegisterData.email}
                        onChange={(e) => setHotelRegisterData({ ...hotelRegisterData, email: e.target.value })}
                        required
                        autoComplete="email"
                        placeholder={t('auth.emailPlaceholder')}
                        className={fieldClass}
                        style={mobileInputStyle}
                      />
                      <p className="mt-1 text-xs text-slate-500">{t('auth.passwordResetEmailNote')}</p>
                    </div>
                    <div>
                      <Label className={labelClass}>{t('auth.username')}</Label>
                      <Input
                        value={hotelRegisterData.username}
                        onChange={(e) => setHotelRegisterData({ ...hotelRegisterData, username: e.target.value.replace(/\s/g, '').toLowerCase() })}
                        required
                        minLength={3}
                        maxLength={32}
                        autoCapitalize="none"
                        autoCorrect="off"
                        autoComplete="username"
                        pattern="[a-z0-9_.\-]{3,32}"
                        placeholder={t('auth.usernamePlaceholder')}
                        className={fieldClass}
                        style={mobileInputStyle}
                      />
                      <p className="mt-1 text-xs text-slate-500">{t('auth.usernameHint')}</p>
                    </div>
                    <div>
                      <Label className={labelClass}>{t('common.phone')}</Label>
                      <Input
                        value={hotelRegisterData.phone}
                        onChange={(e) => setHotelRegisterData({ ...hotelRegisterData, phone: e.target.value })}
                        required
                        autoComplete="tel"
                        placeholder={t('auth.phonePlaceholder')}
                        className={fieldClass}
                        style={mobileInputStyle}
                      />
                    </div>
                    <div>
                      <Label className={labelClass}>{t('common.password')}</Label>
                      <Input
                        type="password"
                        value={hotelRegisterData.password}
                        onChange={(e) => setHotelRegisterData({ ...hotelRegisterData, password: e.target.value })}
                        required
                        minLength={6}
                        autoComplete="new-password"
                        placeholder={t('auth.minSixCharsPlaceholder')}
                        className={fieldClass}
                        style={mobileInputStyle}
                      />
                    </div>
                    <CtaButton type="submit" disabled={loading}>
                      {loading ? t('common.loading') : t('auth.createMyAccountSubmit')}
                    </CtaButton>
                  </form>
                ) : (
                  <div className="space-y-4">
                    <div className="rounded-xl border border-cyan-400/30 bg-cyan-400/10 p-4">
                      <p className="mb-2 text-sm font-medium text-cyan-100">{t('auth.emailVerification')}</p>
                      <p className="text-xs text-cyan-200/80">
                        <strong>{hotelRegisterData.email}</strong> {t('auth.verificationSentTo')}
                      </p>
                    </div>
                    <form onSubmit={handleVerifyCode} className="space-y-4">
                      <div>
                        <Label className={labelClass}>{t('auth.verificationCodeLabel')}</Label>
                        <Input
                          type="text"
                          value={verificationCode}
                          onChange={(e) => setVerificationCode(e.target.value)}
                          required
                          placeholder="123456"
                          maxLength={6}
                          className={cn(fieldClass, 'text-center text-lg tracking-[0.25em]')}
                          style={mobileInputStyle}
                        />
                        <p className="mt-1 text-xs text-slate-500">{t('auth.codeValidFor')}</p>
                      </div>
                      <CtaButton type="submit" disabled={loading}>
                        {loading ? t('auth.verifying') : t('auth.createMyAccount')}
                      </CtaButton>
                      <button
                        type="button"
                        onClick={() => setRegistrationStep('form')}
                        className={cn(linkClass, 'w-full text-center')}
                      >
                        ← {t('auth.goBack')}
                      </button>
                    </form>
                  </div>
                )}
              </TabsContent>
            </Tabs>
          )}
        </div>
      </div>
    </div>
  );
};

export default AuthPage;
