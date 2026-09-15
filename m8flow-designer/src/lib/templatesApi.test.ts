import { describe, expect, it } from 'vitest';

import { API_BASE_URL } from './api';
import {
  contentTypeForTemplateFileName,
  templatePath,
  templateFileDownloadUrl,
  templateModelerFilePath,
  templatesPath,
} from './templatesApi';

describe('templatesPath', () => {
  it('builds the bare path with no filters', () => {
    expect(templatesPath()).toBe('/v1.0/m8flow/templates');
    expect(templatesPath({})).toBe('/v1.0/m8flow/templates');
  });

  it('translates camelCase filters to the backend\'s snake_case query params', () => {
    expect(
      templatesPath({
        latestOnly: false,
        category: 'finance',
        tag: 'approval',
        owner: 'editor',
        visibility: 'PUBLIC',
        search: 'invoice',
        templateKey: 'invoice-v1',
        publishedOnly: true,
        includeDeleted: true,
        deletedOnly: false,
        sortBy: 'name',
        order: 'asc',
        page: 2,
        perPage: 25,
        tenantId: 't1',
      }),
    ).toBe(
      '/v1.0/m8flow/templates?latest_only=false&category=finance&tag=approval&owner=editor' +
        '&visibility=PUBLIC&search=invoice&template_key=invoice-v1&published_only=true' +
        '&include_deleted=true&deleted_only=false&sort_by=name&order=asc&page=2&per_page=25' +
        '&tenantId=t1',
    );
  });

  it('omits falsy string filters but keeps explicit booleans/numbers', () => {
    expect(templatesPath({ category: '', page: 1, deletedOnly: false })).toBe(
      '/v1.0/m8flow/templates?deleted_only=false&page=1',
    );
  });
});

describe('templatePath', () => {
  it('builds the bare path with no options', () => {
    expect(templatePath(7)).toBe('/v1.0/m8flow/templates/7');
  });

  it('appends include_contents and include_deleted when set', () => {
    expect(templatePath(7, { includeContents: false })).toBe(
      '/v1.0/m8flow/templates/7?include_contents=false',
    );
    expect(templatePath(7, { includeContents: true, includeDeleted: true })).toBe(
      '/v1.0/m8flow/templates/7?include_contents=true&include_deleted=true',
    );
  });
});

describe('templateModelerFilePath', () => {
  it('encodes the file name on the designer modeler route', () => {
    expect(templateModelerFilePath(3, 'task schema.json')).toBe(
      '/templates/3/modeler/task%20schema.json',
    );
  });
});

describe('contentTypeForTemplateFileName', () => {
  it('picks mime from extension', () => {
    expect(contentTypeForTemplateFileName('a.bpmn')).toBe('application/xml');
    expect(contentTypeForTemplateFileName('a.dmn')).toBe('application/xml');
    expect(contentTypeForTemplateFileName('a.json')).toBe('application/json');
    expect(contentTypeForTemplateFileName('a.md')).toBe('text/markdown');
  });
});

describe('templateFileDownloadUrl', () => {
  it('encodes the file name and includes the API base URL', () => {
    // API_BASE_URL is resolved from env/build config (see api.ts), so this
    // asserts against whatever value is live rather than hardcoding one —
    // same reason the module-level export exists in the first place.
    expect(templateFileDownloadUrl(3, 'schema file.json')).toBe(
      `${API_BASE_URL}/v1.0/m8flow/templates/3/files/schema%20file.json`,
    );
  });
});
