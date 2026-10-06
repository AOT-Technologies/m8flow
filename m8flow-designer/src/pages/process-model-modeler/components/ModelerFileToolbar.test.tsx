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

  it('keeps Download as a secondary action', () => {
    render(<ModelerFileToolbar {...BASE} />);
    expect(screen.getByRole('button', { name: 'Download' })).toHaveAttribute('data-variant', 'outline');
  });

  it('offers Publish for a draft and Resume for a paused model', () => {
    const onPublish = vi.fn();
    const { rerender } = render(
      <ModelerFileToolbar {...BASE} status="draft" onPublish={onPublish} onStart={vi.fn()} />,
    );
    expect(screen.queryByRole('button', { name: /Start process/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^Publish$/ }));
    expect(onPublish).toHaveBeenCalledTimes(1);

    rerender(<ModelerFileToolbar {...BASE} status="paused" onPublish={onPublish} />);
    expect(screen.getByRole('button', { name: /Resume/ })).toBeEnabled();
  });

  it('offers Start process for a published model', () => {
    const onStart = vi.fn();
    render(
      <ModelerFileToolbar {...BASE} status="published" onPublish={vi.fn()} onStart={onStart} />,
    );
    expect(screen.queryByRole('button', { name: /^Publish$/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Start process/ }));
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  it('blocks lifecycle actions until changes are saved', () => {
    render(
      <ModelerFileToolbar {...BASE} savePhase="dirty" status="draft" onPublish={vi.fn()} />,
    );
    expect(screen.getByRole('button', { name: /^Publish$/ })).toBeDisabled();
    expect(screen.getByTitle('Save your changes before publishing.')).toBeInTheDocument();
  });

  it('shows no lifecycle action before the status is known', () => {
    render(<ModelerFileToolbar {...BASE} onPublish={vi.fn()} onStart={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /Publish|Start process/ })).not.toBeInTheDocument();
  });
});
