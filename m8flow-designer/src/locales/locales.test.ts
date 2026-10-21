import { describe, expect, it } from 'vitest';

import { LOCALE_OPTIONS } from '@/i18n';

/**
 * tsc already fails on a key missing from any language (each bundle is typed as the English
 * tree). This covers what the types can't: each language's extra plural forms (Czech _few,
 * Spanish/French/Portuguese _many), {{placeholders}}, <tags> and empty values.
 */
type Tree = { [key: string]: string | Tree };

const files = import.meta.glob<Tree>('./*/*.json', { eager: true, import: 'default' });

const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/;

function leaves(tree: Tree, prefix = ''): [string, string][] {
  return Object.entries(tree).flatMap(([key, value]): [string, string][] =>
    typeof value === 'string' ? [[prefix + key, value]] : leaves(value, `${prefix}${key}.`),
  );
}

const placeholders = (text: string) => [...text.matchAll(/{{\s*([^}\s]+)\s*}}/g)].map((match) => match[1]);
const tags = (text: string) => (text.match(/<\/?[a-z0-9]+>/gi) ?? []).sort();

function problems(language: string): string[] {
  const found: string[] = [];
  // English supplies _one/_other; the language may need more (zh still keeps _one for the types).
  const categories = new Set(['one', 'other', ...new Intl.PluralRules(language).resolvedOptions().pluralCategories]);

  for (const [path, english] of Object.entries(files).filter(([path]) => path.startsWith('./en-US/'))) {
    const area = path.slice('./en-US/'.length);
    const translated = files[`./${language}/${area}`];
    if (!translated) {
      found.push(`${area}: missing file`);
      continue;
    }
    const source = new Map(leaves(english));
    const target = new Map(leaves(translated));
    const pluralBases = new Set([...source.keys()].filter((key) => PLURAL_SUFFIX.test(key)).map((key) => key.replace(PLURAL_SUFFIX, '')));

    const expected = new Map<string, string>();
    for (const [key, text] of source) if (!pluralBases.has(key.replace(PLURAL_SUFFIX, ''))) expected.set(key, text);
    for (const base of pluralBases) for (const category of categories) expected.set(`${base}_${category}`, source.get(`${base}_other`) ?? '');

    for (const [key, text] of expected) {
      const value = target.get(key);
      if (value === undefined) found.push(`${area}: missing ${key}`);
      else if (!value.trim()) found.push(`${area}: empty ${key}`);
      else {
        const plural = pluralBases.has(key.replace(PLURAL_SUFFIX, ''));
        // A plural form may drop {{count}} (e.g. "one item"), but no other placeholder.
        const want = new Set(placeholders(text).filter((name) => !plural || name !== 'count'));
        const have = new Set(placeholders(value).filter((name) => !plural || name !== 'count'));
        if ([...want].sort().join() !== [...have].sort().join()) found.push(`${area}: placeholders in ${key}`);
        if (tags(value).join() !== tags(text).join()) found.push(`${area}: tags in ${key}`);
      }
    }
    for (const key of target.keys()) if (!expected.has(key)) found.push(`${area}: unexpected ${key}`);
  }
  return found;
}

describe('locale files', () => {
  it.each(LOCALE_OPTIONS.map((option) => option.value).filter((language) => language !== 'en-US'))(
    '%s matches English: keys, plural forms, placeholders and tags',
    (language) => {
      expect(problems(language)).toEqual([]);
    },
  );
});
