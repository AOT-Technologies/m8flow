import type { Preview } from '@storybook/react-vite';

// Pulls in Tailwind + shadcn base layers + the AOT font faces (aot-fonts.css
// is imported from within index.css) so every story renders against the
// same design tokens as the real app — not a separate Storybook-only theme.
import '../src/styles/index.css';

const preview: Preview = {
  parameters: {
    // Every story centers its component in the canvas — both axes, not
    // just horizontally — unless a story explicitly opts out. Storybook's
    // built-in "centered" layout does this via a flex wrapper around
    // `#storybook-root` (confirmed empirically: a plain Button's bounding
    // box sits exactly at the canvas's horizontal *and* vertical midpoint
    // under this layout). Components that are meant to span a real
    // container's width (Pagination, SearchBar, ...) still need their own
    // realistic max-width decorator/wrapper so they don't just shrink to
    // their tightest content fit — centering the canvas and giving a
    // component a sensible width are separate concerns.
    layout: 'centered',
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
  },
};

export default preview;
