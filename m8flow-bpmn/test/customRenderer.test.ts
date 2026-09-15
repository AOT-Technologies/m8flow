import { describe, expect, it } from 'vitest';
import {
  applyTaskShadow,
  ensureLaneDotPattern,
  recolorContainerStrokes,
  recolorOuterStroke,
  recolorTaskIcon,
  roundGatewayCorners,
} from '../lib/features/customRenderer';
import { ICON_COLOR_BY_TYPE } from '../lib/features/shapeTreatment';

const SVG_NS = 'http://www.w3.org/2000/svg';

function svg(tag: string, style?: string): SVGElement {
  const node = document.createElementNS(SVG_NS, tag) as SVGElement;
  if (style) node.setAttribute('style', style);
  return node;
}

function withChildren(parentGfx: SVGElement, children: SVGElement[]): SVGElement {
  children.forEach((child) => parentGfx.appendChild(child));
  return parentGfx;
}

// Every assertion below reads `.style.<prop>`, not `getAttribute(<prop>)`:
// `tiny-svg`'s own `attr()` writer bundles `stroke`/`fill`/`stroke-linejoin`/
// `filter` (and every other name in its `CSS_PROPERTIES` table) into
// `node.style[...]` rather than a plain XML attribute — confirmed reading
// `tiny-svg`'s `setAttribute()`. That's the same style-vs-attribute split
// this file's own functions already document fighting against on the *read*
// side (bpmn-js bundles its own output into an inline `style="..."` too);
// asserting via `.style` here matches what a real renderer actually paints.

describe('recolorTaskIcon', () => {
  // Regression guard for the bug documented in recolorTaskIcon's own
  // comment: bpmn-js bundles stroke/fill into an inline `style="..."`
  // attribute (via its own `lineStyle()` helper) — a plain
  // `getAttribute('stroke')` read on the *source* element always came back
  // `null` and silently skipped every icon path, so this task-icon recolor
  // "never actually fired since ticket 03" until found live. This fixture
  // reproduces that same inline-style shape on the input nodes.
  it('recolors the tail icon children whose color/stroke live in an inline style attribute', () => {
    const parentGfx = withChildren(svg('g'), [
      svg('rect', 'fill:white;stroke:none'),
      svg('path', 'stroke:#1F2937;fill:#1F2937'),
    ]);

    recolorTaskIcon(parentGfx, 'bpmn:UserTask');

    const [background, icon] = Array.from(parentGfx.children) as SVGElement[];
    expect(background.style.stroke).toBe('none');
    expect(icon.style.stroke).toBe(ICON_COLOR_BY_TYPE['bpmn:UserTask']);
    expect(icon.style.fill).toBe(ICON_COLOR_BY_TYPE['bpmn:UserTask']);
  });

  it('leaves the white cutout fill untouched so the icon does not read as a solid blob', () => {
    const parentGfx = withChildren(svg('g'), [svg('path', 'stroke:#1F2937;fill:white')]);

    recolorTaskIcon(parentGfx, 'bpmn:ServiceTask');

    const [icon] = Array.from(parentGfx.children) as SVGElement[];
    expect(icon.style.stroke).toBe(ICON_COLOR_BY_TYPE['bpmn:ServiceTask']);
    expect(icon.style.fill).toBe('white');
  });

  it('is a no-op for element types with no tail-icon entry', () => {
    const parentGfx = withChildren(svg('g'), [svg('rect', 'stroke:#1F2937')]);

    recolorTaskIcon(parentGfx, 'bpmn:Task');

    expect((parentGfx.firstElementChild as SVGElement).style.stroke).toBe('#1F2937');
  });

  it('colors every ICON_TAIL_COUNT entry with its matching ICON_COLOR_BY_TYPE value', () => {
    // ICON_TAIL_COUNT and ICON_COLOR_BY_TYPE are kept in sync by construction
    // (see shapeTreatment.test.ts's own "keeps ... in sync" guard), which
    // makes recolorTaskIcon's `?? SYSTEM_COLOR` fallback structurally
    // unreachable through any real element type today — this instead checks
    // every entry actually in scope resolves to its own color, not the
    // fallback, across the full lookup table rather than one sample type.
    for (const [elementType, color] of Object.entries(ICON_COLOR_BY_TYPE)) {
      const parentGfx = withChildren(svg('g'), [svg('path', 'stroke:#1F2937;fill:#1F2937')]);
      recolorTaskIcon(parentGfx, elementType);
      expect((parentGfx.firstElementChild as SVGElement).style.stroke).toBe(color);
    }
  });
});

