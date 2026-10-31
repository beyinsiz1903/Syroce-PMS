/** Reviewed display-only aliases. Raw API, requests, money and audit stay intact. */
import registry from '@/config/frontdeskPresentation.json';

export const PRESENTATION_TENANT = registry.tenant_id;
const guestById = new Map(registry.guests.map(guest => [guest.id, guest]));
const guestByName = new Map(registry.guests
  .filter(guest => registry.guests.filter(other => other.original === guest.original).length === 1)
  .map(guest => [guest.original, guest.display]));
const nameFields = new Set(['name', 'full_name', 'guest_name', 'client_name', 'guestName']);
const textFields = new Set([
  ...nameFields, 'title', 'description', 'details', 'notes', 'note', 'reason',
  'help_text', 'section', 'event_name', 'survey_name', 'comment', 'response',
  'staff_member', 'assigned_to_name', 'resolution_note', 'message', 'body',
  'location', 'property_name', 'display_name', 'label', 'text', 'answer', 'tr', 'en',
  'target_item', 'resource_name', 'service_name', 'agency_name', 'company_name',
  'marketplace_agency_name', 'hotel_name', 'special_requests', 'hk_notes',
  'guest_note', 'notice', 'tour_operator',
]);
const rawBranches = new Set([
  'history', 'audit', 'audit_log', 'audit_logs', 'audit_trail', 'logs',
  'before', 'after', 'diff', 'changes', 'source_snapshot', 'raw', 'source',
  'presentation_archive', 'features_audit', 'chain', 'values', 'custom_fields',
  'options', 'permissions', 'roles', 'identity',
]);
const blockedPath = /(?:^|\/)(?:auth|admin|audit|history|kbs|kvkk|gdpr|compliance|official-guest-list|invoices?|fiscal|exports?|raw|openapi)(?:\/|$)/i;
const allowedPath = /^\/(?:pms|profile-udf|frontdesk|folios?|folio-windows|crm|feedback|tasks|bookings|revenue|groups|housekeeping|concierge|laundry|spa|mice|transfer-parking|activities|function-space|minibar|room-requests|room-qr|reports|accounting\/inventory|enterprise-billing\/catalog|ai\/upsell)(?:\/|$)/;
const financialRead = /^\/night-audit\/(?:financial-summary|financial-report|payment-reconciliation)$/;
// Forms often spread their GET DTO into an update. Keep the exact observed
// source values in memory so an unchanged display alias cannot become a rename.
const observedSources = new Map();
function presentationPath(config) {
  let path = config.url || '';
  if (typeof path !== 'string') return null;
  if (/^https?:\/\//i.test(path)) {
    if (!path.startsWith('https://pms.syroce.com/api/')) return null;
    path = path.slice('https://pms.syroce.com'.length);
  }
  path = path.split(/[?#]/)[0].replace(/^\/api(?=\/)/, '');
  return blockedPath.test(path) || !(allowedPath.test(path) || financialRead.test(path)) ? null : path;
}
const routeFamily = path => path.split('/').slice(1, 3).join('/');

function rememberSources(raw, displayed, family, depth = 0) {
  if (!raw || typeof raw !== 'object' || !displayed || typeof displayed !== 'object' || depth > 40) return;
  if (raw.tenant_id && raw.tenant_id !== PRESENTATION_TENANT) return;
  if (raw.id && !Array.isArray(raw)) {
    const fields = {};
    for (const [field, value] of Object.entries(raw)) {
      if (typeof value === 'string' && value !== displayed[field] && (textFields.has(field) || ['first_name', 'last_name'].includes(field))) {
        fields[field] = { original: value, display: displayed[field] };
      }
    }
    // Always replace stale observations, including an independently renamed row.
    if (Object.keys(fields).length) observedSources.set(`${family}:${raw.id}`, fields);
    else observedSources.delete(`${family}:${raw.id}`);
    if (observedSources.size > 4000) observedSources.delete(observedSources.keys().next().value);
  }
  for (const [key, value] of Object.entries(raw)) {
    if (!rawBranches.has(key) && value && typeof value === 'object') rememberSources(value, displayed[key], family, depth + 1);
  }
}

export function preserveFrontdeskSourceUpdate(config, currentTenant = storedPresentationTenant()) {
  if (currentTenant !== PRESENTATION_TENANT) {
    observedSources.clear();
    return config;
  }
  if (!['put', 'patch'].includes(config.method?.toLowerCase())) return config;
  const path = presentationPath(config);
  if (!path || !config.data || typeof config.data !== 'object' || Array.isArray(config.data)) return config;
  const family = routeFamily(path);
  const pathId = path.split('/').findLast(segment => observedSources.has(`${family}:${segment}`));
  const visit = (value, inheritedId, depth = 0) => {
    if (!value || typeof value !== 'object' || depth > 40) return value;
    if (value.tenant_id && value.tenant_id !== PRESENTATION_TENANT) return value;
    if (Array.isArray(value)) return value.map(child => visit(child, null, depth + 1));
    if (Object.getPrototypeOf(value) !== Object.prototype) return value;
    const fields = observedSources.get(`${family}:${value.id || inheritedId}`) || {};
    let result = value;
    for (const [key, child] of Object.entries(value)) {
      if (rawBranches.has(key)) continue;
      const mapped = fields[key]?.display === child ? fields[key].original : visit(child, null, depth + 1);
      if (mapped !== child) {
        if (result === value) result = { ...value };
        result[key] = mapped;
      }
    }
    if (Object.hasOwn(result, 'presentation_key')) {
      result = { ...result }; delete result.presentation_key;
    }
    return result;
  };
  const data = visit(config.data, pathId);
  return data === config.data ? config : { ...config, data };
}

export function presentationContextTenant(user, tenant) {
  return user?.tenant_id === PRESENTATION_TENANT && tenant?.id === PRESENTATION_TENANT
    ? PRESENTATION_TENANT : null;
}

export function storedPresentationTenant() {
  try {
    return presentationContextTenant(
      JSON.parse(localStorage.getItem('user') || 'null'),
      JSON.parse(localStorage.getItem('tenant') || 'null'),
    );
  } catch { return null; }
}

export function presentationHotelName(tenant, user) {
  const original = tenant?.property_name;
  return presentationContextTenant(user, tenant) && original === registry.hotel.original
    ? registry.hotel.display : original;
}

export function presentationOperatorName(user, tenant) {
  return presentationContextTenant(user, tenant) && user?.name === registry.operator.original
    ? registry.operator.display : user?.name;
}

function displayText(value, field, row) {
  const guest = guestById.get(row.guest_id) || guestById.get(row.id);
  if (guest && nameFields.has(field)) return value === guest.original ? guest.display : value;
  const visibleName = row.name || row.full_name;
  const readableIdentity = guest && (visibleName ? visibleName === guest.original
    : `${row.first_name || ''} ${row.last_name || ''}`.trim() === guest.original);
  if (readableIdentity && (field === 'first_name' || field === 'last_name')) {
    const [first, ...last] = guest.original.split(/\s+/);
    const [displayFirst, ...displayLast] = guest.display.split(/\s+/);
    if (value === (field === 'first_name' ? first : last.join(' '))) {
      return field === 'first_name' ? displayFirst : displayLast.join(' ');
    }
  }
  if (!textFields.has(field)) return value;
  if (nameFields.has(field)) {
    if (guestByName.has(value)) return guestByName.get(value);
    if (Object.hasOwn(registry.names, value)) return registry.names[value];
  }
  return Object.hasOwn(registry.labels, value) ? registry.labels[value] : value;
}

export function projectFrontdeskPresentation(data, tenantId) {
  if (tenantId !== PRESENTATION_TENANT) return data;
  const seen = new WeakMap();
  const visit = (value, depth = 0) => {
    if (!value || typeof value !== 'object' || depth > 40) return value;
    if (seen.has(value)) return seen.get(value);
    if (value.tenant_id && value.tenant_id !== PRESENTATION_TENANT) return value;
    if (!Array.isArray(value) && Object.getPrototypeOf(value) !== Object.prototype) return value;
    seen.set(value, value);
    if (Array.isArray(value)) {
      const mapped = value.map(child => visit(child, depth + 1));
      const result = mapped.some((child, index) => child !== value[index]) ? mapped : value;
      seen.set(value, result);
      return result;
    }
    let result = value;
    for (const [key, child] of Object.entries(value)) {
      if (rawBranches.has(key)) continue;
      const mapped = typeof child === 'string' ? displayText(child, key, value) : visit(child, depth + 1);
      if (mapped !== child) {
        if (result === value) result = { ...value };
        result[key] = mapped;
      }
    }
    if (Object.hasOwn(registry.field_keys, value.key || '')) {
      if (result === value) result = { ...value };
      result.presentation_key = registry.field_keys[value.key];
    }
    seen.set(value, result);
    return result;
  };
  return visit(data);
}

export function presentFrontdeskResponse(response, currentTenant = storedPresentationTenant()) {
  const config = response?.config || {};
  if (config.method?.toLowerCase() !== 'get' || config._frontdeskPresentationTenant !== PRESENTATION_TENANT || currentTenant !== PRESENTATION_TENANT) return response;
  if (config.responseType && config.responseType !== 'json') return response;
  const path = presentationPath(config);
  if (!path) return response;
  const data = projectFrontdeskPresentation(response.data, currentTenant);
  rememberSources(response.data, data, routeFamily(path));
  // Cache adapters may retain response/data references; do not mutate either.
  return data === response.data ? response : { ...response, data };
}
