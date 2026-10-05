import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

/**
 * Picks `name` from a `ui/select` (Radix Select). Radix opens on the full
 * pointer sequence, which `fireEvent` alone doesn't produce in jsdom.
 */
export async function chooseOption(trigger: HTMLElement, name: string | RegExp) {
  const user = userEvent.setup();
  await user.click(trigger);
  await user.click(await screen.findByRole('option', { name }));
}
