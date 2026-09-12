import React, { useEffect, useState } from 'react';
import { getMarketingConsent, hasMarketingConsentChoice, setMarketingConsent, trackMarketingPageView } from '@/lib/marketingAnalytics';

export default function MarketingConsent() {
  const [visible, setVisible] = useState(() => !hasMarketingConsentChoice());

  useEffect(() => {
    if (getMarketingConsent()) trackMarketingPageView();
    const openPreferences = () => setVisible(true);
    window.addEventListener('syroce:marketing-preferences', openPreferences);
    return () => window.removeEventListener('syroce:marketing-preferences', openPreferences);
  }, []);

  const choose = granted => {
    setMarketingConsent(granted);
    setVisible(false);
    if (granted) trackMarketingPageView();
  };

  if (!visible) return null;
  return <div role="dialog" aria-label="Analitik çerez tercihi" className="fixed bottom-4 left-4 right-4 z-[70] mx-auto max-w-xl rounded-2xl border border-white/20 bg-[#0c1726] p-4 text-sm text-slate-200 shadow-2xl sm:p-5">
    <p>Site kullanımını ölçmek için isteğe bağlı analitik çerezler kullanmak istiyoruz. Reddetseniz de siteyi ve demo formunu kullanabilirsiniz. <a href="/privacy-policy" className="underline">Gizlilik politikası</a></p>
    <div className="mt-4 flex justify-end gap-3">
      <button type="button" onClick={() => choose(false)} className="rounded-full border border-white/20 px-4 py-2">Reddet</button>
      <button type="button" onClick={() => choose(true)} className="rounded-full bg-cyan-400 px-4 py-2 font-semibold text-[#05070f]">Kabul Et</button>
    </div>
  </div>;
}
