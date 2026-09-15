/**
 * Script-task unit tests live on the BPMN as
 * `spiffworkflow:unitTests` / `spiffworkflow:unitTest` (same XML the host
 * `/script-unit-tests` list/create routes persist). The Launch Editor edits
 * that in-memory extension so an unsaved script can still be tested; Run
 * hits the host run API with the current editor text plus these JSON
 * bodies. Do not POST create from the dialog — that writes the saved file
 * and would clobber unsaved diagram edits.
 */

export type ScriptUnitTestCase = {
  id: string;
  inputJson: string;
  expectedOutputJson: string;
};

export function parseJsonObject(raw: string, label: string): Record<string, unknown> {
  const trimmed = raw.trim() || '{}';
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    throw new Error(`${label} must be valid JSON`);
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object`);
  }
  return parsed as Record<string, unknown>;
}

export function newScriptUnitTestId(): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  let suffix = '';
  for (let i = 0; i < 7; i += 1) {
    suffix += alphabet[Math.floor(Math.random() * alphabet.length)];
  }
  return `ScriptUnitTest_${suffix}`;
}

function isSpiffType(node: { $type?: string; $instanceOf?: (type: string) => boolean } | null | undefined, type: string): boolean {
  if (!node) return false;
  if (typeof node.$instanceOf === 'function') {
    try {
      return Boolean(node.$instanceOf(type));
    } catch {
      // Some stubs throw; fall through to $type.
    }
  }
  return node.$type === type;
}

function extensionValues(businessObject: { extensionElements?: { values?: unknown[]; get?: (name: string) => unknown } } | null | undefined): unknown[] {
  const extensions = businessObject?.extensionElements;
  if (!extensions) return [];
  if (typeof extensions.get === 'function') {
    const values = extensions.get('values');
    return Array.isArray(values) ? values : [];
  }
  return Array.isArray(extensions.values) ? extensions.values : [];
}

function unitTestsContainer(businessObject: { extensionElements?: unknown } | null | undefined): { unitTests?: unknown[] } | undefined {
  const match = extensionValues(businessObject as { extensionElements?: { values?: unknown[] } }).find((node) =>
    isSpiffType(node as { $type?: string }, 'spiffworkflow:UnitTests'),
  );
  return match as { unitTests?: unknown[] } | undefined;
}

export function readScriptUnitTests(element: { businessObject?: unknown } | null | undefined): ScriptUnitTestCase[] {
  const container = unitTestsContainer(element?.businessObject as { extensionElements?: unknown });
  const units = container?.unitTests;
  if (!Array.isArray(units)) return [];
  return units.map((unit, index) => {
    const row = unit as {
      id?: string;
      inputJson?: { value?: string };
      expectedOutputJson?: { value?: string };
    };
    return {
      id: row.id || `ScriptUnitTest_${index + 1}`,
      inputJson: row.inputJson?.value ?? '{}',
      expectedOutputJson: row.expectedOutputJson?.value ?? '{}',
    };
  });
}

type ModdleLike = { create: (type: string) => Record<string, unknown> };
type ModelingLike = { updateProperties: (element: unknown, properties: Record<string, unknown>) => void };

/**
 * Replaces the script task's `spiffworkflow:UnitTests` extension with `cases`.
 * Empty `cases` removes the extension. Mutates then `updateProperties` so the
 * command stack marks the diagram dirty — same as bpmn-js-spiffworkflow's
 * ScriptUnitTestArray.
 */
export function applyScriptUnitTestsToElement(args: {
  element: { businessObject: Record<string, unknown> };
  cases: ScriptUnitTestCase[];
  moddle: ModdleLike;
  modeling: ModelingLike;
}): void {
  const { element, cases, moddle, modeling } = args;
  const businessObject = element.businessObject;
  let extensions = businessObject.extensionElements as
    | { values?: unknown[]; get?: (name: string) => unknown }
    | undefined;

  if (!extensions) {
    if (cases.length === 0) return;
    extensions = moddle.create('bpmn:ExtensionElements') as { values?: unknown[] };
    if (!Array.isArray(extensions.values)) extensions.values = [];
    businessObject.extensionElements = extensions;
  }

  const liveValues = typeof extensions.get === 'function' ? extensions.get('values') : undefined;
  const currentValues = Array.isArray(liveValues)
    ? liveValues
    : Array.isArray(extensions.values)
      ? extensions.values
      : [];

  const kept = currentValues.filter(
    (node) => !isSpiffType(node as { $type?: string }, 'spiffworkflow:UnitTests'),
  );

  if (cases.length > 0) {
    const container = moddle.create('spiffworkflow:UnitTests') as { unitTests?: unknown[] };
    container.unitTests = cases.map((testCase) => {
      const unit = moddle.create('spiffworkflow:UnitTest') as {
        id?: string;
        inputJson?: { value?: string };
        expectedOutputJson?: { value?: string };
      };
      const inputJson = moddle.create('spiffworkflow:InputJson') as { value?: string };
      const expectedOutputJson = moddle.create('spiffworkflow:ExpectedOutputJson') as { value?: string };
      unit.id = testCase.id;
      inputJson.value = testCase.inputJson;
      expectedOutputJson.value = testCase.expectedOutputJson;
      unit.inputJson = inputJson;
      unit.expectedOutputJson = expectedOutputJson;
      return unit;
    });
    kept.push(container);
  }

  currentValues.length = 0;
  kept.forEach((node) => currentValues.push(node));
  extensions.values = currentValues;
  if (currentValues.length === 0) {
    businessObject.extensionElements = undefined;
  }
  modeling.updateProperties(element, {});
}
