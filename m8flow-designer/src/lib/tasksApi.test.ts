import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./api', () => ({
  apiGet: vi.fn(),
  apiFetch: vi.fn(),
}));

import { apiFetch, apiGet } from './api';
import {
  fetchTaskReviewDetail,
  fetchTaskReviewList,
  submitTaskReview,
  taskReviewDetailPath,
  taskReviewListPath,
  taskReviewSubmitPath,
} from './tasksApi';

const mockApiGet = apiGet as unknown as ReturnType<typeof vi.fn>;
const mockApiFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});

describe('taskReviewListPath', () => {
  it('builds the bare path with no filters', () => {
    expect(taskReviewListPath()).toBe('/v1.0/m8flow/task-review');
    expect(taskReviewListPath({})).toBe('/v1.0/m8flow/task-review');
  });

  it('appends page / per_page / tenantId', () => {
    expect(taskReviewListPath({ page: 2, perPage: 20, tenantId: 't1' })).toBe(
      '/v1.0/m8flow/task-review?page=2&per_page=20&tenantId=t1',
    );
  });

  it('omits unset filters and a null tenantId', () => {
    expect(taskReviewListPath({ page: 1, tenantId: null })).toBe(
      '/v1.0/m8flow/task-review?page=1',
    );
  });
});

describe('detail + submit paths', () => {
  it('builds the detail path (no tenant query — cookie-scoped)', () => {
    expect(taskReviewDetailPath(42)).toBe('/v1.0/m8flow/task-review/42');
  });

  it('builds the submit path', () => {
    expect(taskReviewSubmitPath(42)).toBe('/v1.0/m8flow/task-review/42/submit');
  });
});

describe('fetchTaskReviewList', () => {
  it('calls apiGet with the filtered path and returns the payload', async () => {
    const payload = { results: [], pagination: { page: 1, per_page: 20, total: 0 } };
    mockApiGet.mockResolvedValue(payload);
    const out = await fetchTaskReviewList({ page: 1, perPage: 20 });
    expect(mockApiGet).toHaveBeenCalledWith('/v1.0/m8flow/task-review?page=1&per_page=20');
    expect(out).toBe(payload);
  });
});

describe('fetchTaskReviewDetail', () => {
  it('calls apiGet with the detail path', async () => {
    mockApiGet.mockResolvedValue({ task: { id: 42 } });
    await fetchTaskReviewDetail(42);
    expect(mockApiGet).toHaveBeenCalledWith('/v1.0/m8flow/task-review/42');
  });
});

describe('submitTaskReview', () => {
  it('POSTs the JSON payload and returns the parsed response', async () => {
    const response = {
      process_instance_id: 210,
      process_status: 'user_input_required',
      process_complete: false,
      message: 'Task completed. The process has advanced to the next step.',
    };
    mockApiFetch.mockResolvedValue({ json: async () => response });
    const out = await submitTaskReview(42, {
      outcome: 'approve',
      wfh_date: '2026-09-01',
      reason: 'Focus time',
    });
    expect(mockApiFetch).toHaveBeenCalledWith('/v1.0/m8flow/task-review/42/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ outcome: 'approve', wfh_date: '2026-09-01', reason: 'Focus time' }),
    });
    expect(out).toEqual(response);
  });

  it('sends an empty object body when no payload is given', async () => {
    mockApiFetch.mockResolvedValue({
      json: async () => ({
        process_instance_id: 7,
        process_status: 'complete',
        process_complete: true,
        message: 'Task completed. The process is now complete.',
      }),
    });
    await submitTaskReview(7);
    expect(mockApiFetch).toHaveBeenCalledWith('/v1.0/m8flow/task-review/7/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
  });
});
