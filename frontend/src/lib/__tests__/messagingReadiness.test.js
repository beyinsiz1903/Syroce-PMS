import { describe, expect, it } from 'vitest';
import { getMessagingReadiness } from '../messagingReadiness';

const configuredWhatsApp = {
  credentials: { access_token: 'masked-token', phone_number_id: '12345' },
  enabled: true,
  is_sandbox: false,
};

describe('getMessagingReadiness', () => {
  it('recognizes the HTTPS email transport without requiring an SMTP host', () => {
    const provider = { enabled: true, is_sandbox: false, health_status: 'healthy', credentials: {
      email_transport: 'zoho_api', from_email: 'hotel@example.com', zoho_account_id: '123', zoho_client_id: 'id', zoho_client_secret: '********', zoho_refresh_token: '********',
    } };
    expect(getMessagingReadiness(provider, 'email').state).toBe('ready');
    expect(getMessagingReadiness({ ...provider, credentials: { ...provider.credentials, zoho_refresh_token: '' } }, 'email').state).toBe('setup_required');
  });
  it('does not treat a missing provider as ready to send', () => {
    expect(getMessagingReadiness(null).state).toBe('setup_required');
  });

  it('requires both WhatsApp sending credentials', () => {
    expect(getMessagingReadiness({ credentials: { phone_number_id: '12345' } }).state)
      .toBe('setup_required');
  });

  it('keeps sandbox distinct from production readiness', () => {
    expect(getMessagingReadiness({ ...configuredWhatsApp, is_sandbox: true, health_status: 'healthy' }).state)
      .toBe('sandbox');
  });

  it('requires a successful health check before calling production ready', () => {
    expect(getMessagingReadiness({ ...configuredWhatsApp, health_status: 'unknown' }).state)
      .toBe('verification_required');
    expect(getMessagingReadiness({ ...configuredWhatsApp, health_status: 'healthy' }).state)
      .toBe('ready');
  });

  it('surfaces a failed connection separately', () => {
    expect(getMessagingReadiness({ ...configuredWhatsApp, health_status: 'failed' }).state)
      .toBe('connection_error');
  });
});
