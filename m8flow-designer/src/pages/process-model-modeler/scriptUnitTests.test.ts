import { describe, expect, it, vi } from 'vitest';

import {
  applyScriptUnitTestsToElement,
  newScriptUnitTestId,
  parseJsonObject,
  readScriptUnitTests,
} from './scriptUnitTests';

function fakeModdle() {
  return {
    create: (type: string) => {
      if (type === 'bpmn:ExtensionElements') return { $type: type, values: [] as unknown[] };
      if (type === 'spiffworkflow:UnitTests') return { $type: type, unitTests: [] as unknown[] };
      if (type === 'spiffworkflow:UnitTest') return { $type: type, id: '' };
      if (type === 'spiffworkflow:InputJson' || type === 'spiffworkflow:ExpectedOutputJson') {
        return { $type: type, value: '' };
      }
      return { $type: type };
    },
  };
}

describe('parseJsonObject', () => {
  it('parses objects and rejects arrays', () => {
    expect(parseJsonObject('{"a": 1}', 'Input JSON')).toEqual({ a: 1 });
    expect(() => parseJsonObject('[1]', 'Input JSON')).toThrow('Input JSON must be a JSON object');
  });
});

describe('script unit tests on a script task', () => {
  it('reads nothing from a task with no extensions', () => {
    expect(readScriptUnitTests({ businessObject: {} })).toEqual([]);
  });

  it('round-trips cases through the Spiff unitTests extension', () => {
    const element = { businessObject: {} as Record<string, unknown> };
    const modeling = { updateProperties: vi.fn() };
    const cases = [
      { id: 'ScriptUnitTest_A', inputJson: '{"n": 1}', expectedOutputJson: '{"n": 2}' },
    ];
    applyScriptUnitTestsToElement({ element, cases, moddle: fakeModdle(), modeling });
    expect(modeling.updateProperties).toHaveBeenCalledWith(element, {});
    expect(readScriptUnitTests(element)).toEqual(cases);
  });

  it('removes the extension when the last case is cleared', () => {
    const element = { businessObject: {} as Record<string, unknown> };
    const modeling = { updateProperties: vi.fn() };
    applyScriptUnitTestsToElement({
      element,
      cases: [{ id: 'ScriptUnitTest_A', inputJson: '{}', expectedOutputJson: '{}' }],
      moddle: fakeModdle(),
      modeling,
    });
    applyScriptUnitTestsToElement({ element, cases: [], moddle: fakeModdle(), modeling });
    expect(element.businessObject.extensionElements).toBeUndefined();
    expect(readScriptUnitTests(element)).toEqual([]);
  });

  it('minted ids match the catalog create prefix style', () => {
    expect(newScriptUnitTestId()).toMatch(/^ScriptUnitTest_[A-Z0-9]{7}$/);
  });
});
