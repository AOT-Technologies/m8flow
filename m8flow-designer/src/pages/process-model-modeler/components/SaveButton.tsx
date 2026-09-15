import { Button } from '@/components/ui/button';

export type SaveButtonProps = {
  onClick: () => void;
  disabled?: boolean;
};

/** Shown instead of SavedStatusPill whenever the diagram is dirty. */
export function SaveButton({ onClick, disabled }: SaveButtonProps) {
  return (
    <Button type="button" variant="pill-info" size="pill" onClick={onClick} disabled={disabled}>
      Save
    </Button>
  );
}
