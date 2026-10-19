import enShell from './en-US/shell.json';

/** English (US) is the bundled fallback; other languages are lazy chunks (see `es-bundle.ts`, `de-bundle.ts`). */
const en = { shell: enShell };

export type Translation = typeof en;

export const resources = { 'en-US': { translation: en } };
