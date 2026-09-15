import { describe, expect, it } from 'vitest';

import {
  decodeProcessModelId,
  encodeProcessModelId,
  slugifyProcessModelId,
} from './processModelId';

describe('processModelId', () => {
  it('encodes path segments with colon', () => {
    expect(encodeProcessModelId('finance/invoice-approval')).toBe(
      'finance:invoice-approval',
    );
  });

  it('decodes colon back to slash', () => {
    expect(decodeProcessModelId('finance:invoice-approval')).toBe(
      'finance/invoice-approval',
    );
  });
});

describe('slugifyProcessModelId', () => {
  it('slugifies a display name the way the create API does', () => {
    expect(slugifyProcessModelId('Invoice Approval')).toBe('invoice-approval');
    expect(slugifyProcessModelId('  Expense Report  ')).toBe('expense-report');
    expect(slugifyProcessModelId('my_template')).toBe('my_template');
    expect(slugifyProcessModelId('a--b--c')).toBe('a-b-c');
    expect(slugifyProcessModelId('test@#$%')).toBe('test');
    expect(slugifyProcessModelId('!!!')).toBe('');
  });
});
