const SVG_NS = 'http://www.w3.org/2000/svg';

/**
 * A 24x24 stroke icon (lucide path data) built with DOM APIs rather than an
 * innerHTML string, so icon markup never goes through the HTML parser.
 */
export function svgIcon(paths: string[], size = 15, className?: string): SVGSVGElement {
  const svg = document.createElementNS(SVG_NS, 'svg');
  const attributes: Record<string, string> = {
    width: String(size),
    height: String(size),
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    'stroke-width': '2',
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'aria-hidden': 'true',
  };
  for (const [name, value] of Object.entries(attributes)) svg.setAttribute(name, value);
  if (className) svg.setAttribute('class', className);
  for (const d of paths) {
    const path = document.createElementNS(SVG_NS, 'path');
    path.setAttribute('d', d);
    svg.appendChild(path);
  }
  return svg;
}

/** Chevron pointing up (rotated by CSS where it means "collapsed"). */
export const CHEVRON_UP_PATHS = ['m18 15-6-6-6 6'];
