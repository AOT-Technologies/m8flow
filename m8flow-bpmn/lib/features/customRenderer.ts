/**
 * Restyles diagram node rendering to match `Process Modeler.dc.html`
 * (node-shape-styling ticket, Process Modeler visual fidelity map):
 * gunmetal-equivalent start events, success-colored end events, and
 * info-colored task-type icons on a light-gray-bordered box (rather than
 * bpmn-js's own black-on-black defaults).
 *
 * Composition, not reimplementation: this wraps bpmn-js's own
 * `bpmnRenderer` singleton (injected, not subclassed/`super`-called) —
 * calling its real `drawShape` to draw the element exactly as stock
 * bpmn-js would (box, embedded label, multi-instance/loop/compensation
 * markers, the lot), then recolors specific already-drawn children.
 * Reimplementing `renderTask`/`renderEvent` from scratch was considered
 * and rejected: those functions also own marker rendering (loop,
 * multi-instance, compensation, ad-hoc) that this seed diagram doesn't
 * happen to exercise but real diagrams do — reproducing them by hand
 * would risk silently dropping that rendering for the sake of a color
 * change. Registered as a higher-priority `bpmnRenderer`-adjacent
 * renderer via `additionalModules`, the same "override/augment the
 * DI-registered internals" pattern `customPalette.ts` and
 * `positionContextPadAboveTarget` (BpmnCanvas.tsx) already use.
 *
 * Scope: start events, end events, user/service/script/manual/business-
 * rule/send/receive tasks, generic tasks, call activities (the original
 * "biggest miss" ticket plus the task-subtype-styling follow-on),
 * all five gateway types (exclusive — the "decision node" the user
 * flagged as still untouched when the map was — wrongly — closed as
 * complete — plus parallel/inclusive/event-based/complex), sequence flow
 * arrows, pool/lane borders, Sub-Process/Ad-Hoc Sub-Process/Transaction
 * containers, every event-definition icon (message/timer/signal/error/
 * escalation/compensate/conditional/link/terminate) across Start/End/
 * Intermediate/Boundary events, and data/artifacts (Data Object/Store
 * References, Text Annotations, Groups, Associations, Message Flows) —
 * the full BPMN element-type inventory a real diagram renders is now
 * covered; see the map's own Decisions-so-far for how each category was
 * treated.
 *
 * Operation-group color palette (color-theory pass, live user feedback:
 * "we are using just 4 colours... the combination of blue and green on
 * some of the icons is genuinely ugly"). Reviewed against
 * https://www.w3.org/WAI/fundamentals/accessibility-intro/ (don't rely on
 * color alone to convey meaning — every group below is also a distinct
 * hand-drawn glyph shape, color is reinforcement, not the sole signal) and
 * basic color-wheel theory (spread hues around the wheel rather than
 * clustering near-adjacent ones, since two saturated near-adjacent hues —
 * exactly what blue ring-icon-on-blue-icon or blue-next-to-green was doing
 * — read as muddy/clashing at small icon sizes). Icons/markers are now
 * sorted into operation groups, each carrying its own hue *and* used
 * nowhere else, so no two groups fight for attention in the same glyph:
 *
 * - Structural (unchanged `TASK_STROKE`, neutral gray `--color-border`):
 *   containers and data holders that aren't "operations" at all — generic
 *   Task, Sub-Process, Ad-Hoc Sub-Process, Transaction, Pool, Lane, Group,
 *   Data Object/Store References. Deliberately left uncolored — WCAG's own
 *   "don't rely on color alone" cuts both ways: reserving color for
 *   elements that actually need distinguishing keeps it meaningful.
 * - Flow control (`FLOW_CONTROL_COLOR`, violet, new `--color-flow-control`
 *   token): all five gateway markers, the Ad-Hoc "~" marker, and the
 *   Terminate/Compensate/Conditional/Link event icons — all "control how
 *   the flow branches, loops, or ends" in kind.
 * - Timing (`TIMER_COLOR`, amber, `--color-warning`): the Timer icon only
 *   — the one operation group with a single, near-universal color
 *   convention (clocks are amber), so it gets a dedicated group of one.
 * - System (`SYSTEM_COLOR`, blue, `--color-info` — the file's original,
 *   now-narrowed `TASK_ICON_COLOR`): every task/activity icon (User,
 *   Service, Script, Manual, Business-Rule, Send, Receive Task, the Call
 *   Activity "+" marker) plus the Message/Signal/Escalation event icons
 *   and the Message Flow connector. **A later live-feedback pass merged
 *   what was originally two groups here** — User/Manual Task first got
 *   their own separate pink "human work" color, but live review showed
 *   that reads as an unintentional inconsistency, not a meaningful
 *   distinction: every *other* task icon shares one color, so having
 *   exactly one (Manual Task) in a different color looked like a mistake,
 *   not a category. All task/activity icons are now uniformly blue.
 * - Error handling (`ERROR_COLOR`, red, `--color-destructive`): the Error
 *   event icon only — the one place reusing the app's "destructive"
 *   semantic is a genuine conceptual match, not just a reused hex.
 *
 * **Unified event styling** (live user feedback: "events dont have a
 * common style. Schedule is different to the rest of the events. Schedule
 * looks better"): every typed event, of any kind (Start/End/Intermediate/
 * Boundary) and any event-definition type, now draws through
 * `buildUnifiedEventIconSpecs` (`shapeTreatment.ts`) — a single ring,
 * filled `--color-card`, stroked in its own operation-group color, exactly
 * matching the look Timer
 * ("Schedule") already had. Previously only Timer collapsed to one
 * colored ring; every other typed event kept bpmn-js's own stock ring(s)
 * (single for Start/End, double for Intermediate/Boundary) recolored
 * *neutral*, with only the small icon glyph carrying color — two
 * genuinely different constructions for what should read as one family.
 * Since ring and icon now always share the same hue, there's no remaining
 * ring-vs-icon mismatch left to clash in the first place (a stronger fix
 * than the prior pass's "make the end-event ring neutral for typed
 * events" workaround, which this supersedes). Untyped ("none") events are
 * unaffected — Start/Boundary/Intermediate keep a plain neutral ring
 * (`START_EVENT_STROKE`/`BOUNDARY_EVENT_STROKE`, now the same muted gray
 * as a sequence flow — see below), and an untyped End event keeps its
 * green ring, matching the mockup's own plain-end-event illustration.
 * Distinguishability between start/end doesn't depend on ring color in
 * the first place — bpmn-js already gives end events a 4px stroke vs.
 * start's ~2px (confirmed reading `BpmnRenderer.js`).
 *
 * **"Solid black" lines fixed** (live user feedback): `START_EVENT_STROKE`
 * and `BOUNDARY_EVENT_STROKE` used `--color-foreground` (near-black,
 * #1F2937 — the mockup's own "gunmetal" spec for a start event), which
 * read as inconsistent stray black lines next to the muted-gray sequence
 * flows and light-gray task borders everywhere else. Both now reuse
 * `SEQUENCE_FLOW_STROKE` directly.
 *
 * **Subtle task shadow** (live user feedback: "add a subtle shadow to
 * tasks"): every task/activity/container box (`applyTaskShadow`) gets a
 * soft `drop-shadow` on its outer rect — a restrained elevation cue, not a
 * heavy border, in the same spirit as this app's existing shadcn/ui card
 * shadows elsewhere.
 *
 * Also introduces this file's first **dashed** connection: a sequence
 * flow whose source is a `BoundaryEvent` (an exception/interrupt path) now
 * draws with a dash pattern, a non-color-based signal distinguishing it
 * from the diagram's normal "happy path" flow — the live user request
 * that prompted this pass explicitly invited trying dashed lines, and
 * boundary-event-sourced flows are a real, meaningful place to use one
 * (every other dashed line already in this file — Association, Group,
 * Message Flow — is a stock bpmn-js default, not a customization).
 *
 * **What lives where**: the color palette, tail-slice/icon lookup tables,
 * and every icon's geometry (path-string math, ring radii) are pure
 * functions of element type/size and live in `shapeTreatment.ts` instead
 * of here — they're the parts with a documented history of hard-won,
 * live-debugged bugs (style-vs-attribute reads, off-by-one tail slices,
 * label-color coupling), and no DOM at all is needed to unit-test them
 * (see `test/shapeTreatment.test.ts`). This file stays the DOM-effecting
 * half: given bpmn-js's already-drawn children and a `ShapeSpec`
 * describing what to draw next, it's the only place that actually
 * queries/mutates/creates real SVG nodes.
 *
 * The DOM-mutation functions below (`recolorTaskIcon`,
 * `recolorOuterStroke`, `recolorContainerStrokes`, `applyTaskShadow`,
 * `roundGatewayCorners`, `ensureLaneDotPattern`) are exported and directly
 * unit-tested against hand-built SVG fixtures (`test/customRenderer.test.ts`)
 * — jsdom can construct a plain `<rect style="...">` tree even though it
 * can't run diagram-js's full canvas/layout pipeline, so the exact
 * style-vs-attribute bug class documented above (`recolorTaskIcon`'s and
 * `recolorContainerStrokes`'s own comments) is now a regression a test
 * catches, not something that ships silently until found live again.
 */
