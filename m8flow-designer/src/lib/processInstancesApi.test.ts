import { describe, expect, it } from 'vitest';

import {
  processInstanceCompletableTasksPath,
  processInstanceCompletedTasksPath,
  processInstanceDetailPath,
  processInstanceEventsPath,
  processInstanceLifecyclePath,
  processInstanceMilestonesPath,
  processInstanceOwnersPath,
  processInstancesPath,
} from './processInstancesApi';

describe('processInstancesPath', () => {
  it('builds the bare path with no filters', () => {
    expect(processInstancesPath()).toBe('/v1.0/m8flow/process-instances');
    expect(processInstancesPath({})).toBe('/v1.0/m8flow/process-instances');
  });

  it('appends filters in declaration order', () => {
    expect(
      processInstancesPath({ status: 'error', search: 'invoice', page: 2, perPage: 10, tenantId: 't1' }),
    ).toBe('/v1.0/m8flow/process-instances?status=error&search=invoice&page=2&per_page=10&tenantId=t1');
  });

  it('omits unset filters', () => {
    expect(processInstancesPath({ status: 'running' })).toBe(
      '/v1.0/m8flow/process-instances?status=running',
    );
  });

  it('appends started_by and sort params', () => {
    expect(processInstancesPath({ startedBy: 'amir', sort: 'oldest' })).toBe(
      '/v1.0/m8flow/process-instances?started_by=amir&sort=oldest',
    );
  });
});

describe('processInstanceOwnersPath', () => {
  it('builds the bare owners path with no tenant', () => {
    expect(processInstanceOwnersPath()).toBe('/v1.0/m8flow/process-instances/owners');
  });

  it('appends tenantId when set', () => {
    expect(processInstanceOwnersPath('t1')).toBe(
      '/v1.0/m8flow/process-instances/owners?tenantId=t1',
    );
  });
});

describe('processInstanceDetailPath', () => {
  it('builds the bare path with no tenant', () => {
    expect(processInstanceDetailPath(7)).toBe('/v1.0/m8flow/process-instances/7');
  });

  it('appends tenantId when set', () => {
    expect(processInstanceDetailPath(7, 't1')).toBe('/v1.0/m8flow/process-instances/7?tenantId=t1');
  });
});

describe('processInstanceEventsPath', () => {
  it('builds the bare events path with no tenant', () => {
    expect(processInstanceEventsPath(7)).toBe('/v1.0/m8flow/process-instances/7/events');
  });

  it('appends tenantId when set', () => {
    expect(processInstanceEventsPath(7, 't1')).toBe(
      '/v1.0/m8flow/process-instances/7/events?tenantId=t1',
    );
  });
});

describe('processInstanceMilestonesPath', () => {
  it('builds the bare milestones path with no tenant', () => {
    expect(processInstanceMilestonesPath(7)).toBe('/v1.0/m8flow/process-instances/7/milestones');
  });

  it('appends tenantId when set', () => {
    expect(processInstanceMilestonesPath(7, 't1')).toBe(
      '/v1.0/m8flow/process-instances/7/milestones?tenantId=t1',
    );
  });
});

describe('processInstanceCompletableTasksPath', () => {
  it('builds the bare completable-tasks path with no tenant', () => {
    expect(processInstanceCompletableTasksPath(7)).toBe(
      '/v1.0/m8flow/process-instances/7/completable-tasks',
    );
  });

  it('appends tenantId when set', () => {
    expect(processInstanceCompletableTasksPath(7, 't1')).toBe(
      '/v1.0/m8flow/process-instances/7/completable-tasks?tenantId=t1',
    );
  });
});

describe('processInstanceCompletedTasksPath', () => {
  it('builds the bare completed-tasks path with no tenant', () => {
    expect(processInstanceCompletedTasksPath(7)).toBe(
      '/v1.0/m8flow/process-instances/7/completed-tasks',
    );
  });

  it('appends tenantId when set', () => {
    expect(processInstanceCompletedTasksPath(7, 't1')).toBe(
      '/v1.0/m8flow/process-instances/7/completed-tasks?tenantId=t1',
    );
  });
});

describe('processInstanceLifecyclePath', () => {
  it('builds suspend, resume, and terminate paths', () => {
    expect(processInstanceLifecyclePath(7, 'suspend')).toBe(
      '/v1.0/m8flow/process-instances/7/suspend',
    );
    expect(processInstanceLifecyclePath(7, 'resume', 't1')).toBe(
      '/v1.0/m8flow/process-instances/7/resume?tenantId=t1',
    );
    expect(processInstanceLifecyclePath(7, 'terminate')).toBe(
      '/v1.0/m8flow/process-instances/7/terminate',
    );
  });
});
