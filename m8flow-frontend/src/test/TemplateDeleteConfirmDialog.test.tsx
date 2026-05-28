import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import TemplateDeleteConfirmDialog, {
  TemplateRestoreConfirmDialog,
} from '../components/TemplateDeleteConfirmDialog';

// Mock react-i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
  }),
}));

describe('TemplateDeleteConfirmDialog', () => {
  const defaultProps = {
    open: true,
    onClose: vi.fn(),
    onConfirm: vi.fn(),
    templateName: 'My Template',
    isPublished: false,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render the dialog when open is true', () => {
    render(<TemplateDeleteConfirmDialog {...defaultProps} />);
    expect(screen.getByTestId('delete-template-confirm-dialog')).toBeInTheDocument();
    expect(screen.getByText('Delete template?')).toBeInTheDocument();
  });

  it('should not render dialog content when open is false', () => {
    render(<TemplateDeleteConfirmDialog {...defaultProps} open={false} />);
    expect(screen.queryByText('Delete template?')).not.toBeInTheDocument();
  });

  it('should show permanent delete message for draft templates', () => {
    render(<TemplateDeleteConfirmDialog {...defaultProps} isPublished={false} />);
    expect(screen.getByText('"My Template" will be permanently deleted.')).toBeInTheDocument();
  });

  it('should show soft-delete message for published templates', () => {
    render(<TemplateDeleteConfirmDialog {...defaultProps} isPublished={true} />);
    expect(
      screen.getByText('"My Template" will be soft-deleted and can be restored from the Deleted tab.')
    ).toBeInTheDocument();
  });

  it('should call onConfirm and onClose when confirm button is clicked', () => {
    render(<TemplateDeleteConfirmDialog {...defaultProps} />);
    fireEvent.click(screen.getByTestId('delete-template-confirm-button'));
    expect(defaultProps.onConfirm).toHaveBeenCalledTimes(1);
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
  });

  it('should call onClose when cancel button is clicked', () => {
    render(<TemplateDeleteConfirmDialog {...defaultProps} />);
    fireEvent.click(screen.getByTestId('delete-template-cancel-button'));
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
    expect(defaultProps.onConfirm).not.toHaveBeenCalled();
  });

  it('should have correct aria attributes for accessibility', () => {
    render(<TemplateDeleteConfirmDialog {...defaultProps} />);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-labelledby', 'delete-template-dialog-title');
    expect(dialog).toHaveAttribute('aria-describedby', 'delete-template-dialog-description');
  });
});

describe('TemplateRestoreConfirmDialog', () => {
  const defaultProps = {
    open: true,
    onClose: vi.fn(),
    onConfirm: vi.fn(),
    templateName: 'Restored Template',
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render the restore dialog when open is true', () => {
    render(<TemplateRestoreConfirmDialog {...defaultProps} />);
    expect(screen.getByTestId('restore-template-confirm-dialog')).toBeInTheDocument();
    expect(screen.getByText('Restore template?')).toBeInTheDocument();
  });

  it('should show the correct restore message with template name', () => {
    render(<TemplateRestoreConfirmDialog {...defaultProps} />);
    expect(
      screen.getByText('"Restored Template" will be restored and become active again.')
    ).toBeInTheDocument();
  });

  it('should call onConfirm and onClose when restore button is clicked', () => {
    render(<TemplateRestoreConfirmDialog {...defaultProps} />);
    fireEvent.click(screen.getByTestId('restore-template-confirm-button'));
    expect(defaultProps.onConfirm).toHaveBeenCalledTimes(1);
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
  });

  it('should call onClose when cancel button is clicked', () => {
    render(<TemplateRestoreConfirmDialog {...defaultProps} />);
    fireEvent.click(screen.getByTestId('restore-template-cancel-button'));
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
    expect(defaultProps.onConfirm).not.toHaveBeenCalled();
  });

  it('should not render when open is false', () => {
    render(<TemplateRestoreConfirmDialog {...defaultProps} open={false} />);
    expect(screen.queryByText('Restore template?')).not.toBeInTheDocument();
  });

  it('should have correct aria attributes for accessibility', () => {
    render(<TemplateRestoreConfirmDialog {...defaultProps} />);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-labelledby', 'restore-template-dialog-title');
    expect(dialog).toHaveAttribute('aria-describedby', 'restore-template-dialog-description');
  });
});