import { is } from 'bpmn-js/lib/util/ModelUtil';
import { append as svgAppend, attr as svgAttr, create as svgCreate } from 'tiny-svg';

import {
  buildCustomTaskSubtypeIconSpec,
  buildExclusiveGatewayMarkerSpec,
  buildGatewayMarkerSpec,
  buildUnifiedEventIconSpecs,
  CUSTOM_TASK_ICON_TAIL_COUNT,
  getEventDefinitionType,
  ICON_COLOR_BY_TYPE,
  ICON_TAIL_COUNT,
  SYSTEM_COLOR,
  type ShapeSpec,
} from './shapeTreatment';

const HIGH_PRIORITY = 2000;

/**
 * The only place a `ShapeSpec` from `shapeTreatment.ts` becomes a real SVG
 * node — the DOM-effecting half of the split described at the top of this
 * file's own module doc: `shapeTreatment.ts` decides *what* to draw (pure,
 * unit-tested without a DOM); this executes it.
 */
function appendSpec(parentGfx: SVGElement, spec: ShapeSpec): void {
  svgAppend(parentGfx, svgCreate(spec.tag, spec.attrs));
}

function appendSpecs(parentGfx: SVGElement, specs: ShapeSpec[]): void {
  specs.forEach((spec) => appendSpec(parentGfx, spec));
}

