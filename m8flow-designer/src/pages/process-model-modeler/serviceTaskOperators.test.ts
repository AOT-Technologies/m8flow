import { describe, expect, it } from 'vitest';

import type { ConnectorGroup } from '@/lib/api';
import { flattenConnectorGroupsToOperators } from './serviceTaskOperators';

const HTTP_V2_GROUP: ConnectorGroup = {
  id: 'http',
  name: 'HTTP',
  description: '',
  status: 'ok',
  icon: '',
  operationCount: 6,
  operations: [
    {
      id: 'http/GetRequestV2',
      name: 'Get Request V2',
      rawName: 'GetRequestV2',
      description: '',
      parameters: [
        { id: 'url', type: 'str' },
        { id: 'headers', type: 'any' },
        { id: 'params', type: 'any' },
        { id: 'basic_auth_username', type: 'str' },
        { id: 'basic_auth_password', type: 'str' },
        { id: 'attempts', type: 'int' },
      ],
    },
    {
      id: 'http/HeadRequestV2',
      name: 'Head Request V2',
      rawName: 'HeadRequestV2',
      description: '',
      parameters: [
        { id: 'url', type: 'str' },
        { id: 'headers', type: 'any' },
        { id: 'params', type: 'any' },
        { id: 'basic_auth_username', type: 'str' },
        { id: 'basic_auth_password', type: 'str' },
        { id: 'attempts', type: 'int' },
      ],
    },
    {
      id: 'http/PostRequestV2',
      name: 'Post Request V2',
      rawName: 'PostRequestV2',
      description: '',
      parameters: [
        { id: 'url', type: 'str' },
        { id: 'headers', type: 'any' },
        { id: 'data', type: 'any' },
        { id: 'basic_auth_username', type: 'str' },
        { id: 'basic_auth_password', type: 'str' },
      ],
    },
    {
      id: 'http/PutRequestV2',
      name: 'Put Request V2',
      rawName: 'PutRequestV2',
      description: '',
      parameters: [
        { id: 'url', type: 'str' },
        { id: 'headers', type: 'any' },
        { id: 'data', type: 'any' },
        { id: 'basic_auth_username', type: 'str' },
        { id: 'basic_auth_password', type: 'str' },
      ],
    },
    {
      id: 'http/PatchRequestV2',
      name: 'Patch Request V2',
      rawName: 'PatchRequestV2',
      description: '',
      parameters: [
        { id: 'url', type: 'str' },
        { id: 'headers', type: 'any' },
        { id: 'data', type: 'any' },
        { id: 'basic_auth_username', type: 'str' },
        { id: 'basic_auth_password', type: 'str' },
      ],
    },
    {
      id: 'http/DeleteRequestV2',
      name: 'Delete Request V2',
      rawName: 'DeleteRequestV2',
      description: '',
      parameters: [
        { id: 'url', type: 'str' },
        { id: 'headers', type: 'any' },
        { id: 'params', type: 'any' },
        { id: 'data', type: 'any' },
        { id: 'basic_auth_username', type: 'str' },
        { id: 'basic_auth_password', type: 'str' },
      ],
    },
  ],
};

describe('flattenConnectorGroupsToOperators', () => {
  it('returns an empty list for an empty catalog', () => {
    expect(flattenConnectorGroupsToOperators([])).toEqual([]);
  });

  it('preserves HTTP V2 operator ids and parameter lists for the Parameters tab', () => {
    const operators = flattenConnectorGroupsToOperators([HTTP_V2_GROUP]);
    expect(operators.map((op) => op.id)).toEqual([
      'http/GetRequestV2',
      'http/HeadRequestV2',
      'http/PostRequestV2',
      'http/PutRequestV2',
      'http/PatchRequestV2',
      'http/DeleteRequestV2',
    ]);
    expect(operators[0].parameters).toEqual(
      HTTP_V2_GROUP.operations[0].parameters,
    );
    expect(operators[2].parameters.map((p) => p.id)).toEqual([
      'url',
      'headers',
      'data',
      'basic_auth_username',
      'basic_auth_password',
    ]);
  });

  it('defaults a missing parameters array to empty', () => {
    const groups: ConnectorGroup[] = [
      {
        ...HTTP_V2_GROUP,
        operations: [
          {
            id: 'http/GetRequestV2',
            name: 'Get',
            rawName: 'GetRequestV2',
            description: '',
            parameters: undefined as unknown as [],
          },
        ],
      },
    ];
    expect(flattenConnectorGroupsToOperators(groups)).toEqual([
      { id: 'http/GetRequestV2', parameters: [] },
    ]);
  });
});
