export const emptyKbsIdentity = () => ({ nationality: 'TR', id_type: 'tc_kimlik', id_number: '', passport_number: '', birth_date: '', gender: '' });
export const kbsFieldLabels = { id_number: 'Kimlik numarası', id_number_invalid: '11 haneli kimlik numarası', passport_number: 'Pasaport numarası', nationality: 'Uyruk', guest_name: 'Ad ve soyad', birth_date: 'Doğum tarihi', birth_date_invalid: 'Geçerli doğum tarihi', gender: 'Cinsiyet' };
export function kbsIdentityMissing(value, name) {
  const missing = [];
  const domestic = ['TR', 'TC', 'TUR', 'TURKIYE'].includes(String(value.nationality || '').trim().toUpperCase());
  if (!value.nationality?.trim()) missing.push('nationality');
  if (domestic || value.id_type === 'foreign_identity_card') {
    if (!/^\d{11}$/.test(value.id_number?.trim() || '')) missing.push('id_number_invalid');
  } else {
    if (!value.passport_number?.trim()) missing.push('passport_number');
    if (String(name || '').trim().split(/\s+/).length < 2) missing.push('guest_name');
    const date = new Date(value.birth_date);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value.birth_date || '') || !Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== value.birth_date || date > new Date()) missing.push('birth_date_invalid');
    if (!['M', 'F'].includes(value.gender)) missing.push('gender');
  }
  return missing;
}