// Reuses the app's own theme tokens (src/styles/index.css) rather than the
// mockup's raw --aot-gunmetal/--aot-sky-blue/--status-success names, same
// convention as every other restyle in this map.
const TASK_STROKE = 'var(--color-border)';
const SEQUENCE_FLOW_STROKE = 'var(--color-muted-foreground)';
// Every "neutral" ring in the diagram — Start's plain ring, Boundary's/
// Intermediate's double ring when untyped — reuses the exact same gray as
// a sequence flow arrow. Previously these used `--color-foreground`
// (near-black, the mockup's own "gunmetal" spec for a start event); live
// user feedback flagged that as reading like stray "solid black" lines
// inconsistent with everything else in the canvas, so this now matches
// the muted gray already established for connectors. End's own ring stays
// `--color-success` green (untyped only — see the unified-event-icon
// comment below for typed events) since that's a distinct, intentional
// "this is a terminal/success state" signal, not a stray neutral.
const START_EVENT_STROKE = SEQUENCE_FLOW_STROKE;
const END_EVENT_STROKE = 'var(--color-success)';
// A boundary-event-sourced sequence flow (an exception/interrupt path) —
// see this file's own top-of-file comment on why a dash pattern, not a
// color, is the differentiator here.
const EXCEPTION_FLOW_DASH = '4,4';

// Same treatment as a plain start event ring — a boundary event is a
// (usually interrupting) event attached to an activity, closer in kind to
// a start/intermediate event than to the task it's attached to. No
// mockup guidance exists either way (its own illustration has no
// boundary event at all); decided live rather than left unstyled.
const BOUNDARY_EVENT_STROKE = SEQUENCE_FLOW_STROKE;
// Subtle task elevation — live user feedback: "add a subtle shadow to
// tasks," refined twice since: first to reduce top/left bleed, then to a
// specific value the user supplied directly:
// `box-shadow: rgba(149, 157, 165, 0.2) 0px 8px 24px`. Translated to
// `filter: drop-shadow(...)` rather than the literal `box-shadow`
// property — SVG shape elements (the `<rect>`/`<polygon>` this targets)
// don't reliably support `box-shadow` across browsers the way HTML boxes
// do, whereas `drop-shadow` is the SVG-safe equivalent already proven
// live in this file. `drop-shadow(offsetX offsetY blurRadius color)`
// takes the same three length values and color in the same order
// `box-shadow` does (no spread-radius support, but none was specified
// here), so this is a direct value carry-over, not a re-tuned one — the
// larger blur-vs-offset ratio here (24px blur vs. 8px/0px offset) is a
// deliberately soft, diffuse "floating card" look, wider than the tighter
// directional shadow the prior tuning pass produced.
const TASK_SHADOW = 'drop-shadow(0px 8px 24px rgba(149, 157, 165, 0.2))';
// Cross-participant message flow (data-artifacts-styling ticket) reuses
// `SYSTEM_COLOR` — the "system & communication" operation-group color — on
// purpose, and the ticket's own Question flagged wanting a message flow to
// read as visually different from a same-participant sequence flow "at a
// glance": bpmn-js already dashes it distinctly (`10, 11` vs a sequence
// flow's solid line), and this adds a distinct *color* on top of that.
// Kept as its own named constant since the reasoning (communication
// connector, not a task icon) is genuinely distinct from `SYSTEM_COLOR`'s
// other uses, even though the value is identical.
const MESSAGE_FLOW_STROKE = SYSTEM_COLOR;
// bpmn-js's own unstyled default fill (`BpmnRenderUtil.js`'s `white`
// constant, `'white'`) — never overridden here (see recolorOuterStroke's
// comment), so this is what the cutout/background paths inside task-type
// icons actually carry and must be matched *against* to know which of an
// icon's own child shapes to leave alone.
const DEFAULT_SHAPE_FILL = 'white';

// Matches the canvas's own dot-grid background (diagram-chrome.css's
// `.djs-container` rule, ticket 01) — same 22px pitch, same 1.1px dot
// radius, same `--color-border` dot color — so a lane's background reads
// as "the canvas's own texture, made visible here" rather than an
// unrelated new pattern. Live user feedback, after three failed attempts
// at a translucent/flat-color swimlane background (see this ticket's own
// "Reverted" section): texture, not color/opacity, is what actually
// distinguishes a lane from a white task box in this app's near-white
// palette.
const DOT_PATTERN_ID = 'm8flow-lane-dot-pattern';
const DOT_PATTERN_PITCH = 22;
const DOT_PATTERN_RADIUS = 1.1;

/**
 * Lazily defines (once per diagram) and returns a `url(#...)` reference
 * to the dot pattern above, as an SVG `<pattern>` in the diagram's own
 * `<defs>` — the SVG-native equivalent of the canvas's CSS
 * `radial-gradient` background, since a `<rect fill="...">` inside the
 * diagram can only reference an SVG paint server, not a CSS background
 * image. Checked by id rather than tracked in a variable: bpmn-js tears
 * down and recreates this renderer's own gfx groups on reimport/undo, but
 * never the root `<svg>` itself, so the pattern only needs creating once
 * per diagram lifetime, not once per render call.
 */
