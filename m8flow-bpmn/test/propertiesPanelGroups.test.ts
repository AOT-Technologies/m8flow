import { describe, expect, it } from 'vitest';
import { insertGroupAfter, removeGroupsById, replaceOrAppendGroup } from '../lib/features/propertiesPanelGroups';

describe('insertGroupAfter', () => {
  it('inserts immediately after the anchor', () => {
    const groups = [{ id: 'a' }, { id: 'anchor' }, { id: 'c' }];
    const result = insertGroupAfter(groups, { id: 'new' }, 'anchor');
    expect(result.map((g) => g.id)).toEqual(['a', 'anchor', 'new', 'c']);
  });

  it('appends when the anchor is missing', () => {
    const groups = [{ id: 'a' }, { id: 'b' }];
    const result = insertGroupAfter(groups, { id: 'new' }, 'no-such-anchor');
    expect(result.map((g) => g.id)).toEqual(['a', 'b', 'new']);
  });

  it('appends to an empty array', () => {
    const result = insertGroupAfter([], { id: 'new' }, 'anchor');
    expect(result.map((g) => g.id)).toEqual(['new']);
  });

  it('mutates and returns the same array instance', () => {
    const groups = [{ id: 'anchor' }];
    const result = insertGroupAfter(groups, { id: 'new' }, 'anchor');
    expect(result).toBe(groups);
  });
});

describe('replaceOrAppendGroup', () => {
  it('replaces an existing group in place, preserving position', () => {
    const groups = [{ id: 'a', label: 'old-a' }, { id: 'target', label: 'old' }, { id: 'c' }];
    const result = replaceOrAppendGroup(groups, { id: 'target', label: 'new' });
    expect(result.map((g) => g.id)).toEqual(['a', 'target', 'c']);
    expect(result[1].label).toBe('new');
  });

  it('appends when no group with that id exists yet', () => {
    const groups = [{ id: 'a' }];
    const result = replaceOrAppendGroup(groups, { id: 'target' });
    expect(result.map((g) => g.id)).toEqual(['a', 'target']);
  });

  it('is a no-op replace when the array only has the target', () => {
    const groups = [{ id: 'target', label: 'old' }];
    const result = replaceOrAppendGroup(groups, { id: 'target', label: 'new' });
    expect(result).toEqual([{ id: 'target', label: 'new' }]);
  });
});

describe('removeGroupsById', () => {
  it('removes listed groups in place and keeps the rest', () => {
    const groups = [{ id: 'a' }, { id: 'called_element' }, { id: 'c' }, { id: 'multiInstance' }];
    const result = removeGroupsById(groups, ['called_element', 'multiInstance']);
    expect(result.map((g) => g.id)).toEqual(['a', 'c']);
    expect(result).toBe(groups);
  });

  it('is a no-op when none of the ids are present', () => {
    const groups = [{ id: 'a' }];
    expect(removeGroupsById(groups, ['missing'])).toEqual([{ id: 'a' }]);
  });
});
