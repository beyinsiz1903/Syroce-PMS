export const maskSecurityActor = value => {
  if (!value || String(value).startsWith('SYR1:')) return 'Korunan kullanıcı';
  const [local, domain] = String(value).split('@');
  return local && domain ? `${local.slice(0, 1)}***@${domain}` : 'Korunan kullanıcı';
};

export const safeSecurityEventDetail = event => {
  const details = String(event?.details || '');
  if (/jti\s*=|refresh[_ -]?token|access[_ -]?token|SYR1:/i.test(details)) {
    return 'Güvenlik ayrıntısı korundu';
  }
  return details || '-';
};
