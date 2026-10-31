// Pure role/entitlement helpers for the mobile app. This module has NO React,
// React-Native, zustand or storage imports on purpose: it must be importable
// from the plain-Node unit test runner (see `yarn test:unit`) AND from the
// zustand `authStore`. `authStore` re-exports everything here so existing
// import sites keep working unchanged.
//
// All gating below is COSMETIC — it only decides what the mobile UI surfaces.
// The backend still enforces every read/write via its own RBAC, so nothing in
// this file weakens authorization.

export type AppRole = 'front_desk' | 'housekeeping' | 'gm' | 'guest_app' | 'other';

export type ServerAccessContext = {
  role?: string;
  effective_permissions?: string[];
  module_scopes?: string[] | null;
  page_access?: Record<string, boolean>;
};

/**
 * UI visibility is fail-closed when the server supplied an access context.
 * Legacy sessions without it retain the old cosmetic role map until /auth/me
 * refreshes them; authorization remains exclusively on the backend.
 */
export function hasServerAccess(user: ServerAccessContext | undefined, page: string, permission?: string): boolean | undefined {
  if (!user) return undefined;
  if (user.role === 'super_admin') return true;
  if (user.module_scopes != null && !Array.isArray(user.module_scopes)) return false;
  // /auth/me publishes a complete page map. An omitted key is not a grant.
  if (user.page_access) {
    return user.page_access[page] === true
      && (!permission || !user.effective_permissions || user.effective_permissions.includes(permission));
  }
  const workspace = PAGE_POLICY[page];
  if (workspace && Array.isArray(user.module_scopes)
    && !user.module_scopes.includes('*') && !user.module_scopes.includes(workspace.scope)) return false;
  if (user.effective_permissions) {
    const required = [...(workspace?.permissions || []), ...(permission ? [permission] : [])];
    return !!workspace && required.every((key) => user.effective_permissions!.includes(key));
  }
  return undefined;
}

// Exact vocabulary from backend/modules/pms_core/user_access_catalog.json.
// Operation aliases (e.g. view_finance_reports) are NOT permission values.
const PAGE_POLICY: Record<string, { scope: string; permissions: string[] }> = {
  frontdesk: { scope: 'frontdesk', permissions: ['view_bookings'] },
  calendar: { scope: 'frontdesk', permissions: ['view_bookings'] },
  rooms: { scope: 'frontdesk', permissions: ['view_bookings'] },
  bookings: { scope: 'frontdesk', permissions: ['view_bookings'] },
  guests: { scope: 'frontdesk', permissions: ['view_bookings'] },
  housekeeping: { scope: 'housekeeping', permissions: ['view_hk_board'] },
  finance: { scope: 'finance', permissions: ['view_financial_reports'] },
  reports: { scope: 'reports', permissions: ['view_reports'] },
  cashier: { scope: 'cashier', permissions: ['view_folio'] },
  procurement: { scope: 'procurement', permissions: ['view_procurement'] },
  hr: { scope: 'hr', permissions: ['view_hr'] },
  maintenance: { scope: 'maintenance', permissions: [] },
  pos: { scope: 'pos', permissions: [] },
  night_audit: { scope: 'night_audit', permissions: [] },
};

export function mobileOperationAllowed(user: ServerAccessContext | null | undefined, permission: string): boolean {
  if (!user) return false;
  if (user.role === 'super_admin') return true;
  if (user.effective_permissions) return user.effective_permissions.includes(permission);
  // Conservative compatibility for older servers without effective context.
  const role = user.role?.trim().toLowerCase();
  if (role === 'admin' || role === 'supervisor') return true;
  if (permission === 'assign_task') return role === 'housekeeping';
  if (permission === 'update_room_status') return ['housekeeping', 'front_desk'].includes(role || '');
  if (permission === 'post_payment') return ['finance', 'front_desk'].includes(role || '');
  if (['edit_booking', 'create_booking', 'checkin', 'checkout'].includes(permission)) return role === 'front_desk';
  return false;
}

export function normalizeRole(raw: string | undefined): AppRole {
  if (!raw) return 'other';
  const r = raw.trim().toLowerCase();
  if (['front_desk', 'reception', 'frontdesk', 'receptionist'].includes(r)) return 'front_desk';
  if (['housekeeping', 'housekeeper', 'hk'].includes(r)) return 'housekeeping';
  if (['gm', 'general_manager', 'manager', 'owner', 'super_admin', 'admin'].includes(r)) return 'gm';
  if (['guest', 'guest_app'].includes(r)) return 'guest_app';
  return 'other';
}

