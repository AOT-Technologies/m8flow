/**
 * Application logo — m8flow branding (override of upstream SpiffLogo).
 */
import m8fLogo from '../assets/images/m8fLogo.webp';

export default function SpiffLogo() {
  return (
    <img
      src={m8fLogo}
      alt="M8Flow Logo"
      height={28}
      style={{ display: 'block', margin: '0.25rem 0.75rem' }}
    />
  );
}
