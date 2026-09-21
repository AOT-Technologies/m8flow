// The theme bundles fontawesome.min.css (glyph codepoints only) but declares no
// @font-face for it, so `<i class="fa fa-eye">` renders as tofu. Inline SVG
// sidesteps the missing webfont entirely.
const EYE = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
const EYE_OFF = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';

for (const button of document.querySelectorAll('[data-password-toggle]')) {
  const input = document.getElementById(button.getAttribute('aria-controls'));
  if (!input) {
    continue;
  }

  const showLabel = button.dataset.labelShow || 'Show password';
  const hideLabel = button.dataset.labelHide || 'Hide password';

  const render = () => {
    const revealed = input.type === 'text';
    button.innerHTML = revealed ? EYE_OFF : EYE;
    button.setAttribute('aria-label', revealed ? hideLabel : showLabel);
  };

  button.addEventListener('click', () => {
    input.type = input.type === 'password' ? 'text' : 'password';
    render();
  });

  render();
}