// All-access roles can browse EVERY role group's screens in the mobile app
// (not just their normalized home group). `normalizeRole` collapses these
// into 'gm', so we detect them from the RAW backend role to preserve the
// distinction. This is a UI-navigation affordance only — backend RBAC
// already grants super_admin/admin full authority; nothing is weakened here.
const ALL_ACCESS_ROLES = ['super_admin', 'admin'];

export function isAllAccessRole(raw: string | undefined): boolean {
  if (!raw) return false;
  return ALL_ACCESS_ROLES.includes(raw.toLowerCase());
}

// Raw backend roles that hold the `view_finance_reports` permission (see
// backend ROLE_PERMISSIONS: admin/super_admin grant everything; supervisor
// and finance hold VIEW_FINANCIAL_REPORTS explicitly). This is a COSMETIC
// mirror used only to decide whether to surface the manager Reports tab —
// the backend's require_op("view_finance_reports") remains the real guard,
// so nothing here weakens RBAC. `normalizeRole` collapses these into 'gm'/
// 'other', so we derive the capability from the RAW role.
const FINANCE_REPORTS_ROLES = ['super_admin', 'admin', 'supervisor', 'finance'];

export function canViewFinanceReports(raw: string | undefined): boolean {
  if (!raw) return false;
  return FINANCE_REPORTS_ROLES.includes(raw.toLowerCase());
}

// ── Department entitlement (cosmetic hub/entry gating) ──────────────────────
// These mirror the backend authorizers in `core/spa_mice_authz.py`
// (`require_spa_ops` / `require_mice_ops`) using the canonical UserRole values
// so the mobile hub only SHOWS what the user could act on. This is gating for
// navigation/affordances only — the backend still enforces every write. We
// derive from the RAW role because `normalizeRole` collapses several roles
// (e.g. super_admin → gm) and would otherwise lose the distinction.
const SPA_OPS_ROLES = ['super_admin', 'admin', 'supervisor', 'front_desk', 'staff'];
const MICE_OPS_ROLES = ['super_admin', 'admin', 'supervisor', 'sales'];
// Mirrors backend MODULE_ROLES["housekeeping"] in role_permission_service.py —
// the roles that pass require_module("housekeeping") for the maintenance
// work-order create + technician-task endpoints. Cosmetic gating only; the
// backend still enforces every write.
const MAINTENANCE_OPS_ROLES = ['super_admin', 'admin', 'supervisor', 'housekeeping'];
// Task #331 (Faz 4) cosmetic gate. Mirrors backend MODULE_ROLES["pos"] in
// role_permission_service.py — the roles that pass require_module("pos") for the
// POS/F&B order open/close, table transfer and folio-post writes. Cosmetic
// gating only; the backend still enforces every write. Derived from the RAW
// role because `normalizeRole` collapses several roles (e.g. super_admin → gm).
const POS_OPS_ROLES = ['super_admin', 'admin', 'supervisor', 'front_desk'];

export function hasSpaAccess(raw: string | undefined): boolean {
  if (!raw) return false;
  return SPA_OPS_ROLES.includes(raw.toLowerCase());
}

export function hasMiceAccess(raw: string | undefined): boolean {
  if (!raw) return false;
  return MICE_OPS_ROLES.includes(raw.toLowerCase());
}

export function hasMaintenanceAccess(raw: string | undefined): boolean {
  if (!raw) return false;
  return MAINTENANCE_OPS_ROLES.includes(raw.toLowerCase());
}

// Task #330 (Faz 3) cosmetic gates. Each mirrors a backend authorizer using
// the canonical UserRole values so the hub only SHOWS what the user could act
// on; the backend still enforces every read/write, so nothing here weakens RBAC.
// Derived from the RAW role because `normalizeRole` collapses several roles.
//
// Procurement: mirrors PROCUREMENT_ROLES in core/spa_mice_authz.py (the roles
// that pass require_procurement for PR/PO state changes).
const PROCUREMENT_ROLES = ['super_admin', 'admin', 'supervisor', 'finance', 'procurement'];
// HR: mirrors the raw roles that hold the VIEW_HR permission in backend
// ROLE_PERMISSIONS (admin/super_admin everything; supervisor + finance hold it
// explicitly). `hr`/`hr_manager` kept defensively (same union as APPROVALS_ROLES).
const HR_VIEW_ROLES = ['super_admin', 'admin', 'supervisor', 'finance', 'hr', 'hr_manager'];
// Revenue: mirrors require_op("view_revenue") which maps to VIEW_FINANCIAL_REPORTS
// (see role_permission_service.py) — same raw-role set as the finance reports gate.
const REVENUE_ROLES = ['super_admin', 'admin', 'supervisor', 'finance'];

export function hasProcurementAccess(raw: string | undefined): boolean {
  if (!raw) return false;
  return PROCUREMENT_ROLES.includes(raw.toLowerCase());
}

