import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import TemplateCard from '../components/TemplateCard';
import type { Template } from '../types/template';

// Mock react-i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
  }),
}));

// Mock TimeAgo
vi.mock('@spiffworkflow-frontend/helpers/timeago', () => ({
  TimeAgo: {
    inWords: (seconds: number) => `${seconds}s ago`,
  },
}));

// Mock DateAndTimeService
vi.mock('@spiffworkflow-frontend/services/DateAndTimeService', () => ({
  default: {
    convertSecondsToFormattedDateTime: (seconds: number) =>
      seconds ? new Date(seconds * 1000).toISOString() : null,
  },
}));

const createTemplate = (overrides: Partial<Template> = {}): Template => ({
  id: 1,
  templateKey: 'test-key',
  version: 'V1',
  name: 'Test Template',
  description: 'A test description',
  tags: null,
  category: null,
  tenantId: null,
  visibility: 'PRIVATE',
  files: [],
  isPublished: false,
  isDeleted: false,
  status: null,
  createdAtInSeconds: 1700000000,
  createdBy: 'user1',
  updatedAtInSeconds: 1700001000,
  modifiedBy: 'user1',
  ...overrides,
});

function renderCard(props: Partial<React.ComponentProps<typeof TemplateCard>> = {}) {
  const template = props.template ?? createTemplate();
  return render(
    <MemoryRouter>
      <TemplateCard template={template} {...props} />
    </MemoryRouter>
  );
}

