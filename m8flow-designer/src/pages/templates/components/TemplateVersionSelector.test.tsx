import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { Template } from '@/lib/templatesApi';
import { mergeTemplateVersions, TemplateVersionSelector } from './TemplateVersionSelector';

const V1: Template = {
  id: 1,
  templateKey: 'invoice',
  version: 'V1',
  name: 'Invoice',
  description: null,
  tags: null,
  category: null,
  tenantId: 't1',
  visibility: 'TENANT',
  files: [],
  isPublished: true,
  status: 'published',
  createdBy: 'editor',
  modifiedBy: 'editor',
  createdAtInSeconds: 1,
  updatedAtInSeconds: 1,
};

const V2: Template = { ...V1, id: 2, version: 'V2', isPublished: false, status: 'draft' };

describe('mergeTemplateVersions', () => {
  it('sorts V-prefixed versions and includes the current row', () => {
    const merged = mergeTemplateVersions([V2], V1);
    expect(merged.map((row) => row.id)).toEqual([1, 2]);
  });
});

describe('TemplateVersionSelector', () => {
  it('hides when there is only one version', () => {
    render(<TemplateVersionSelector current={V1} versions={[V1]} onSelect={vi.fn()} />);
    expect(screen.queryByLabelText('All versions')).not.toBeInTheDocument();
  });

  it('navigates to the chosen version id', () => {
    const onSelect = vi.fn();
    render(<TemplateVersionSelector current={V2} versions={[V1, V2]} onSelect={onSelect} />);
    fireEvent.change(screen.getByLabelText('All versions'), { target: { value: '1' } });
    expect(onSelect).toHaveBeenCalledWith(1);
  });
});
