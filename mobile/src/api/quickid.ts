import { getQuickIdUrl } from './client';

export type QuickIdResult = {
  first_name?: string;
  last_name?: string;
  full_name?: string;
  id_number?: string;
  passport_number?: string;
  nationality?: string;
  birth_date?: string;
  document_type?: string;
};

type QuickIdRaw = {
  first_name?: string;
  given_name?: string;
  name?: string;
  last_name?: string;
  surname?: string;
  family_name?: string;
  full_name?: string;
  id_number?: string;
  tc_no?: string;
  passport_number?: string;
  nationality?: string;
  country?: string;
  birth_date?: string;
  dob?: string;
  document_type?: string;
  type?: string;
  fields?: Partial<{
    first_name: string;
    last_name: string;
    id_number: string;
    passport_number: string;
  }>;
};

type RNFile = { uri: string; name: string; type: string };

export async function scanIdPhoto(uri: string): Promise<QuickIdResult> {
  const url = `${getQuickIdUrl()}/scan`;
  const form = new FormData();
  const file: RNFile = { uri, name: 'id-photo.jpg', type: 'image/jpeg' };
  // React Native FormData accepts file descriptors; cast through unknown to avoid lib DOM mismatch.
  form.append('file', file as unknown as Blob);

  const res = await fetch(url, { method: 'POST', body: form });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Quick-ID hata: ${res.status} ${text.slice(0, 120)}`);
  }
  const data = (await res.json()) as QuickIdRaw;
  const first = data.first_name || data.given_name || data.name || data.fields?.first_name || '';
  const last = data.last_name || data.surname || data.family_name || data.fields?.last_name || '';
  return {
    first_name: first,
    last_name: last,
    full_name: data.full_name || `${first} ${last}`.trim(),
    id_number: data.id_number || data.tc_no || data.fields?.id_number,
    passport_number: data.passport_number || data.fields?.passport_number,
    nationality: data.nationality || data.country,
    birth_date: data.birth_date || data.dob,
    document_type: data.document_type || data.type,
  };
}
