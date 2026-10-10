// A deliberately short-lived handoff between the reservation dialog and the
// operational waitlist screen.  Keeping it in sessionStorage prevents a
// failed availability search from making the operator type the same data twice.
const KEY = 'syroce.reservation-waitlist-draft';

export function saveReservationWaitlistDraft(draft) {
  try { sessionStorage.setItem(KEY, JSON.stringify(draft)); } catch { /* non-critical */ }
}

export function consumeReservationWaitlistDraft() {
  try {
    const raw = sessionStorage.getItem(KEY);
    sessionStorage.removeItem(KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}
