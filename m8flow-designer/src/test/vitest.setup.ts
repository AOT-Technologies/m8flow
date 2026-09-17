import '@testing-library/jest-dom';

// jsdom doesn't implement these — without them, mounting any Radix primitive
// that positions a floating panel (Select, DropdownMenu, Popover, Tooltip)
// throws ("ResizeObserver is not defined") or silently fails to open
// ("target.hasPointerCapture is not a function") in tests.
if (typeof globalThis.ResizeObserver === 'undefined') {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
}

// dmn-js/bpmn-js properties panels observe sticky headers with an
// IntersectionObserver — unstubbed, mounting either canvas rejects with
// "IntersectionObserver is not defined" from inside preact's render.
if (typeof globalThis.IntersectionObserver === 'undefined') {
  class IntersectionObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  }
  globalThis.IntersectionObserver = IntersectionObserverStub as unknown as typeof IntersectionObserver;
}

if (typeof Element !== 'undefined') {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => {};
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
}
