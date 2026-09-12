import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { apiPost, trackLead } = vi.hoisted(() => ({ apiPost: vi.fn(), trackLead: vi.fn() }));
vi.mock('axios', () => ({ default: { post: (...args) => apiPost(...args) } }));
vi.mock('@/lib/marketingAnalytics', () => ({
  getLeadAttribution: () => ({ utm_source: 'google', landing_path: '/otel-programi' }),
  trackDemoLeadSuccess: () => trackLead(),
}));

import MarketingContactForm from './MarketingContactForm';

function submitForm() {
  fireEvent.change(screen.getByRole('textbox', { name: /Ad Soyad/ }), { target: { value: 'Ada Test' } });
  fireEvent.change(screen.getByRole('textbox', { name: /İşletme Adı/ }), { target: { value: 'Örnek Otel' } });
  fireEvent.change(screen.getByRole('textbox', { name: /Telefon/ }), { target: { value: '5551234567' } });
  fireEvent.change(screen.getByRole('textbox', { name: /E-posta/ }), { target: { value: 'ada@example.com' } });
  fireEvent.click(screen.getByRole('button', { name: /Demo Talep Et/ }));
}

describe('MarketingContactForm', () => {
  beforeEach(() => { apiPost.mockReset(); trackLead.mockReset(); });
  afterEach(cleanup);

  it('sends the lead with attribution and tracks only a new successful submission', async () => {
    apiPost.mockResolvedValue({ data: { ok: true, deduped: false } });
    render(<MarketingContactForm />);
    submitForm();
    await waitFor(() => expect(trackLead).toHaveBeenCalledTimes(1));
    expect(apiPost).toHaveBeenCalledWith('/leads/contact', expect.objectContaining({
      full_name: 'Ada Test', company: 'Örnek Otel', metadata: { utm_source: 'google', landing_path: '/otel-programi' },
    }));
    expect(screen.getByRole('status')).toHaveTextContent('Demo talebiniz alındı');
  });

  it('does not count a deduplicated lead as a new conversion', async () => {
    apiPost.mockResolvedValue({ data: { ok: true, deduped: true } });
    render(<MarketingContactForm />);
    submitForm();
    await screen.findByRole('status');
    expect(trackLead).not.toHaveBeenCalled();
  });

  it('does not count a failed request as a conversion', async () => {
    apiPost.mockRejectedValue({ response: { status: 422 } });
    render(<MarketingContactForm />);
    submitForm();
    expect(await screen.findByRole('status')).toHaveTextContent('Lütfen ad soyad');
    expect(trackLead).not.toHaveBeenCalled();
  });
});
