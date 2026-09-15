/**
 * Companion filenames for a User Task web form. Launch Editor creates and
 * edits these three files together, matching the previous product's form
 * builder: `{base}-schema.json`, `{base}-uischema.json`, `{base}-exampledata.json`.
 */

export const SCHEMA_SUFFIX = '-schema.json';
export const UI_SUFFIX = '-uischema.json';
export const EXAMPLE_SUFFIX = '-exampledata.json';

export type FormSchemaFileNames = {
  schema: string;
  ui: string;
  example: string;
};

/** Same identifier rule the previous form builder required for a new schema name. */
export function isValidFormSchemaBase(name: string): boolean {
  return /^[a-z0-9][0-9a-z-]+[a-z0-9]$/.test(name);
}

export function schemaBaseName(fileName: string): string {
  const lower = fileName.toLowerCase();
  if (lower.endsWith(SCHEMA_SUFFIX)) return fileName.slice(0, -SCHEMA_SUFFIX.length);
  if (lower.endsWith('.schema.json')) return fileName.slice(0, -'.schema.json'.length);
  if (lower.endsWith(UI_SUFFIX)) return fileName.slice(0, -UI_SUFFIX.length);
  if (lower.endsWith(EXAMPLE_SUFFIX)) return fileName.slice(0, -EXAMPLE_SUFFIX.length);
  return fileName.replace(/\.json$/i, '');
}

export function formSchemaFileNames(base: string): FormSchemaFileNames {
  return {
    schema: `${base}${SCHEMA_SUFFIX}`,
    ui: `${base}${UI_SUFFIX}`,
    example: `${base}${EXAMPLE_SUFFIX}`,
  };
}

/** True for the three companion JSON files Launch Editor and the form-schema
 * canvas edit together — not for generic `*.json`. */
export function isFormSchemaFile(fileName: string): boolean {
  const lower = fileName.toLowerCase();
  return (
    lower.endsWith(SCHEMA_SUFFIX) ||
    lower.endsWith('.schema.json') ||
    lower.endsWith(UI_SUFFIX) ||
    lower.endsWith(EXAMPLE_SUFFIX)
  );
}

export type FormSchemaTab = 'schema' | 'ui' | 'data';

/** Which FormSchemaEditor tab matches the file the process-modeler route opened. */
export function formSchemaTabForFile(fileName: string): FormSchemaTab {
  const lower = fileName.toLowerCase();
  if (lower.endsWith(UI_SUFFIX)) return 'ui';
  if (lower.endsWith(EXAMPLE_SUFFIX)) return 'data';
  return 'schema';
}

/** Companion set for an opened form-schema file. Preserves a legacy
 * `{base}.schema.json` schema name so opening it does not invent `{base}-schema.json`. */
export function formSchemaFileNamesFrom(fileName: string): FormSchemaFileNames {
  const base = schemaBaseName(fileName);
  const names = formSchemaFileNames(base);
  const lower = fileName.toLowerCase();
  if (lower.endsWith('.schema.json') && !lower.endsWith(SCHEMA_SUFFIX)) {
    return { ...names, schema: fileName };
  }
  return names;
}

export function formSchemaOpenFileContent(
  fileName: string,
  names: FormSchemaFileNames,
  contents: { schema: string; ui: string; example: string },
): string {
  const lower = fileName.toLowerCase();
  if (lower === names.ui.toLowerCase() || lower.endsWith(UI_SUFFIX)) return contents.ui;
  if (lower === names.example.toLowerCase() || lower.endsWith(EXAMPLE_SUFFIX)) {
    return contents.example;
  }
  return contents.schema;
}

/** Filename base from a user-task name or element id, so Launch Editor can
 * attach a form without asking the designer to name files. Falls back to
 * `form` when the label cannot be slugified into a valid identifier. */
export function formSchemaBaseFromLabel(label: string): string {
  const slug = label
    .trim()
    .toLowerCase()
    .replace(/[_\s]+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '');
  if (isValidFormSchemaBase(slug)) return slug;
  const padded = `${slug}-form`.replace(/^-+/, '');
  if (isValidFormSchemaBase(padded)) return padded;
  return 'form';
}

export const EMPTY_JSON = '{}\n';
