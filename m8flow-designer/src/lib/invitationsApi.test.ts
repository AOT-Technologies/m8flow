import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from './api';
import { acceptInvitation, invitationErrorMessage, validateInvitation } from './invitationsApi';

const makeResponse = ({
  ok,
  status,
  body,
}: {
  ok: boolean;
  status: number;
  body?: unknown;
}) => ({
  ok,
  status,
  json: vi.fn().mockResolvedValue(body ?? {}),
  clone: vi.fn().mockReturnThis(),
});

describe('invitationsApi', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it('validates a token without sending a bearer token', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      makeResponse({
        ok: true,
        status: 200,
        body: {
          email: 'user@example.com',
          tenant_id: 't1',
          tenant_name: 'Acme',
          roles: ['editor'],
          expires_at_in_seconds: 1,
        },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await validateInvitation('raw-token');

    expect(result.email).toBe('user@example.com');
    expect(fetchMock.mock.calls[0][0]).toEqual(
      expect.stringContaining('/v1.0/m8flow/invitations/validate?token=raw-token'),
    );
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).get('Authorization')).toBeNull();
  });

  it('posts accept with token and password', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      makeResponse({ ok: true, status: 200, body: { email: 'user@example.com' } }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await acceptInvitation('raw-token', 'password123');

    expect(fetchMock.mock.calls[0][0]).toEqual(
      expect.stringContaining('/v1.0/m8flow/invitations/accept'),
    );
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ token: 'raw-token', password: 'password123' }),
      }),
    );
  });

  it('surfaces the backend message on failure', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      makeResponse({
        ok: false,
        status: 410,
        body: { error_code: 'invitation_expired', message: 'This invitation link has expired.' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(validateInvitation('expired')).rejects.toMatchObject({
      status: 410,
      serverMessage: 'This invitation link has expired.',
    });
  });

  it('prefers ApiError.serverMessage for display', () => {
    const error = new ApiError('/x', 410, 'GET', 'This invitation link has expired.');
    expect(invitationErrorMessage(error, 'fallback')).toBe('This invitation link has expired.');
  });
});
