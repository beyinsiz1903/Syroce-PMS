// Browser storage is shared by every tab on the same origin.  Authentication
// UI state must not be: a second login (or a super-admin workspace switch) in
// one tab must never repaint another tab as a different hotel/user.
const TAB_AUTH_SUBJECT_KEY = "syroce:tab-auth-subject:v1";
const TAB_AUTH_BLOCKED_KEY = "syroce:tab-auth-blocked:v1";

function subjectFor(user) {
  const userId = user?.id || user?._id || user?.user_id;
  const tenantId = user?.tenant_id || user?.tenantId;
  if (!userId || !tenantId) return null;
  return `${String(userId)}:${String(tenantId)}`;
}

export function readTabAuthSubject() {
  try {
    return sessionStorage.getItem(TAB_AUTH_SUBJECT_KEY);
  } catch {
    return null;
  }
}

export function rememberTabAuthSubject(user) {
  const subject = subjectFor(user);
  if (!subject) return null;
  try {
    sessionStorage.setItem(TAB_AUTH_SUBJECT_KEY, subject);
    sessionStorage.removeItem(TAB_AUTH_BLOCKED_KEY);
  } catch { /* private/hardened browser storage is optional */ }
  return subject;
}

export function isForeignIdentityForTab(user) {
  const remembered = readTabAuthSubject();
  const incoming = subjectFor(user);
  return Boolean(remembered && incoming && remembered !== incoming);
}

export function isTabAuthBlocked() {
  try {
    return sessionStorage.getItem(TAB_AUTH_BLOCKED_KEY) === "1";
  } catch {
    return false;
  }
}

// Deliberately only touches sessionStorage.  Clearing localStorage here would
// erase the fresh session created in the other tab, recreating the race this
// guard is designed to prevent.
export function blockTabAfterExternalSessionChange() {
  try {
    sessionStorage.removeItem(TAB_AUTH_SUBJECT_KEY);
    sessionStorage.setItem(TAB_AUTH_BLOCKED_KEY, "1");
  } catch { /* private/hardened browser storage is optional */ }
}

export function clearTabAuthScope() {
  try {
    sessionStorage.removeItem(TAB_AUTH_SUBJECT_KEY);
    sessionStorage.removeItem(TAB_AUTH_BLOCKED_KEY);
  } catch { /* private/hardened browser storage is optional */ }
}

export function readSharedAuthUser(storage = localStorage) {
  try {
    const raw = storage.getItem("user");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
