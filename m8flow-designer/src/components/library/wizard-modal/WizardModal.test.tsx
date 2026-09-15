import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { WizardModal, type WizardModalStep } from './WizardModal';

const steps: WizardModalStep[] = [
  { title: 'Connect a source', body: 'Choose where this process pulls its trigger data from.' },
  { title: 'Map the fields', body: 'Match incoming fields to the variables this process model expects.' },
  { title: 'Review & launch', body: 'Confirm the connection and mapping, then turn the process on.' },
];

describe('WizardModal', () => {
  it('renders nothing when closed', () => {
    render(
      <WizardModal open={false} steps={steps} onClose={() => {}} onComplete={() => {}} />,
    );

    expect(screen.queryByText('Connect a source')).not.toBeInTheDocument();
  });

  it('starts on step 1 of N with Back disabled and shows the first step title/body', () => {
    render(<WizardModal open steps={steps} onClose={() => {}} onComplete={() => {}} />);

    expect(screen.getByText('Connect a source')).toBeInTheDocument();
    expect(
      screen.getByText('Choose where this process pulls its trigger data from.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Step 1 of 3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Back' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument();
  });

  it('advances through steps via Continue, enabling Back, and reads Finish on the last step', () => {
    render(<WizardModal open steps={steps} onClose={() => {}} onComplete={() => {}} />);

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    expect(screen.getByText('Map the fields')).toBeInTheDocument();
    expect(screen.getByText('Step 2 of 3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Back' })).not.toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    expect(screen.getByText('Review & launch')).toBeInTheDocument();
    expect(screen.getByText('Step 3 of 3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Finish' })).toBeInTheDocument();
  });

  it('navigates back a step and re-disables Back on step 1', () => {
    render(<WizardModal open steps={steps} onClose={() => {}} onComplete={() => {}} />);

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));

    expect(screen.getByText('Connect a source')).toBeInTheDocument();
    expect(screen.getByText('Step 1 of 3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Back' })).toBeDisabled();
  });

  it('calls onComplete when Finish is clicked on the last step, without closing itself', () => {
    const onComplete = vi.fn();
    const onClose = vi.fn();
    render(<WizardModal open steps={steps} onClose={onClose} onComplete={onComplete} />);

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    fireEvent.click(screen.getByRole('button', { name: 'Finish' }));

    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('calls onClose via the built-in round close button', () => {
    const onClose = vi.fn();
    render(<WizardModal open steps={steps} onClose={onClose} onComplete={() => {}} />);

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('disables Continue while the active step reports canContinue: false', () => {
    const gatedSteps: WizardModalStep[] = [
      { title: 'Pick a user', body: 'Search and select.', canContinue: false },
      { title: 'Confirm', body: 'Review your pick.' },
    ];
    render(<WizardModal open steps={gatedSteps} onClose={() => {}} onComplete={() => {}} />);

    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
  });

  it('renders a per-step continueLabel and continueTestId override', () => {
    const customSteps: WizardModalStep[] = [
      { title: 'Pick a user', body: 'Search and select.' },
      {
        title: 'Confirm',
        body: 'Review your pick.',
        continueLabel: 'Adding…',
        continueTestId: 'add-member-submit',
      },
    ];
    render(<WizardModal open steps={customSteps} onClose={() => {}} onComplete={() => {}} />);

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    const finishButton = screen.getByTestId('add-member-submit');
    expect(finishButton).toHaveTextContent('Adding…');
  });

  it('defaults to the small modal size and forwards an explicit size to Modal', () => {
    const { rerender } = render(
      <WizardModal open steps={steps} onClose={() => {}} onComplete={() => {}} />,
    );
    expect(screen.getByRole('dialog')).toHaveAttribute('data-size', 'sm');

    rerender(
      <WizardModal open steps={steps} onClose={() => {}} onComplete={() => {}} size="md" />,
    );
    expect(screen.getByRole('dialog')).toHaveAttribute('data-size', 'md');
  });

  it('resets to step 1 the next time it is reopened', () => {
    const { rerender } = render(
      <WizardModal open steps={steps} onClose={() => {}} onComplete={() => {}} />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(screen.getByText('Step 2 of 3')).toBeInTheDocument();

    rerender(<WizardModal open={false} steps={steps} onClose={() => {}} onComplete={() => {}} />);
    rerender(<WizardModal open steps={steps} onClose={() => {}} onComplete={() => {}} />);

    expect(screen.getByText('Step 1 of 3')).toBeInTheDocument();
  });
});
