import { describe, expect, it } from 'vitest';

import { buildArguments, FIELD_REQUIRED, INVALID_JSON, INVALID_NUMBER } from './mcpToolArgs';

const p = (name: string, type: string, required = false) => ({ name, type, required, description: '' });

describe('buildArguments', () => {
  it('coerces each JSON-Schema type and omits blank optionals', () => {
    expect(
      buildArguments(
        [
          p('id', 'integer', true),
          p('ratio', 'number'),
          p('flag', 'boolean'),
          p('data', 'object'),
          p('tags', 'array'),
          p('name', 'string'),
          p('skip', 'string'),
        ],
        { id: ' 42 ', ratio: '0.5', flag: 'false', data: '{"a":1}', tags: '["x"]', name: 'demo', skip: '  ' },
      ),
    ).toEqual({ ok: true, args: { id: 42, ratio: 0.5, flag: false, data: { a: 1 }, tags: ['x'], name: 'demo' } });
  });

  it('reports required, number and JSON errors per field', () => {
    expect(
      buildArguments([p('id', 'integer', true), p('n', 'integer'), p('data', 'object')], { n: '1.5', data: '{oops' }),
    ).toEqual({ ok: false, errors: { id: FIELD_REQUIRED, n: INVALID_NUMBER, data: INVALID_JSON } });
  });
});
