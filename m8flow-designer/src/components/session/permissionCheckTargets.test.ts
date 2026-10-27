import { describe, expect, it } from 'vitest';

import { buildPermissionCheckRequest, hasPermission } from './permissionCheckTargets';

describe('permission check targets', () => {
  it('groups operation targets into the request shape expected by permissions-check', () => {
    const request = buildPermissionCheckRequest();

    expect(request['/process-models']).toEqual(['GET', 'POST', 'PUT']);
    expect(request['/m8flow/templates/{id}']).toEqual(['PUT', 'DELETE']);
    expect(request['/m8flow/tenants/{id}/groups/{group}/members/{username}']).toEqual(['PUT', 'DELETE']);
    expect(request['/m8flow/task-review-access']).toEqual(['GET']);
    expect(request['/m8flow/task-review-access/{id}/submit']).toEqual(['POST']);
    expect(request['/m8flow/home-task-count']).toEqual(['GET']);
    expect(request).not.toHaveProperty('/tasks');
  });

  it('derives version history capabilities from the echoed templated URIs', () => {
    const request = buildPermissionCheckRequest();
    expect(request['/process-models/{id}/versions']).toEqual(['GET']);
    expect(request['/process-models/{id}/versions/{version}/revert']).toEqual(['POST']);

    const granted = {
      '/process-models/{id}/versions': { GET: true },
      '/process-models/{id}/versions/{version}/revert': { POST: false },
    };
    expect(hasPermission(granted, 'readProcessModelVersions')).toBe(true);
    expect(hasPermission(granted, 'revertProcessModelVersions')).toBe(false);
  });

  it('reads a named permission from the matching URI and method', () => {
    expect(hasPermission({ '/process-models': { PUT: true } }, 'updateProcessModels')).toBe(true);
    expect(hasPermission({ '/process-models': { POST: true } }, 'updateProcessModels')).toBe(false);
    expect(hasPermission({}, 'updateProcessModels')).toBe(false);
  });
});