describe('TemplateCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('rendering', () => {
    it('should render template name', () => {
      renderCard();
      expect(screen.getByText('Test Template')).toBeInTheDocument();
    });

    it('should render template description', () => {
      renderCard();
      expect(screen.getByText('A test description')).toBeInTheDocument();
    });

    it('should render "--" when description is empty', () => {
      renderCard({ template: createTemplate({ description: null }) });
      expect(screen.getByText('--')).toBeInTheDocument();
    });

    it('should render version', () => {
      renderCard();
      expect(screen.getByText(/V1/)).toBeInTheDocument();
    });

    it('should render visibility chip', () => {
      renderCard({ template: createTemplate({ visibility: 'PUBLIC' }) });
      expect(screen.getByText('public')).toBeInTheDocument();
    });

    it('should render category chip when present', () => {
      renderCard({ template: createTemplate({ category: 'Finance' }) });
      expect(screen.getByText(/Finance/)).toBeInTheDocument();
    });

    it('should not render category chip when category is null', () => {
      renderCard({ template: createTemplate({ category: null }) });
      expect(screen.queryByText(/category:/i)).not.toBeInTheDocument();
    });

    it('should render tags when present (max 3)', () => {
      renderCard({
        template: createTemplate({
          tags: ['tag1', 'tag2', 'tag3'],
        }),
      });
      expect(screen.getByText('tag1')).toBeInTheDocument();
      expect(screen.getByText('tag2')).toBeInTheDocument();
      expect(screen.getByText('tag3')).toBeInTheDocument();
    });

    it('should show overflow count when more than 3 tags', () => {
      renderCard({
        template: createTemplate({
          tags: ['tag1', 'tag2', 'tag3', 'tag4', 'tag5'],
        }),
      });
      expect(screen.getByText('+2')).toBeInTheDocument();
    });

    it('should not render tags section when tags is null', () => {
      renderCard({ template: createTemplate({ tags: null }) });
      expect(screen.queryByText('tag1')).not.toBeInTheDocument();
    });

    it('should show tenant context when showTenantContext is true', () => {
      renderCard({
        template: createTemplate({
          tenantId: 'tenant-1',
          tenant: { id: 'tenant-1', name: 'Acme Corp', slug: 'acme' },
          createdBy: 'admin',
        }),
        showTenantContext: true,
      });
      expect(screen.getByText(/Acme Corp/)).toBeInTheDocument();
      expect(screen.getByText(/admin/)).toBeInTheDocument();
    });

    it('should not show tenant context when showTenantContext is false', () => {
      renderCard({
        template: createTemplate({
          tenant: { id: 'tenant-1', name: 'Acme Corp', slug: 'acme' },
        }),
        showTenantContext: false,
      });
      expect(screen.queryByText(/Acme Corp/)).not.toBeInTheDocument();
    });

    it('should have correct data-testid', () => {
      renderCard({ template: createTemplate({ id: 42 }) });
      expect(screen.getByTestId('template-card-42')).toBeInTheDocument();
    });
  });

  describe('overflow menu', () => {
    it('should show ⋮ button when any action handler is provided', () => {
      renderCard({ onEditTemplate: vi.fn() });
      expect(screen.getByTestId('template-card-more-actions-1')).toBeInTheDocument();
    });

    it('should not show ⋮ button when no action handler is provided', () => {
      renderCard();
      expect(screen.queryByTestId('template-card-more-actions-1')).not.toBeInTheDocument();
    });

    it('should open menu on ⋮ click and show Edit action', () => {
      const onEdit = vi.fn();
      renderCard({ onEditTemplate: onEdit });
      fireEvent.click(screen.getByTestId('template-card-more-actions-1'));
      expect(screen.getByTestId('template-card-edit-1')).toBeInTheDocument();
    });

    it('should call onEditTemplate when Edit menu item is clicked', () => {
      const onEdit = vi.fn();
      renderCard({ onEditTemplate: onEdit });
      fireEvent.click(screen.getByTestId('template-card-more-actions-1'));
      fireEvent.click(screen.getByTestId('template-card-edit-1'));
      expect(onEdit).toHaveBeenCalledTimes(1);
    });

    it('should call onExportTemplate when Export menu item is clicked', () => {
      const onExport = vi.fn();
      renderCard({ onExportTemplate: onExport });
      fireEvent.click(screen.getByTestId('template-card-more-actions-1'));
      fireEvent.click(screen.getByTestId('template-card-export-1'));
      expect(onExport).toHaveBeenCalledTimes(1);
    });

    it('should show delete action in menu when onDeleteTemplate is provided', () => {
      renderCard({ onDeleteTemplate: vi.fn() });
      fireEvent.click(screen.getByTestId('template-card-more-actions-1'));
      expect(screen.getByTestId('template-card-delete-1')).toBeInTheDocument();
    });

    it('should disable delete menu item when deleteDisabled is true', () => {
      renderCard({
        onDeleteTemplate: vi.fn(),
        deleteDisabled: true,
        deleteDisabledReason: 'No permission',
      });
      fireEvent.click(screen.getByTestId('template-card-more-actions-1'));
      const deleteItem = screen.getByTestId('template-card-delete-1');
      expect(deleteItem).toHaveAttribute('aria-disabled', 'true');
    });

    it('should show restore action when onRestoreTemplate is provided', () => {
      renderCard({ onRestoreTemplate: vi.fn() });
      fireEvent.click(screen.getByTestId('template-card-more-actions-1'));
      expect(screen.getByTestId('template-card-restore-1')).toBeInTheDocument();
    });

    it('should disable restore menu item when restoreDisabled is true', () => {
      renderCard({
        onRestoreTemplate: vi.fn(),
        restoreDisabled: true,
        restoreDisabledReason: 'Admin only',
      });
      fireEvent.click(screen.getByTestId('template-card-more-actions-1'));
      const restoreItem = screen.getByTestId('template-card-restore-1');
      expect(restoreItem).toHaveAttribute('aria-disabled', 'true');
    });

    it('should not show duplicate menu item when onDuplicateTemplate is not provided', () => {
      renderCard({ onEditTemplate: vi.fn() });
      fireEvent.click(screen.getByTestId('template-card-more-actions-1'));
      expect(screen.queryByTestId('template-card-duplicate-1')).not.toBeInTheDocument();
    });

    it('should show duplicate menu item when onDuplicateTemplate is provided', () => {
      const onDuplicate = vi.fn();
      renderCard({ onDuplicateTemplate: onDuplicate });
      fireEvent.click(screen.getByTestId('template-card-more-actions-1'));
      const duplicateItem = screen.getByTestId('template-card-duplicate-1');
      expect(duplicateItem).toBeInTheDocument();
      fireEvent.click(duplicateItem);
      expect(onDuplicate).toHaveBeenCalledTimes(1);
    });
  });

  describe('visibility chip colors', () => {
    it('should render primary color chip for PUBLIC visibility', () => {
      renderCard({ template: createTemplate({ visibility: 'PUBLIC' }) });
      const chip = screen.getByText('public');
      expect(chip.closest('.MuiChip-root')).toHaveClass('MuiChip-colorPrimary');
    });

    it('should render secondary color chip for TENANT visibility', () => {
      renderCard({ template: createTemplate({ visibility: 'TENANT' }) });
      const chip = screen.getByText('tenant');
      expect(chip.closest('.MuiChip-root')).toHaveClass('MuiChip-colorSecondary');
    });

    it('should render default color chip for PRIVATE visibility', () => {
      renderCard({ template: createTemplate({ visibility: 'PRIVATE' }) });
      const chip = screen.getByText('private');
      expect(chip.closest('.MuiChip-root')).toHaveClass('MuiChip-colorDefault');
    });
  });
});
