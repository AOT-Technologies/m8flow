/**
 * Pad/palette agreement for dropped BPMN constructs.
 *
 * Catalog `_reject_unsupported_constructs` 400s on message events,
 * compensation events, and event subprocesses other than error, escalation
 * and non-interrupting timer ones. Call activity and multi-instance are supported (M8F-668), so
 * their morphs and the multi-instance toggles stay in the pad.
 * Data-store persist is also dropped. The palette already omits data store;
 * this replaces stock `replaceMenuProvider` so the pad cannot morph or
 * toggle a dropped construct into existence.
 *
 * A second `popupMenu.registerProvider` updater does *not* work: stock
 * ReplaceMenuProvider already owns `bpmn-replace`, and a trailing updater
 * never sees those entries in the live modeler. Override the DI key the
 * same way `customPalette` replaces `paletteProvider`.
 */
import inherits from 'inherits-browser';
import ReplaceMenuProvider from 'bpmn-js/lib/features/popup-menu/ReplaceMenuProvider';
import type { PopupMenuTarget } from 'diagram-js/lib/features/popup-menu/PopupMenu';

export const DROPPED_REPLACE_ACTIONS = [
  'replace-with-data-store-reference',
  'replace-with-event-subprocess',
  'replace-with-message-start',
  'replace-with-message-intermediate-catch',
  'replace-with-message-intermediate-throw',
  'replace-with-message-end',
  'replace-with-message-boundary',
  'replace-with-non-interrupting-message-boundary',
  'replace-with-non-interrupting-message-start',
  'replace-with-compensation-intermediate-throw',
  'replace-with-compensation-end',
  'replace-with-compensation-boundary',
  'replace-with-compensation-start',
] as const;

export function omitDroppedReplaceEntries<T extends Record<string, unknown>>(
  entries: T | undefined | null,
): T {
  if (!entries) {
    // Passes `null`/`undefined` straight through unchanged (see
    // droppedConstructCreate.test.ts's "passes through empty/missing
    // menus") — routed through `unknown` because TS considers a direct
    // `null | undefined` -> `T` cast suspect (TS2352) even though this is
    // intentionally just an identity return, not a real conversion.
    return entries as unknown as T;
  }
  let changed = false;
  const next = { ...entries };
  for (const action of DROPPED_REPLACE_ACTIONS) {
    if (action in next) {
      delete next[action];
      changed = true;
    }
  }
  return changed ? next : entries;
}

export function DroppedConstructReplaceMenuProvider(
  this: any,
  ...args: ConstructorParameters<typeof ReplaceMenuProvider>
) {
  ReplaceMenuProvider.apply(this, args);
}

inherits(DroppedConstructReplaceMenuProvider, ReplaceMenuProvider);

(DroppedConstructReplaceMenuProvider as any).$inject = ReplaceMenuProvider.$inject;

DroppedConstructReplaceMenuProvider.prototype.getPopupMenuEntries = function getPopupMenuEntries(
  this: any,
  target: PopupMenuTarget,
) {
  return omitDroppedReplaceEntries(
    ReplaceMenuProvider.prototype.getPopupMenuEntries.call(this, target),
  );
};

export const droppedConstructReplaceFilterModule = {
  __init__: ['replaceMenuProvider'],
  replaceMenuProvider: ['type', DroppedConstructReplaceMenuProvider],
};
