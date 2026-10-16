import deShell from './de/shell.json';
import enShell from './en-US/shell.json';
import esShell from './es/shell.json';

const en = { shell: enShell };
// Typed as the English tree, so a key missing from any other language fails `tsc`.
const es: typeof en = { shell: esShell };
const de: typeof en = { shell: deShell };

export const resources = {
  'en-US': { translation: en },
  es: { translation: es },
  de: { translation: de },
};
