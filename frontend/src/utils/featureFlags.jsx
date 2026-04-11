// Feature flag normalizer for tenant.features coming from backend
// Maps legacy core_* keys and new lite keys into a unified frontend shape

export function normalizeFeatures(raw = {}) {
  const f = raw || {};

  return {
    // Core / PMS Lite set
    dashboard: !!(f.dashboard ?? f.core_dashboard),
    reservation_calendar: !!(f.reservation_calendar ?? f.core_calendar),
    pms: !!(f.pms ?? f.core_pms),
    rooms: !!(f.rooms ?? f.core_rooms),
    bookings: !!(f.bookings ?? f.core_bookings_frontdesk),
    guests: !!(f.guests ?? f.core_guests_basic),
    reports_lite: !!(f.reports_lite ?? f.core_reports_basic),
    settings_lite: !!(f.settings_lite ?? f.core_users_roles),

    // Full / advanced modules (best-effort mapping; can be refined later)
    rms: !!(f.rms ?? f.core_rates_availability),
    ai: !!(f.ai ?? f.hidden_ai),
    marketplace: !!(f.marketplace ?? f.hidden_marketplace),
  };
}
