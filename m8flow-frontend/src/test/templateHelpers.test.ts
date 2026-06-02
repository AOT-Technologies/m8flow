import { describe, it, expect } from 'vitest';
import { normalizeTemplate, sortFilesWithPrimaryFirst } from '../utils/templateHelpers';

describe('normalizeTemplate', () => {
  const baseRaw = {
    id: 1,
    templateKey: 'test-key',
    version: 'V1',
    name: 'Test Template',
    description: null,
    tags: null,
    category: null,
    tenantId: null,
    visibility: 'PRIVATE',
    isPublished: false,
    status: null,
    createdBy: 'user1',
    modifiedBy: 'user1',
  };

  it('should preserve existing epoch seconds when present', () => {
    const raw = {
      ...baseRaw,
      createdAtInSeconds: 1700000000,
      updatedAtInSeconds: 1700001000,
    };
    const result = normalizeTemplate(raw);
    expect(result.createdAtInSeconds).toBe(1700000000);
    expect(result.updatedAtInSeconds).toBe(1700001000);
  });

  it('should derive epoch seconds from ISO date strings when seconds are missing', () => {
    const raw = {
      ...baseRaw,
      createdAt: '2024-01-15T12:00:00Z',
      updatedAt: '2024-01-16T12:00:00Z',
    };
    const result = normalizeTemplate(raw);
    expect(result.createdAtInSeconds).toBe(Math.floor(Date.parse('2024-01-15T12:00:00Z') / 1000));
    expect(result.updatedAtInSeconds).toBe(Math.floor(Date.parse('2024-01-16T12:00:00Z') / 1000));
  });

  it('should default to 0 when neither seconds nor ISO strings are present', () => {
    const result = normalizeTemplate({ ...baseRaw });
    expect(result.createdAtInSeconds).toBe(0);
    expect(result.updatedAtInSeconds).toBe(0);
  });

  it('should prefer seconds over ISO strings when both exist', () => {
    const raw = {
      ...baseRaw,
      createdAtInSeconds: 1700000000,
      createdAt: '2024-01-15T12:00:00Z',
      updatedAtInSeconds: 1700001000,
      updatedAt: '2024-01-16T12:00:00Z',
    };
    const result = normalizeTemplate(raw);
    expect(result.createdAtInSeconds).toBe(1700000000);
    expect(result.updatedAtInSeconds).toBe(1700001000);
  });

  it('should normalize files array to empty array when null or missing', () => {
    const result = normalizeTemplate({ ...baseRaw });
    expect(result.files).toEqual([]);
  });

  it('should preserve files array when present', () => {
    const files = [{ fileType: 'bpmn', fileName: 'test.bpmn' }];
    const raw = { ...baseRaw, files };
    const result = normalizeTemplate(raw);
    expect(result.files).toEqual(files);
  });

  it('should preserve all template scalar fields', () => {
    const raw = {
      ...baseRaw,
      description: 'A test description',
      tags: ['tag1', 'tag2'],
      category: 'Testing',
      tenantId: 'tenant-1',
      visibility: 'PUBLIC',
      isPublished: true,
      status: 'active',
      createdAtInSeconds: 1000,
      updatedAtInSeconds: 2000,
    };
    const result = normalizeTemplate(raw);
    expect(result.id).toBe(1);
    expect(result.templateKey).toBe('test-key');
    expect(result.version).toBe('V1');
    expect(result.name).toBe('Test Template');
    expect(result.description).toBe('A test description');
    expect(result.tags).toEqual(['tag1', 'tag2']);
    expect(result.category).toBe('Testing');
    expect(result.tenantId).toBe('tenant-1');
    expect(result.visibility).toBe('PUBLIC');
    expect(result.isPublished).toBe(true);
    expect(result.status).toBe('active');
    expect(result.createdBy).toBe('user1');
    expect(result.modifiedBy).toBe('user1');
  });

  it('should handle NaN seconds gracefully (falls back to ISO or 0)', () => {
    const raw = {
      ...baseRaw,
      createdAtInSeconds: NaN,
      updatedAtInSeconds: NaN,
      createdAt: '2024-06-01T00:00:00Z',
    };
    const result = normalizeTemplate(raw);
    // NaN is not a valid number, so it should fall back to ISO
    expect(result.createdAtInSeconds).toBe(Math.floor(Date.parse('2024-06-01T00:00:00Z') / 1000));
    // No ISO string for updatedAt, should be 0
    expect(result.updatedAtInSeconds).toBe(0);
  });
});

describe('sortFilesWithPrimaryFirst', () => {
  it('should move the primary file to the front', () => {
    const files = [
      { name: 'schema.json' },
      { name: 'main.bpmn' },
      { name: 'readme.md' },
    ];
    const sorted = sortFilesWithPrimaryFirst(files, 'main.bpmn');
    expect(sorted[0].name).toBe('main.bpmn');
    expect(sorted.length).toBe(3);
  });

  it('should preserve relative order of non-primary files', () => {
    const files = [
      { name: 'b.json' },
      { name: 'a.bpmn' },
      { name: 'c.md' },
    ];
    const sorted = sortFilesWithPrimaryFirst(files, 'a.bpmn');
    expect(sorted.map((f) => f.name)).toEqual(['a.bpmn', 'b.json', 'c.md']);
  });

  it('should return unchanged array when primaryFileName is empty', () => {
    const files = [{ name: 'b.json' }, { name: 'a.bpmn' }];
    const sorted = sortFilesWithPrimaryFirst(files, '');
    expect(sorted).toEqual(files);
  });

  it('should return unchanged array when primary file is not found', () => {
    const files = [{ name: 'b.json' }, { name: 'a.bpmn' }];
    const sorted = sortFilesWithPrimaryFirst(files, 'nonexistent.bpmn');
    expect(sorted.map((f) => f.name)).toEqual(['b.json', 'a.bpmn']);
  });

  it('should not mutate the original array', () => {
    const files = [{ name: 'b.json' }, { name: 'a.bpmn' }];
    const original = [...files];
    sortFilesWithPrimaryFirst(files, 'a.bpmn');
    expect(files).toEqual(original);
  });

  it('should handle single-element array', () => {
    const files = [{ name: 'only.bpmn' }];
    const sorted = sortFilesWithPrimaryFirst(files, 'only.bpmn');
    expect(sorted).toEqual([{ name: 'only.bpmn' }]);
  });

  it('should handle empty array', () => {
    const sorted = sortFilesWithPrimaryFirst([], 'any.bpmn');
    expect(sorted).toEqual([]);
  });
});
