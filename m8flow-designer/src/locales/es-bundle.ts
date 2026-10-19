import type { Translation } from '.';
import shell from './es/shell.json';

// Typed as the English tree, so a key missing from Spanish fails `tsc`.
const es: Translation = { shell };

export default es;
