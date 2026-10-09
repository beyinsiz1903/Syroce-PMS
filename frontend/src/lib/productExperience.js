import { NAV_ITEMS, NAV_GROUPS } from '@/config/navItems';
import { effectiveModuleScopes } from '@/utils/moduleAccess';

// Presentation only. Callers must pass the already-authorized navigation list.
export function roleStartItems(user, items) {
  const granted = effectiveModuleScopes(user);
  const scopes = granted.includes('*') ? [] : granted;
  const roles = [user?.role, ...(user?.roles || []), ...(scopes.length <= 2 ? scopes : [])];
  const groups = roles.includes('housekeeping') ? ['operations']
    : roles.some(r => ['finance', 'accounting', 'cashier'].includes(r)) ? ['backoffice', 'reports']
      : roles.some(r => ['waiter', 'fnb', 'restaurant', 'pos'].includes(r)) ? ['fb']
        : roles.includes('sales') ? ['sales', 'guest'] : ['frontdesk', 'operations', 'guest'];
  const preferred = roles.includes('housekeeping') ? ['housekeeping_status', 'tasks_workspace']
    : roles.some(r => ['finance', 'accounting', 'cashier'].includes(r)) ? ['cashier_workspace', 'invoices']
      : roles.some(r => ['waiter', 'fnb', 'restaurant', 'pos'].includes(r)) ? ['pos_dashboard'] : ['pms', 'reservation_calendar', 'shift_handover', 'tasks_workspace'];
  return [...items].filter(item => item.path && (preferred.includes(item.key) || groups.includes(item.navGroup)))
    .sort((a, b) => (preferred.indexOf(a.key) < 0 ? 99 : preferred.indexOf(a.key)) - (preferred.indexOf(b.key) < 0 ? 99 : preferred.indexOf(b.key)))
    .filter((item, index, all) => all.findIndex(other => other.path === item.path) === index).slice(0, 6);
}

const GROUP_KEYS = {
  frontdesk: ['pms', 'reservation_calendar', 'guests', 'guest_advanced', 'night_audit', 'night_audit_basic', 'quick_id', 'kbs_notify', 'pms_mobile'],
  operations: ['housekeeping', 'housekeeping_advanced', 'mobile_housekeeping', 'maintenance', 'parking', 'room_qr_requests', 'spa', 'operator_incident'],
  fb: ['pos_fnb', 'pos_basic', 'mice'],
  backoffice: ['invoices', 'invoices_basic', 'folio_basic', 'folio_management', 'cost_management', 'payments_link', 'hr'],
  guest: ['sales_crm', 'loyalty_program', 'af_sadakat', 'contact_center', 'mailing', 'ai_chatbot', 'ai_whatsapp'],
  sales: ['revenue_management', 'rate_management', 'group_sales', 'ai_pricing', 'ai_revenue_autopilot', 'mobile_revenue'],
  reports: ['reports', 'basic_reporting', 'gm_dashboards', 'audit_trail', 'ai_predictive'],
  system: ['channel_manager', 'channel_manager_lite', 'booking_engine', 'api_access'],
};
export function applicationPresentation(item, groupLabels = {}) {
  const nav = NAV_ITEMS.find(n => n.key === item.key) || NAV_ITEMS.find(n => n.path === item.path);
  const group = Object.keys(GROUP_KEYS).find(key => GROUP_KEYS[key].includes(item.key)) || item.navGroup || nav?.navGroup || 'admin';
  const groupTitle = groupLabels[group] || NAV_GROUPS.find(g => g.id === group)?.label || 'Yönetim';
  const descriptions = {
    pms: 'Müsait odaları bulun, konaklama tarihlerini seçin ve rezervasyon oluşturun.',
    reservation_calendar: 'Oda doluluğunu tarih aralığında inceleyin ve rezervasyonları yönetin.',
    guests: 'Misafir iletişim bilgilerini, tercihlerini ve konaklama geçmişini inceleyin.',
    guest_advanced: 'Misafir profillerini ve ilişkili konaklama bilgilerini yönetin.',
    housekeeping: 'Temizlik görevlerini ve oda hazırlığını takip edin.',
    housekeeping_status: 'Odaların temizlik, kontrol ve bakım durumlarını güncelleyin.',
    pos_fnb: 'Masa, adisyon, menü ve restoran satışlarını yönetin.',
    pos_basic: 'Siparişleri ve satış noktası işlemlerini yönetin.',
    folio_basic: 'Konaklama ücretlerini, tahsilatları ve hesap bakiyelerini inceleyin.',
    invoices: 'Faturaları, tahsilatları ve belge durumlarını takip edin.',
    invoices_basic: 'Konaklamalara bağlı belgeleri ve tahsilatları inceleyin.',
    tasks_workspace: 'Açık işleri, sorumluları ve tamamlanan görevleri takip edin.',
    shift_handover: 'Açık işleri sonraki vardiyaya aktarın ve sonuçlarını takip edin.',
    channel_manager: 'Kanal bağlantıları, eşleştirmeler ve veri aktarımını yönetin.',
    sales_crm: 'Misafir ilişkilerini, kampanyaları ve satış fırsatlarını takip edin.',
    ai: 'Önerileri ve otomasyon kurallarını inceleyin.',
    ai_revenue_autopilot: 'Fiyat önerilerini, onayları ve uygulama geçmişini inceleyin.',
  };
  return { ...item, navGroup: group, groupTitle,
    // Entitlement hints belong in administrator setup, not the employee catalogue.
    hint: descriptions[item.key] || `${item.label} işlemlerini görüntüleyin ve yönetin.`,
  };
}