export function ensureLaneDotPattern(rootSvg: SVGElement | null): string {
  if (!rootSvg) return 'none';

  if (rootSvg.querySelector(`#${DOT_PATTERN_ID}`)) {
    return `url(#${DOT_PATTERN_ID})`;
  }

  let defs = rootSvg.querySelector('defs') as SVGElement | null;
  if (!defs) {
    defs = svgCreate('defs');
    svgAppend(rootSvg, defs);
  }

  const pattern = svgCreate('pattern', {
    id: DOT_PATTERN_ID,
    patternUnits: 'userSpaceOnUse',
    width: DOT_PATTERN_PITCH,
    height: DOT_PATTERN_PITCH,
  });
  const dot = svgCreate('circle', {
    cx: DOT_PATTERN_PITCH / 2,
    cy: DOT_PATTERN_PITCH / 2,
    r: DOT_PATTERN_RADIUS,
    fill: 'var(--color-border)',
  });
  svgAppend(pattern, dot);
  svgAppend(defs, pattern);

  return `url(#${DOT_PATTERN_ID})`;
}

/**
 * Tail-slice recolor for icon shapes bpmn-js already drew in place (User/
 * Service Task, Call Activity, Ad-Hoc Sub-Process) — the counts and colors
 * live in `shapeTreatment.ts`'s `ICON_TAIL_COUNT`/`ICON_COLOR_BY_TYPE`
 * (pure lookups, tested there); this is the DOM-reading half that actually
 * finds and repaints those already-drawn children.
 */
export function recolorTaskIcon(parentGfx: SVGElement, elementType: string) {
  const tailCount = ICON_TAIL_COUNT[elementType];
  if (!tailCount) return;
  const color = ICON_COLOR_BY_TYPE[elementType] ?? SYSTEM_COLOR;

  const children = Array.from(parentGfx.childNodes) as SVGElement[];
  children.slice(-tailCount).forEach((node) => {
    if (!(node instanceof SVGElement)) return;
    // Read via the CSSStyleDeclaration (`.style.stroke`/`.style.fill`),
    // not `getAttribute('stroke'|'fill')` — found live, the hard way (see
    // recolorContainerStrokes's own comment for the full story): bpmn-js's
    // `drawPath` bundles stroke/fill into one inline `style="..."`
    // attribute via its own `lineStyle()` helper, so a plain
    // `getAttribute` read always came back `null` and silently skipped
    // every icon path — this task-icon recolor has never actually
    // fired since ticket 03 first wrote it. `.style.stroke`/`.style.fill`
    // correctly parse the inline style string regardless.
    const stroke = node.style.stroke;
    if (stroke && stroke !== 'none') {
      svgAttr(node, 'stroke', color);
    }
    // Only recolor solid-filled icon strokes (bpmn-js draws the user-task
    // head as fill=strokeColor) — the two white cutout fills (task-type
    // icon backgrounds, ServiceTask's gear cutouts) already equal the
    // default fill color and must stay untouched, or the icon reads as a
    // solid blob.
    const fill = node.style.fill;
    if (fill && fill !== 'none' && fill !== DEFAULT_SHAPE_FILL) {
      svgAttr(node, 'fill', color);
    }
  });
}

/**
 * Recolors just the outer box/ring's own stroke — always the *first*
 * child bpmn-js appends (the box `rect` for tasks, the ring `circle` for
 * events), before any embedded label or type-icon children.
 *
 * Deliberately **not** done by passing a custom `attrs.stroke` into
 * `bpmnRenderer.drawShape()` — found live, the hard way: bpmn-js's own
 * `renderEmbeddedLabel()` reuses `attrs.stroke` as the *label's* text
 * color too (`getLabelColor(element, defaultLabelColor,
 * defaultStrokeColor, attrs.stroke)` in `BpmnRenderer.js`), so passing a
 * light gray box-border override also silently turned "Submit WFH
 * Request"'s own label text light gray — nearly illegible against the
 * white task fill. Recoloring only the specific already-drawn `rect`/
 * `circle` element after the fact sidesteps that coupling entirely: the
 * label text (and, for typed start/end events, any event-type icon) never
 * gets touched, so it keeps bpmn-js's own default dark color.
 */
export function recolorOuterStroke(parentGfx: SVGElement, color: string) {
  const outer = parentGfx.firstElementChild as SVGElement | null;
  if (outer) {
    svgAttr(outer, 'stroke', color);
  }
}

/**
 * Applies `TASK_SHADOW` to the outer box (always the first child, same as
 * `recolorOuterStroke`) of every task/activity/container shape — live user
 * feedback: "add a subtle shadow to tasks." Set via the real DOM `.style`
 * property rather than `svgAttr`, since `filter` isn't a presentation
 * attribute bpmn-js's own `lineStyle()`/`shapeStyle()` helpers already
 * bundle into `style="..."` the way `stroke`/`fill` are (see
 * `recolorContainerStrokes`'s own comment for that story) — there's no
 * existing inline style to fight with here, so a direct `.style.filter`
 * write is the simplest correct approach.
 */
export function applyTaskShadow(parentGfx: SVGElement) {
  const outer = parentGfx.firstElementChild as SVGElement | null;
  if (outer) {
    outer.style.filter = TASK_SHADOW;
  }
}

