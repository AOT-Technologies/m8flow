/**
 * The Properties panel's `getGroups` middleware chain hands every provider
 * the same plain array of `{ id, ... }` group objects to mutate and return.
 * Both `externalFormPropertiesProvider.ts` and `serviceTaskConnectorPanel.ts`
 * need to slot one group into that array relative to another provider's
 * (bpmn-js-spiffworkflow's) own group — the same "find this id, splice
 * relative to it, else append" shape twice, previously hand-rolled in each
 * file with no shared code and no tests. Two real adapters justify pulling
 * it out: this is a plain-array interface — no bpmn-js instance, no DOM —
 * so it's tested directly (`test/propertiesPanelGroups.test.ts`) with
 * nothing more than array literals.
 */

export type PropertiesPanelGroup = { id: string; [key: string]: unknown };

/**
 * Inserts `group` immediately after the group whose id is `anchorId`.
 * Falls back to appending when no such anchor exists — e.g. the anchor
 * provider hasn't registered a group for this element type at all.
 *
 * Used by `externalFormPropertiesProvider.ts` to slot "Web Form (External
 * Form)" right after bpmn-js-spiffworkflow's own "Web Form (with Json
 * Schemas)" group.
 */
export function insertGroupAfter(
  groups: PropertiesPanelGroup[],
  group: PropertiesPanelGroup,
  anchorId: string,
): PropertiesPanelGroup[] {
  const anchorIndex = groups.findIndex((g) => g && g.id === anchorId);
  if (anchorIndex === -1) {
    groups.push(group);
  } else {
    groups.splice(anchorIndex + 1, 0, group);
  }
  return groups;
}

/**
 * Replaces the existing group sharing `group.id`, in place, so it keeps
 * whatever position it already had. Falls back to appending when no group
 * with that id exists yet.
 *
 * Used by `serviceTaskConnectorPanel.ts` to swap bpmn-js-spiffworkflow's
 * own "service_task_properties" group for the tabbed version — splice, not
 * filter+push, so the group stays between "Instructions" and "Input/Output
 * Management" instead of moving to the end of the list.
 */
export function replaceOrAppendGroup(
  groups: PropertiesPanelGroup[],
  group: PropertiesPanelGroup,
): PropertiesPanelGroup[] {
  const existingIndex = groups.findIndex((g) => g && g.id === group.id);
  if (existingIndex === -1) {
    groups.push(group);
  } else {
    groups.splice(existingIndex, 1, group);
  }
  return groups;
}

/**
 * Removes every group whose id is in `ids`, in place. Used to strip dropped
 * BPMN construct groups (call activity, messages, data store, multi-instance)
 * after the Spiff providers have already pushed them.
 */
export function removeGroupsById(
  groups: PropertiesPanelGroup[],
  ids: readonly string[],
): PropertiesPanelGroup[] {
  const drop = new Set(ids);
  for (let i = groups.length - 1; i >= 0; i -= 1) {
    if (groups[i] && drop.has(groups[i].id)) {
      groups.splice(i, 1);
    }
  }
  return groups;
}
