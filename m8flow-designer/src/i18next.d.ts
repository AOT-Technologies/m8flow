import 'i18next';

import type { resources } from './locales';

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation';
    resources: (typeof resources)['en-US'];
  }
}
