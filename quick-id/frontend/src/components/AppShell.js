import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../lib/AuthContext';
import { useTheme } from '../lib/ThemeContext';
import { useLanguage } from '../lib/LanguageContext';
import { Button } from './ui/button';
import { Sheet, SheetContent, SheetTrigger } from './ui/sheet';
import { Badge } from './ui/badge';
import {
  LayoutDashboard,
  ScanLine,
  Users,
  Layers,
  Menu,
  CreditCard,
  Settings,
  UserCog,
  LogOut,
  Shield,
  BookOpen,
  UserCheck,
  Fingerprint,
  Building2,
  Monitor,
  DoorOpen,
  BarChart3,
  UsersRound,
  Clock,
  Moon,
  Sun,
  Globe,
} from 'lucide-react';

export default function AppShell({ children }) {
  const location = useLocation();
  const { user, logout, isAdmin, sessionWarning, sessionRemainingMinutes } = useAuth();
  const { isDark, toggleTheme } = useTheme();
  const { lang, t, changeLang } = useLanguage();
  const [mobileOpen, setMobileOpen] = useState(false);

  const navItems = [
    { path: '/', label: t('nav.overview'), icon: LayoutDashboard },
    { path: '/scan', label: t('nav.scan'), icon: ScanLine },
    { path: '/bulk-scan', label: t('nav.bulkScan'), icon: Layers },
    { path: '/guests', label: t('nav.guests'), icon: Users },
    { path: '/group-checkin', label: t('nav.groupCheckin'), icon: UsersRound },
    { path: '/rooms', label: t('nav.rooms'), icon: DoorOpen },
    { path: '/face-match', label: t('nav.faceMatch'), icon: UserCheck },
    { path: '/tc-kimlik', label: t('nav.tcKimlik'), icon: Fingerprint },
    ...(isAdmin ? [
      { path: '/monitoring', label: t('nav.monitoring'), icon: BarChart3 },
      { path: '/properties', label: t('nav.properties'), icon: Building2 },
      { path: '/kiosk', label: t('nav.kiosk'), icon: Monitor },
      { path: '/users', label: t('nav.users'), icon: UserCog },
      { path: '/settings', label: t('nav.settings'), icon: Settings },
      { path: '/kvkk', label: t('nav.kvkk'), icon: Shield },
      { path: '/api-docs', label: t('nav.apiDocs'), icon: BookOpen },
    ] : []),
  ];

  const isActive = (path) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname.startsWith(path);
  };

  const NavLinks = ({ onNavigate }) => (
    <nav className="flex flex-col gap-1" data-testid="sidebar-nav">
      {navItems.map((item) => (
        <Link
          key={item.path}
          to={item.path}
          onClick={onNavigate}
          className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors duration-150 ${
            isActive(item.path)
              ? 'bg-[var(--brand-sky-soft)] text-[var(--brand-sky)]'
              : 'text-[var(--brand-slate)] hover:bg-[hsl(var(--secondary))] hover:text-[var(--brand-ink)]'
          }`}
        >
          <item.icon className="w-5 h-5" />
          {item.label}
        </Link>
      ))}
    </nav>
  );

  return (
    <div className="min-h-screen bg-[hsl(var(--background))] noise-bg">
      {/* Desktop Sidebar */}
      <aside className="hidden lg:fixed lg:flex lg:flex-col lg:w-64 lg:h-screen border-r border-[hsl(var(--border))] bg-white dark:bg-[hsl(222,47%,11%)] z-20">
        <div className="p-5 border-b border-[hsl(var(--border))]">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-[var(--brand-sky)] flex items-center justify-center">
              <CreditCard className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-[var(--brand-ink)]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                Quick ID
              </h1>
              <p className="text-[10px] text-[var(--brand-slate)] -mt-0.5">Kimlik Okuyucu</p>
            </div>
          </Link>
        </div>
        <div className="flex-1 p-3 overflow-y-auto">
          <NavLinks />
        </div>
        {/* User info + controls */}
        <div className="p-4 border-t border-[hsl(var(--border))]">
          {/* Theme + Language controls */}
          <div className="flex items-center gap-1 mb-3">
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleTheme}
              className="h-8 w-8"
              title={isDark ? t('theme.light') : t('theme.dark')}
            >
              {isDark ? <Sun className="w-4 h-4 text-yellow-500" /> : <Moon className="w-4 h-4 text-gray-500" />}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => changeLang(lang === 'tr' ? 'en' : 'tr')}
              className="h-8 px-2 text-xs gap-1"
              title="Dil / Language"
            >
              <Globe className="w-3.5 h-3.5" />
              {lang === 'tr' ? 'TR' : 'EN'}
            </Button>
          </div>
          {user && (
            <div className="flex items-center gap-2 mb-3">
              <div className="w-8 h-8 rounded-full bg-[var(--brand-sky-soft)] flex items-center justify-center">
                <span className="text-xs font-semibold text-[var(--brand-sky)]">
                  {user.name?.[0] || 'U'}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium truncate">{user.name}</p>
                <div className="flex items-center gap-1">
                  <Badge variant="outline" className="text-[9px] px-1 py-0 h-4">
                    {user.role === 'admin' ? 'Admin' : 'Resepsiyon'}
                  </Badge>
                </div>
              </div>
            </div>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={logout}
            className="w-full justify-start text-muted-foreground hover:text-[var(--brand-danger)]"
            data-testid="logout-button"
          >
            <LogOut className="w-4 h-4 mr-2" />
            {t('nav.logout')}
          </Button>
        </div>
      </aside>

      {/* Mobile Header */}
      <header className="lg:hidden sticky top-0 z-30 flex items-center justify-between h-14 px-4 border-b border-[hsl(var(--border))] bg-white/95 backdrop-blur">
        <Link to="/" className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-[var(--brand-sky)] flex items-center justify-center">
            <CreditCard className="w-4 h-4 text-white" />
          </div>
          <span className="text-sm font-semibold text-[var(--brand-ink)]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            Quick ID
          </span>
        </Link>
        <div className="flex items-center gap-2">
          {user && (
            <Badge variant="outline" className="text-[10px] h-6 px-2">
              {user.name}
            </Badge>
          )}
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" data-testid="mobile-nav-sheet-trigger">
                <Menu className="w-5 h-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-64 p-4" aria-describedby="mobile-nav-description">
              <div className="mb-6">
                <h2 className="text-lg font-semibold" style={{ fontFamily: "'Space Grotesk', sans-serif" }} id="mobile-nav-title">Quick ID</h2>
                <p className="text-xs text-muted-foreground" id="mobile-nav-description">Kimlik Okuyucu - Navigasyon</p>
              </div>
              <NavLinks onNavigate={() => setMobileOpen(false)} />
              <div className="mt-6 pt-4 border-t">
                <Button variant="ghost" size="sm" onClick={() => { logout(); setMobileOpen(false); }} className="w-full justify-start text-muted-foreground">
                  <LogOut className="w-4 h-4 mr-2" /> Çıkış Yap
                </Button>
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </header>

      {/* Main Content */}
      <main className="lg:ml-64 min-h-screen relative z-10">
        {/* Session Timeout Warning */}
        {sessionWarning && (
          <div className="sticky top-0 z-50 bg-amber-50 border-b border-amber-200 px-4 py-2">
            <div className="max-w-[1400px] mx-auto flex items-center justify-between">
              <div className="flex items-center gap-2 text-amber-800">
                <Clock className="w-4 h-4" />
                <span className="text-sm font-medium">
                  Oturum süreniz dolmak üzere{sessionRemainingMinutes ? ` (${sessionRemainingMinutes} dakika kaldı)` : ''}.
                </span>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={logout}
                className="text-amber-700 border-amber-300 hover:bg-amber-100 text-xs h-7"
              >
                Tekrar Giriş Yap
              </Button>
            </div>
          </div>
        )}
        <div className="max-w-[1400px] mx-auto p-4 sm:p-6">
          {children}
        </div>
      </main>
    </div>
  );
}
