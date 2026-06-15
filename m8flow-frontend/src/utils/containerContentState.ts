export type ContainerContentState =
  | 'loading'
  | 'backend-down'
  | 'frontend-access-denied'
  | 'session-expired-recovery'
  | 'routes';

export function resolveContainerContentState({
  backendIsUp,
  canAccessFrontend,
  isLoggedIn,
  pathname,
}: {
  backendIsUp: boolean | null;
  canAccessFrontend: boolean;
  isLoggedIn: boolean;
  pathname: string;
}): ContainerContentState {
  if (backendIsUp === null) {
    return 'loading';
  }

  if (!backendIsUp) {
    return 'backend-down';
  }

  if (!canAccessFrontend) {
    if (!isLoggedIn) {
      return pathname === '/login' ? 'routes' : 'session-expired-recovery';
    }

    return 'frontend-access-denied';
  }

  return 'routes';
}
