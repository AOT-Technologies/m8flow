import { describe, expect, it } from 'vitest';

import {
  HTTP_PROFILE_FIELD_IDS,
  PROFILE_PARAMETER_ID,
  blankSuppliedParameters,
  connectorTypeForOperator,
  createProfileMemory,
  hiddenParameterIds,
  displayStringParameter,
  quoteProfileName,
  quoteStringParameterIfLiteral,
  selectedProfileName,
  unquoteProfileName,
  visibleParameterItems,
  writeProfileParameter,
} from '../lib/features/connectorProfileBinding';

function fakeModdle() {
  return {
    create(type: string) {
      if (type === 'spiffworkflow:Parameters') {
        return { parameters: [] as { id: string; type?: string; value?: string }[] };
      }
      return { id: '', type: 'any', value: '' };
    },
  };
}

function httpOperator(parameters: { id: string; value?: string }[] = []) {
  return {
    id: 'http/GetRequestV2',
    parameterList: { parameters },
  };
}

describe('connectorTypeForOperator', () => {
  it('takes the prefix before the slash', () => {
    expect(connectorTypeForOperator('http/GetRequestV2')).toBe('http');
    expect(connectorTypeForOperator('http')).toBe('http');
    expect(connectorTypeForOperator('')).toBe('');
  });
});

describe('quoteProfileName', () => {
  it('round-trips a literal name as a Python string expression', () => {
    expect(quoteProfileName('http-prod')).toBe('"http-prod"');
    expect(unquoteProfileName('"http-prod"')).toBe('http-prod');
    expect(unquoteProfileName('not-json')).toBe('');
    expect(unquoteProfileName(undefined)).toBe('');
  });
});

describe('quoteStringParameterIfLiteral', () => {
  it('quotes an unquoted URL and leaves Python names alone', () => {
    expect(quoteStringParameterIfLiteral('https://example.test/hook')).toBe(
      '"https://example.test/hook"',
    );
    expect(quoteStringParameterIfLiteral('"https://example.test/hook"')).toBe(
      '"https://example.test/hook"',
    );
    expect(quoteStringParameterIfLiteral('decision')).toBe('decision');
    expect(displayStringParameter('"https://example.test/hook"')).toBe(
      'https://example.test/hook',
    );
  });
});

describe('writeProfileParameter', () => {
  it('writes a quoted m8flow_profile and clears it on empty', () => {
    const operator = httpOperator([{ id: 'url', value: '"https://example.com"' }]);
    const moddle = fakeModdle();
    writeProfileParameter(operator, moddle, 'http-prod');
    expect(selectedProfileName(operator)).toBe('http-prod');
    expect(operator.parameterList.parameters.some((p) => p.id === PROFILE_PARAMETER_ID)).toBe(true);

    writeProfileParameter(operator, moddle, '');
    expect(selectedProfileName(operator)).toBe('');
    expect(operator.parameterList.parameters.some((p) => p.id === PROFILE_PARAMETER_ID)).toBe(false);
    expect(operator.parameterList.parameters.find((p) => p.id === 'url')?.value).toBe(
      '"https://example.com"',
    );
  });
});

describe('hiddenParameterIds / visibleParameterItems', () => {
  it('always hides m8flow_profile and hides basic-auth when a profile is set', () => {
    const withProfile = hiddenParameterIds(true);
    expect(withProfile.has(PROFILE_PARAMETER_ID)).toBe(true);
    expect(withProfile.has('basic_auth_username')).toBe(true);
    expect(withProfile.has('basic_auth_password')).toBe(true);
    expect(withProfile.has('url')).toBe(false);

    const without = hiddenParameterIds(false);
    expect(without.has(PROFILE_PARAMETER_ID)).toBe(true);
    expect(without.has('basic_auth_username')).toBe(false);

    const items = [
      { label: 'url' },
      { label: 'basic_auth_username' },
      { label: 'basic_auth_password' },
      { label: PROFILE_PARAMETER_ID },
    ];
    expect(visibleParameterItems(items, withProfile).map((item) => item.label)).toEqual(['url']);
    expect(HTTP_PROFILE_FIELD_IDS).toEqual(['basic_auth_username', 'basic_auth_password']);
  });
});

describe('blankSuppliedParameters', () => {
  it('clears profile-supplied values but keeps the parameter elements', () => {
    const operator = httpOperator([
      { id: 'url', value: '"https://example.com"' },
      { id: 'basic_auth_username', value: '"left-in-diagram"' },
      { id: 'basic_auth_password', value: '"secret"' },
    ]);
    blankSuppliedParameters(operator, HTTP_PROFILE_FIELD_IDS);
    expect(operator.parameterList.parameters.find((p) => p.id === 'url')?.value).toBe(
      '"https://example.com"',
    );
    expect(operator.parameterList.parameters.find((p) => p.id === 'basic_auth_username')?.value).toBe(
      undefined,
    );
    expect(operator.parameterList.parameters.find((p) => p.id === 'basic_auth_password')?.value).toBe(
      undefined,
    );
  });
});

describe('createProfileMemory', () => {
  it('restores the profile when the operator stays in the same family', () => {
    const memory = createProfileMemory();
    const moddle = fakeModdle();
    const first = httpOperator();
    writeProfileParameter(first, moddle, 'http-prod');
    memory.remember('Task_1', 'http', 'http-prod');

    const rebuilt = httpOperator([{ id: 'url', value: '""' }]);
    const restored = memory.reconcile('Task_1', rebuilt, 'http', moddle, HTTP_PROFILE_FIELD_IDS);
    expect(restored).toBe('http-prod');
    expect(selectedProfileName(rebuilt)).toBe('http-prod');
  });

  it('drops the profile when the operator moves to another family', () => {
    const memory = createProfileMemory();
    const moddle = fakeModdle();
    memory.remember('Task_1', 'http', 'http-prod');
    const other = { id: 'smtp/Send', parameterList: { parameters: [] as { id: string }[] } };
    expect(memory.reconcile('Task_1', other, 'smtp', moddle, [])).toBe('');
    expect(selectedProfileName(other)).toBe('');
  });
});
