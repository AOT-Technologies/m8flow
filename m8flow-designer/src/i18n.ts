import i18n, { type BackendModule, type InitOptions, type LanguageDetectorModule } from 'i18next';
import { initReactI18next } from 'react-i18next';

import { resources, type Translation } from '@/locales';

// Only en-US (the fallback) is bundled; es/de are chunks fetched when first selected.
const LAZY_LOCALES: Record<string, () => Promise<{ default: Translation }>> = {
  es: () => import('@/locales/es-bundle'),
  de: () => import('@/locales/de-bundle'),
};

export const lazyLocaleBackend: BackendModule = {
  type: 'backend',
  init() {},
  read(language, _namespace, callback) {
    const load = LAZY_LOCALES[language];
    if (!load) return callback(null, {});
    load().then((module) => callback(null, module.default), (error: Error) => callback(error, null));
  },
};

/** Each language is listed in its own name (endonym), so it is never translated. */
export const LOCALE_OPTIONS = [
  { value: 'en-US', label: 'English (US)' },
  { value: 'es', label: 'Español' },
  { value: 'de', label: 'Deutsch' },
] as const;

// Same key the Sidebar used before i18n, so a saved choice survives the upgrade.
export const LOCALE_STORAGE_KEY = 'm8flow_locale';

const SUPPORTED: readonly string[] = LOCALE_OPTIONS.map((option) => option.value);

/** Exact match, else the same base language: en-GB → en-US, de-DE → de. */
function toSupported(code: string): string | undefined {
  const base = code.split('-')[0];
  return SUPPORTED.find((lng) => lng === code) ?? SUPPORTED.find((lng) => lng.split('-')[0] === base);
}

// Saved choice first, then the browser's languages in preference order, so
// ['de-DE', 'en-US'] picks German. (Replaces i18next-browser-languagedetector,
// ~2 KB gzip of first load, which picked en-US there.)
export const localeDetector: LanguageDetectorModule = {
  type: 'languageDetector',
  detect() {
    let saved: string | null = null;
    try {
      saved = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    } catch {
      // Storage can be blocked (e.g. private mode); fall back to the browser languages.
    }
    const codes = saved ? [saved, ...navigator.languages] : navigator.languages;
    return codes.map(toSupported).find((lng) => lng !== undefined);
  },
  cacheUserLanguage(lng) {
    try {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, lng);
    } catch {
      // Ignore unavailable storage; the language still applies for this page.
    }
  },
};

export const i18nOptions: InitOptions = {
  resources,
  partialBundledLanguages: true,
  supportedLngs: LOCALE_OPTIONS.map((option) => option.value),
  fallbackLng: 'en-US',
  load: 'currentOnly',
  // en-US starts are ready synchronously; es/de resolve `i18nReady` once their chunk loads.
  initAsync: false,
  interpolation: { escapeValue: false }, // React already escapes output.
  react: { useSuspense: false },
};

i18n.on('languageChanged', (lng) => {
  document.documentElement.lang = lng;
});

export const i18nReady = i18n.use(localeDetector).use(lazyLocaleBackend).use(initReactI18next).init(i18nOptions);

export default i18n;
