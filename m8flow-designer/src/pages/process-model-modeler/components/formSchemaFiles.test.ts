import { describe, expect, it } from 'vitest';

import {
  formSchemaBaseFromLabel,
  formSchemaFileNames,
  formSchemaFileNamesFrom,
  formSchemaOpenFileContent,
  formSchemaTabForFile,
  isFormSchemaFile,
  isValidFormSchemaBase,
  schemaBaseName,
} from './formSchemaFiles';

describe('isValidFormSchemaBase', () => {
  it('accepts lowercase hyphenated names of at least three characters', () => {
    expect(isValidFormSchemaBase('abc')).toBe(true);
    expect(isValidFormSchemaBase('sample-form')).toBe(true);
    expect(isValidFormSchemaBase('wfh-form')).toBe(true);
  });

  it('rejects empty, short, or illegal identifiers', () => {
    expect(isValidFormSchemaBase('')).toBe(false);
    expect(isValidFormSchemaBase('ab')).toBe(false);
    expect(isValidFormSchemaBase('Sample Form')).toBe(false);
    expect(isValidFormSchemaBase('sample_form')).toBe(false);
    expect(isValidFormSchemaBase('-sample')).toBe(false);
  });
});

describe('schemaBaseName', () => {
  it('strips the schema / ui / example suffixes', () => {
    expect(schemaBaseName('sample-form-schema.json')).toBe('sample-form');
    expect(schemaBaseName('sample-form-uischema.json')).toBe('sample-form');
    expect(schemaBaseName('sample-form-exampledata.json')).toBe('sample-form');
    expect(schemaBaseName('wfh-form.schema.json')).toBe('wfh-form');
  });
});

describe('formSchemaBaseFromLabel', () => {
  it('slugifies a task name or element id into a valid base', () => {
    expect(formSchemaBaseFromLabel('Task')).toBe('task');
    expect(formSchemaBaseFromLabel('Example user task')).toBe('example-user-task');
    expect(formSchemaBaseFromLabel('Activity_1abc')).toBe('activity-1abc');
  });

  it('pads short labels and falls back to form', () => {
    expect(formSchemaBaseFromLabel('ab')).toBe('ab-form');
    expect(formSchemaBaseFromLabel('!!!')).toBe('form');
  });
});

describe('formSchemaFileNames', () => {
  it('builds the three companion filenames from a base', () => {
    expect(formSchemaFileNames('sample-form')).toEqual({
      schema: 'sample-form-schema.json',
      ui: 'sample-form-uischema.json',
      example: 'sample-form-exampledata.json',
    });
  });
});

describe('isFormSchemaFile', () => {
  it('matches companion suffixes and the legacy .schema.json name', () => {
    expect(isFormSchemaFile('sample-form-schema.json')).toBe(true);
    expect(isFormSchemaFile('sample-form-uischema.json')).toBe(true);
    expect(isFormSchemaFile('sample-form-exampledata.json')).toBe(true);
    expect(isFormSchemaFile('wfh-form.schema.json')).toBe(true);
    expect(isFormSchemaFile('test_payload.json')).toBe(false);
    expect(isFormSchemaFile('notes.md')).toBe(false);
  });
});

describe('formSchemaTabForFile', () => {
  it('opens the tab that matches the route file', () => {
    expect(formSchemaTabForFile('sample-form-schema.json')).toBe('schema');
    expect(formSchemaTabForFile('sample-form-uischema.json')).toBe('ui');
    expect(formSchemaTabForFile('sample-form-exampledata.json')).toBe('data');
  });
});

describe('formSchemaFileNamesFrom', () => {
  it('keeps a legacy .schema.json schema filename', () => {
    expect(formSchemaFileNamesFrom('wfh-form.schema.json')).toEqual({
      schema: 'wfh-form.schema.json',
      ui: 'wfh-form-uischema.json',
      example: 'wfh-form-exampledata.json',
    });
  });

  it('derives companions from a ui or example file via the hyphen suffix', () => {
    expect(formSchemaFileNamesFrom('sample-form-uischema.json').schema).toBe(
      'sample-form-schema.json',
    );
  });
});

describe('formSchemaOpenFileContent', () => {
  it('returns the companion that the open route file is', () => {
    const names = formSchemaFileNames('sample-form');
    const contents = { schema: '{s}', ui: '{u}', example: '{e}' };
    expect(formSchemaOpenFileContent('sample-form-schema.json', names, contents)).toBe('{s}');
    expect(formSchemaOpenFileContent('sample-form-uischema.json', names, contents)).toBe('{u}');
    expect(formSchemaOpenFileContent('sample-form-exampledata.json', names, contents)).toBe('{e}');
  });
});
