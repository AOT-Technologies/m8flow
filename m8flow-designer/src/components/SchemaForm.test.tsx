import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SchemaForm, validateSchemaForm, type JsonSchema } from './SchemaForm';

describe('validateSchemaForm', () => {
  const schema: JsonSchema = {
    type: 'object',
    required: ['reason'],
    properties: {
      reason: { type: 'string', title: 'Reason', minLength: 5 },
      amount: { type: 'number', title: 'Amount' },
    },
  };

  it('returns no errors for a valid value', () => {
    expect(validateSchemaForm(schema, { reason: 'because', amount: 12 })).toEqual({});
  });

  it('flags a missing required field', () => {
    const errors = validateSchemaForm(schema, {});
    expect(errors.reason).toMatch(/required/i);
  });

  it('flags a too-short string via minLength', () => {
    const errors = validateSchemaForm(schema, { reason: 'no' });
    expect(errors.reason).toMatch(/at least 5/i);
  });

  it('flags a non-numeric number field', () => {
    const errors = validateSchemaForm(schema, { reason: 'valid', amount: 'x' as unknown as number });
    expect(errors.amount).toMatch(/number/i);
  });
});

describe('SchemaForm', () => {
  it('renders a control per property and reports changes', () => {
    const schema: JsonSchema = {
      type: 'object',
      properties: {
        name: { type: 'string', title: 'Name' },
        active: { type: 'boolean', title: 'Active' },
      },
    };
    const onChange = vi.fn();
    render(<SchemaForm schema={schema} value={{}} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText(/Name/i), { target: { value: 'Ada' } });
    expect(onChange).toHaveBeenCalledWith({ name: 'Ada' });

    fireEvent.click(screen.getByLabelText(/Active/i));
    expect(onChange).toHaveBeenCalledWith({ active: true });
  });

  it('applies ui:placeholder and ui:widget password from the UI schema', () => {
    const schema: JsonSchema = {
      type: 'object',
      properties: {
        accessCode: { type: 'string', title: 'Access code' },
      },
    };
    render(
      <SchemaForm
        schema={schema}
        uiSchema={{ accessCode: { 'ui:widget': 'password', 'ui:placeholder': 'secret' } }}
        value={{}}
        onChange={vi.fn()}
      />,
    );
    const input = screen.getByLabelText(/Access code/i);
    expect(input).toHaveAttribute('type', 'password');
    expect(input).toHaveAttribute('placeholder', 'secret');
  });

  it('renders a readOnly field as text instead of an input', () => {
    const schema: JsonSchema = {
      type: 'object',
      properties: {
        ref: { type: 'string', title: 'Reference', readOnly: true },
      },
    };
    render(<SchemaForm schema={schema} value={{ ref: 'REQ-1' }} onChange={vi.fn()} />);
    expect(screen.getByText('REQ-1')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });
});
