import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import APIErrorProvider from '@spiffworkflow-frontend/contexts/APIErrorContext';

const { makeCallToBackend } = vi.hoisted(() => ({
  makeCallToBackend: vi.fn(),
}));

vi.mock('@spiffworkflow-frontend/services/HttpService', () => ({
  default: {
    makeCallToBackend,
  },
}));

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    initReactI18next: {
      type: '3rdParty',
      init: () => undefined,
    },
    useTranslation: () => ({
      t: (key: string) => key,
    }),
  };
});

vi.mock('@spiffworkflow-frontend/views/TaskShow/TaskShow', async () => {
  const React = await import('react');
  const { default: useAPIError } = await import(
    '@spiffworkflow-frontend/hooks/UseApiError'
  );

  return {
    default: function MockTaskShow() {
      const { addError } = useAPIError();

      return React.createElement(
        'button',
        {
          type: 'button',
          onClick: () =>
            addError({
              message: 'Unable to locate a secret with the name: SMTP_HOST.',
            }),
        },
        'trigger task error',
      );
    },
  };
});

import ExternalFormAwareTaskShow from './ExternalFormAwareTaskShow';

describe('ExternalFormAwareTaskShow', () => {
  beforeEach(() => {
    makeCallToBackend.mockReset();
    makeCallToBackend.mockImplementation(({ successCallback }: any) => {
      successCallback({
        task_definition_properties_json: {},
      });
    });
  });

  it('renders the shared error banner for task submit failures on the task route', async () => {
    render(
      <APIErrorProvider>
        <MemoryRouter initialEntries={['/tasks/1/task-guid-1']}>
          <Routes>
            <Route
              path="/tasks/:process_instance_id/:task_guid"
              element={<ExternalFormAwareTaskShow />}
            />
          </Routes>
        </MemoryRouter>
      </APIErrorProvider>,
    );

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'trigger task error' }),
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'trigger task error' }));

    await waitFor(() => {
      expect(
        screen.getByText('Unable to locate a secret with the name: SMTP_HOST.'),
      ).toBeInTheDocument();
    });
  });
});
