import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/tasksApi', () => ({
  fetchTaskReviewDetail: vi.fn(),
  submitTaskReview: vi.fn(),
}));

import { ApiError } from '@/lib/api';
import { fetchTaskReviewDetail, submitTaskReview, type TaskReviewDetail } from '@/lib/tasksApi';
import TaskReviewDetailPage from './TaskReviewDetailPage';

const mockFetch = fetchTaskReviewDetail as unknown as ReturnType<typeof vi.fn>;
const mockSubmit = submitTaskReview as unknown as ReturnType<typeof vi.fn>;

const NOW = Math.floor(Date.now() / 1000);

function mockDetail(overrides: Partial<TaskReviewDetail> = {}): TaskReviewDetail {
  return {
    task: {
      id: 42,
      task_title: 'Work From Home Request',
      task_name: 'wfh_request',
      task_type: 'User Task',
      status: 'READY',
      completed: false,
      process_model_display_name: 'HR / WFH',
      bpmn_process_identifier: 'hr/wfh',
      submitted_by: 'Priya Nair',
      created_at_in_seconds: NOW - 3600,
    },
    form: {
      schema: {
        type: 'object',
        required: ['wfh_date', 'reason'],
        properties: {
          wfh_date: { type: 'string', format: 'date', title: 'WFH Date' },
          wfh_type: {
            type: 'string',
            title: 'WFH Type',
            enum: ['Full Day', 'Half Day (Morning)'],
            default: 'Full Day',
          },
          reason: { type: 'string', title: 'Reason for WFH', minLength: 10 },
          additional_notes: { type: 'string', title: 'Additional Notes' },
        },
      },
      ui_schema: null,
      values: {},
    },
    outcomes: [
      { value: 'approve', label: 'Approve' },
      { value: 'reject', label: 'Reject' },
    ],
    approval_chain: [
      {
        name: 'Priya Nair',
        status: 'COMPLETED',
        completed: true,
        is_current: false,
        lane_name: 'Submitter',
        completed_at_in_seconds: NOW - 3600,
      },
      {
        name: 'You',
        status: 'READY',
        completed: false,
        is_current: true,
        lane_name: 'Manager',
        completed_at_in_seconds: null,
      },
    ],
    activity: [
      {
        event_type: 'process_instance_created',
        actor_name: 'Priya Nair',
        timestamp: NOW - 3600,
        task_guid: null,
        task_title: null,
      },
      {
        event_type: 'human_task_ready',
        actor_name: null,
        timestamp: NOW - 1800,
        task_guid: 'abc',
        task_title: 'Work From Home Request',
      },
    ],
    instance: {
      id: 210,
      status: 'user_input_required',
      start_in_seconds: NOW - 3600,
      last_milestone_bpmn_name: 'Manager Review',
      detail_path: '/process-instances/210',
    },
    ...overrides,
  };
}