export const experienceScope = (user, tenant) => `${user?.id || user?.email || 'anonymous'}:${tenant?.id || tenant?._id || user?.tenant_id || 'none'}`;

export function readExperiencePreference(scope, name, fallback) {
  try { return JSON.parse(sessionStorage.getItem(`syroce.experience:${scope}:${name}`)) ?? fallback; }
  catch { return fallback; }
}
export function writeExperiencePreference(scope, name, value) {
  try { sessionStorage.setItem(`syroce.experience:${scope}:${name}`, JSON.stringify(value)); } catch { /* Private browsing must not break navigation. */ }
}

export const GUEST_CONTEXT_EVENT = 'syroce:guest-context';
export function openGuestContext(guestId) {
  if (guestId) window.dispatchEvent(new CustomEvent(GUEST_CONTEXT_EVENT, { detail: { guestId: String(guestId) } }));
}

export function normalizeWorkItems(sources) {
  const result = [];
  for (const task of sources.tasks?.tasks || []) {
    if (['completed', 'cancelled'].includes(task.status)) continue;
    result.push({ key: `task:${task.id}`, source: 'tasks', title: task.title || 'Görev',
      priority: task.priority, owner: task.assigned_to, date: task.created_at, due: task.due_at || task.due_date,
      detail: task.description, path: '/app/tasks', status: task.status });
  }
  for (const note of sources.handover?.items || []) {
    if (note.status === 'resolved') continue;
    result.push({ key: `handover:${note.id}`, source: 'handover', title: note.note,
      priority: note.priority, owner: note.acknowledged_by_name, date: note.created_at,
      path: '/shift-handover', status: note.status || (note.acknowledged ? 'acknowledged' : 'open') });
  }
  for (const alert of sources.alerts?.alerts || []) {
    const paths = { housekeeping: '/housekeeping-status', payments: '/app/pms', frontdesk: '/app/pms' };
    if (!paths[alert.action]) continue;
    result.push({ key: `alert:${alert.type}`, source: 'alerts', title: alert.title,
      priority: alert.severity === 'high' ? 'high' : 'normal', detail: alert.description,
      path: paths[alert.action], status: 'open' });
  }
  const priority = { urgent: 0, high: 1, normal: 2, low: 3 };
  return result.sort((a, b) => (priority[a.priority] ?? 2) - (priority[b.priority] ?? 2) || String(a.date || '').localeCompare(String(b.date || '')));
}
