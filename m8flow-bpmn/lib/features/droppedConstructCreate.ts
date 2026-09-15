/**
 * Pad/palette agreement for dropped BPMN constructs.
 *
 * Catalog `_reject_unsupported_constructs` 400s on call activity, message
 * events, compensation events, multi-instance, and event subprocess.
 * Data-store persist is also dropped. The palette already omits data store;
 * this replaces stock `replaceMenuProvider` so the pad cannot morph or
 * toggle a dropped construct into existence.
 *
 * A second `popupMenu.registerProvider` updater does *not* work: stock
 * ReplaceMenuProvider already owns `bpmn-replace`, and a trailing updater
 * never sees those entries in the live modeler. Override the DI key the
 * same way `customPalette` replaces `paletteProvider`.
 *
 * Multi-instance header toggles that are already *active* stay so a leftover
 * shape can be turned back into a plain task. Inactive MI toggles are hidden.
 */
import inherits from 'inherits-browser';
import ReplaceMenuProvider from 'bpmn-js/lib/features/popup-menu/ReplaceMenuProvider';
import type { PopupMenuTarget } from 'diagram-js/lib/features/popup-menu/PopupMenu';

// bpmn-js@17.11.1 started shipping ReplaceMenuProvider.d.ts (the
// `@ts-expect-error` this import used to need is gone). Its declared return
// type for `getPopupMenuHeaderEntries` is `PopupMenuHeaderEntries`
// (`PopupMenuHeaderEntry[]`, an array) — but the real implementation
// (node_modules/bpmn-js/lib/features/popup-menu/ReplaceMenuProvider.js,
// `getPopupMenuHeaderEntries`) builds and returns a plain object keyed by
// action id (`{ 'toggle-parallel-mi': {...}, 'toggle-sequential-mi': {...} }`
// via object spreads), never an array. That's an upstream `.d.ts`/runtime
// mismatch in bpmn-js itself, confirmed by reading both files — not
// something to "fix" by reshaping the working logic below to treat it as
// an array. This local type documents the shape we actually receive.
type HeaderEntriesRecord = Record<string, { active?: boolean }>;

export const DROPPED_REPLACE_ACTIONS = [
  'replace-with-data-store-reference',
  'replace-with-call-activity',
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

export const DROPPED_REPLACE_HEADER_ACTIONS = [
  'toggle-parallel-mi',
  'toggle-sequential-mi',
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

export function omitDroppedReplaceHeaderEntries<T extends Record<string, unknown>>(
  entries: T | undefined | null,
): T {
  if (!entries) {
    // Same identity-passthrough reasoning as omitDroppedReplaceEntries above.
    return entries as unknown as T;
  }
  let changed = false;
  const next = { ...entries };
  for (const action of DROPPED_REPLACE_HEADER_ACTIONS) {
    const entry = next[action] as { active?: boolean } | undefined;
    if (entry && !entry.active) {
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

DroppedConstructReplaceMenuProvider.prototype.getPopupMenuHeaderEntries =
  function getPopupMenuHeaderEntries(this: any, target: PopupMenuTarget) {
    return omitDroppedReplaceHeaderEntries(
      // See the HeaderEntriesRecord comment at the top of this file: the
      // real return value here is a plain dict, not the array bpmn-js's
      // own .d.ts declares.
      ReplaceMenuProvider.prototype.getPopupMenuHeaderEntries.call(
        this,
        target,
      ) as unknown as HeaderEntriesRecord,
    );
  };

export const droppedConstructReplaceFilterModule = {
  __init__: ['replaceMenuProvider'],
  replaceMenuProvider: ['type', DroppedConstructReplaceMenuProvider],
};
