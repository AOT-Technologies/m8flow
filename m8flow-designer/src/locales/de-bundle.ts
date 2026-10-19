import type { Translation } from '.';
import shell from './de/shell.json';

// Typed as the English tree, so a key missing from German fails `tsc`.
const de: Translation = { shell };

export default de;
