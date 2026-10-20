import 'i18next';

import type { Translation } from './locales';

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation';
    // The full English tree, including page areas that are loaded lazily.
    resources: { translation: Translation };
  }
}
