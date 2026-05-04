import { api } from './client';

export type Guest = {
  id: string;
  first_name?: string;
  last_name?: string;
  full_name?: string;
  email?: string;
  phone?: string;
  id_number?: string;
  passport_number?: string;
  nationality?: string;
  birth_date?: string;
  vip_status?: boolean;
  blacklisted?: boolean;
  preferences?: Record<string, unknown>;
  notes?: string;
};

type GuestListResponse = Guest[] | { guests?: Guest[]; items?: Guest[]; results?: Guest[] };

function unwrap(res: GuestListResponse): Guest[] {
  if (Array.isArray(res)) return res;
  if (Array.isArray(res?.guests)) return res.guests;
  if (Array.isArray(res?.items)) return res.items;
  if (Array.isArray(res?.results)) return res.results;
  return [];
}

// GET /api/pms/guests/search?q=<text>  (pms_guests.py:150)
export async function searchGuests(q: string): Promise<Guest[]> {
  try {
    const res = await api.get<GuestListResponse>('/api/pms/guests/search', { q, limit: 50 });
    const list = unwrap(res);
    if (list.length) return list;
  } catch {
    // fall through
  }
  // Fallback: full list with backend search param
  try {
    const res = await api.get<GuestListResponse>('/api/pms/guests', { search: q, limit: 50 });
    return unwrap(res);
  } catch {
    return [];
  }
}

// POST /api/pms/guests
export async function createGuest(data: Partial<Guest>): Promise<Guest> {
  return api.post<Guest>('/api/pms/guests', data);
}

// GET /api/pms/guests/{id}/highlights — vip + blacklist signals
export async function checkBlacklist(guestId: string): Promise<{ blacklisted: boolean }> {
  try {
    const res = await api.get<{ blacklisted?: boolean; highlights?: { blacklisted?: boolean } }>(
      `/api/pms/guests/${guestId}/highlights`,
    );
    const flagged = !!(res?.blacklisted ?? res?.highlights?.blacklisted);
    return { blacklisted: flagged };
  } catch {
    return { blacklisted: false };
  }
}
