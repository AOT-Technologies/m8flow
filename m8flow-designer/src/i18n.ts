import i18n, { type BackendModule, type InitOptions, type LanguageDetectorModule } from 'i18next';
import { initReactI18next } from 'react-i18next';

import { resources, type Translation } from '@/locales';

// Only en-US (the fallback) is bundled; every other language is a chunk fetched when first selected.
const LAZY_LOCALES: Record<string, () => Promise<{ default: Translation }>> = {
  es: () => import('@/locales/es-bundle'),
  de: () => import('@/locales/de-bundle'),
  'pt-BR': () => import('@/locales/pt-BR-bundle'),
  'pt-PT': () => import('@/locales/pt-PT-bundle'),
  'fr-FR': () => import('@/locales/fr-FR-bundle'),
  fi: () => import('@/locales/fi-bundle'),
  'cs-CZ': () => import('@/locales/cs-CZ-bundle'),
  'zh-CN': () => import('@/locales/zh-CN-bundle'),
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
  // Listed before pt-PT, so a plain `pt` browser language picks Brazilian Portuguese.
  { value: 'pt-BR', label: 'Português (Brasil)' },
  { value: 'pt-PT', label: 'Português (Portugal)' },
  { value: 'fr-FR', label: 'Français' },
  { value: 'fi', label: 'Suomi' },
  { value: 'cs-CZ', label: 'Čeština' },
  { value: 'zh-CN', label: '简体中文' },
] as const;

// Same key the Sidebar used before i18n, so a saved choice survives the upgrade.
export const LOCALE_STORAGE_KEY = 'm8flow_locale';

const SUPPORTED: readonly string[] = LOCALE_OPTIONS.map((option) => option.value);

/** Exact match, else the same base language: en-GB → en-US, de-DE → de. */
function toSupported(code: string): string | undefined {
  const base = code.split('-')[0];
  return SUPPORTED.find((lng) => lng === code) ?? SUPPORTED.find((lng) => lng.split('-')[0] === base);
}

/** The browser's languages in preference order. navigator (or its .languages) can be missing outside a browser. */
function browserLanguages(): readonly string[] {
  if (typeof navigator === 'undefined') return [];
  return Array.isArray(navigator.languages) ? navigator.languages : [navigator.language].filter(Boolean);
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
    const browser = browserLanguages();
    const codes = saved ? [saved, ...browser] : browser;
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
  if (typeof document !== 'undefined') document.documentElement.lang = lng;
});

/**
 * Locale for dates and numbers: the browser's own variant of the UI language when it has one,
 * so an en-GB browser keeps day/month order under the en-US UI; otherwise the UI language.
 */
export function formatLocale(): string {
  const language = i18n.language || 'en-US';
  const base = language.split('-')[0];
  return browserLanguages().find((code) => code.split('-')[0] === base) ?? language;
}

export const i18nReady = i18n.use(localeDetector).use(lazyLocaleBackend).use(initReactI18next).init(i18nOptions);

/**
 * Spread on a <Trans> whose `values` hold user text (names, usernames, file names): Trans parses
 * its string as markup after interpolation, so a name like `a <i>b</i>` would render as HTML.
 * Escaping first and unescaping after keeps the value literal.
 */
export const literalTransValues = { shouldUnescape: true, tOptions: { interpolation: { escapeValue: true } } };

let pageStrings: Promise<void> | undefined;

/** English strings for every page except Home: one chunk, fetched before the first lazy page renders. */
export function loadPageStrings(): Promise<void> {
  pageStrings ??= import('@/locales/en-pages').then(
    (module) => {
      i18n.addResourceBundle('en-US', 'translation', module.default, true, true);
    },
    (error: unknown) => {
      pageStrings = undefined; // let the next navigation retry
      throw error;
    },
  );
  return pageStrings;
}

export default i18n;