/**
 * Softens a gateway diamond's four sharp corners — live user feedback:
 * "add a subtle rounding to the edges of gates." bpmn-js draws a gateway
 * as a single `<polygon>` (`drawDiamond` in `BpmnRenderer.js`), not a
 * `<path>` with per-corner arcs, so there's no `rx`/`ry`-style radius to
 * set the way `drawRect`'s task boxes already get one from bpmn-js
 * itself. `stroke-linejoin: round` is the SVG-native equivalent for a
 * polygon: it rounds the *join* between each pair of edges using the
 * existing stroke width as the rounding radius, which reads as a subtle
 * softening at this diamond's small size without redrawing the shape's
 * geometry from scratch.
 */
export function roundGatewayCorners(parentGfx: SVGElement) {
  const diamond = parentGfx.firstElementChild as SVGElement | null;
  if (diamond) {
    svgAttr(diamond, 'stroke-linejoin', 'round');
  }
}

/**
 * Pool/lane border recolor. Unlike every other shape here, this doesn't
 * assume a fixed child index: `bpmn:Participant`'s handler
 * (`BpmnRenderer.js`) draws its own rect, then — only when expanded — a
 * horizontal/vertical divider `<line>` separating the pool's name header
 * from its lanes, *before* the name label text; `bpmn:Lane` draws just
 * its rect, then its own rotated name label directly, no divider. Rather
 * than special-case each shape's own exact structure, this recolors every
 * *non-text* child's stroke (the rect, and the pool's divider line if
 * present) and explicitly skips any `<text>` element — the same safety
 * property `recolorOuterStroke`'s own comment documents (labels reuse
 * `attrs.stroke` as their own color when a caller passes it; skipping
 * `<text>` here matters only as a defensive belt-and-braces check, since
 * this renderer never passes a custom `attrs.stroke` into the wrapped
 * `drawShape()` call in the first place).
 *
 * Recolors unconditionally, with no `getAttribute('stroke')` pre-check —
 * found live, the hard way: `drawRect`'s own `shapeStyle()` helper
 * (`BpmnRenderer.js`) bundles `stroke`/`fill`/`strokeWidth`/etc. into a
 * single inline `style="..."` attribute rather than separate XML
 * attributes (confirmed by dumping the real DOM — this is true even for
 * the task boxes ticket 03 already recolored). `getAttribute('stroke')`
 * can't see a color living inside `style`, so a guard built on it always
 * read `null` and silently skipped every child; `svgAttr`'s own *write*
 * path already handles this correctly regardless (it's what let ticket
 * 03's task-box recolor work in the first place) — only the read-based
 * gate here was the bug.
 */
export function recolorContainerStrokes(parentGfx: SVGElement, color: string) {
  Array.from(parentGfx.children).forEach((child) => {
    if (child.tagName.toLowerCase() === 'text') return;
    svgAttr(child as SVGElement, 'stroke', color);
  });
}

export default function CustomBpmnRenderer(this: any, eventBus: any, bpmnRenderer: any) {
  const self = this;

  eventBus.on(['render.shape'], HIGH_PRIORITY, (_evt: any, context: any) => {
    const { element, gfx } = context;
    if (!self.canRender(element)) return undefined;
    return self.drawShape(gfx, element);
  });

  eventBus.on(['render.connection'], HIGH_PRIORITY, (_evt: any, context: any) => {
    const { element, gfx } = context;
    if (!self.canRender(element)) return undefined;
    return self.drawConnection(gfx, element);
  });

  this._bpmnRenderer = bpmnRenderer;
}

CustomBpmnRenderer.$inject = ['eventBus', 'bpmnRenderer'];

CustomBpmnRenderer.prototype.canRender = function canRender(element: any) {
  // External labels (diagram-js's own synthetic `type: 'label'` shapes,
  // e.g. a start/end event's name floating below its ring) share their
  // *target* element's businessObject — `is(label, 'bpmn:EndEvent')` is
  // true for them too. Found live: without this guard, an end event's
  // label got recolored right along with its ring (this function's own
  // `recolorOuterStroke` reached into the label's one-child gfx group and
  // repainted its `<text>`), which the mockup doesn't do — its labels stay
  // a neutral gray regardless of the element's own color.
  if (element.type === 'label') {
    return false;
  }

  return (
    is(element, 'bpmn:StartEvent') ||
    is(element, 'bpmn:EndEvent') ||
    is(element, 'bpmn:UserTask') ||
    is(element, 'bpmn:ServiceTask') ||
    is(element, 'bpmn:ExclusiveGateway') ||
    is(element, 'bpmn:ParallelGateway') ||
    is(element, 'bpmn:InclusiveGateway') ||
    is(element, 'bpmn:EventBasedGateway') ||
    is(element, 'bpmn:ComplexGateway') ||
    is(element, 'bpmn:SequenceFlow') ||
    is(element, 'bpmn:BoundaryEvent') ||
    is(element, 'bpmn:IntermediateCatchEvent') ||
    is(element, 'bpmn:IntermediateThrowEvent') ||
    is(element, 'bpmn:Participant') ||
    is(element, 'bpmn:Lane') ||
    is(element, 'bpmn:Task') ||
    is(element, 'bpmn:ScriptTask') ||
    is(element, 'bpmn:ManualTask') ||
    is(element, 'bpmn:BusinessRuleTask') ||
    is(element, 'bpmn:SendTask') ||
    is(element, 'bpmn:ReceiveTask') ||
    is(element, 'bpmn:CallActivity') ||
    is(element, 'bpmn:SubProcess') ||
    is(element, 'bpmn:AdHocSubProcess') ||
    is(element, 'bpmn:Transaction') ||
    is(element, 'bpmn:DataObjectReference') ||
    is(element, 'bpmn:DataStoreReference') ||
    is(element, 'bpmn:TextAnnotation') ||
    is(element, 'bpmn:Group') ||
    is(element, 'bpmn:Association') ||
    is(element, 'bpmn:MessageFlow')
  );
};

