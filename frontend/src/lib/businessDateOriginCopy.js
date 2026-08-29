const BUSINESS_DATE_FORMATTER = new Intl.DateTimeFormat("tr-TR", {
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "Europe/Istanbul",
});

const AUDIT_TIMESTAMP_FORMATTER = new Intl.DateTimeFormat("tr-TR", {
  day: "numeric",
  month: "long",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Europe/Istanbul",
});

const INITIALIZATION_COPY = {
  earliest_unresolved_arrival: "Açık rezervasyonlar esas alınarak güvenli başlangıç tarihi oluşturuldu.",
  night_audit_history: "Son başarılı Night Audit kaydı esas alınarak başlangıç tarihi oluşturuldu.",
  first_operational_use: "İlk operasyon günü esas alınarak başlangıç tarihi oluşturuldu.",
  tenant_provisioning: "Tesis kurulum günü esas alınarak başlangıç tarihi oluşturuldu.",
};

function parseBusinessDate(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ""));
  if (!match) return null;

  const [, year, month, day] = match;
  const parsed = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day), 12));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function formatBusinessDateForDisplay(value) {
  const parsed = parseBusinessDate(value);
  return parsed ? BUSINESS_DATE_FORMATTER.format(parsed) : String(value || "-");
}

function formatAuditTimestamp(value) {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : AUDIT_TIMESTAMP_FORMATTER.format(parsed);
}

function userIdMatchesActor(user, actorId) {
  if (!actorId) return false;
  const normalizedActorId = String(actorId);
  return [user?.id, user?.user_id, user?._id, user?.sub]
    .filter(Boolean)
    .some((candidate) => String(candidate) === normalizedActorId);
}

function visibleActorName(meta, user) {
  if (!userIdMatchesActor(user, meta?.updated_by)) return null;
  return user?.name || user?.full_name || user?.email || null;
}

function completedAuditDetail(meta, user) {
  const parts = [`Yeni PMS iş günü: ${formatBusinessDateForDisplay(meta.business_date)}.`];
  const completedAt = formatAuditTimestamp(meta.updated_at);
  const actorName = visibleActorName(meta, user);

  if (completedAt) parts.push(`Tamamlanma: ${completedAt}.`);

  if (meta.trigger_source === "scheduler") {
    parts.push("Otomatik Night Audit ile tamamlandı.");
  } else if (meta.trigger_source === "manual") {
    parts.push(actorName
      ? `${actorName} tarafından manuel olarak tamamlandı.`
      : "Yetkili kullanıcı tarafından manuel olarak tamamlandı.");
  } else {
    parts.push("Night Audit işlemi başarıyla kaydedildi.");
  }

  return parts.join(" ");
}

function initializationDetail(meta) {
  const parts = [`PMS iş günü: ${formatBusinessDateForDisplay(meta.business_date)}.`];
  const reason = INITIALIZATION_COPY[meta.initialization_reason];
  const initializedAt = formatAuditTimestamp(meta.initialized_at || meta.updated_at);

  if (reason) parts.push(reason);
  if (initializedAt) parts.push(`Kayıt zamanı: ${initializedAt}.`);
  if (meta.update_source === "legacy_record") {
    parts.push("Bu tarih eski sistem kaydından aktarıldı.");
  }

  return parts.join(" ");
}

export function buildBusinessDateOriginCopy(meta, user) {
  if (meta?.update_source === "night_audit") {
    return {
      title: "Night Audit tamamlandı",
      detail: completedAuditDetail(meta, user),
    };
  }

  return {
    title: meta?.update_source === "legacy_record"
      ? "PMS iş günü eski sistem kaydından geliyor"
      : "PMS iş günü güvenli başlangıç kaydından oluşturuldu",
    detail: initializationDetail(meta || {}),
  };
}
