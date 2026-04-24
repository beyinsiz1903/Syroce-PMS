import { Building2, Zap, Crown, Settings2, BarChart3, Bot, Users, Mail, Shield, Sparkles } from 'lucide-react';

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
      { key: 'mailing', label: 'Mailing & Kampanya', hint: 'E-posta şablonları, kampanyalar, otomasyon', tier: 'professional' },
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
    id: 'ops_security',
    title: 'Operasyon & Güvenlik',
    icon: Shield,
    color: 'rose',
    items: [
      { key: 'system_health', label: 'System Health', hint: 'Runtime izleme & operasyon konsolu', tier: 'enterprise' },
      { key: 'security_hardening', label: 'Güvenlik Sertleştirme', hint: 'Güvenlik kontrol paneli', tier: 'enterprise' },
      { key: 'encryption_management', label: 'Şifreleme Yönetimi', hint: 'Anahtar rotasyonu & şifreleme', tier: 'enterprise' },
      { key: 'runtime_cockpit', label: 'Runtime Cockpit', hint: 'Canlı sistem komutası', tier: 'enterprise' },
      { key: 'operator_incident', label: 'Operatör Olay Paneli', hint: 'Olay yönetimi', tier: 'enterprise' },
      { key: 'control_plane', label: 'Control Plane', hint: 'Platform yönetimi', tier: 'enterprise' },
      { key: 'lockdown', label: 'Lockdown Modu', hint: 'Acil durum kilitleme', tier: 'enterprise' },
      { key: 'data_model', label: 'Data Model', hint: 'Şema & eşleme yönetimi', tier: 'enterprise' },
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
  {
    id: 'addons',
    title: 'Add-on Modüller (Ekstra Ücretli)',
    icon: Sparkles,
    color: 'pink',
    items: [
      { key: 'spa', label: 'Spa & Wellness', hint: 'Hizmet kataloğu, terapist & oda yönetimi, randevu defteri, folio entegrasyonu', tier: 'addon', addon: true },
      { key: 'mice', label: 'MICE & Banquet', hint: 'Toplantı/balo salonları, catering menüleri, kurumsal CRM, etkinlik yönetimi', tier: 'addon', addon: true },
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
  // Add-on modules are never "included" in any plan — they're always
  // upsell items that super_admin enables per-tenant.
  if (moduleItem.addon || moduleItem.tier === 'addon') return false;
  const moduleTier = moduleItem.tier || 'enterprise';
  return tierRank[tenantTier] >= tierRank[moduleTier];
};
