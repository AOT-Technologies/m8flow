import i18n, { type InitOptions } from 'i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import { initReactI18next } from 'react-i18next';

import { resources } from '@/locales';

/** Each language is listed in its own name (endonym), so it is never translated. */
export const LOCALE_OPTIONS = [
  { value: 'en-US', label: 'English (US)' },
  { value: 'es', label: 'Español' },
  { value: 'de', label: 'Deutsch' },
] as const;

// Same key the Sidebar used before i18n, so a saved choice survives the upgrade.
export const LOCALE_STORAGE_KEY = 'm8flow_locale';

export const i18nOptions: InitOptions = {
  resources,
  supportedLngs: LOCALE_OPTIONS.map((option) => option.value),
  fallbackLng: 'en-US',
  load: 'currentOnly',
  // Resources are bundled, so init completes before the first render.
  initAsync: false,
  interpolation: { escapeValue: false }, // React already escapes output.
  detection: {
    order: ['localStorage', 'navigator'],
    lookupLocalStorage: LOCALE_STORAGE_KEY,
    caches: ['localStorage'],
  },
  react: { useSuspense: false },
};

i18n.on('languageChanged', (lng) => {
  document.documentElement.lang = lng;
});

void i18n.use(LanguageDetector).use(initReactI18next).init(i18nOptions);

export default i18n;
