import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ModelerFileToolbar } from './ModelerFileToolbar';

const BASE = {
  savePhase: 'saved' as const,
  fileLoaded: true,
  canManage: true,
  isPrimary: false,
  isBpmn: true,
  isDiagram: true,
  onSave: vi.fn(),
  onDownload: vi.fn(),
  onNewFile: vi.fn(),
  onDelete: vi.fn(),
  onSetPrimary: vi.fn(),
  onViewXml: vi.fn(),
};

describe('ModelerFileToolbar', () => {
  it('shows new-file, set-as-primary, view XML, and delete for a non-primary BPMN', () => {
    render(<ModelerFileToolbar {...BASE} />);

    expect(screen.getByRole('button', { name: 'New file' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Set as primary' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'View XML' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Download' })).toBeInTheDocument();
  });

  it('hides delete and set-as-primary on the primary BPMN', () => {
    render(<ModelerFileToolbar {...BASE} isPrimary />);

    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Set as primary' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'View XML' })).toBeInTheDocument();
  });

  it('hides view XML and set-as-primary for markdown, but still allows delete', () => {
    render(<ModelerFileToolbar {...BASE} isBpmn={false} isDiagram={false} />);

    expect(screen.queryByRole('button', { name: 'View XML' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Set as primary' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
  });

  it('hides mutating chrome when the user cannot manage the catalog', () => {
    render(<ModelerFileToolbar {...BASE} canManage={false} />);

    expect(screen.queryByRole('button', { name: 'New file' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Set as primary' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'View XML' })).toBeInTheDocument();
  });

  it('shows Save instead of the saved pill when dirty', () => {
    const onSave = vi.fn();
    render(<ModelerFileToolbar {...BASE} savePhase="dirty" onSave={onSave} />);

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('Saved')).not.toBeInTheDocument();
  });
});
