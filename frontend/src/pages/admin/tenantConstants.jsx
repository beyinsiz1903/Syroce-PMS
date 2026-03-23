import { Building2, Zap, Crown, Settings2, BarChart3, Bot, Users } from 'lucide-react';

export const PLANS = {
  basic: {
    key: 'basic',
    label: 'Basic',
    color: 'emerald',
    badgeClass: 'bg-emerald-100 text-emerald-800 border-emerald-200',
    iconBg: 'bg-emerald-100',
    icon: Building2,
    description: '1-15 oda',
    maxRooms: 15,
    maxUsers: 3,
    price: '79€/ay',
  },
  professional: {
    key: 'professional',
    label: 'Professional',
    color: 'blue',
    badgeClass: 'bg-blue-100 text-blue-800 border-blue-200',
    iconBg: 'bg-blue-100',
    icon: Zap,
    description: '15-80 oda',
    maxRooms: 80,
    maxUsers: 15,
    price: '299€/ay',
  },
  enterprise: {
    key: 'enterprise',
    label: 'Enterprise',
    color: 'purple',
    badgeClass: 'bg-purple-100 text-purple-800 border-purple-200',
    iconBg: 'bg-purple-100',
    icon: Crown,
    description: '80+ oda',
    maxRooms: null,
    maxUsers: null,
    price: '799€/ay',
  },
};

export const MODULE_GROUPS = [
  {
    id: 'core',
    title: 'Core Modüller',
    icon: Settings2,
    color: 'gray',
    items: [
      { key: 'pms', label: 'PMS Core', hint: 'Rezervasyon, check-in/out, oda yönetimi', tier: 'basic' },
      { key: 'reservation_calendar', label: 'Rezervasyon Takvimi', hint: 'Drag & drop takvim görünümü', tier: 'basic' },
      { key: 'dashboard', label: 'Dashboard', hint: 'Ana kontrol paneli', tier: 'basic' },
      { key: 'guests', label: 'Misafir Yönetimi', hint: 'Temel misafir profilleri', tier: 'basic' },
      { key: 'housekeeping', label: 'Housekeeping', hint: 'Temel oda durumu takibi', tier: 'basic' },
      { key: 'basic_reporting', label: 'Temel Raporlar', hint: 'Günlük doluluk ve gelir', tier: 'basic' },
      { key: 'settings', label: 'Ayarlar', hint: 'Otel ayarları', tier: 'basic' },
      { key: 'pms_mobile', label: 'Mobil PMS', hint: 'Mobil erişim', tier: 'basic' },
      { key: 'invoices_basic', label: 'Basit Fatura', hint: 'PDF fatura oluşturma', tier: 'basic' },
    ],
  },
  {
    id: 'professional',
    title: 'Professional Modüller',
    icon: BarChart3,
    color: 'blue',
    items: [
      { key: 'channel_manager', label: 'Channel Manager', hint: 'OTA senkronizasyonu', tier: 'professional' },
      { key: 'folio_management', label: 'Folio Yönetimi', hint: 'Split, routing, posting', tier: 'professional' },
      { key: 'night_audit', label: 'Gece Denetimi', hint: 'End-of-day otomasyonu', tier: 'professional' },
      { key: 'invoices', label: 'Gelişmiş Fatura & Finans', hint: 'E-fatura, AR/AP', tier: 'professional' },
      { key: 'cost_management', label: 'Maliyet Yönetimi', hint: 'Maliyet takibi', tier: 'professional' },
      { key: 'reports', label: 'Gelişmiş Raporlar', hint: 'Detaylı analitik raporlar', tier: 'professional' },
      { key: 'rate_management', label: 'Rate Management', hint: 'Fiyat planı yönetimi', tier: 'professional' },
      { key: 'booking_engine', label: 'Booking Engine', hint: 'Direkt rezervasyon motoru', tier: 'professional' },
      { key: 'guest_advanced', label: 'Gelişmiş Misafir Profili', hint: 'VIP, tercihler, LTV', tier: 'professional' },
    ],
  },
  {
    id: 'enterprise',
    title: 'Enterprise Modüller',
    icon: Crown,
    color: 'purple',
    items: [
      { key: 'revenue_management', label: 'Revenue Management', hint: 'Dinamik fiyatlandırma, RMS', tier: 'enterprise' },
      { key: 'multi_property', label: 'Multi-Property', hint: 'Çoklu otel yönetimi', tier: 'enterprise' },
      { key: 'group_sales', label: 'Grup Satış & MICE', hint: 'Grup rezervasyon, etkinlik', tier: 'enterprise' },
      { key: 'sales_crm', label: 'Satış CRM', hint: 'Pipeline, lead yönetimi', tier: 'enterprise' },
      { key: 'loyalty_program', label: 'Sadakat Programı', hint: 'Puan, tier, ödüller', tier: 'enterprise' },
      { key: 'api_access', label: 'API Erişimi', hint: 'Open API, webhook', tier: 'enterprise' },
      { key: 'audit_trail', label: 'Audit Trail', hint: 'Compliance logging', tier: 'enterprise' },
    ],
  },
  {
    id: 'ai',
    title: 'AI Modülleri',
    icon: Bot,
    color: 'amber',
    items: [
      { key: 'ai', label: 'AI Genel', hint: 'Tüm AI modüllerinin üst anahtarı', tier: 'enterprise' },
      { key: 'ai_chatbot', label: 'AI Chatbot', hint: 'Akıllı misafir asistanı', tier: 'enterprise' },
      { key: 'ai_pricing', label: 'AI Dynamic Pricing', hint: 'ML fiyat önerileri', tier: 'enterprise' },
      { key: 'ai_predictive', label: 'AI Tahminler', hint: 'No-show, demand prediction', tier: 'enterprise' },
    ],
  },
];

export const ROLE_LABELS = {
  super_admin: 'Super Admin',
  admin: 'Admin',
  front_desk: 'Resepsiyon',
  housekeeping: 'Housekeeping',
  manager: 'Müdür',
  revenue: 'Revenue',
  night_audit: 'Gece Denetimi',
  gm: 'Genel Müdür',
  finance: 'Finans',
  sales: 'Satış',
};

export const tierRank = { basic: 0, professional: 1, enterprise: 2 };

export const isModuleIncludedInPlan = (moduleItem, tenantTier) => {
  const moduleTier = moduleItem.tier || 'enterprise';
  return tierRank[tenantTier] >= tierRank[moduleTier];
};
