import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

// ── Lazy locale loaders ────────────────────────────────────────────
// Her dil ayrı chunk olarak indirilir (Vite dynamic JSON import).
// Önceden 10 dil × ~140 KB = 1.4 MB JSON entry bundle'a gömülüydü;
// şimdi sadece kullanıcının dili + fallback (en) ilk yüklemede iner.
const localeLoaders = {
  en: () => import('./locales/en.json'),
  tr: () => import('./locales/tr.json'),
  ar: () => import('./locales/ar.json'),
  ru: () => import('./locales/ru.json'),
  it: () => import('./locales/it.json'),
  fr: () => import('./locales/fr.json'),
  es: () => import('./locales/es.json'),
  de: () => import('./locales/de.json'),
  pt: () => import('./locales/pt.json'),
  zh: () => import('./locales/zh.json'),
};

const SUPPORTED = Object.keys(localeLoaders);
const FALLBACK = 'en';

async function loadLanguage(lng) {
  if (!lng || !SUPPORTED.includes(lng)) return;
  if (i18n.hasResourceBundle(lng, 'translation')) return;
  try {
    const mod = await localeLoaders[lng]();
    i18n.addResourceBundle(lng, 'translation', mod.default || mod, true, true);
  } catch {
    /* network failure — fallback dil zaten yüklü olur */
  }
}

function applyDir(lng) {
  document.documentElement.dir = lng === 'ar' ? 'rtl' : 'ltr';
  document.documentElement.lang = lng || FALLBACK;
}

let initPromise = null;

export function initI18n() {
  if (initPromise) return initPromise;

  // Detect: localStorage > navigator > fallback
  const stored = (typeof localStorage !== 'undefined' && localStorage.getItem('language')) || null;
  const nav = (typeof navigator !== 'undefined' && (navigator.language || '').slice(0, 2)) || null;
  const initialLng = SUPPORTED.includes(stored) ? stored
    : SUPPORTED.includes(nav) ? nav
    : FALLBACK;

  initPromise = (async () => {
    await i18n
      .use(LanguageDetector)
      .use(initReactI18next)
      .init({
        resources: {},
        partialBundledLanguages: true,
        fallbackLng: FALLBACK,
        lng: initialLng,
        supportedLngs: SUPPORTED,
        interpolation: { escapeValue: false },
        detection: {
          order: ['localStorage', 'navigator'],
          caches: ['localStorage'],
        },
        react: { useSuspense: false },
      });

    // İlk yükleme: kullanıcı dili + fallback (paralel).
    const tasks = [loadLanguage(initialLng)];
    if (initialLng !== FALLBACK) tasks.push(loadLanguage(FALLBACK));
    await Promise.all(tasks);

    applyDir(i18n.language);

    // Güvenlik ağı: i18n.changeLanguage doğrudan başka yerden çağrılırsa
    // (changeLanguage helper'ı atlayarak), eksik paketi arka planda indir.
    // Re-emit ile react-i18next'in re-render tetiklemesini sağla.
    i18n.on('languageChanged', async (lng) => {
      applyDir(lng);
      if (lng && !i18n.hasResourceBundle(lng, 'translation')) {
        await loadLanguage(lng);
        // Bundle eklendi, react-i18next bileşenleri yeniden render etsin.
        i18n.emit('languageChanged', lng);
      }
    });
  })();

  return initPromise;
}

/**
 * Güvenli dil değiştirme: önce paketi indir, sonra aktif et.
 * react-i18next'in fallback/key text gösterme race condition'ını önler.
 * Tüm UI bileşenleri (LanguageSelector vs.) bu helper'ı kullanmalı.
 */
export async function changeLanguage(lng) {
  await loadLanguage(lng);
  await i18n.changeLanguage(lng);
}

export default i18n;
