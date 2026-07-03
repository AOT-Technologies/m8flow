import { describe, expect, it } from 'vitest';
import type { ConnectorConfigField } from '../components/ConnectorOperationsModal';
import { validateConnectorField } from './connectorFieldValidation';

// Identity translator: returns the key (with min/max appended) so assertions can
// match on the message key without pulling in i18n.
const t = (key: string, opts?: Record<string, unknown>) =>
  opts ? `${key}:${JSON.stringify(opts)}` : key;

const field = (over: Partial<ConnectorConfigField> = {}): ConnectorConfigField => ({
  id: 'f',
  label: 'F',
  type: 'text',
  required: false,
  ...over,
});

describe('validateConnectorField', () => {
  it('flags whitespace-only input', () => {
    expect(validateConnectorField(field(), '   ', false, t)).toBe(
      'connector_config_whitespace_only',
    );
  });

  it('flags a required, unset, empty field', () => {
    expect(
      validateConnectorField(field({ required: true }), '', false, t),
    ).toBe('connector_config_required_field');
  });

  it('allows empty when the secret is already set', () => {
    expect(
      validateConnectorField(field({ required: true }), '', true, t),
    ).toBeUndefined();
  });

  it('allows empty for an optional field', () => {
    expect(validateConnectorField(field(), '', false, t)).toBeUndefined();
  });

  it('enforces minLength on the trimmed value', () => {
    expect(
      validateConnectorField(field({ minLength: 5 }), '  ab  ', false, t),
    ).toBe('connector_config_min_length:{"min":5}');
  });

  it('enforces maxLength on the trimmed value', () => {
    expect(
      validateConnectorField(field({ maxLength: 3 }), 'abcd', false, t),
    ).toBe('connector_config_max_length:{"max":3}');
  });

  describe('url format', () => {
    const f = field({ format: 'url' });
    it('accepts http/https URLs', () => {
      expect(validateConnectorField(f, 'https://x.example.com', false, t)).toBeUndefined();
    });
    it('rejects a bare host', () => {
      expect(validateConnectorField(f, 'x.example.com', false, t)).toBe(
        'connector_config_invalid_url',
      );
    });
  });

  describe('email format', () => {
    const f = field({ format: 'email' });
    it('accepts a valid address', () => {
      expect(validateConnectorField(f, 'a@b.co', false, t)).toBeUndefined();
    });
    it('rejects a malformed address', () => {
      expect(validateConnectorField(f, 'a@b', false, t)).toBe(
        'connector_config_invalid_email',
      );
    });
  });

  describe('port format', () => {
    const f = field({ format: 'port' });
    it('accepts a valid port', () => {
      expect(validateConnectorField(f, '587', false, t)).toBeUndefined();
    });
    it('rejects 0 and out-of-range', () => {
      expect(validateConnectorField(f, '0', false, t)).toBe('connector_config_invalid_port');
      expect(validateConnectorField(f, '70000', false, t)).toBe(
        'connector_config_invalid_port',
      );
    });
    it('rejects non-numeric', () => {
      expect(validateConnectorField(f, '25a', false, t)).toBe(
        'connector_config_invalid_port',
      );
    });
  });

  describe('number format', () => {
    const f = field({ format: 'number' });
    it('accepts a number', () => {
      expect(validateConnectorField(f, '42', false, t)).toBeUndefined();
    });
    it('rejects non-numeric', () => {
      expect(validateConnectorField(f, 'abc', false, t)).toBe(
        'connector_config_invalid_number',
      );
    });
  });
});
