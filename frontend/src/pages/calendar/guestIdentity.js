const cleanText = value => String(value || '').trim().toLocaleLowerCase('tr-TR').replace(/\s+/g, ' ');
const cleanPhone = value => String(value || '').replace(/\D/g, '');
const cleanDocument = value => String(value || '').toLocaleLowerCase('tr-TR').replace(/[^0-9a-z]/g, '');

export const guestIdentityTokens = (guest, { includeNameFallback = false } = {}) => {
  const tokens = [];
  const name = cleanText(guest?.name);
  const document = cleanDocument(guest?.id_number || guest?.passport_number);
  const email = cleanText(guest?.email);
  const phone = cleanPhone(guest?.phone);
  if (document) tokens.push(`document:${document}`);
  if (email && !email.endsWith('@placeholder.local')) tokens.push(name ? `email:${email}|name:${name}` : `email:${email}`);
  if (phone.length >= 7) tokens.push(name ? `phone:${phone}|name:${name}` : `phone:${phone}`);
  if (tokens.length === 0 && includeNameFallback) {
    if (name) tokens.push(`name-only:${name}`);
  }
  return tokens;
};

const guestRank = guest => [
  Number(guest?.total_stays || 0),
  guestIdentityTokens(guest).length,
];

const isHigherRank = (candidate, current) => {
  const a = guestRank(candidate);
  const b = guestRank(current);
  return a[0] > b[0] || (a[0] === b[0] && a[1] > b[1]);
};

export const deduplicateGuestSearchResults = guests => {
  const groups = [];
  for (const guest of Array.isArray(guests) ? guests : []) {
    const tokens = new Set(guestIdentityTokens(guest, { includeNameFallback: true }));
    const matchingIndexes = groups
      .map((group, index) => ([...tokens].some(token => group.tokens.has(token)) ? index : -1))
      .filter(index => index >= 0);
    if (matchingIndexes.length === 0) {
      groups.push({ tokens, guest });
      continue;
    }
    const firstIndex = matchingIndexes[0];
    const candidates = [guest];
    const mergedTokens = new Set(tokens);
    [...matchingIndexes].reverse().forEach(index => {
      const [group] = groups.splice(index, 1);
      group.tokens.forEach(token => mergedTokens.add(token));
      candidates.push(group.guest);
    });
    const canonical = candidates.reduce((best, candidate) => (
      isHigherRank(candidate, best) ? candidate : best
    ));
    groups.splice(firstIndex, 0, { tokens: mergedTokens, guest: canonical });
  }
  return groups.map(group => group.guest);
};

export const maskGuestDocument = value => {
  const cleaned = String(value || '').replace(/\s+/g, '');
  if (!cleaned) return '';
  if (cleaned.length <= 4) return cleaned;
  return `${'*'.repeat(Math.min(6, cleaned.length - 4))}${cleaned.slice(-4)}`;
};
