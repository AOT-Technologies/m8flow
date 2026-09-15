import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { parseJsonObject, ProcessModelTestsCard } from './ProcessModelTestsCard';

describe('parseJsonObject', () => {
  it('parses objects and rejects arrays', () => {
    expect(parseJsonObject('{"a": 1}', 'Input JSON')).toEqual({ a: 1 });
    expect(() => parseJsonObject('[1]', 'Input JSON')).toThrow('Input JSON must be a JSON object');
  });
});

describe('ProcessModelTestsCard', () => {
  it('keeps Run BPMN tests disabled without a test file', () => {
    render(<ProcessModelTestsCard canManage hasBpmnTests={false} onRunBpmnTests={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Run BPMN tests' })).toBeDisabled();
  });

  it('runs BPMN tests and shows pass count', async () => {
    const onRunBpmnTests = vi.fn().mockResolvedValue({
      all_passed: true,
      passing: [{ passed: true, bpmn_file: 'notes.bpmn', test_case_identifier: 'happy_path' }],
      failing: [],
    });
    render(<ProcessModelTestsCard canManage hasBpmnTests onRunBpmnTests={onRunBpmnTests} />);
    fireEvent.click(screen.getByRole('button', { name: 'Run BPMN tests' }));
    await waitFor(() => {
      expect(screen.getByText('All 1 test passed.')).toBeInTheDocument();
    });
    expect(onRunBpmnTests).toHaveBeenCalled();
  });

  it('creates and runs a stored script unit test', async () => {
    const onFetchScriptUnitTests = vi.fn().mockResolvedValue([]);
    const onCreateScriptUnitTest = vi.fn().mockResolvedValue({ id: 'unit_test_ABC1234' });
    const onRunScriptUnitTest = vi.fn().mockResolvedValue({ result: true });
    render(
      <ProcessModelTestsCard
        canManage
        hasBpmnTests={false}
        onFetchScriptUnitTests={onFetchScriptUnitTests}
        onCreateScriptUnitTest={onCreateScriptUnitTest}
        onRunScriptUnitTest={onRunScriptUnitTest}
      />,
    );
    await waitFor(() => {
      expect(onFetchScriptUnitTests).toHaveBeenCalled();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create script unit test' }));
    fireEvent.change(screen.getByLabelText('Script task ID'), { target: { value: 'Script_1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => {
      expect(onCreateScriptUnitTest).toHaveBeenCalledWith({
        bpmn_task_identifier: 'Script_1',
        input_json: {},
        expected_output_json: {},
      });
    });
    expect(screen.getByText('unit_test_ABC1234')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    await waitFor(() => {
      expect(screen.getByText('Passed.')).toBeInTheDocument();
    });
    expect(onRunScriptUnitTest).toHaveBeenCalledWith({ unit_test_id: 'unit_test_ABC1234' });
  });
});
