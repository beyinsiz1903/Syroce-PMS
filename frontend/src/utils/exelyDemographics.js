// PMSConnect's AdultBed is a placement count, not proof of adult-only guests.
// Legacy records have no independently verified demographic provenance.
export const exelyDemographicsUnverified = (booking) => (
  [booking?.channel, booking?.source_channel, booking?.booking_source,
    booking?.source_provider, booking?.ota_channel, booking?.source?.provider]
    .some((provider) => String(provider || '').toLowerCase() === 'exely')
    && !exelyDemographicsVerified(booking)
);

export const exelyDemographicsVerified = booking => {
  const proof = booking?.exely_demographics;
  const ages = booking?.children_ages;
  return Boolean(proof?.status === 'verified' && proof.source === 'exely_read_reservation_v1'
    && booking.property_id && proof.property_id === booking.property_id
    && booking.provider_group_reservation_id && proof.reservation_id === booking.provider_group_reservation_id
    && booking.provider_version_key && proof.provider_version_key === booking.provider_version_key
    && ['check_in', 'check_out', 'room_type', 'currency', 'total_amount'].every(key => booking[key] != null && proof[key] === booking[key])
    && Number.isInteger(booking.adults) && booking.adults === proof.adults
    && Array.isArray(ages) && ages.every(age => Number.isInteger(age) && age >= 0 && age <= 17)
    && Array.isArray(proof.children_ages) && ages.length === proof.children_ages.length
    && ages.every((age, index) => age === proof.children_ages[index])
    && booking.children === ages.length && booking.guests_count === booking.adults + ages.length);
};

export const EXELY_DEMOGRAPHICS_WARNING = 'Exely kaydındaki yetişkin/çocuk ayrımı ve çocuk yaşları henüz doğrulanmadı. Yatak sayısı yetişkin sayısı anlamına gelmeyebilir.';
