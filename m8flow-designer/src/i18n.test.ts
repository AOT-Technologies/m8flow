import i18next from 'i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import { describe, expect, it } from 'vitest';

import { i18nOptions, LOCALE_STORAGE_KEY } from './i18n';

// A fresh instance with the app's options stands in for a page reload.
async function boot() {
  const instance = i18next.createInstance();
  await instance.use(LanguageDetector).init(i18nOptions);
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
});
