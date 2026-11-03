export type KbsIdentity = {
  name: string; nationality: string; id_type: string; id_number: string;
  passport_number: string; date_of_birth: string; gender: string;
};
export const emptyKbsIdentity = (): KbsIdentity => ({ name: '', nationality: 'TR', id_type: 'tc_kimlik', id_number: '', passport_number: '', date_of_birth: '', gender: '' });
export const KBS_FIELD_LABELS: Record<string, string> = {
  id_number: 'T.C. / yabancı kimlik numarası', id_number_invalid: '11 haneli kimlik numarası',
  passport_number: 'Pasaport numarası', nationality: 'Uyruk', nationality_unsupported: 'Desteklenen ülke kodu',
  birth_date: 'Doğum tarihi', birth_date_invalid: 'Geçerli doğum tarihi', gender: 'Cinsiyet',
  guest_name: 'Ad ve soyad', guest_record: 'Misafir kaydı', room_number: 'Oda', check_in: 'Giriş tarihi', check_out: 'Çıkış tarihi',
};
export const kbsMissingText = (fields: string[]) => fields.map(f => KBS_FIELD_LABELS[f] || 'Misafir bilgisi').join(', ');
export function kbsIdentityMissing(v: KbsIdentity): string[] {
  const missing: string[] = [];
  const domestic = ['TR', 'TC', 'TUR', 'TURKIYE'].includes(v.nationality.trim().toUpperCase());
  if (!v.nationality.trim()) missing.push('nationality');
  if (domestic || v.id_type === 'foreign_identity_card') {
    if (!/^\d{11}$/.test(v.id_number.trim())) missing.push('id_number_invalid');
  } else {
    if (!v.passport_number.trim()) missing.push('passport_number');
    if (v.name.trim().split(/\s+/).length < 2) missing.push('guest_name');
    const d = new Date(v.date_of_birth);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(v.date_of_birth) || !Number.isFinite(d.getTime()) || d.toISOString().slice(0, 10) !== v.date_of_birth || d > new Date()) missing.push('birth_date_invalid');
    if (!['M', 'F'].includes(v.gender)) missing.push('gender');
  }
  return missing;
}
export function identityPatch(v: KbsIdentity): Partial<KbsIdentity> {
  return Object.fromEntries(Object.entries(v).filter(([, value]) => value.trim()).map(([k, value]) => [k, value.trim()]));
}
export function kbsStatusLabel(job: { status?: string; status_reason?: string; kbs_test?: boolean }): string {
  if (job.kbs_test) return 'Test kaydı — resmî bildirim değil';
  if (job.status_reason === 'delivery_uncertain') return 'Teslim belirsiz — kurumdan kontrol edilmeli';
  if (job.status_reason === 'awaiting_checkin') return 'Giriş kabulünü bekliyor';
  if (job.status_reason === 'missing_data') return 'Eksik bilgi — düzeltme gerekli';
  if (job.status_reason === 'already_registered') return 'Kurumda aynı kimlik için açık kayıt var — kurum kaydı uzlaştırılmalı, tekrar gönderilemez';
  if (job.status_reason === 'authority_rejected') return 'Kurum veya gönderici reddetti — kayıt ve bağlantı kontrol edilmeli';
  if (job.status_reason === 'processing') return 'Gönderim sürüyor; kurum kabulü henüz alınmadı';
  if (job.status_reason === 'awaiting_delivery') return 'Kurum kabulü henüz alınmadı — otomatik gönderici ve bağlantı kontrol edilmeli';
  return job.status === 'done' ? 'Kurum kabulü alındı' : 'Gönderim sonucu doğrulanamadı';
}
