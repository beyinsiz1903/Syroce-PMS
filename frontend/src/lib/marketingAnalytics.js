const CONSENT_KEY = 'syroce_marketing_analytics_consent';
const UTM_KEYS = ['utm_source', 'utm_medium', 'utm_campaign'];

export function getMarketingConsent() {
  try {
    return window.localStorage.getItem(CONSENT_KEY) === 'granted';
  } catch {
    return false;
  }
}

export function setMarketingConsent(granted) {
  try {
    window.localStorage.setItem(CONSENT_KEY, granted ? 'granted' : 'denied');
  } catch {
    // The site and contact form remain usable when storage is unavailable.
  }
  if (granted) {
    initMarketingAnalytics();
    window.gtag?.('consent', 'update', { analytics_storage: 'granted', ad_storage: 'granted', ad_user_data: 'granted', ad_personalization: 'granted' });
  } else {
    window.gtag?.('consent', 'update', { analytics_storage: 'denied', ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied' });
  }
}

export function hasMarketingConsentChoice() {
  try {
    return window.localStorage.getItem(CONSENT_KEY) !== null;
  } catch {
    return false;
  }
}

export function getLeadAttribution() {
  const params = new URLSearchParams(window.location.search);
  const metadata = {};
  UTM_KEYS.forEach(key => {
    const value = params.get(key);
    if (value) metadata[key] = value.slice(0, 120);
  });
  metadata.landing_path = window.location.pathname.slice(0, 200);
  return metadata;
}

export function initMarketingAnalytics() {
  const tagId = import.meta.env.VITE_GOOGLE_TAG_ID || import.meta.env.VITE_GOOGLE_ADS_ID;
  if (!tagId || !getMarketingConsent() || window.__syroceMarketingTagLoaded) return;
  window.__syroceMarketingTagLoaded = true;
  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function gtag() { window.dataLayer.push(arguments); };
  window.gtag('js', new Date());
  window.gtag('consent', 'default', { analytics_storage: 'granted', ad_storage: 'granted', ad_user_data: 'granted', ad_personalization: 'granted' });
  window.gtag('config', tagId, { send_page_view: false });
  const adsId = import.meta.env.VITE_GOOGLE_ADS_ID;
  if (adsId && adsId !== tagId) window.gtag('config', adsId, { send_page_view: false });
  const script = document.createElement('script');
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(tagId)}`;
  document.head.appendChild(script);
}

export function trackMarketingPageView() {
  if (!getMarketingConsent()) return;
  initMarketingAnalytics();
  window.gtag?.('event', 'page_view', {
    page_path: window.location.pathname,
    page_location: window.location.href,
    page_title: document.title,
  });
}

export function trackDemoLeadSuccess() {
  if (!getMarketingConsent()) return;
  initMarketingAnalytics();
  window.gtag?.('event', 'generate_lead', { method: 'contact_form' });
  const conversionId = import.meta.env.VITE_GOOGLE_ADS_ID;
  const conversionLabel = import.meta.env.VITE_GOOGLE_ADS_DEMO_CONVERSION_LABEL;
  if (conversionId && conversionLabel) {
    window.gtag?.('event', 'conversion', {
      send_to: `${conversionId}/${conversionLabel}`,
    });
  }
}
