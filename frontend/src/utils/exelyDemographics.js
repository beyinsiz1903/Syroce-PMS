// PMSConnect's AdultBed is a placement count, not proof of adult-only guests.
// Legacy records have no independently verified demographic provenance.
export const exelyDemographicsUnverified = (booking) => (
  [booking?.channel, booking?.source_channel, booking?.booking_source,
    booking?.source_provider, booking?.ota_channel, booking?.source?.provider]
    .some((provider) => String(provider || '').toLowerCase() === 'exely')
);

export const EXELY_DEMOGRAPHICS_WARNING = 'Exely kaydındaki yetişkin/çocuk ayrımı ve çocuk yaşları henüz doğrulanmadı. Yatak sayısı yetişkin sayısı anlamına gelmeyebilir.';