CustomBpmnRenderer.prototype.drawShape = function drawShape(
  this: any,
  parentGfx: SVGElement,
  element: any,
) {
  // No custom attrs passed in at all — draw exactly as stock bpmn-js
  // would (default black/white), then recolor specific already-drawn
  // children. See recolorOuterStroke's own comment for why this, not an
  // `attrs` override, is the approach.
  const shape = this._bpmnRenderer.drawShape(parentGfx, element);

  if (is(element, 'bpmn:StartEvent')) {
    // Unified-event-styling pass: a typed start event now gets the same
    // single-ring colored badge as every other typed event (see
    // `drawUnifiedEventIcon`'s own comment) — strip the whole shape and
    // redraw. An untyped ("none") event keeps its plain neutral ring.
    const defType = getEventDefinitionType(element);
    if (defType && defType !== 'bpmn:MultipleEventDefinition') {
      Array.from(parentGfx.children).forEach((child) => parentGfx.removeChild(child));
      appendSpecs(parentGfx, buildUnifiedEventIconSpecs(element.width, element.height, defType));
    } else {
      recolorOuterStroke(parentGfx, START_EVENT_STROKE);
    }
  } else if (is(element, 'bpmn:EndEvent')) {
    // Same unified treatment as Start above. An untyped ("none") end event
    // keeps its green ring — nothing to clash with, matching the mockup's
    // own plain-end-event illustration.
    const defType = getEventDefinitionType(element);
    if (defType && defType !== 'bpmn:MultipleEventDefinition') {
      Array.from(parentGfx.children).forEach((child) => parentGfx.removeChild(child));
      appendSpecs(parentGfx, buildUnifiedEventIconSpecs(element.width, element.height, defType));
    } else {
      recolorOuterStroke(parentGfx, END_EVENT_STROKE);
    }
  } else if (is(element, 'bpmn:IntermediateCatchEvent') || is(element, 'bpmn:IntermediateThrowEvent')) {
    // Intermediate events draw a *double* ring like boundary events do
    // when untyped (confirmed reading `bpmn:IntermediateEvent`'s shared
    // handler) — collapsed to the same single unified badge as every other
    // typed event when a definition is present.
    const defType = getEventDefinitionType(element);
    if (defType && defType !== 'bpmn:MultipleEventDefinition') {
      Array.from(parentGfx.children).forEach((child) => parentGfx.removeChild(child));
      appendSpecs(parentGfx, buildUnifiedEventIconSpecs(element.width, element.height, defType));
    } else {
      recolorOuterStroke(parentGfx, BOUNDARY_EVENT_STROKE);
      const innerRing = parentGfx.children[1] as SVGElement | undefined;
      if (innerRing) {
        svgAttr(innerRing, 'stroke', BOUNDARY_EVENT_STROKE);
      }
    }
  } else if (is(element, 'bpmn:ExclusiveGateway')) {
    recolorOuterStroke(parentGfx, TASK_STROKE);
    roundGatewayCorners(parentGfx);
    // Stock bpmn-js only draws the "X" marker at all when the diagram's
    // own `isMarkerVisible` DI flag is set (`BpmnRenderer.js`'s
    // `bpmn:ExclusiveGateway` handler) — respect that: a second child
    // means the stock marker was drawn, so swap it for the custom one;
    // no second child means the source diagram deliberately has a bare
    // diamond, and this leaves it bare rather than forcing an X in.
    const marker = parentGfx.children[1];
    if (marker) {
      parentGfx.removeChild(marker);
      appendSpec(parentGfx, buildExclusiveGatewayMarkerSpec(element.width, element.height));
    }
  } else if (
    is(element, 'bpmn:ParallelGateway') ||
    is(element, 'bpmn:InclusiveGateway') ||
    is(element, 'bpmn:EventBasedGateway') ||
    is(element, 'bpmn:ComplexGateway')
  ) {
    recolorOuterStroke(parentGfx, TASK_STROKE);
    roundGatewayCorners(parentGfx);
    // Each of these draws exactly one marker child after the diamond in
    // our seed diagram's own configuration (confirmed reading each
    // handler in `BpmnRenderer.js` — Event-Based only draws its extra
    // event-glyph paths when `eventGatewayType` is set, which our
    // diagram never does, so it's the same "diamond + one ring" shape as
    // the others here). Same swap pattern as the exclusive gateway above.
    const kind = is(element, 'bpmn:ParallelGateway')
      ? 'parallel'
      : is(element, 'bpmn:InclusiveGateway')
        ? 'inclusive'
        : is(element, 'bpmn:EventBasedGateway')
          ? 'eventBased'
          : 'complex';
    const marker = parentGfx.children[1];
    if (marker) {
      parentGfx.removeChild(marker);
      appendSpec(parentGfx, buildGatewayMarkerSpec(element.width, element.height, kind));
    }
  } else if (is(element, 'bpmn:BoundaryEvent')) {
    // Same unified treatment as every other event kind above — this also
    // covers Timer's own former dedicated branch (drop the stock double
    // ring entirely, per live feedback: "remove the outer circles
    // surrounding the clock for scheduled tasks"), since
    // `drawUnifiedEventIcon` special-cases Timer the same way. A boundary
    // event without any definition (a malformed/edge-case diagram) falls
    // back to the plain double-ring neutral treatment.
    const defType = getEventDefinitionType(element);
    if (defType && defType !== 'bpmn:MultipleEventDefinition') {
      Array.from(parentGfx.children).forEach((child) => parentGfx.removeChild(child));
      appendSpecs(parentGfx, buildUnifiedEventIconSpecs(element.width, element.height, defType));
    } else {
      recolorOuterStroke(parentGfx, BOUNDARY_EVENT_STROKE);
      const innerRing = parentGfx.children[1] as SVGElement | undefined;
      if (innerRing) {
        svgAttr(innerRing, 'stroke', BOUNDARY_EVENT_STROKE);
      }
    }
  } else if (is(element, 'bpmn:Participant') || is(element, 'bpmn:Lane')) {
    recolorContainerStrokes(parentGfx, TASK_STROKE);
    if (is(element, 'bpmn:Lane')) {
      // Live user feedback, this ticket's 4th attempt at a visible
      // swimlane background (see "Reverted" above for the first three):
      // "add a dot pattern background" — texture instead of a translucent
      // or flat color, which this app's near-white palette kept
      // defeating. Lane rect is always the first child (see
      // recolorContainerStrokes's own comment on `Lane`'s structure).
      const laneRect = parentGfx.firstElementChild as SVGElement | null;
      if (laneRect) {
        svgAttr(laneRect, 'fill', ensureLaneDotPattern(parentGfx.ownerSVGElement));
        svgAttr(laneRect, 'fill-opacity', 1);
      }
    }
  } else if (is(element, 'bpmn:Transaction')) {
    // Found live: recoloring the inner double-border rect via the generic
    // `recolorTaskIcon`/`TASK_ICON_COLOR` path (the same technique
    // AdHocSubProcess's marker uses) made the whole box read as blue —
    // the inner rect is a *border* variant (the classic transaction
    // "double border" look), not an icon, so it gets the same
    // `TASK_STROKE` as the outer border, not the info-blue icon color.
    recolorOuterStroke(parentGfx, TASK_STROKE);
    applyTaskShadow(parentGfx);
    const innerBorder = parentGfx.lastElementChild as SVGElement | null;
    if (innerBorder && innerBorder !== parentGfx.firstElementChild) {
      svgAttr(innerBorder, 'stroke', TASK_STROKE);
    }
  } else if (
    is(element, 'bpmn:DataObjectReference') ||
    is(element, 'bpmn:DataStoreReference') ||
    is(element, 'bpmn:Group')
  ) {
    // Data-artifacts-styling ticket. All three draw exactly one visible
    // child (the folded-document path, the data-store cylinder path, or the
    // dashed rect, respectively — confirmed reading each handler in
    // `BpmnRenderer.js`) with no embedded label of their own (`bpmn:Group`
    // in particular renders *no* name label at all in this bpmn-js version,
    // despite the moddle schema modeling `categoryValueRef`), so the plain
    // `recolorOuterStroke` (first child) used everywhere else in this file
    // applies directly. Grouped with the container family (`TASK_STROKE`,
    // the same light gray as pool/lane/task borders) rather than the
    // connector family below — these are standalone box-like elements, not
    // lines.
    recolorOuterStroke(parentGfx, TASK_STROKE);
  } else if (is(element, 'bpmn:TextAnnotation')) {
    // Text Annotation draws an invisible sizing rect *first*
    // (`fill: 'none', stroke: 'none'`), then the visible bracket path,
    // then its own text label — confirmed reading `BpmnRenderer.js`'s own
    // handler. Unlike the three shapes above, its `renderLabel` call *does*
    // couple to a passed-in `attrs.stroke` via `getLabelColor`'s own
    // `overrideColor` — the same label-coupling hazard `recolorOuterStroke`'s
    // own comment already documents for tasks/embedded labels — so this
    // targets the bracket path specifically (`children[1]`, not
    // `firstElementChild`) rather than reusing `recolorOuterStroke`, leaving
    // the annotation's own text at bpmn-js's default color untouched.
    // Connector/annotation family (`SEQUENCE_FLOW_STROKE`, the same muted
    // gray as a sequence flow and — see `drawConnection` below —
    // Association), not the box family above: this is closer in kind to an
    // annotative device than a structural container.
    const bracket = parentGfx.children[1] as SVGElement | undefined;
    if (bracket) {
      svgAttr(bracket, 'stroke', SEQUENCE_FLOW_STROKE);
    }
  } else if (CUSTOM_TASK_ICON_TAIL_COUNT[element.type]) {
    // Script/Manual/BusinessRule/Send/Receive Task — task-subtype-styling
    // ticket. Strip bpmn-js's own stock icon path(s) and draw a genuinely
    // custom glyph, same "replace outright" pattern as the gateway's X
    // and the boundary event's clock (not a recolor-in-place, unlike
    // User/ServiceTask below — decided per the standing "create custom
    // icons" instruction).
    recolorOuterStroke(parentGfx, TASK_STROKE);
    applyTaskShadow(parentGfx);
    const tailCount = CUSTOM_TASK_ICON_TAIL_COUNT[element.type];
    Array.from(parentGfx.children)
      .slice(-tailCount)
      .forEach((child) => parentGfx.removeChild(child));
    const subtypeIconSpec = buildCustomTaskSubtypeIconSpec(element.type);
    if (subtypeIconSpec) appendSpec(parentGfx, subtypeIconSpec);
  } else {
    // Generic bpmn:Task (border only, no icon), Call Activity (border +
    // recolor its existing "+" marker in place), User/ServiceTask (border
    // + recolor their icons in place), Sub-Process/Ad-Hoc Sub-Process
    // (fall through here too — no dedicated branch of their own).
    recolorOuterStroke(parentGfx, TASK_STROKE);
    applyTaskShadow(parentGfx);
    recolorTaskIcon(parentGfx, element.type);
  }

  return shape;
};