describe('recolorOuterStroke', () => {
  it('recolors only the first child, leaving label/icon siblings untouched', () => {
    const parentGfx = withChildren(svg('g'), [svg('rect'), svg('text')]);

    recolorOuterStroke(parentGfx, 'var(--color-border)');

    const [outer, label] = Array.from(parentGfx.children) as SVGElement[];
    expect(outer.style.stroke).toBe('var(--color-border)');
    expect(label.style.stroke).toBe('');
  });

  it('is a no-op on an empty group', () => {
    expect(() => recolorOuterStroke(svg('g'), 'red')).not.toThrow();
  });
});

describe('applyTaskShadow', () => {
  it('sets a drop-shadow filter on the outer box', () => {
    const parentGfx = withChildren(svg('g'), [svg('rect')]);

    applyTaskShadow(parentGfx);

    const outer = parentGfx.firstElementChild as SVGElement;
    expect(outer.style.filter).toContain('drop-shadow');
  });
});

describe('roundGatewayCorners', () => {
  it('sets stroke-linejoin on the diamond polygon', () => {
    const parentGfx = withChildren(svg('g'), [svg('polygon')]);

    roundGatewayCorners(parentGfx);

    expect((parentGfx.firstElementChild as SVGElement).style.strokeLinejoin).toBe('round');
  });
});

describe('recolorContainerStrokes', () => {
  // Regression guard for recolorContainerStrokes's own documented bug: an
  // unconditional write (no `getAttribute('stroke')` pre-check on the
  // *source* element) is required because bpmn-js bundles stroke into
  // `style="..."`, which a read-based guard can't see.
  it('recolors every non-text child, including a pool divider line after the rect', () => {
    const parentGfx = withChildren(svg('g'), [svg('rect', 'stroke:#1F2937'), svg('line', 'stroke:#1F2937')]);

    recolorContainerStrokes(parentGfx, 'var(--color-border)');

    const [rect, line] = Array.from(parentGfx.children) as SVGElement[];
    expect(rect.style.stroke).toBe('var(--color-border)');
    expect(line.style.stroke).toBe('var(--color-border)');
  });

  it('skips text children so labels keep bpmn-js default color', () => {
    const parentGfx = withChildren(svg('g'), [svg('rect'), svg('text')]);

    recolorContainerStrokes(parentGfx, 'var(--color-border)');

    const label = parentGfx.children[1] as SVGElement;
    expect(label.style.stroke).toBe('');
  });
});

describe('ensureLaneDotPattern', () => {
  it('lazily creates a defs + pattern in the root svg and returns a url() reference', () => {
    const rootSvg = svg('svg');

    const url = ensureLaneDotPattern(rootSvg);

    expect(url).toBe('url(#m8flow-lane-dot-pattern)');
    expect(rootSvg.querySelector('defs > pattern#m8flow-lane-dot-pattern')).not.toBeNull();
  });

  it('is idempotent — a second call reuses the existing pattern instead of duplicating it', () => {
    const rootSvg = svg('svg');

    ensureLaneDotPattern(rootSvg);
    ensureLaneDotPattern(rootSvg);

    expect(rootSvg.querySelectorAll('pattern#m8flow-lane-dot-pattern')).toHaveLength(1);
  });

  it('returns "none" when there is no root svg to attach a pattern to', () => {
    expect(ensureLaneDotPattern(null)).toBe('none');
  });
});
