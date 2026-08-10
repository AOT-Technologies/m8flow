import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import APIErrorProvider from '@spiffworkflow-frontend/contexts/APIErrorContext';
import ErrorDisplay from '@spiffworkflow-frontend/components/ErrorDisplay';
import useAPIError from '@spiffworkflow-frontend/hooks/UseApiError';

import HttpService from '../services/HttpService';

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

const makeResponse = ({
  body,
  ok,
  status,
  statusText = '',
}: {
  body: string;
  ok: boolean;
  status: number;
  statusText?: string;
}) => ({
  ok,
  status,
  statusText,
  text: vi.fn().mockResolvedValue(body),
});

function SubmitHarness() {
  const { addError } = useAPIError();

  return (
    <button
      type="button"
      onClick={() => {
        HttpService.makeCallToBackend({
          path: '/tasks/123/task-guid-1',
          httpMethod: 'PUT',
          postBody: { approved: true },
          successCallback: vi.fn(),
          failureCallback: (error: unknown) => addError(error),
        });
      }}
    >
      submit
    </button>
  );
}

describe('Vault error display', () => {
  it('renders a missing-secret error message in the shared UI error banner', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        makeResponse({
          body: JSON.stringify({
            type: 'about:blank',
            title: 'vault_secret_value_missing',
            detail: 'Unable to locate the Vault secret value for key: SMTP_USER.',
            status: 404,
            error_code: 'vault_secret_value_missing',
          }),
          ok: false,
          status: 404,
          statusText: 'Not Found',
        }),
      ),
    );

    render(
      <APIErrorProvider>
        <SubmitHarness />
        <ErrorDisplay />
      </APIErrorProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'submit' }));

    await waitFor(() => {
      expect(
        screen.getByText('Unable to locate the Vault secret value for key: SMTP_USER.'),
      ).toBeInTheDocument();
    });
  });
});
