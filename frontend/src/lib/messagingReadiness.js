const PROVIDER_LABELS = {
  email: 'E-posta',
  whatsapp: 'WhatsApp',
};

/**
 * Converts a saved provider configuration into the operational state a hotel
 * user needs to act on. A record existing in the database is not proof that
 * outbound communication is ready for production.
 */
export function getMessagingReadiness(provider, channel = 'whatsapp') {
  const label = PROVIDER_LABELS[channel] || 'Sağlayıcı';
  const credentials = provider?.credentials || {};
  const hasCredentials = channel === 'whatsapp'
    ? Boolean(credentials.access_token && credentials.phone_number_id)
    : Boolean(credentials.smtp_host && credentials.from_email);

  if (!provider || !hasCredentials) {
    return {
      state: 'setup_required',
      intent: 'neutral',
      label: 'Kurulum gerekli',
      description: `${label} bilgileri tamamlanmadan mesaj gönderilemez.`,
    };
  }
  if (!provider.enabled) {
    return {
      state: 'disabled',
      intent: 'neutral',
      label: 'Devre dışı',
      description: `${label} yapılandırılmış ancak gönderim kapalı.`,
    };
  }
  if (provider.is_sandbox) {
    return {
      state: 'sandbox',
      intent: 'warning',
      label: 'Deneme ortamı',
      description: 'Gerçek misafirlere gönderim için deneme modunu kapatın ve bağlantıyı doğrulayın.',
    };
  }
  if (provider.health_status === 'healthy') {
    return {
      state: 'ready',
      intent: 'success',
      label: 'Gönderime hazır',
      description: `${label} üretim ayarları bağlantı testinden geçti.`,
    };
  }
  if (provider.health_status === 'unknown' || provider.health_status == null) {
    return {
      state: 'verification_required',
      intent: 'warning',
      label: 'Doğrulama bekliyor',
      description: 'Ayarlar kaydedildi; üretime geçmeden önce bağlantı testi yapın.',
    };
  }
  return {
    state: 'connection_error',
    intent: 'danger',
    label: 'Bağlantı hatası',
    description: 'Son bağlantı testi başarısız. Bilgileri kontrol edip yeniden deneyin.',
  };
}
