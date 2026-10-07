/**
 * Pre/Post-script context pad entries (M8F-564).
 *
 * bpmn-js-spiffworkflow's CustomContextPadProvider adds `trigger-preScript`
 * / `trigger-postScript` only once a script exists, opens the Monaco modal,
 * and paints them as teal 32px images that ignore the pad's grid. This
 * provider runs after it (lower priority; diagram-js applies providers
 * high → low) and rewrites both entries: always present wherever the panel
 * shows the Pre/Post Scripts group, an Add/Edit tooltip, a `configured`
 * class for the dot, and a click that opens that group's textarea via the
 * properties panel's own `propertiesPanel.showEntry`. Glyphs and the dot
 * live in diagram-chrome.css.
 */
import { is, isAny } from 'bpmn-js/lib/util/ModelUtil';

// Below spiffworkflow's CustomContextPadProvider (500).
const PRIORITY = 400;

// How long a click waits for the panel to focus its textarea.
export const FOCUS_WAIT_MS = 1000;

const SCRIPT_ENTRIES = [
  { action: 'trigger-preScript', scriptType: 'spiffworkflow:PreScript', add: 'Add pre-script', edit: 'Edit pre-script' },
  { action: 'trigger-postScript', scriptType: 'spiffworkflow:PostScript', add: 'Add post-script', edit: 'Edit post-script' },
];

/** Same element set spiffworkflow's ExtensionsPropertiesProvider gives the Pre/Post Scripts group. */
function hasPrePostScripts(element: any) {
  return !is(element, 'bpmn:ScriptTask') && isAny(element, ['bpmn:Task', 'bpmn:CallActivity', 'bpmn:SubProcess']);
}

/** Same lookup as spiffworkflow's getScriptString (what the panel's textarea
 * reads), so "configured" matches the panel's own has-content dot. Inlined:
 * importing SpiffScriptGroup drags the whole properties-panel tree in. */
function hasScript(element: any, scriptType: string) {
  const values: any[] = element.businessObject?.extensionElements?.values ?? [];
  return Boolean(values.find((ext) => ext.$instanceOf(scriptType))?.value);
}

export function ScriptContextPadProvider(this: any, contextPad: any, eventBus: any, translate: any) {
  contextPad.registerProvider(PRIORITY, this);

  this.getContextPadEntries = (element: any) => (entries: Record<string, unknown>) => {
    if (!hasPrePostScripts(element)) return entries;

    for (const { action, scriptType, add, edit } of SCRIPT_ENTRIES) {
      const configured = hasScript(element, scriptType);
      entries[action] = {
        group: 'connect',
        className: configured ? 'm8flow-script-configured' : undefined,
        title: translate(configured ? edit : add),
        action: {
          click: () => {
            const id = `pythonScript_${scriptType}`;
            // showEntry focuses *and selects* the field, so the first keystroke
            // would replace the whole script. focus() and select() run back to
            // back, so a timeout queued from focusin lands after select().
            // The panel focuses in a Preact effect a frame later; if it never
            // does (no panel, unknown id) the signal drops the listener so a
            // later, unrelated focus can't move the caret.
            document.addEventListener(
              'focusin',
              (event) => {
                const field = event.target;
                if (field instanceof HTMLTextAreaElement && field.name === id) {
                  setTimeout(() => field.setSelectionRange(field.value.length, field.value.length));
                }
              },
              { once: true, signal: AbortSignal.timeout(FOCUS_WAIT_MS) },
            );
            eventBus.fire('propertiesPanel.showEntry', { id });
          },
        },
      };
    }
    return entries;
  };
}

(ScriptContextPadProvider as any).$inject = ['contextPad', 'eventBus', 'translate'];

export const scriptContextPadModule = {
  __init__: ['scriptContextPadProvider'],
  scriptContextPadProvider: ['type', ScriptContextPadProvider],
};