export function hasHrAccess(raw: string | undefined): boolean {
  if (!raw) return false;
  return HR_VIEW_ROLES.includes(raw.toLowerCase());
}

export function hasRevenueAccess(raw: string | undefined): boolean {
  if (!raw) return false;
  return REVENUE_ROLES.includes(raw.toLowerCase());
}

export function hasPosAccess(raw: string | undefined): boolean {
  if (!raw) return false;
  return POS_OPS_ROLES.includes(raw.toLowerCase());
}

// Cosmetic mirror of the backend approval-visibility gates used by the mobile
// hub `/approvals` endpoint: finance approvals require `manage_approvals` and
// HR streams require `view_hr`. The union of raw roles that hold either is used
// only to decide whether to SHOW the "Onaylarım" tab — every approve/reject
// endpoint still enforces its own RBAC, so nothing here weakens authorization.
const APPROVALS_ROLES = ['super_admin', 'admin', 'supervisor', 'finance', 'hr', 'hr_manager'];

export function hasApprovalsAccess(raw: string | undefined): boolean {
  if (!raw) return false;
  return APPROVALS_ROLES.includes(raw.toLowerCase());
}

// Accounting (read-focused) mirrors the backend require_op("view_finance_reports")
// guard, so we reuse `canViewFinanceReports` for that department's gate.
export function hasDepartmentAccess(raw: string | undefined): boolean {
  return (
    hasSpaAccess(raw) ||
    hasMiceAccess(raw) ||
    hasMaintenanceAccess(raw) ||
    canViewFinanceReports(raw) ||
    hasProcurementAccess(raw) ||
    hasHrAccess(raw) ||
    hasRevenueAccess(raw) ||
    hasPosAccess(raw)
  );
}

/** One derivation for password login, 2FA and restored sessions. UI only;
 * backend object, operation and subscription guards remain authoritative. */
export function deriveMobileAccess(user: ServerAccessContext | null | undefined) {
  const raw = user?.role;
  const role = normalizeRole(raw);
  const page = (key: string, fallback: boolean, permission?: string) =>
    hasServerAccess(user || undefined, key, permission) ?? fallback;
  const financial = user?.effective_permissions
    ? user.effective_permissions.includes('view_financial_reports') || raw === 'super_admin'
    : canViewFinanceReports(raw);
  const frontdeskAccess = page('frontdesk', role === 'front_desk' || isAllAccessRole(raw));
  const housekeepingAccess = page('housekeeping', role === 'housekeeping' || isAllAccessRole(raw));
  const financeReports = page('reports', financial, 'view_financial_reports');
  const accountingAccess = page('finance', financial, 'view_financial_reports');
  const nightAuditAccess = financial && page('night_audit', financial);
  // Current mobile cashier reads finance-grade endpoints as well as folios.
  const cashierAccess = financial && page('cashier', canViewFinanceReports(raw)) && financeReports;
  // Work-order reads also retain the backend's housekeeping-role guard.
  const maintenanceAccess = page('maintenance', hasMaintenanceAccess(raw)) && hasMaintenanceAccess(raw);
  const procurementAccess = page('procurement', hasProcurementAccess(raw));
  const hrAccess = page('hr', hasHrAccess(raw));
  const posAccess = page('pos', hasPosAccess(raw)) && hasPosAccess(raw);
  const spaAccess = hasSpaAccess(raw); // No backend page/scope named "spa".
  const miceAccess = hasMiceAccess(raw); // No backend page/scope named "mice".
  const revenueAccess = financial && financeReports;
  const managerAccess = (role === 'gm' || raw === 'supervisor') && financial && (accountingAccess || financeReports);
  const approvalsAccess = hrAccess || (user?.effective_permissions
    ? user.effective_permissions.includes('system_settings') : hasApprovalsAccess(raw));
  // Only unrestricted admins get an unconditional role switcher. Scoped
  // tenant admins must observe the same page denies as every other user.
  const allAccess = raw === 'super_admin' || (isAllAccessRole(raw)
    && frontdeskAccess && housekeepingAccess && managerAccess && accountingAccess
    && cashierAccess && maintenanceAccess && procurementAccess && hrAccess && posAccess);
  return { role, allAccess, frontdeskAccess, housekeepingAccess, managerAccess,
    financeReports, accountingAccess, nightAuditAccess, cashierAccess, spaAccess, miceAccess,
    maintenanceAccess, procurementAccess, hrAccess, revenueAccess, posAccess,
    approvalsAccess,
    deptAccess: role !== 'guest_app' && [spaAccess, miceAccess, cashierAccess, accountingAccess,
      maintenanceAccess, procurementAccess, hrAccess, revenueAccess, posAccess].some(Boolean) };
}
