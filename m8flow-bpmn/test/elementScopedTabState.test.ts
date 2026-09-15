import { describe, expect, it, vi } from 'vitest';
import { createElementScopedTabStore } from '../lib/features/elementScopedTabState';

describe('createElementScopedTabStore', () => {
  it('returns the default tab for an element with no recorded selection', () => {
    const store = createElementScopedTabStore<'action' | 'config'>('action');
    expect(store.getActiveTab('Task_1')).toBe('action');
  });

  it('tracks the active tab per element id independently', () => {
    const store = createElementScopedTabStore<'action' | 'config'>('action');
    store.setActiveTab('Task_1', 'config');
    expect(store.getActiveTab('Task_1')).toBe('config');
    expect(store.getActiveTab('Task_2')).toBe('action');
  });

  it('notifies every subscribed listener on a tab change', () => {
    const store = createElementScopedTabStore<'action' | 'config'>('action');
    const listenerA = vi.fn();
    const listenerB = vi.fn();
    store.subscribe(listenerA);
    store.subscribe(listenerB);

    store.setActiveTab('Task_1', 'config');

    expect(listenerA).toHaveBeenCalledTimes(1);
    expect(listenerB).toHaveBeenCalledTimes(1);
  });

  it('stops notifying a listener once it unsubscribes', () => {
    const store = createElementScopedTabStore<'action' | 'config'>('action');
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);

    unsubscribe();
    store.setActiveTab('Task_1', 'config');

    expect(listener).not.toHaveBeenCalled();
  });
});
