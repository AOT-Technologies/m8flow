import i18next from 'i18next';
import { describe, expect, it, vi } from 'vitest';

import type { Translation } from '@/locales';

import i18n, {
  formatLocale,
  i18nOptions,
  lazyLocaleBackend,
  LOCALE_OPTIONS,
  LOCALE_STORAGE_KEY,
  localeDetector,
} from './i18n';

// A fresh instance with the app's options stands in for a page reload.
async function boot() {
  const instance = i18next.createInstance();
  await instance.use(localeDetector).use(lazyLocaleBackend).init(i18nOptions);
  return instance;
}

describe('i18n startup language', () => {
  it('restores the language saved by the Locale menu', async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, 'es');
    const instance = await boot();
    expect(instance.language).toBe('es');
    expect(instance.t('shell.nav.home')).toBe('Inicio');
  });

  it('uses English (US) when the saved language is not supported', async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, 'xx');
    const instance = await boot();
    expect(instance.language).toBe('en-US');
    expect(instance.t('shell.nav.home')).toBe('Home');
  });

  it('falls back to the browser language and saves it', async () => {
    window.localStorage.removeItem(LOCALE_STORAGE_KEY);
    const languages = vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['de-DE', 'en-US']);
    const instance = await boot();
    languages.mockRestore();
    expect(instance.language).toBe('de');
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('de');
  });

  it('does not throw when navigator.languages is missing', () => {
    window.localStorage.removeItem(LOCALE_STORAGE_KEY);
    const languages = vi.spyOn(navigator, 'languages', 'get').mockReturnValue(undefined as unknown as string[]);
    const language = vi.spyOn(navigator, 'language', 'get').mockReturnValue('es-ES');
    expect(localeDetector.detect()).toBe('es');
    languages.mockRestore();
    language.mockRestore();
  });

  it('maps a plain pt to Brazilian Portuguese and keeps an exact pt-PT', () => {
    window.localStorage.removeItem(LOCALE_STORAGE_KEY);
    const languages = vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['pt']);
    expect(localeDetector.detect()).toBe('pt-BR');
    languages.mockReturnValue(['pt-PT', 'pt']);
    expect(localeDetector.detect()).toBe('pt-PT');
    languages.mockRestore();
  });
});

describe('formatLocale', () => {
  it("uses the browser's own variant of the UI language, else the UI language", async () => {
    const languages = vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['en-GB', 'de-AT']);
    expect(formatLocale()).toBe('en-GB'); // UI is en-US: dates keep day/month order
    await i18n.changeLanguage('de');
    expect(formatLocale()).toBe('de-AT');
    await i18n.changeLanguage('es');
    expect(formatLocale()).toBe('es');
    languages.mockRestore();
  });
});

describe('lazy language bundles', () => {
  it.each(LOCALE_OPTIONS.map((option) => option.value).filter((lng) => lng !== 'en-US'))('loads %s', async (lng) => {
    const bundle = await new Promise<Translation>((resolve, reject) => {
      lazyLocaleBackend.read(lng, 'translation', (error, data) => (error ? reject(error) : resolve(data as Translation)));
    });
    expect(bundle.shell.nav.home).toBeTruthy();
  });
});