/**
 * Sequence flows — the user's "arrows did not change" complaint. Unlike
 * shapes, this *does* pass a custom `attrs.stroke` straight into the
 * wrapped `bpmnRenderer.drawConnection()` call, not a post-hoc DOM
 * recolor: read live, `bpmn:SequenceFlow`'s handler
 * (`BpmnRenderer.js`) has no embedded-label call to fight over
 * `attrs.stroke` the way tasks/events did (a sequence flow's own name,
 * e.g. "Approved"/"Rejected" off the gateway, is always an *external*
 * label — a separate `type: 'label'` element this renderer already
 * excludes via `canRender`'s own guard). `attrs.stroke` also flows into
 * every marker the handler creates for this connection (the arrowhead,
 * plus any conditional-flow/default-flow marker) via bpmn-js's own
 * `marker()` helper, which mints a brand-new `<marker>` def per call
 * (confirmed live: no caching/dedup by color at all) — so passing our
 * color once here recolors the line *and* every arrowhead variant this
 * connection could have, with no separate one-time `<defs>` patch needed.
 */
CustomBpmnRenderer.prototype.drawConnection = function drawConnection(
  this: any,
  parentGfx: SVGElement,
  element: any,
) {
  if (is(element, 'bpmn:SequenceFlow')) {
    // A sequence flow whose source is a BoundaryEvent is an exception/
    // interrupt path, not the diagram's normal "happy path" — dashed per
    // this file's top-of-file comment, a non-color-based signal per WCAG's
    // own "don't rely on color alone" guidance. Found live: unlike
    // `stroke`, `attrs.strokeDasharray` does *not* survive into
    // `drawConnectionSegments` — `bpmn:SequenceFlow`'s own handler calls
    // `pickAttrs(attrs, ['fill', 'stroke'])` first, silently dropping any
    // other attrs key — so this sets it as a post-hoc DOM attribute on the
    // returned path instead, the same "recolor after the fact" discipline
    // every shape branch in this file already uses.
    const isExceptionFlow = is(element.source, 'bpmn:BoundaryEvent');
    const connection = this._bpmnRenderer.drawConnection(parentGfx, element, { stroke: SEQUENCE_FLOW_STROKE });
    if (isExceptionFlow) {
      svgAttr(connection, 'stroke-dasharray', EXCEPTION_FLOW_DASH);
    }
    return connection;
  }
  if (is(element, 'bpmn:Association')) {
    // Data-artifacts-styling ticket. `renderAssociation` never calls
    // `renderLabel` at all — confirmed reading `BpmnRenderer.js` — so, like
    // sequence flow above, a custom `attrs.stroke` can be passed straight
    // through with no label-coupling risk. Same muted gray as a sequence
    // flow (the connector/annotation family, see the TextAnnotation shape
    // branch above); bpmn-js's own dashed pattern (`0, 5`) already
    // distinguishes it from a solid sequence flow.
    return this._bpmnRenderer.drawConnection(parentGfx, element, { stroke: SEQUENCE_FLOW_STROKE });
  }
  if (is(element, 'bpmn:MessageFlow')) {
    // `renderMessageFlow`'s own message-name label *does* couple to
    // `attrs.stroke` via the same `getLabelColor` override — but only when
    // `semantic.get('messageRef')` is set, which this map's seed diagram's
    // two message flows never do (confirmed reading the source XML) — safe
    // here. Flagged, not silently assumed universal: a message flow with a
    // named `messageRef` would have that label recolored too, untested
    // since no such flow exists in this diagram.
    return this._bpmnRenderer.drawConnection(parentGfx, element, { stroke: MESSAGE_FLOW_STROKE });
  }
  return this._bpmnRenderer.drawConnection(parentGfx, element);
};

export const customRendererModule = {
  __init__: ['customBpmnRenderer'],
  customBpmnRenderer: ['type', CustomBpmnRenderer],
};
