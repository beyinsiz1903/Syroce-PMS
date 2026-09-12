import { afterEach, describe, expect, it, vi } from 'vitest';
import { getLeadAttribution, getMarketingConsent, setMarketingConsent, trackDemoLeadSuccess } from './marketingAnalytics';

describe('marketing analytics consent and attribution', () => {
  afterEach(() => {
    window.localStorage.clear();
    window.history.replaceState({}, '', '/');
    delete window.gtag;
    vi.restoreAllMocks();
  });

  it('does not send conversion events without consent', () => {
    window.gtag = vi.fn();
    trackDemoLeadSuccess();
    expect(window.gtag).not.toHaveBeenCalled();
    expect(getMarketingConsent()).toBe(false);
  });

  it('captures UTM fields and landing path without collecting other query parameters', () => {
    window.history.replaceState({}, '', '/otel-programi?utm_source=google&utm_medium=cpc&utm_campaign=hotel&email=private');
    expect(getLeadAttribution()).toEqual({
      utm_source: 'google', utm_medium: 'cpc', utm_campaign: 'hotel', landing_path: '/otel-programi',
    });
  });

  it('records a revocable choice', () => {
    setMarketingConsent(true);
    expect(getMarketingConsent()).toBe(true);
    setMarketingConsent(false);
    expect(getMarketingConsent()).toBe(false);
  });
});
