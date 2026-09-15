import { describe, expect, it } from 'vitest';

import { FORM_SCHEMA_EXAMPLES, insertExample, mergeFormObjects } from './formSchemaExamples';

describe('mergeFormObjects', () => {
  it('deep-merges nested objects and unions required arrays', () => {
    const merged = mergeFormObjects(
      {
        type: 'object',
        required: ['givenName'],
        properties: { givenName: { type: 'string', title: 'Given name' } },
      },
      {
        required: ['notes'],
        properties: { notes: { type: 'string', title: 'Notes' } },
      },
    );
    expect(merged.required).toEqual(['givenName', 'notes']);
    expect(merged.properties).toEqual({
      givenName: { type: 'string', title: 'Given name' },
      notes: { type: 'string', title: 'Notes' },
    });
  });
});

describe('insertExample', () => {
  it('merges an example into existing schema, UI, and data JSON', () => {
    const text = FORM_SCHEMA_EXAMPLES.find((item) => item.id === 'text');
    if (!text) throw new Error('expected text example');
    const next = insertExample(
      {
        schema: '{"type":"object","properties":{}}',
        ui: '{}',
        data: '{}',
      },
      text,
    );
    expect(JSON.parse(next.schema).properties.givenName.title).toBe('Given name');
    expect(JSON.parse(next.ui).givenName['ui:placeholder']).toBe('Enter a given name');
    expect(JSON.parse(next.data)).toEqual({});
  });
});
