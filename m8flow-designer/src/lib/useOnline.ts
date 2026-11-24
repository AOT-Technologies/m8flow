import { useSyncExternalStore } from 'react';

function subscribe(onChange: () => void) {
  if (typeof window === 'undefined') return () => {};
  window.addEventListener('online', onChange);
  window.addEventListener('offline', onChange);
  return () => {
    window.removeEventListener('online', onChange);
    window.removeEventListener('offline', onChange);
  };
}

function getSnapshot(): boolean {
  return typeof navigator === 'undefined' ? true : navigator.onLine;
}

export function useOnline(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, () => true);
}
