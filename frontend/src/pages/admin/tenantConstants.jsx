import { Home, Building2, Zap, Crown, Settings2, BarChart3, Bot, Users, Mail, Shield, Sparkles, BedDouble, PlugZap, FileText, TrendingUp } from 'lucide-react';

export const PLANS = {
  // Mini — Elektraweb Mini muadili: pansiyon, butik otel, apart için
  // minimum çalışır PMS. Rezervasyon, folyo, basit fatura, gün sonu,
  // KBS polis bildirimi, sanal POS + ödeme linki ve 3 kanala kadar
  // OTA bağlantısı dahildir. Üst paketler bu özelliklerin tümünü +
  // ek modülleri kapsar.
  mini: {
    key: 'mini',
    label: 'Mini',
    color: 'teal',
    badgeClass: 'bg-teal-100 text-teal-800 border-teal-200',
    iconBg: 'bg-teal-100',
    icon: Home,
    description: '1-15 oda · pansiyon / butik',
    maxRooms: 15,
    maxUsers: 2,
    price: '35€/ay',
  },
  basic: {
    key: 'basic',
    label: 'Basic',
    color: 'emerald',
    badgeClass: 'bg-emerald-100 text-emerald-800 border-emerald-200',
    iconBg: 'bg-emerald-100',
    icon: Building2,
    description: '16-30 oda · küçük şehir oteli',
    maxRooms: 30,
    maxUsers: 4,
    price: '79€/ay',
  },
  professional: {
    key: 'professional',
    label: 'Professional',
    color: 'sky',
    badgeClass: 'bg-sky-100 text-sky-800 border-sky-200',
    iconBg: 'bg-sky-100 text-sky-700',
    icon: Zap,
    description: '31-80 oda · orta ölçekli otel',
    maxRooms: 80,
    maxUsers: 15,
    price: '299€/ay',
  },
  enterprise: {
    key: 'enterprise',
    label: 'Enterprise',
    color: 'indigo',
    badgeClass: 'bg-indigo-100 text-indigo-800 border-indigo-200',
    iconBg: 'bg-indigo-100 text-indigo-700',
    icon: Crown,
    description: '80+ oda · resort / zincir',
    maxRooms: null,
    maxUsers: null,
    price: '799€/ay',
  },
};