function renderDetail(initial = '/task-review/42') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/task-review/:taskId" element={<TaskReviewDetailPage />} />
        <Route path="/task-review" element={<div>INBOX MARKER</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('TaskReviewDetailPage', () => {
  it('renders editable inputs from the schema (date, enum select, textarea, applied default)', async () => {
    mockFetch.mockResolvedValue(mockDetail());
    renderDetail();

    expect(
      await screen.findByRole('heading', { name: 'Work From Home Request' }),
    ).toBeInTheDocument();
    expect(screen.getByText('HR / WFH')).toBeInTheDocument();

    // date input
    const date = screen.getByLabelText(/WFH Date/i);
    expect(date).toHaveAttribute('type', 'date');

    // enum → native select, with its default applied
    const select = screen.getByLabelText(/WFH Type/i) as HTMLSelectElement;
    expect(select.tagName).toBe('SELECT');
    expect(select.value).toBe('Full Day');
    expect(screen.getByRole('option', { name: 'Half Day (Morning)' })).toBeInTheDocument();

    // "reason" key → textarea (multiline heuristic)
    const reason = screen.getByLabelText(/Reason for WFH/i);
    expect(reason.tagName).toBe('TEXTAREA');

    // old hardcoded comment box is gone
    expect(screen.queryByPlaceholderText(/Add an optional note/)).not.toBeInTheDocument();
  });

  it('submits the entered form values + outcome, then navigates to the inbox', async () => {
    mockFetch.mockResolvedValue(mockDetail());
    mockSubmit.mockResolvedValue({ process_instance_id: 210, status: 'complete' });
    renderDetail();

    await screen.findByRole('heading', { name: 'Work From Home Request' });

    fireEvent.change(screen.getByLabelText(/WFH Date/i), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText(/Reason for WFH/i), {
      target: { value: 'Deep focus work needed at home.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));

    await waitFor(() =>
      expect(mockSubmit).toHaveBeenCalledWith(42, {
        wfh_type: 'Full Day',
        wfh_date: '2026-09-01',
        reason: 'Deep focus work needed at home.',
        outcome: 'approve',
      }),
    );
    expect(await screen.findByText('INBOX MARKER')).toBeInTheDocument();
  });

  it('disables submit when the process instance is suspended', async () => {
    mockFetch.mockResolvedValue(mockDetail({ instance: { ...mockDetail().instance, status: 'suspended' } }));
    renderDetail();

    await screen.findByRole('heading', { name: 'Work From Home Request' });
    expect(
      screen.getByText('This process instance is suspended. Resume it before submitting.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    expect(mockSubmit).not.toHaveBeenCalled();
  });

  it('blocks submit and shows an error when a required field is empty', async () => {
    mockFetch.mockResolvedValue(mockDetail());
    renderDetail();

    await screen.findByRole('heading', { name: 'Work From Home Request' });

    // leave required wfh_date + reason empty
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));

    expect(await screen.findByText(/Reason for WFH is required/i)).toBeInTheDocument();
    expect(mockSubmit).not.toHaveBeenCalled();
  });

  it('renders a single Submit for a linear task and submits values without an outcome', async () => {
    mockFetch.mockResolvedValue(mockDetail({ outcomes: [] }));
    mockSubmit.mockResolvedValue({ process_instance_id: 210, status: 'complete' });
    renderDetail();

    await screen.findByRole('heading', { name: 'Work From Home Request' });

    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/WFH Date/i), { target: { value: '2026-09-02' } });
    fireEvent.change(screen.getByLabelText(/Reason for WFH/i), {
      target: { value: 'Home internet install visit.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));

    await waitFor(() =>
      expect(mockSubmit).toHaveBeenCalledWith(42, {
        wfh_type: 'Full Day',
        wfh_date: '2026-09-02',
        reason: 'Home internet install visit.',
      }),
    );
  });

  it('shows the backend reason when submit fails', async () => {
    mockFetch.mockResolvedValue(mockDetail());
    mockSubmit.mockRejectedValue(
      new ApiError('/v1.0/m8flow/task-review/42/submit', 500, 'POST', 'Error evaluating expression'),
    );
    renderDetail();

    await screen.findByRole('heading', { name: 'Work From Home Request' });
    fireEvent.change(screen.getByLabelText(/WFH Date/i), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText(/Reason for WFH/i), {
      target: { value: 'Deep focus work needed at home.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Error evaluating expression');
  });

  it('renders the approval chain and activity log', async () => {
    mockFetch.mockResolvedValue(mockDetail());
    renderDetail();

    await screen.findByRole('heading', { name: 'Work From Home Request' });

    expect(screen.getByText('Approval chain')).toBeInTheDocument();
    expect(screen.getByText('You')).toBeInTheDocument();
    expect(screen.getAllByText(/Manager/).length).toBeGreaterThan(0);

    expect(screen.getByText('Activity')).toBeInTheDocument();
    expect(screen.getByText('started the process')).toBeInTheDocument();
    expect(screen.getByText('became ready for review')).toBeInTheDocument();
    expect(screen.getByText('System')).toBeInTheDocument();
  });

  it('shows a loading state before data resolves', () => {
    mockFetch.mockReturnValue(new Promise(() => {}));
    renderDetail();
    expect(screen.getByText('Loading task…')).toBeInTheDocument();
  });

  it('shows an error state when the fetch fails', async () => {
    mockFetch.mockRejectedValue(new Error('boom'));
    renderDetail();
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(screen.getByText('boom')).toBeInTheDocument();
  });

  it('shows "not found" for a non-numeric id without fetching', () => {
    renderDetail('/task-review/not-a-number');
    expect(screen.getByText('Task not found.')).toBeInTheDocument();
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
