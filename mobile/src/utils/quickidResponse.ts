export type QuickIdDocument = {
  first_name?: string | null;
  last_name?: string | null;
  full_name?: string | null;
  id_number?: string | null;
  document_number?: string | null;
  passport_number?: string | null;
  nationality?: string | null;
  birth_date?: string | null;
  document_type?: string | null;
  is_valid?: boolean;
};

export type QuickIdApiResponse = QuickIdDocument & {
  success?: boolean;
  documents?: QuickIdDocument[];
  extracted_data?: { documents?: QuickIdDocument[] };
};

export type NormalizedQuickId = {
  first_name?: string;
  last_name?: string;
  full_name?: string;
  id_number?: string;
  passport_number?: string;
  nationality?: string;
  birth_date?: string;
  document_type?: string;
};

function text(value: string | null | undefined): string | undefined {
  const normalized = String(value || '').trim();
  return normalized || undefined;
}

/** Normalize both the current embedded Quick-ID contract and legacy responses. */
export function normalizeQuickIdResponse(data: QuickIdApiResponse): NormalizedQuickId {
  const document = data.documents?.[0] || data.extracted_data?.documents?.[0] || data;
  const first = text(document.first_name);
  const last = text(document.last_name);
  const type = text(document.document_type);
  const documentNumber = text(document.document_number);
  const passport = text(document.passport_number) || (type === 'passport' ? documentNumber : undefined);
  const idNumber = text(document.id_number) || (type !== 'passport' ? documentNumber : undefined);
  const fullName = text(document.full_name) || [first, last].filter(Boolean).join(' ') || undefined;

  if (!fullName && !idNumber && !passport) {
    throw new Error('Kimlik üzerinde okunabilir bilgi bulunamadı. Fotoğrafı net ve ışık yansıması olmadan yeniden çekin.');
  }

  return {
    first_name: first,
    last_name: last,
    full_name: fullName,
    id_number: idNumber,
    passport_number: passport,
    nationality: text(document.nationality),
    birth_date: text(document.birth_date),
    document_type: type,
  };
}