export const MODULE_GROUPS = [
  {
    id: 'mini',
    title: 'Mini — Çekirdek PMS (Pansiyon / Butik)',
    icon: Home,
    color: 'teal',
    description: 'Elektraweb Mini muadili: az odalı tesis için minimum çalışır PMS seti.',
    items: [
      { key: 'pms', label: 'PMS Çekirdek', hint: 'Rezervasyon, check-in/out, konaklama, oda blokajı', tier: 'mini' },
      { key: 'reservation_calendar', label: 'Rezervasyon Takvimi', hint: 'Drag & drop takvim görünümü', tier: 'mini' },
      { key: 'dashboard', label: 'Dashboard', hint: 'Doluluk, gelir, hareket grafikleri', tier: 'mini' },
      { key: 'guests', label: 'Misafir Yönetimi', hint: 'Temel misafir profilleri', tier: 'mini' },
      { key: 'housekeeping', label: 'Housekeeping (Temel)', hint: 'Temel oda durumu takibi', tier: 'mini' },
      { key: 'basic_reporting', label: 'Doluluk & Gelir Raporları', hint: 'Maliye uyumlu günlük raporlar', tier: 'mini' },
      { key: 'settings', label: 'Ayarlar', hint: 'Otel ayarları', tier: 'mini' },
      { key: 'pms_mobile', label: 'Mobil PMS', hint: 'Mobil erişim', tier: 'mini' },
      { key: 'folio_basic', label: 'Folyo (Basit)', hint: 'Konaklama folyosu, ödeme/şarj satırları', tier: 'mini' },
      { key: 'invoices_basic', label: 'Fatura (Basit)', hint: 'PDF fatura + e-arşiv', tier: 'mini' },
      { key: 'night_audit_basic', label: 'Gün Sonu (Basit)', hint: 'Tek-tıkla gün sonu (night audit lite)', tier: 'mini' },
      { key: 'channel_manager_lite', label: 'Channel Manager (Lite)', hint: 'Booking, Expedia, Hotels.com vb. — 3 kanal limiti', tier: 'mini' },
      { key: 'payments_link', label: 'Sanal POS & Ödeme Linki', hint: 'Kredi kartı çekimi + misafire güvenli ödeme linki', tier: 'mini' },
      { key: 'kbs_notify', label: 'KBS Polis Bildirimi', hint: 'Konaklama bildirim sistemi (Quick-ID destekli)', tier: 'mini' },
    ],
  },
  {
    id: 'basic',
    title: 'Basic — Küçük Şehir Oteli',
    icon: Building2,
    color: 'emerald',
    description: 'Mini\'nin tümü + günlük operasyonu büyüten ek modüller.',
    items: [
      { key: 'mailing', label: 'Mailing & Kampanya', hint: 'E-posta şablonları, kampanyalar, otomasyon', tier: 'basic' },
      { key: 'guest_advanced', label: 'Gelişmiş Misafir Profili', hint: 'VIP, tercihler, LTV', tier: 'basic' },
      { key: 'housekeeping_advanced', label: 'Housekeeping (Gelişmiş)', hint: 'Atama, görev kuyruğu, performans', tier: 'basic' },
      { key: 'cost_management', label: 'Maliyet Yönetimi', hint: 'Maliyet takibi', tier: 'basic' },
      { key: 'reports', label: 'Gelişmiş Raporlar', hint: 'Detaylı analitik raporlar', tier: 'basic' },
      { key: 'channel_manager', label: 'Channel Manager (Tam)', hint: 'Sınırsız kanal, derin OTA entegrasyonu', tier: 'basic' },
    ],
  },
  {
    id: 'professional',
    title: 'Professional — Orta Ölçekli Otel',
    icon: BarChart3,
    color: 'sky',
    description: 'Basic\'in tümü + gelir-yönetimi ve operasyonel derinlik.',
    items: [
      { key: 'folio_management', label: 'Folio Yönetimi (Tam)', hint: 'Split, routing, posting', tier: 'professional' },
      { key: 'night_audit', label: 'Gece Denetimi (Tam)', hint: 'End-of-day otomasyonu, audit izleri', tier: 'professional' },
      { key: 'invoices', label: 'Gelişmiş Fatura & Finans', hint: 'E-fatura, AR/AP', tier: 'professional' },
      { key: 'rate_management', label: 'Rate Management', hint: 'Fiyat planı yönetimi', tier: 'professional' },
      { key: 'booking_engine', label: 'Booking Engine', hint: 'Direkt rezervasyon motoru', tier: 'professional' },
      { key: 'pos_basic', label: 'POS (Temel)', hint: 'Restoran/bar adisyon, folyo aktarımı', tier: 'professional' },
      { key: 'maintenance', label: 'Bakım / Maintenance', hint: 'Arıza takibi, planlı bakım', tier: 'professional' },
    ],
  },
  {
    id: 'enterprise',
    title: 'Enterprise Modüller',
    icon: Crown,
    color: 'indigo',
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
    id: 'pms_submodules',
    title: 'PMS Alt Sekmeleri',
    icon: BedDouble,
    color: 'sky',
    description: 'PMS modülünün hangi alt sekmelerinin görüneceğini seçin. İşaretsiz olanlar operatöre hiç gözükmez.',
    items: [
      { key: 'pms.frontdesk', label: 'Ön Büro', hint: 'Check-in/out, varış, ayrılış, in-house', tier: 'mini' },
      { key: 'pms.rooms', label: 'Odalar', hint: 'Oda envanteri', tier: 'mini' },
      { key: 'pms.guests', label: 'Misafirler', hint: 'Misafir kartları', tier: 'mini' },
      { key: 'pms.bookings', label: 'Rezervasyonlar', hint: 'Rezervasyon listesi', tier: 'mini' },
      { key: 'pms.housekeeping', label: 'Kat Hizmetleri', hint: 'Oda durumu, görevler', tier: 'mini' },
      { key: 'pms.cashier', label: 'Kasa', hint: 'Kasa hareketleri', tier: 'basic' },
      { key: 'pms.upsell', label: 'Upsell', hint: 'Ek hizmet satışı', tier: 'basic' },
      { key: 'pms.internal_chat', label: 'İletişim', hint: 'Personel chat', tier: 'basic' },
      { key: 'pms.reports', label: 'PMS Raporları', hint: 'PMS sekmesi içi raporlar', tier: 'basic' },
      { key: 'pms.flash', label: 'Flash Rapor', hint: 'Anlık özet', tier: 'basic' },
      { key: 'pms.tasks', label: 'Görevler', hint: 'Personel görev kuyruğu', tier: 'basic' },
      { key: 'pms.feedback', label: 'Geri Bildirim', hint: 'Misafir geri bildirim sistemi', tier: 'basic' },
      { key: 'pms.allotment', label: 'Kontenjan', hint: 'Allotment grid', tier: 'professional' },
      { key: 'pms.pos', label: 'POS', hint: 'Restoran/bar POS', tier: 'professional' },
      { key: 'pms.laundry', label: 'Çamaşırhane', hint: 'Çamaşır siparişleri', tier: 'professional' },
      { key: 'pms.concierge', label: 'Concierge', hint: 'Concierge masası', tier: 'professional' },
      { key: 'pms.revenue', label: 'Gelir Kontrol', hint: 'Gelir kontrol panelleri', tier: 'professional' },
      { key: 'pms.manager_report', label: 'Müdür Raporu', hint: 'Günlük müdür raporu', tier: 'professional' },
      { key: 'pms.kbs', label: 'KBS / GİKS', hint: 'Polis bildirimi', tier: 'mini' },
      { key: 'pms.kvkk', label: 'KVKK', hint: 'KVKK yönetimi', tier: 'basic' },
    ],
  },
  {
    id: 'rms_submodules',
    title: 'Gelir Yönetimi (RMS) Alt Sekmeleri',
    icon: TrendingUp,
    color: 'violet',
    description: 'RMS modülü içinde hangi alt sekmelerin görüneceğini seçin. Üst-modül "Revenue Management" kapalıysa hiçbiri görünmez.',
    items: [
      { key: 'rms.dashboard', label: 'Dashboard', hint: 'KPI kartları, grafikler ve kanal kırılımı', tier: 'enterprise' },
      { key: 'rms.recommendations', label: 'Fiyat Önerileri', hint: 'AI fiyat önerileri tablosu + onay aksiyonları', tier: 'enterprise' },
    ],
  },
  {
    id: 'channels_submodules',
    title: 'Kanallar Alt Sekmeleri',
    icon: PlugZap,
    color: 'amber',
    description: 'Kanallar hub\'ında hangi alt sekmelerin görüneceğini seçin. Operasyon sekmesi her zaman sadece super admin\'e açıktır.',
    items: [
      { key: 'channels.connections', label: 'Bağlantılar', hint: 'OTA ve channel manager bağlantı ayarları', tier: 'mini' },
      { key: 'channels.dashboard', label: 'Dashboard', hint: 'Kanal performansı ve sync durumu', tier: 'basic' },
    ],
  },
  {
    id: 'reports_submodules',
    title: 'Raporlar Alt Sekmeleri',
    icon: FileText,
    color: 'sky',
    description: 'Raporlar sayfasında hangi alt bölümlerin görüneceğini seçin.',
    items: [
      { key: 'reports.excel', label: 'Excel Raporları', hint: 'Hazır Excel rapor şablonları', tier: 'mini' },
      { key: 'reports.night_audit', label: 'Night Audit', hint: 'Gün sonu denetim raporları', tier: 'basic' },
    ],
  },
  {
    id: 'reports_items',
    title: 'Rapor Listesi (Excel Raporları)',
    icon: FileText,
    color: 'sky',
    description: 'Excel rapor seçim listesinde hangi raporların gösterileceğini seçin. Üst sekme "Excel Raporları" kapalıysa bu liste hiç görünmez.',
    items: [
      { key: 'reports.daily-flash', label: 'Günlük Flash Raporu', hint: 'Finans — günlük özet', tier: 'mini' },
      { key: 'reports.company-aging', label: 'Şirket Yaşlandırma', hint: 'Finans — alacak yaşlandırma', tier: 'basic' },
      { key: 'reports.revenue-detail', label: 'Gelir Detay Raporu', hint: 'Finans — tarih aralıklı', tier: 'basic' },
      { key: 'reports.forecast-detail', label: 'Tahmin Detay Raporu', hint: 'Finans — tarih aralıklı', tier: 'professional' },
      { key: 'reports.housekeeping-efficiency', label: 'Housekeeping Verimliliği', hint: 'Operasyon — tarih aralıklı', tier: 'basic' },
      { key: 'reports.operations-daily-summary', label: 'Günlük Operasyon Özeti', hint: 'Operasyon — günlük', tier: 'mini' },
      { key: 'reports.market-segment', label: 'Pazar Segmenti Analizi', hint: 'Pazar — tarih aralıklı', tier: 'professional' },
      { key: 'reports.channel-distribution', label: 'Kanal Dağılımı', hint: 'Pazar — tarih aralıklı', tier: 'basic' },
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

export const tierRank = { mini: 0, basic: 1, professional: 2, enterprise: 3 };

export const isModuleIncludedInPlan = (moduleItem, tenantTier) => {
  // Add-on modules are never "included" in any plan — they're always
  // upsell items that super_admin enables per-tenant.
  if (moduleItem.addon || moduleItem.tier === 'addon') return false;
  const moduleTier = moduleItem.tier || 'enterprise';
  // Higher tier always includes lower-tier modules; Mini (rank 0) is the
  // minimum baseline matching Elektraweb Mini's feature set.
  return tierRank[tenantTier] >= tierRank[moduleTier];
};
