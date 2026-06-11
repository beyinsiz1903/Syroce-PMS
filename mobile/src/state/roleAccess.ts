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

export function normalizeRole(raw: string | undefined): AppRole {
  if (!raw) return 'other';
  const r = raw.toLowerCase();
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
